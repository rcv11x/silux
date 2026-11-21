"""OpenGL, Vulkan y OpenCL preguntados directamente a sus bibliotecas.

Lo natural aquí sería llamar a `glxinfo`, `vulkaninfo` y `clinfo` y leerles la
salida, que es lo que hace medio mundo. Tiene dos pegas: son tres paquetes que
el usuario puede no tener instalados, y su salida es texto pensado para
personas, que cambia entre versiones. Las bibliotecas, en cambio, están puestas
siempre que el driver lo esté, y su ABI no se mueve.

Así que se cargan con `ctypes`, igual que `rawcpuid` hace con CPUID. Cada una
va por su cuenta: que falte Vulkan no impide leer OpenGL.

De aquí sale además el dato que el kernel no sabe dar. `pci.ids` dice que esta
tarjeta es una «Radeon RX 9070/9070 XT/9070 GRE» (tres modelos distintos con el
mismo identificador PCI) y es el driver, a través de Vulkan, quien dice cuál de
las tres hay puesta.

Nada de esto se llama desde el hilo de la interfaz: crear una instancia Vulkan
o un contexto de OpenGL tarda lo suyo.

Y no se llama en este proceso siquiera. Preguntar a las tres cuesta 118 MB de
residente (rusticl arrastra LLVM entero por decir «OpenCL 3.1») y el programa
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
import re
import subprocess
import sys
import tempfile
from typing import Any, Iterator, Optional

# Margen de sobra: cargar los drivers de las tres es lo lento, y cuando algo se
# atasca de verdad es que el driver está colgado y no va a contestar nunca.
TIMEOUT_S = 20

# Las bibliotecas, en el orden en que suelen llamarse los enlaces.
LIB_VULKAN = ("libvulkan.so.1", "libvulkan.so")
LIB_OPENCL = ("libOpenCL.so.1", "libOpenCL.so")
LIB_EGL = ("libEGL.so.1", "libEGL.so")
LIB_GL = ("libGL.so.1", "libGL.so")
LIB_VA = ("libva.so.2", "libva.so.1", "libva.so")
LIB_VA_DRM = ("libva-drm.so.2", "libva-drm.so.1", "libva-drm.so")


class ApiError(RuntimeError):
    """No se pudo preguntar. Nunca sale del módulo: aquí se traduce a None."""


def _load(names: tuple[str, ...]) -> Optional[ctypes.CDLL]:
    for name in names:
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    return None


@contextlib.contextmanager
def _silenced() -> Iterator[None]:
    """Tapa el descriptor 2 mientras se pregunta.

    Los drivers de Mesa escriben avisos por su cuenta al cargarse (que RADV no
    está certificado, que rusticl es experimental) y no hay forma de pedirles
    que se callen. Sin esto, un `silux --json` deja de ser JSON.
    """
    try:
        saved = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
    except OSError:
        yield
        return
    try:
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(saved, 2)
        os.close(devnull)
        os.close(saved)


@contextlib.contextmanager
def _capturing(said: list) -> Iterator[None]:
    """Fd 2 to a temporary file while asking, its text appended to `said`.

    A driver that rejects a card says why only there, and `silux --json`
    must stay JSON.
    """
    try:
        copy = os.dup(2)
        held = tempfile.TemporaryFile()
    except OSError:
        yield
        return
    try:
        os.dup2(held.fileno(), 2)
        yield
    finally:
        os.dup2(copy, 2)
        os.close(copy)
        held.seek(0)
        said.append(held.read().decode("utf-8", "replace"))
        held.close()


# Mesa's vk_errorf writes «<reason> for <device> (VK_ERROR_…)», after an
# optional «MESA-INTEL: error: » prefix.
_REJECTION = re.compile(r"(?P<reason>\S.*?) for (?P<device>.+?) \((?P<code>VK_ERROR_[A-Z_]+)\)\s*$")
_MESA_PREFIX = re.compile(r"^\S*MESA[^:]*:\s*\w+:\s*")
# Where Vulkan's loader finds its drivers (the ICD manifests).
ICD_FOLDERS = ("/usr/share/vulkan/icd.d", "/usr/local/share/vulkan/icd.d", "/etc/vulkan/icd.d")


def vulkan_rejections(said: str) -> list[dict]:
    """The cards a Vulkan driver refused, with its reason, from what it wrote."""
    found = []
    for line in said.splitlines():
        match = _REJECTION.search(_MESA_PREFIX.sub("", line.strip()))
        if match:
            found.append(match.groupdict())
    return found


def vulkan_icds() -> list[str]:
    """The library each installed Vulkan driver manifest points to."""
    libraries = []
    for folder in ICD_FOLDERS:
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            try:
                with open(os.path.join(folder, name), encoding="utf-8") as handle:
                    path = json.load(handle).get("ICD", {}).get("library_path")
            except (OSError, ValueError, AttributeError):
                continue
            if path:
                libraries.append(os.path.basename(path))
    return libraries


_VULKAN_SAID: list[str] = []


def _version(packed: int) -> str:
    """Vulkan mete la versión en 32 bits: 7 de mayor, 10 de menor, 12 de parche."""
    return f"{(packed >> 22) & 0x7F}.{(packed >> 12) & 0x3FF}.{packed & 0xFFF}"


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


class _VkMemoryHeap(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint64), ("flags", ctypes.c_uint32),
                ("_relleno", ctypes.c_uint32)]


class _VkMemoryType(ctypes.Structure):
    _fields_ = [("propertyFlags", ctypes.c_uint32), ("heapIndex", ctypes.c_uint32)]


class _VkMemoryProps(ctypes.Structure):
    """`VkPhysicalDeviceMemoryProperties`: de dónde sale la memoria de la tarjeta.

    Es la única vía para saber cuánta VRAM tiene una gráfica cuyo driver no la
    publica en sysfs. amdgpu la escribe en `mem_info_vram_total` y NVML la da
    para las NVIDIA con el driver propietario, pero con nouveau no hay ni una
    cosa ni la otra y la ficha se quedaba entera en blanco.
    """

    _fields_ = [
        ("memoryTypeCount", ctypes.c_uint32),
        ("memoryTypes", _VkMemoryType * 32),
        ("memoryHeapCount", ctypes.c_uint32),
        ("memoryHeaps", _VkMemoryHeap * 16),
    ]


# El montón que vive en la propia tarjeta, frente al que se le presta del
# sistema. Es el bit que distingue la VRAM de la memoria compartida.
VK_MEMORY_HEAP_DEVICE_LOCAL_BIT = 0x1

VK_KINDS = {1: "integrada", 2: "dedicada", 3: "virtual", 4: "CPU"}

VK_STRUCTURE_TYPE_APPLICATION_INFO = 0
VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO = 1
# Se pide 1.0 a propósito: una instancia que pide más de lo que hay se niega a
# crearse, y aquí lo que interesa es que el driver diga hasta dónde llega él.
VK_API_1_0 = 1 << 22


def vulkan() -> list[dict]:
    """Las tarjetas que ve Vulkan, con su versión de API y su nombre real."""
    lib = _load(LIB_VULKAN)
    if lib is None:
        return []

    with _capturing(_VULKAN_SAID):
        instance_version = ctypes.c_uint32(VK_API_1_0)
        with contextlib.suppress(AttributeError):
            lib.vkEnumerateInstanceVersion(ctypes.byref(instance_version))

        app = _VkAppInfo(VK_STRUCTURE_TYPE_APPLICATION_INFO, None, b"silux", 0,
                         None, 0, VK_API_1_0)
        info = _VkInstanceInfo(VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, None, 0,
                               ctypes.pointer(app), 0, None, 0, None)
        instance = ctypes.c_void_p()
        if lib.vkCreateInstance(ctypes.byref(info), None, ctypes.byref(instance)) != 0:
            return []

        try:
            count = ctypes.c_uint32()
            if lib.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), None) != 0:
                return []
            if not count.value:
                return []
            devices = (ctypes.c_void_p * count.value)()
            lib.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), devices)

            found = []
            for handle in devices:
                props = _VkProps()
                lib.vkGetPhysicalDeviceProperties(ctypes.c_void_p(handle), ctypes.byref(props))
                found.append({
                    "name": props.deviceName.decode("utf-8", "replace") or None,
                    "api_version": _version(props.apiVersion),
                    "instance_version": _version(instance_version.value),
                    "driver_version": props.driverVersion,
                    "vendor_id": props.vendorID,
                    "device_id": props.deviceID,
                    "kind": VK_KINDS.get(props.deviceType),
                    "device_memory_bytes": _vk_device_memory(lib, handle),
                })
            return found
        finally:
            lib.vkDestroyInstance(instance, None)


def _vk_device_memory(lib, handle) -> Optional[int]:
    """La memoria que la tarjeta lleva encima, sumando sus montones propios.

    Solo cuentan los marcados como locales del dispositivo: los demás son
    memoria del sistema que el driver le deja usar, y sumarla daría una cifra
    que no se corresponde con ningún chip.
    """
    try:
        props = _VkMemoryProps()
        lib.vkGetPhysicalDeviceMemoryProperties(ctypes.c_void_p(handle),
                                                ctypes.byref(props))
    except Exception:                                  # noqa: BLE001
        return None
    total = sum(props.memoryHeaps[i].size
                for i in range(min(props.memoryHeapCount, 16))
                if props.memoryHeaps[i].flags & VK_MEMORY_HEAP_DEVICE_LOCAL_BIT)
    return total or None


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


def _cl_text(fn, obj, code: int) -> Optional[str]:
    size = ctypes.c_size_t()
    if fn(obj, code, 0, None, ctypes.byref(size)) != 0 or not size.value:
        return None
    buffer = ctypes.create_string_buffer(size.value)
    if fn(obj, code, size.value, buffer, None) != 0:
        return None
    return buffer.value.decode("utf-8", "replace").strip() or None


def _cl_number(fn, obj, code: int, ctype) -> Optional[int]:
    value = ctype()
    if fn(obj, code, ctypes.sizeof(ctype), ctypes.byref(value), None) != 0:
        return None
    return value.value


def opencl() -> list[dict]:
    """Los dispositivos de cómputo, con sus unidades y su versión de OpenCL."""
    lib = _load(LIB_OPENCL)
    if lib is None:
        return []

    with _silenced():
        count = ctypes.c_uint32()
        if lib.clGetPlatformIDs(0, None, ctypes.byref(count)) != 0 or not count.value:
            return []
        platforms = (ctypes.c_void_p * count.value)()
        lib.clGetPlatformIDs(count.value, platforms, None)

        found = []
        for platform in platforms:
            handle = ctypes.c_void_p(platform)
            platform_name = _cl_text(lib.clGetPlatformInfo, handle, CL_PLATFORM_NAME)

            device_count = ctypes.c_uint32()
            if lib.clGetDeviceIDs(handle, ctypes.c_uint64(CL_DEVICE_TYPE_ALL), 0, None,
                                  ctypes.byref(device_count)) != 0 or not device_count.value:
                continue
            devices = (ctypes.c_void_p * device_count.value)()
            lib.clGetDeviceIDs(handle, ctypes.c_uint64(CL_DEVICE_TYPE_ALL),
                               device_count.value, devices, None)

            for device in devices:
                d = ctypes.c_void_p(device)
                info = lib.clGetDeviceInfo
                found.append({
                    "platform": platform_name,
                    "platform_version": _cl_text(lib.clGetPlatformInfo, handle,
                                                  CL_PLATFORM_VERSION),
                    "name": _cl_text(info, d, CL_DEVICE_NAME),
                    "vendor": _cl_text(info, d, CL_DEVICE_VENDOR),
                    "version": _cl_text(info, d, CL_DEVICE_VERSION),
                    "driver_version": _cl_text(info, d, CL_DRIVER_VERSION),
                    "compute_units": _cl_number(info, d, CL_DEVICE_MAX_COMPUTE_UNITS,
                                                ctypes.c_uint32),
                    "max_clock_mhz": _cl_number(info, d, CL_DEVICE_MAX_CLOCK_FREQUENCY,
                                                ctypes.c_uint32),
                    "global_memory_bytes": _cl_number(info, d, CL_DEVICE_GLOBAL_MEM_SIZE,
                                                      ctypes.c_uint64),
                })
        return found


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
    egl = _load(LIB_EGL)
    gl = _load(LIB_GL)
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

    with _silenced():
        egl_display = egl.eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, None, None)
        if not egl_display:
            return None
        egl_display = ctypes.c_void_p(egl_display)
        major, minor = ctypes.c_int(), ctypes.c_int()
        if not egl.eglInitialize(egl_display, ctypes.byref(major), ctypes.byref(minor)):
            return None

        context = None
        try:
            if not egl.eglBindAPI(EGL_OPENGL_API):
                return None
            configs = (ctypes.c_void_p * 1)()
            count = ctypes.c_int()
            attributes = (ctypes.c_int * 5)(EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
                                           EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT, EGL_NONE)
            if not egl.eglChooseConfig(egl_display, attributes, configs, 1,
                                       ctypes.byref(count)) or not count.value:
                return None

            context = egl.eglCreateContext(egl_display, configs[0], None, None)
            if not context:
                return None
            context = ctypes.c_void_p(context)
            if not egl.eglMakeCurrent(egl_display, None, None, context):
                return None

            text = lambda code: (
                (gl.glGetString(code) or b"").decode("utf-8", "replace").strip() or None
            )
            return {
                "version": text(GL_VERSION),
                "renderer": text(GL_RENDERER),
                "vendor": text(GL_VENDOR),
                "glsl": text(GL_SHADING_LANGUAGE_VERSION),
                "egl_version": f"{major.value}.{minor.value}",
                "egl_vendor": (egl.eglQueryString(egl_display, EGL_VENDOR) or b"").decode(
                    "utf-8", "replace") or None,
            }
        finally:
            # Soltar el contexto antes de cerrar: si se queda activo, la
            # siguiente biblioteca gráfica de este proceso se lo encuentra puesto.
            with contextlib.suppress(Exception):
                egl.eglMakeCurrent(egl_display, None, None, None)
                if context:
                    egl.eglDestroyContext(egl_display, context)
                egl.eglTerminate(egl_display)


# -- VA-API: qué códecs acelera la tarjeta -----------------------------------
#
# Es lo que contesta `vainfo`, y es de lo más útil que se puede saber de una
# gráfica: si el equipo va a decodificar un vídeo en el chip o a quemarle la
# CPU. Vale para las tres marcas —Intel con iHD, AMD con radeonsi, NVIDIA con
# el driver de VA-API— y, a diferencia de OpenGL, se abre sobre un nodo de
# render concreto, así que **se sabe de qué tarjeta se está hablando**.

# Perfiles de VA-API, agrupados por códec. El número es el valor del enum de
# `va.h` y no se puede deducir del nombre, así que va escrito.
VA_PROFILES: dict[int, tuple[str, str, Optional[int]]] = {
    0:  ("MPEG-2", "Simple", 8),
    1:  ("MPEG-2", "Main", 8),
    2:  ("MPEG-4", "Simple", 8),
    3:  ("MPEG-4", "Advanced Simple", 8),
    4:  ("MPEG-4", "Main", 8),
    5:  ("H.264", "Baseline", 8),
    6:  ("H.264", "Main", 8),
    7:  ("H.264", "High", 8),
    8:  ("VC-1", "Simple", 8),
    9:  ("VC-1", "Main", 8),
    10: ("VC-1", "Advanced", 8),
    11: ("H.263", "Baseline", 8),
    12: ("JPEG", "Baseline", 8),
    13: ("H.264", "Constrained Baseline", 8),
    14: ("VP8", "Version 0.3", 8),
    15: ("H.264", "Multiview High", 8),
    16: ("H.264", "Stereo High", 8),
    17: ("HEVC", "Main", 8),
    18: ("HEVC", "Main 10", 10),
    19: ("VP9", "Profile 0", 8),
    20: ("VP9", "Profile 1", 8),
    21: ("VP9", "Profile 2", 10),
    22: ("VP9", "Profile 3", 10),
    23: ("HEVC", "Main 12", 12),
    24: ("HEVC", "Main 4:2:2 10", 10),
    25: ("HEVC", "Main 4:2:2 12", 12),
    26: ("HEVC", "Main 4:4:4", 8),
    27: ("HEVC", "Main 4:4:4 10", 10),
    28: ("HEVC", "Main 4:4:4 12", 12),
    29: ("HEVC", "SCC Main", 8),
    30: ("HEVC", "SCC Main 10", 10),
    31: ("HEVC", "SCC Main 4:4:4", 8),
    32: ("AV1", "Profile 0", 10),
    33: ("AV1", "Profile 1", 10),
    34: ("HEVC", "SCC Main 4:4:4 10", 10),
    36: ("H.264", "High 10", 10),
    37: ("VVC", "Main 10", 10),
    38: ("VVC", "Multilayer Main 10", 10),
}

# Qué significa cada punto de entrada. Los que no están aquí —postproceso,
# estadísticas, contenido protegido— no son ni decodificar ni codificar.
VA_DECODE = frozenset({1})                    # VLD
VA_ENCODE = frozenset({6, 7, 8, 11})            # EncSlice, EncPicture, LP, FEI

# El orden en que se enseñan: primero lo que la gente busca.
VA_ORDER = ("AV1", "VVC", "HEVC", "H.264", "VP9", "VP8", "MPEG-2", "MPEG-4",
            "VC-1", "H.263", "JPEG")


def _render_nodes() -> list[str]:
    try:
        entries = sorted(os.listdir("/dev/dri"))
    except OSError:
        return []
    return [f"/dev/dri/{n}" for n in entries if n.startswith("renderD")]


def vaapi() -> list[dict]:
    """Los códecs que acelera cada nodo de render, uno por uno.

    Se abre cada nodo por separado a propósito: así el resultado va atado a
    una tarjeta concreta y no hay que adivinar de cuál habla, que es el
    problema que tienen OpenGL y OpenCL en un portátil híbrido.
    """
    lib = _load(LIB_VA)
    drm = _load(LIB_VA_DRM)
    if lib is None or drm is None:
        return []

    drm.vaGetDisplayDRM.restype = ctypes.c_void_p
    drm.vaGetDisplayDRM.argtypes = [ctypes.c_int]
    lib.vaInitialize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                                 ctypes.POINTER(ctypes.c_int)]
    lib.vaTerminate.argtypes = [ctypes.c_void_p]
    lib.vaMaxNumProfiles.argtypes = [ctypes.c_void_p]
    lib.vaMaxNumEntrypoints.argtypes = [ctypes.c_void_p]
    lib.vaQueryVendorString.restype = ctypes.c_char_p
    lib.vaQueryVendorString.argtypes = [ctypes.c_void_p]
    # Sin declarar estos dos, ctypes le pasa el puntero del display truncado a
    # 32 bits y el proceso se cae de golpe. El resto de la biblioteca perdona
    # porque devuelve entero; estas escriben en memoria del que llama.
    lib.vaQueryConfigProfiles.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    lib.vaQueryConfigEntrypoints.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int)]

    found = []
    for path in _render_nodes():
        data = _vaapi_of(lib, drm, path)
        if data is not None:
            found.append(data)
    return found


def _vaapi_of(lib, drm, path: str) -> Optional[dict]:
    """Abre un nodo de render, pregunta y lo cierra todo pase lo que pase."""
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError:
        return None                      # sin permiso sobre el nodo, o no está

    display = None
    try:
        with _silenced():
            display = drm.vaGetDisplayDRM(fd)
            if not display:
                return None
            major, minor = ctypes.c_int(), ctypes.c_int()
            if lib.vaInitialize(display, ctypes.byref(major),
                                ctypes.byref(minor)) != 0:
                return None

            vendor = lib.vaQueryVendorString(display)
            codecs = _va_codecs(lib, display)
        if not codecs:
            return None
        return {
            "node": os.path.basename(path),
            "version": f"{major.value}.{minor.value}",
            "driver": (vendor or b"").decode("utf-8", "replace").strip() or None,
            "codecs": codecs,
        }
    except (OSError, AttributeError, ValueError):
        return None
    finally:
        if display:
            with _silenced():
                lib.vaTerminate(display)
        os.close(fd)


def _va_codecs(lib, display) -> list[dict]:
    """Recorre los perfiles y agrupa por códec lo que sabe hacer cada uno."""
    max_profiles = lib.vaMaxNumProfiles(display)
    if max_profiles <= 0:
        return []
    profiles = (ctypes.c_int * max_profiles)()
    profile_count = ctypes.c_int()
    if lib.vaQueryConfigProfiles(display, profiles,
                                 ctypes.byref(profile_count)) != 0:
        return []

    max_entrypoints = max(lib.vaMaxNumEntrypoints(display), 1)
    entrypoint_buffer = (ctypes.c_int * max_entrypoints)()
    by_codec: dict[str, dict] = {}

    for index in range(min(profile_count.value, max_profiles)):
        known = VA_PROFILES.get(profiles[index])
        if known is None:
            continue                     # perfil nuevo que aún no está en la tabla
        codec, profile, bits = known
        entrypoint_count = ctypes.c_int()
        if lib.vaQueryConfigEntrypoints(display, profiles[index], entrypoint_buffer,
                                        ctypes.byref(entrypoint_count)) != 0:
            continue
        entrypoints = {entrypoint_buffer[i] for i in range(min(entrypoint_count.value, max_entrypoints))}
        decodes = bool(entrypoints & VA_DECODE)
        encodes = bool(entrypoints & VA_ENCODE)
        if not (decodes or encodes):
            continue

        codec_entry = by_codec.setdefault(codec, {"name": codec, "decode": False,
                                              "encode": False, "bits": None,
                                              "profiles": []})
        codec_entry["decode"] = codec_entry["decode"] or decodes
        codec_entry["encode"] = codec_entry["encode"] or encodes
        if bits is not None:
            codec_entry["bits"] = max(codec_entry["bits"] or 0, bits)
        codec_entry["profiles"].append(profile)

    order = {name: i for i, name in enumerate(VA_ORDER)}
    return sorted(by_codec.values(),
                  key=lambda c: (order.get(c["name"], len(order)), c["name"]))


# -- las tres a la vez, en un proceso que se tira después ---------------------

def in_this_process() -> dict[str, Any]:
    """Pregunta a las tres aquí mismo. Es lo que ejecuta el proceso hijo."""
    found = {"vulkan": vulkan(), "opencl": opencl(), "opengl": opengl(),
             "vaapi": vaapi()}
    found["vulkan_rejected"] = vulkan_rejections("".join(_VULKAN_SAID))
    found["vulkan_icds"] = vulkan_icds()
    return found


def query() -> dict[str, Any]:
    """Las tres APIs, preguntadas fuera para no cargar aquí sus drivers.

    Si el proceso hijo no sale adelante se devuelve vacío en vez de preguntar
    aquí: hacerlo funcionaría, pero dejaría el programa por encima de su
    presupuesto de memoria para siempre, y eso no se arregla luego.
    """
    empty: dict[str, Any] = {"vulkan": [], "opencl": [], "opengl": None,
                             "vaapi": []}
    # El directorio que contiene el paquete, para que el hijo lo encuentre esté
    # silux instalado o ejecutándose desde el código fuente.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [root] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "silux.gpuapi"],
            capture_output=True, timeout=TIMEOUT_S, env=env, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return empty

    if completed.returncode != 0 or not completed.stdout:
        return empty
    try:
        data = json.loads(completed.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return empty
    return data if isinstance(data, dict) else empty


def main() -> int:
    # La salida tiene que ser JSON limpio: los avisos de los drivers ya van
    # tapados, pero cualquier otra cosa que se imprima aquí rompería al padre.
    json.dump(in_this_process(), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
