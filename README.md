# <img src="silux/ui/assets/silux.svg" width="40" align="top" alt=""> Silux

[![CI](https://github.com/rcv11x/silux/actions/workflows/appimage.yml/badge.svg)](https://github.com/rcv11x/silux/actions/workflows/appimage.yml)

*Hardware profiler for Linux. The interface is in Spanish and English.*

Silux identifica el hardware de un equipo con Linux y vigila sus sensores: lo que en Windows hacen CPU-Z, GPU-Z y HWMonitor, en un solo programa. Cuando no puede leer un dato, dice por qué.

![Inicio](capturas/inicio.png)

<p>
  <img src="capturas/cpu.png" width="49%" alt="CPU">
  <img src="capturas/graficos.png" width="49%" alt="Gráficos">
  <img src="capturas/memoria.png" width="49%" alt="Memoria">
  <img src="capturas/sensores.png" width="49%" alt="Sensores">
</p>

## Descargar

Cada [versión](https://github.com/rcv11x/silux/releases) trae dos AppImage:

| Archivo | Procesador | Distribución |
|---|---|---|
| `silux-x86_64.AppImage` | Intel desde 2008, AMD desde 2011 | glibc 2.34 o posterior: RHEL 9, Ubuntu 22.04, Debian 12 y más nuevas |
| `silux-x86_64-compat.AppImage` | cualquier procesador de 64 bits | glibc 2.35 o posterior: Ubuntu 22.04, Debian 12 y más nuevas |

```
chmod +x silux-x86_64.AppImage
./silux-x86_64.AppImage
```

Funciona con [Linux 5.15](docs/kernel.md) o posterior. Algunos datos, como los módulos de memoria, la salud de los discos o el voltaje, solo los puede leer el administrador: Silux los pide al pulsar un candado, explica antes qué va a leer, y no cambia nada en el equipo.

Desde el código, con [uv](https://docs.astral.sh/uv/), que trae Python 3.10 o posterior y PySide6:

```
git clone https://github.com/rcv11x/silux.git && cd silux
uv run --extra gui python -m silux.ui.app
```

## En la terminal

```
./silux-x86_64.AppImage --cli                 # todo el hardware, por pantalla
./silux-x86_64.AppImage --sensors --watch     # los sensores, cada segundo
./silux-x86_64.AppImage --json                # todo en JSON
./silux-x86_64.AppImage --cli --help          # todas las opciones
```

Desde el código, lo mismo con `uv run python -m silux.cli`.

## Si algo falla

```
./silux-x86_64.AppImage --report informe.md
```

Pide la contraseña para leer también lo que solo ve el administrador. El informe no lleva el nombre del equipo, ni direcciones, ni números de serie: revísalo y adjúntalo en un [issue](https://github.com/rcv11x/silux/issues) o en el canal #silux-pruebas del Discord de UniversoLinux.

## Más

- [Arquitectura](docs/arquitectura.md): cómo está hecho y cómo ejecutar cada cosa.
- [Convenciones](docs/convenciones.md): cómo contribuir.
- [Equipos probados](docs/equipos-probados.md) y [lo que falta](docs/pendientes.md).
- [Cambios de cada versión](CHANGELOG.md).

Silux se escribe con ayuda de Claude, el asistente de IA de Anthropic.

## Licencia

GPL-3.0 o posterior: [LICENSE](LICENSE). La tabla de procesadores lleva datos de libcpuid y CPU-X; sus avisos, en [THIRD_PARTY_NOTICES.md](silux/db/THIRD_PARTY_NOTICES.md).
