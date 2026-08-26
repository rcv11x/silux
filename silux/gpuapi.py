"""OpenGL, Vulkan y OpenCL preguntados directamente a sus bibliotecas.

Lo natural aquí sería llamar a `glxinfo`, `vulkaninfo` y `clinfo` y leerles la
salida, que es lo que hace medio mundo. Tiene dos pegas: son tres paquetes que
el usuario puede no tener instalados, y su salida es texto pensado para
personas, que cambia entre versiones. Las bibliotecas, en cambio, están puestas
siempre que el driver lo esté, y su ABI no se mueve.

Así que se cargan con `ctypes`, igual que `rawcpuid` hace con CPUID. Cada una
va por su cuenta: que falte Vulkan no impide leer OpenGL.

De aquí sale además el dato que el kernel no sabe dar. `pci.ids` dice que esta
tarjeta es una «Radeon RX 9070/9070 XT/9070 GRE» —tres modelos distintos con el
mismo identificador PCI— y es el driver, a través de Vulkan, quien dice cuál de
las tres hay puesta.

Nada de esto se llama desde el hilo de la interfaz: crear una instancia Vulkan
o un contexto de OpenGL tarda lo suyo.

Y no se llama en este proceso siquiera. Preguntar a las tres cuesta 118 MB de
residente —rusticl arrastra LLVM entero por decir «OpenCL 3.1»— y el programa
tiene un presupuesto de 100 MB para todo. Así que `consultar()` lanza una copia
de este módulo como proceso aparte, le lee la respuesta y lo deja morir con los
drivers dentro. De paso sale gratis lo otro que preocupaba: un driver roto que
se lleva por delante al proceso ya solo se lleva al hijo.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import subprocess
import sys
from typing import Any, Iterator, Optional

# Margen de sobra: cargar los drivers de las tres es lo lento, y cuando algo se
# atasca de verdad es que el driver está colgado y no va a contestar nunca.
TIEMPO_MAXIMO = 20

# Las bibliotecas, en el orden en que suelen llamarse los enlaces.
LIB_VULKAN = ("libvulkan.so.1", "libvulkan.so")
LIB_OPENCL = ("libOpenCL.so.1", "libOpenCL.so")
LIB_EGL = ("libEGL.so.1", "libEGL.so")
LIB_GL = ("libGL.so.1", "libGL.so")


class ApiError(RuntimeError):
    """No se pudo preguntar. Nunca sale del módulo: aquí se traduce a None."""


def _cargar(nombres: tuple[str, ...]) -> Optional[ctypes.CDLL]:
    for nombre in nombres:
        try:
            return ctypes.CDLL(nombre)
        except OSError:
            continue
    return None


@contextlib.contextmanager
def _sin_ruido() -> Iterator[None]:
    """Tapa el descriptor 2 mientras se pregunta.

    Los drivers de Mesa escriben avisos por su cuenta al cargarse —que RADV no
    está certificado, que rusticl es experimental— y no hay forma de pedirles
    que se callen. Sin esto, un `silux --json` deja de ser JSON.
    """
    try:
        copia = os.dup(2)
        nulo = os.open(os.devnull, os.O_WRONLY)
    except OSError:
        yield
        return
    try:
        os.dup2(nulo, 2)
        yield
    finally:
        os.dup2(copia, 2)
        os.close(nulo)
        os.close(copia)


def _version(empaquetada: int) -> str:
    """Vulkan mete la versión en 32 bits: 7 de mayor, 10 de menor, 12 de parche."""
    return f"{(empaquetada >> 22) & 0x7F}.{(empaquetada >> 12) & 0x3FF}.{empaquetada & 0xFFF}"


# -- Vulkan ------------------------------------------------------------------

class _VkAppInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_int), ("pNext", ctypes.c_void_p),
        ("pApplicationName", ctypes.c_char_p), ("applicationVersion", ctypes.c_uint32),
        ("pEngineName", ctypes.c_char_p), ("engineVersion", ctypes.c_uint32),
        ("apiVersion", ctypes.c_uint32),
    ]


class _VkInstanceInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_int), ("pNext", ctypes.c_void_p), ("flags", ctypes.c_uint32),
        ("pApplicationInfo", ctypes.POINTER(_VkAppInfo)),
        ("enabledLayerCount", ctypes.c_uint32), ("ppEnabledLayerNames", ctypes.c_void_p),
        ("enabledExtensionCount", ctypes.c_uint32), ("ppEnabledExtensionNames", ctypes.c_void_p),
    ]


class _VkProps(ctypes.Structure):
    """`VkPhysicalDeviceProperties`, de la que solo interesa la cabecera.

    El resto va como relleno con su tamaño exacto y un colchón detrás: la
    biblioteca escribe la estructura entera, y declararla más corta de lo que es
    sería dejarla pisar memoria ajena.
    """

    _fields_ = [
        ("apiVersion", ctypes.c_uint32), ("driverVersion", ctypes.c_uint32),
        ("vendorID", ctypes.c_uint32), ("deviceID", ctypes.c_uint32),
        ("deviceType", ctypes.c_uint32), ("deviceName", ctypes.c_char * 256),
        ("pipelineCacheUUID", ctypes.c_uint8 * 16),
        ("limits", ctypes.c_uint8 * 504),          # VkPhysicalDeviceLimits
        ("sparseProperties", ctypes.c_uint32 * 5),
        ("_colchon", ctypes.c_uint8 * 256),
    ]


VK_TIPOS = {1: "integrada", 2: "dedicada", 3: "virtual", 4: "CPU"}

VK_STRUCTURE_TYPE_APPLICATION_INFO = 0
VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO = 1
# Se pide 1.0 a propósito: una instancia que pide más de lo que hay se niega a
# crearse, y aquí lo que interesa es que el driver diga hasta dónde llega él.
VK_API_1_0 = 1 << 22


def vulkan() -> list[dict]:
    """Las tarjetas que ve Vulkan, con su versión de API y su nombre real."""
    lib = _cargar(LIB_VULKAN)
    if lib is None:
        return []

    with _sin_ruido():
        instancia_ver = ctypes.c_uint32(VK_API_1_0)
        with contextlib.suppress(AttributeError):
            lib.vkEnumerateInstanceVersion(ctypes.byref(instancia_ver))

        app = _VkAppInfo(VK_STRUCTURE_TYPE_APPLICATION_INFO, None, b"silux", 0,
                         None, 0, VK_API_1_0)
        info = _VkInstanceInfo(VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, None, 0,
                               ctypes.pointer(app), 0, None, 0, None)
        instancia = ctypes.c_void_p()
        if lib.vkCreateInstance(ctypes.byref(info), None, ctypes.byref(instancia)) != 0:
            return []

        try:
            cuantas = ctypes.c_uint32()
            if lib.vkEnumeratePhysicalDevices(instancia, ctypes.byref(cuantas), None) != 0:
                return []
            if not cuantas.value:
                return []
            dispositivos = (ctypes.c_void_p * cuantas.value)()
            lib.vkEnumeratePhysicalDevices(instancia, ctypes.byref(cuantas), dispositivos)

            encontradas = []
            for handle in dispositivos:
                props = _VkProps()
                lib.vkGetPhysicalDeviceProperties(ctypes.c_void_p(handle), ctypes.byref(props))
                encontradas.append({
                    "name": props.deviceName.decode("utf-8", "replace") or None,
                    "api_version": _version(props.apiVersion),
                    "instance_version": _version(instancia_ver.value),
                    "driver_version": props.driverVersion,
                    "vendor_id": props.vendorID,
                    "device_id": props.deviceID,
                    "kind": VK_TIPOS.get(props.deviceType),
                })
            return encontradas
        finally:
            lib.vkDestroyInstance(instancia, None)


# -- OpenCL ------------------------------------------------------------------

CL_PLATFORM_NAME = 0x0902
CL_PLATFORM_VERSION = 0x0901
CL_DEVICE_TYPE_ALL = 0xFFFFFFFF
CL_DEVICE_MAX_COMPUTE_UNITS = 0x1002
CL_DEVICE_MAX_CLOCK_FREQUENCY = 0x100C
CL_DEVICE_GLOBAL_MEM_SIZE = 0x101F
CL_DEVICE_NAME = 0x102B
CL_DEVICE_VENDOR = 0x102C
CL_DRIVER_VERSION = 0x102D
CL_DEVICE_VERSION = 0x102F


def _cl_texto(fn, objeto, codigo: int) -> Optional[str]:
    tamano = ctypes.c_size_t()
    if fn(objeto, codigo, 0, None, ctypes.byref(tamano)) != 0 or not tamano.value:
        return None
    buffer = ctypes.create_string_buffer(tamano.value)
    if fn(objeto, codigo, tamano.value, buffer, None) != 0:
        return None
    return buffer.value.decode("utf-8", "replace").strip() or None


def _cl_numero(fn, objeto, codigo: int, tipo) -> Optional[int]:
    valor = tipo()
    if fn(objeto, codigo, ctypes.sizeof(tipo), ctypes.byref(valor), None) != 0:
        return None
    return valor.value


def opencl() -> list[dict]:
    """Los dispositivos de cómputo, con sus unidades y su versión de OpenCL."""
    lib = _cargar(LIB_OPENCL)
    if lib is None:
        return []

    with _sin_ruido():
        cuantas = ctypes.c_uint32()
        if lib.clGetPlatformIDs(0, None, ctypes.byref(cuantas)) != 0 or not cuantas.value:
            return []
        plataformas = (ctypes.c_void_p * cuantas.value)()
        lib.clGetPlatformIDs(cuantas.value, plataformas, None)

        encontrados = []
        for plataforma in plataformas:
            handle = ctypes.c_void_p(plataforma)
            nombre_plataforma = _cl_texto(lib.clGetPlatformInfo, handle, CL_PLATFORM_NAME)

            cuantos = ctypes.c_uint32()
            if lib.clGetDeviceIDs(handle, ctypes.c_uint64(CL_DEVICE_TYPE_ALL), 0, None,
                                  ctypes.byref(cuantos)) != 0 or not cuantos.value:
                continue
            dispositivos = (ctypes.c_void_p * cuantos.value)()
            lib.clGetDeviceIDs(handle, ctypes.c_uint64(CL_DEVICE_TYPE_ALL),
                               cuantos.value, dispositivos, None)

            for dispositivo in dispositivos:
                d = ctypes.c_void_p(dispositivo)
                info = lib.clGetDeviceInfo
                encontrados.append({
                    "platform": nombre_plataforma,
                    "platform_version": _cl_texto(lib.clGetPlatformInfo, handle,
                                                  CL_PLATFORM_VERSION),
                    "name": _cl_texto(info, d, CL_DEVICE_NAME),
                    "vendor": _cl_texto(info, d, CL_DEVICE_VENDOR),
                    "version": _cl_texto(info, d, CL_DEVICE_VERSION),
                    "driver_version": _cl_texto(info, d, CL_DRIVER_VERSION),
                    "compute_units": _cl_numero(info, d, CL_DEVICE_MAX_COMPUTE_UNITS,
                                                ctypes.c_uint32),
                    "max_clock_mhz": _cl_numero(info, d, CL_DEVICE_MAX_CLOCK_FREQUENCY,
                                                ctypes.c_uint32),
                    "global_memory_bytes": _cl_numero(info, d, CL_DEVICE_GLOBAL_MEM_SIZE,
                                                      ctypes.c_uint64),
                })
        return encontrados


# -- OpenGL ------------------------------------------------------------------

EGL_PLATFORM_SURFACELESS_MESA = 0x31DD
EGL_OPENGL_API = 0x30A2
EGL_SURFACE_TYPE, EGL_PBUFFER_BIT = 0x3033, 0x0001
EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT = 0x3040, 0x0008
EGL_NONE = 0x3038
EGL_VENDOR = 0x3053

GL_VENDOR, GL_RENDERER, GL_VERSION = 0x1F00, 0x1F01, 0x1F02
GL_SHADING_LANGUAGE_VERSION = 0x8B8C


def opengl() -> Optional[dict]:
    """La versión de OpenGL, sin abrir ninguna ventana.

    Hace falta un contexto para poder preguntar, y un contexto normalmente pide
    una ventana. EGL permite uno «sin superficie», que es justo lo que se
    necesita: crear, preguntar cuatro cadenas y cerrarlo.
    """
    egl = _cargar(LIB_EGL)
    gl = _cargar(LIB_GL)
    if egl is None or gl is None:
        return None

    egl.eglGetPlatformDisplay.restype = ctypes.c_void_p
    egl.eglGetPlatformDisplay.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
    egl.eglCreateContext.restype = ctypes.c_void_p
    egl.eglCreateContext.argtypes = [ctypes.c_void_p] * 4
    egl.eglMakeCurrent.argtypes = [ctypes.c_void_p] * 4
    egl.eglQueryString.restype = ctypes.c_char_p
    egl.eglQueryString.argtypes = [ctypes.c_void_p, ctypes.c_int]
    gl.glGetString.restype = ctypes.c_char_p
    gl.glGetString.argtypes = [ctypes.c_uint32]

    with _sin_ruido():
        pantalla = egl.eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, None, None)
        if not pantalla:
            return None
        pantalla = ctypes.c_void_p(pantalla)
        mayor, menor = ctypes.c_int(), ctypes.c_int()
        if not egl.eglInitialize(pantalla, ctypes.byref(mayor), ctypes.byref(menor)):
            return None

        contexto = None
        try:
            if not egl.eglBindAPI(EGL_OPENGL_API):
                return None
            configuraciones = (ctypes.c_void_p * 1)()
            cuantas = ctypes.c_int()
            atributos = (ctypes.c_int * 5)(EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
                                           EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT, EGL_NONE)
            if not egl.eglChooseConfig(pantalla, atributos, configuraciones, 1,
                                       ctypes.byref(cuantas)) or not cuantas.value:
                return None

            contexto = egl.eglCreateContext(pantalla, configuraciones[0], None, None)
            if not contexto:
                return None
            contexto = ctypes.c_void_p(contexto)
            if not egl.eglMakeCurrent(pantalla, None, None, contexto):
                return None

            texto = lambda codigo: (
                (gl.glGetString(codigo) or b"").decode("utf-8", "replace").strip() or None
            )
            return {
                "version": texto(GL_VERSION),
                "renderer": texto(GL_RENDERER),
                "vendor": texto(GL_VENDOR),
                "glsl": texto(GL_SHADING_LANGUAGE_VERSION),
                "egl_version": f"{mayor.value}.{menor.value}",
                "egl_vendor": (egl.eglQueryString(pantalla, EGL_VENDOR) or b"").decode(
                    "utf-8", "replace") or None,
            }
        finally:
            # Soltar el contexto antes de cerrar: si se queda activo, la
            # siguiente biblioteca gráfica de este proceso se lo encuentra puesto.
            with contextlib.suppress(Exception):
                egl.eglMakeCurrent(pantalla, None, None, None)
                if contexto:
                    egl.eglDestroyContext(pantalla, contexto)
                egl.eglTerminate(pantalla)


# -- las tres a la vez, en un proceso que se tira después ---------------------

def en_este_proceso() -> dict[str, Any]:
    """Pregunta a las tres aquí mismo. Es lo que ejecuta el proceso hijo."""
    return {"vulkan": vulkan(), "opencl": opencl(), "opengl": opengl()}


def consultar() -> dict[str, Any]:
    """Las tres APIs, preguntadas fuera para no cargar aquí sus drivers.

    Si el proceso hijo no sale adelante se devuelve vacío en vez de preguntar
    aquí: hacerlo funcionaría, pero dejaría el programa por encima de su
    presupuesto de memoria para siempre, y eso no se arregla luego.
    """
    vacio: dict[str, Any] = {"vulkan": [], "opencl": [], "opengl": None}
    # El directorio que contiene el paquete, para que el hijo lo encuentre esté
    # silux instalado o ejecutándose desde el código fuente.
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    entorno = dict(os.environ)
    entorno["PYTHONPATH"] = os.pathsep.join(
        [raiz] + ([entorno["PYTHONPATH"]] if entorno.get("PYTHONPATH") else [])
    )
    try:
        completado = subprocess.run(
            [sys.executable, "-m", "silux.gpuapi"],
            capture_output=True, timeout=TIEMPO_MAXIMO, env=entorno, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return vacio

    if completado.returncode != 0 or not completado.stdout:
        return vacio
    try:
        leido = json.loads(completado.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return vacio
    return leido if isinstance(leido, dict) else vacio


def main() -> int:
    # La salida tiene que ser JSON limpio: los avisos de los drivers ya van
    # tapados, pero cualquier otra cosa que se imprima aquí rompería al padre.
    json.dump(en_este_proceso(), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
