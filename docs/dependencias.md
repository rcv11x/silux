# Lo que Silux usa del sistema

Todo lo que Silux toma del sistema y no lleva dentro: archivos de datos,
bibliotecas y programas. Para cada uno, para qué sirve, en qué paquete viene y
qué pasa si falta.

**Nada imprescindible depende de esto.** Lo que lee el hardware (el
procesador, la memoria, los sensores, los discos, las gráficas por sysfs) es
Python leyendo `/sys`, `/proc`, `/dev` y el propio procesador. El AppImage
lleva dentro su Python y su Qt; instalado con pip, los pone pip. Lo de aquí
añade nombres, lo que un driver solo cuenta por su biblioteca, la forma de
pedir permisos y algunas comodidades.

**Si falta algo que este equipo necesita, se dice.** Sale en Diagnóstico (el
final del informe) y en la página del dato, con el motivo «Falta un paquete
del sistema», lo que no sale y el paquete de esta distribución. En una
distribución que no es de estas cinco familias se nombran los cinco.

Los nombres de los paquetes se preguntaron a cada distribución, a su propio
gestor de paquetes, el 21 de noviembre de 2026: Debian 13, Ubuntu 24.04,
Fedora 45 y Arch. Los de Gentoo, a packages.gentoo.org y a portagefilelist.de,
su base de qué paquete instala cada archivo. Las derivadas usan los de su familia: Linux Mint y Pop!_OS,
los de Ubuntu; CachyOS, Manjaro y EndeavourOS, los de Arch; RHEL, Rocky y
Alma, los de Fedora. La tabla del código es `silux/system_deps.py`, y
`tests/test_system_deps.py` comprueba que esta página dice lo mismo.

## Datos

| Qué | Para qué | Debian | Ubuntu | Fedora | Arch | Gentoo | Si falta | ¿Se avisa? |
|---|---|---|---|---|---|---|---|---|
| `pci.ids` | El nombre de cada dispositivo PCI: la gráfica, la red, el chipset, lo de Dispositivos | `pci.ids` | `hwdata` | `hwdata` | `hwdata` | `sys-apps/hwdata` | Salen con su número (`8086:46a3`) y no con su nombre | Sí, en Placa base |
| `pnp.ids` | El nombre del fabricante de cada monitor | `pnp.ids` | `hwdata` | `hwdata` | `hwdata` | `sys-apps/hwdata` | Sale el código de tres letras del EDID | Sí, en Gráficos, si hay un monitor conectado |

## Gráficas

Las bibliotecas que se usan para preguntar al driver. La respuesta la da el
driver de cada tarjeta (Mesa o el de NVIDIA), que no se busca aquí: sin él,
la biblioteca está y no tiene a quién preguntar.

| Qué | Para qué | Debian | Ubuntu | Fedora | Arch | Gentoo | Si falta | ¿Se avisa? |
|---|---|---|---|---|---|---|---|---|
| NVML (`libnvidia-ml.so.1`) | Todo lo de una NVIDIA con el driver propietario: uso, temperatura, consumo, relojes, memoria | `libnvidia-ml1` (non-free) | `libnvidia-compute-NNN` (NNN, la versión del driver) | `xorg-x11-drv-nvidia-cuda-libs` (RPM Fusion) | `nvidia-utils` | `x11-drivers/nvidia-drivers` | La tarjeta sale con su nombre y nada más | Sí, en Gráficos, si hay una NVIDIA con su driver |
| Vulkan (`libvulkan.so.1`) | La versión de Vulkan y lo que declara cada tarjeta | `libvulkan1` | `libvulkan1` | `vulkan-loader` | `vulkan-icd-loader` | `media-libs/vulkan-loader` | No sale su fila en «Bibliotecas gráficas» | Sí, en Gráficos, junto con las demás que falten |
| EGL (`libEGL.so.1`) | Preguntar a OpenGL sin abrir una ventana | `libegl1` | `libegl1` | `libglvnd-egl` | `libglvnd` | `media-libs/libglvnd` | No sale OpenGL | Sí, igual |
| OpenGL (`libGL.so.1`) | La versión de OpenGL y su driver | `libgl1` | `libgl1` | `libglvnd-glx` | `libglvnd` | `media-libs/libglvnd` | No sale OpenGL | Sí, igual |
| OpenCL (`libOpenCL.so.1`) | Las plataformas de cálculo de cada tarjeta | `ocl-icd-libopencl1` | `ocl-icd-libopencl1` | `ocl-icd` | `ocl-icd` | `dev-libs/opencl-icd-loader` | No sale OpenCL | Sí, igual |
| VA-API (`libva.so.2`, `libva-drm.so.2`) | Qué codecs decodifica y codifica cada tarjeta | `libva2 libva-drm2` | `libva2 libva-drm2` | `libva` | `libva` | `media-libs/libva` | No salen los codecs | Sí, igual |

## Permisos

| Qué | Para qué | Debian | Ubuntu | Fedora | Arch | Gentoo | Si falta | ¿Se avisa? |
|---|---|---|---|---|---|---|---|---|
| `pkexec` | Pedir la contraseña para lo que solo lee root: los módulos de memoria, el voltaje, el diagnóstico de los discos | `pkexec` | `pkexec` | `polkit` | `polkit` | `sys-auth/polkit` | No hay forma de dar permisos (salvo abrir Silux como root) | Sí |
| `python3` del sistema | Desde el AppImage, el ayudante de permisos se lanza con él: root no puede entrar en el montaje del AppImage | `python3` | `python3` | `python3` | `python` | `dev-lang/python` (el `python3` lo pone su dependencia `dev-lang/python-exec`) | No se pueden dar permisos desde el AppImage | Sí, desde el AppImage |

## Programas del sistema

| Qué | Para qué | Debian | Ubuntu | Fedora | Arch | Gentoo | Si falta | ¿Se avisa? |
|---|---|---|---|---|---|---|---|---|
| `systemctl` | Los tiempos de arranque, con systemd | `systemd` | `systemd` | `systemd` | `systemd` | `sys-apps/systemd` | No salen los tiempos de arranque | Sí, con systemd en marcha |
| `modinfo`, `modprobe` | Saber qué módulos del kernel hay y cargar uno de la lista blanca | `kmod` | `kmod` | `kmod` | `kmod` | `sys-apps/kmod` | No se sabe qué módulos hay, ni se puede cargar uno desde Silux | Sí |
| `xdg-open` | Abrir los enlaces y las carpetas | `xdg-utils` | `xdg-utils` | `xdg-utils` | `xdg-utils` | `x11-misc/xdg-utils` | No se abren | Sí, en una sesión gráfica |
| `ca-certificates` | Comprobar a GitHub al buscar una versión nueva (solo si se pide) | `ca-certificates` | `ca-certificates` | `ca-certificates` | `ca-certificates` | `app-misc/ca-certificates` | No se puede buscar ni descargar una versión nueva | Sí, al buscarla: lo dice el error |
| `sensors-detect` | Solo se propone: identifica el chip de sensores de la placa | `lm-sensors` | `lm-sensors` | `lm_sensors` | `lm_sensors` | `sys-apps/lm-sensors` | Nada: Silux no lo ejecuta | No hace falta |

## La entrada de menú

Al añadir Silux al menú se avisa a cada escritorio de que mire. Si falta el
programa de uno, la entrada se crea igual y el menú la ve al volver a entrar
en la sesión. No falta ningún dato, así que no se avisa.

| Qué | Para qué | Debian | Ubuntu | Fedora | Arch | Gentoo |
|---|---|---|---|---|---|---|
| `gio` | Marcar el acceso del escritorio como de confianza (GNOME) | `libglib2.0-bin` | `libglib2.0-bin` | `glib2` | `glib2` | `dev-libs/glib` |
| `update-desktop-database` | Que el menú vea la entrada al momento | `desktop-file-utils` | `desktop-file-utils` | `desktop-file-utils` | `desktop-file-utils` | `dev-util/desktop-file-utils` |
| `gtk-update-icon-cache` | Que el icono salga al momento | `gtk-update-icon-cache` | `gtk-update-icon-cache` | `gtk-update-icon-cache` | `gtk-update-icon-cache` | `dev-util/gtk-update-icon-cache` |
| `kbuildsycoca6` | Lo mismo en KDE Plasma | `libkf6service-bin` | — (la 24.04 trae Plasma 5) | `kf6-kservice` | `kservice` | `kde-frameworks/kservice` |
| `dbus-send` | Avisar a KDE de que cambió el icono | `dbus-bin` | `dbus-bin` | `dbus-tools` | `dbus` | `sys-apps/dbus` |

## Módulos del kernel

Van con el kernel de cada distribución, no en un paquete aparte. Silux dice
cuándo falta uno y qué daría, y puede cargar los de su lista blanca
(`privileged/cargar_modulo.py`) con la contraseña:

| Módulo | Para qué |
|---|---|
| `msr` | El voltaje del procesador y, en un Zen, su P-state (con permisos) |
| `ee1004`, `spd5118`, `at24` | El chip SPD de cada módulo de memoria |
| `i2c-i801`, `i2c-piix4` | El bus por el que se llega a ese chip |
| `drivetemp` | La temperatura de los discos SATA |
| `coretemp`, `k10temp` | La temperatura del procesador |
| El del Super I/O de la placa (`nct6775`, `it87`…) | Ventiladores, voltajes y temperaturas de la placa: lo identifica `sensors-detect` |

## Solo para desarrollar

`git` da el commit en la versión que se enseña cuando Silux corre desde el
código; `uv` y `pytest` pasan la suite. Nada de esto lo necesita quien lo usa.
