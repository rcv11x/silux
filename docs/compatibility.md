**English** · [Español](compatibilidad.md)

# Compatibility

Which AppImage to pick, and the hardware Silux has been tested on. Each row
says whether it has been seen working on a real machine; the detail of each
machine is in [tested machines](equipos-probados.md) (in Spanish).

| | Means |
|---|---|
| ✅ | Tested on a real machine, and it works. |
| ⚠️ | Works, with something missing or weaker; the note says what. |
| ❌ | Can't be done: the hardware or its driver doesn't publish it. |
| ❔ | Not tested: written without the hardware at hand. |

## Which AppImage

| File | Which machines |
|---|---|
| `silux-x86_64.AppImage` | The regular one: almost any PC from 2010 on. Intel Core i, Pentium and Celeron from Nehalem; Atom from 2013; AMD FX, Ryzen, and the A-series and E-series from Trinity and Kabini (A4/A6/A8/A10-5xxx onwards, E1/E2 from 2013). |
| `silux-x86_64-compat.AppImage` | Only if the regular one doesn't start: Core 2, Atom before 2013, Athlon II, Phenom II, Llano A-series (A4/A6/A8-3xxx) and Bobcat E/C-series (E-350, E-450, E1-1200, E2-1800, C-60). If you don't know which, try the regular one first: if it can't run on your processor, it tells you when you open it. |

The regular one needs glibc 2.34 or later (RHEL 9, Ubuntu 22.04, Debian 12 and
newer) and an x86-64-v2 processor. The compat one needs glibc 2.30 or later
(Ubuntu 20.04, Debian 11 and newer) and any 64-bit processor.

## Processors

| Processors | Tested on | | Notes |
|---|---|---|---|
| Intel Core, 10th to 12th generation | i5-10400, i7-10700F, i5-1135G7, i3-1115G4, i5-12450H, i7-12700, i7-12700KF | ✅ | Hybrids, with their P and E cores apart. |
| Intel Core, 3rd to 8th generation | i5-3330, i7-4710HQ, i5-5200U, i5-8350U, Celeron G3900 | ✅ | |
| Low-power Intel Celeron and Pentium | Celeron N4000 | ✅ | |
| Intel Core 2 and Celerons of that time | Core 2 Duo P8400, Celeron 560 | ✅ | With the compat AppImage. No power or voltage: they don't publish them. |
| AMD Ryzen, Zen to Zen 3 | Ryzen 7 5800X3D, Ryzen 7 5700X3D, Ryzen 5 5600G, Ryzen 3 4100, Athlon 3000G | ✅ | |
| AMD Ryzen with Zen 4 | Ryzen 9 7900 | ✅ | |
| AMD Ryzen with Zen 5 | — | ❔ | Its name and Tjmax come from AMD's sheet. |
| AMD before Zen | FX-8150, A8-6410 | ⚠️ | They don't publish their base clock. On an A8-6410, the TDP counts as the critical power limit. |
| ARM | — | ❔ | Recognises the core, tested with `/proc/cpuinfo` from real machines; never run on one. |

## Graphics

| Graphics | Tested on | | Notes |
|---|---|---|---|
| AMD with `amdgpu` | RX 9070 XT, RX 9060 XT, RX 5500 XT, RX 550, Radeon 740M, Vega 3 | ✅ | Firmware telemetry in versions 1.3 and 2.1. The others are recognised and not read. |
| AMD with `radeon` | Radeon R4/R5 | ⚠️ | Less data than with `amdgpu`. |
| Intel with `i915` | UHD 630, 770, 620, 600 and G4, Iris Xe, HD 2500, 4600, 5500 and 510, GM965 | ⚠️ | All but the temperature, which no path publishes. |
| Intel Arc, and Intel with `xe` | — | ❔ | |
| NVIDIA with the proprietary driver | RTX 4060, RTX 4050 Laptop, RTX 3060, RTX 3050 Mobile, GTX 1660 Ti | ✅ | No memory type or ROPs: NVML doesn't publish them. Letting a laptop's GPU sleep, tested on one model. |
| NVIDIA with `nouveau` | GeForce 210, Quadro NVS 160M, GTX 850M | ⚠️ | Less data; the fan shows under «Usage» in Sensors. |

## Memory

| Memory | | Notes |
|---|---|---|
| DDR4, with its SPD and XMP | ✅ | |
| DDR3, DDR3L and DDR2 | ✅ | |
| Soldered memory | ✅ | |
| DDR5 | ⚠️ | On a laptop with `spd5118`, its SPD couldn't be read. |

## Disks

| Disks | | Notes |
|---|---|---|
| NVMe, SATA SSDs and hard disks | ✅ | With their SMART, which needs the administrator. |
| Over USB: enclosures and pen drives | ✅ | |
| Card readers | ✅ | An empty slot isn't listed as a disk. |
| The disk test | ⚠️ | Experimental. Checked against fio on NVMe, and tested on SATA, a hard disk and USB, with ext4, btrfs, exFAT and FAT32. Random 4K writes with 32 requests come out 12-15 % low on btrfs. |
| The disk test on NTFS | ❔ | |

## Systems

| System | | Notes |
|---|---|---|
| Fedora 43 to 45, Debian 13, Ubuntu 24.04 and 26.04, Linux Mint 22.3, Arch, CachyOS, Manjaro, Bazzite | ✅ | |
| Gentoo with OpenRC, antiX with runit | ✅ | |
| Ubuntu 20.04 | ✅ | With the compat AppImage. |
| KDE Plasma, GNOME, XFCE, Cinnamon, bspwm | ✅ | |
| Linux 5.15 or later | ✅ | |
| Linux 5.10 | ⚠️ | Opens, and System says what is missing. |
| QEMU/KVM virtual machines | ⚠️ | No sensors or frequency: the machine has none. |
| Containers | ✅ | The disk test, without io_uring, measures with threads. |
