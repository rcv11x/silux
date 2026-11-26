[English](compatibility.md) · **Español**

# Compatibilidad

Qué AppImage elegir y en qué hardware se ha probado Silux. Cada fila dice si
se ha visto funcionar en un equipo de verdad; el detalle de cada equipo está en
[equipos probados](equipos-probados.md).

| | Quiere decir |
|---|---|
| ✅ | Probado en un equipo de verdad, y va bien. |
| ⚠️ | Va, con algo que falta o que sale peor; la nota dice qué. |
| ❌ | No se puede: el hardware o su driver no lo publican. |
| ❔ | Sin probar: escrito sin la pieza delante. |

## Qué AppImage

| Archivo | Para qué equipos |
|---|---|
| `silux-x86_64.AppImage` | El normal: casi cualquier PC desde 2010. Intel Core i, Pentium y Celeron desde Nehalem; Atom desde 2013; AMD FX, Ryzen, y las A-series y E-series desde Trinity y Kabini (A4/A6/A8/A10-5xxx en adelante, E1/E2 desde 2013). |
| `silux-x86_64-compat.AppImage` | Solo si el normal no arranca: Core 2, Atom anteriores a 2013, Athlon II, Phenom II, A-series Llano (A4/A6/A8-3xxx) y E/C-series Bobcat (E-350, E-450, E1-1200, E2-1800, C-60). Si no sabes cuál, prueba primero el normal: si no vale para tu procesador, te lo dice al abrirlo. |

El normal pide glibc 2.34 o posterior (RHEL 9, Ubuntu 22.04, Debian 12 y
posteriores) y un procesador x86-64-v2. El compat pide glibc 2.30 o posterior
(Ubuntu 20.04, Debian 11 y posteriores) y cualquier procesador de 64 bits.

## Procesadores

| Procesadores | Probado en | | Notas |
|---|---|---|---|
| Intel Core de 10.ª a 12.ª generación | i5-10400, i7-10700F, i5-1135G7, i3-1115G4, i5-12450H, i7-12700, i7-12700KF | ✅ | Los híbridos, con sus núcleos P y E por separado. |
| Intel Core de 3.ª a 8.ª generación | i5-3330, i7-4710HQ, i5-5200U, i5-8350U, Celeron G3900 | ✅ | |
| Intel Celeron y Pentium de bajo consumo | Celeron N4000 | ✅ | |
| Intel Core 2 y Celeron de la misma época | Core 2 Duo P8400, Celeron 560 | ✅ | Con el AppImage compatible. Sin consumo ni voltaje: no los publican. |
| AMD Ryzen, de Zen a Zen 3 | Ryzen 7 5800X3D, Ryzen 7 5700X3D, Ryzen 5 5600G, Ryzen 3 4100, Athlon 3000G | ✅ | |
| AMD Ryzen con Zen 4 | Ryzen 9 7900 | ✅ | |
| AMD Ryzen con Zen 5 | — | ❔ | El nombre y el Tjmax salen de la ficha de AMD. |
| AMD anteriores a Zen | FX-8150, A8-6410 | ⚠️ | No publican su reloj base. En un A8-6410, el TDP cuenta como límite crítico del consumo. |
| ARM | — | ❔ | Reconoce el núcleo, probado con `/proc/cpuinfo` de máquinas reales; nunca se ha ejecutado en una. |

## Gráficas

| Gráficas | Probado en | | Notas |
|---|---|---|---|
| AMD con `amdgpu` | RX 9070 XT, RX 9060 XT, RX 5500 XT, RX 550, Radeon 740M, Vega 3 | ✅ | La telemetría del firmware, en las versiones 1.3 y 2.1. Las demás se reconocen y no se leen. |
| AMD con `radeon` | Radeon R4/R5 | ⚠️ | Menos datos que con `amdgpu`. |
| Intel con `i915` | UHD 630, 770, 620, 600 y G4, Iris Xe, HD 2500, 4600, 5500 y 510, GM965 | ⚠️ | Todo menos la temperatura, que no publica ningún camino. |
| Intel Arc, e Intel con `xe` | — | ❔ | |
| NVIDIA con el driver propietario | RTX 4060, RTX 4050 Laptop, RTX 3060, RTX 3050 Mobile, GTX 1660 Ti | ✅ | Sin tipo de memoria ni ROPs: NVML no los publica. Que Silux deje dormir la de un portátil, probado en un modelo. |
| NVIDIA con `nouveau` | GeForce 210, Quadro NVS 160M, GTX 850M | ⚠️ | Menos datos; el ventilador sale en «Uso» de Sensores. |

## Memoria

| Memoria | | Notas |
|---|---|---|
| DDR4, con su SPD y XMP | ✅ | |
| DDR3, DDR3L y DDR2 | ✅ | |
| Memoria soldada | ✅ | |
| DDR5 | ⚠️ | En un portátil con `spd5118`, su SPD no se pudo leer. |

## Discos

| Discos | | Notas |
|---|---|---|
| NVMe, SSD SATA y discos de platos | ✅ | Con su SMART, que pide al administrador. |
| Por USB: cajas y pendrives | ✅ | |
| Lectores de tarjetas | ✅ | Una ranura vacía no sale como un disco. |
| La prueba de disco | ⚠️ | Experimental. Comparada con fio en NVMe, y probada en SATA, en un disco de platos y por USB, con ext4, btrfs, exFAT y FAT32. La escritura aleatoria 4K con 32 peticiones, en btrfs, sale un 12-15 % baja. |
| La prueba de disco en NTFS | ❔ | |

## Sistemas

| Sistema | | Notas |
|---|---|---|
| Fedora 43 a 45, Debian 13, Ubuntu 24.04 y 26.04, Linux Mint 22.3, Arch, CachyOS, Manjaro, Bazzite | ✅ | |
| Gentoo con OpenRC, antiX con runit | ✅ | |
| Ubuntu 20.04 | ✅ | Con el AppImage compatible. |
| KDE Plasma, GNOME, XFCE, Cinnamon, bspwm | ✅ | |
| Linux 5.15 o posterior | ✅ | |
| Linux 5.10 | ⚠️ | Abre, y Sistema avisa de lo que falta. |
| Máquinas virtuales QEMU/KVM | ⚠️ | Sin sensores ni frecuencia: la máquina no los tiene. |
| Contenedores | ✅ | La prueba de disco, sin io_uring, mide con hilos. |
