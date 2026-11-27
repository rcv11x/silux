[English](usage.md) · **Español**

# Uso

Cómo se abre Silux, qué hace en la terminal, cómo mandar un informe cuando algo
falla y qué datos necesitan permisos de administrador. Qué AppImage elegir está en
[compatibilidad](compatibilidad.md).

## Abrirlo

```
chmod +x silux-x86_64.AppImage
./silux-x86_64.AppImage
```

Funciona con [Linux 5.15](kernel.md) o posterior.

En KDE, el archivo enseña el logo de Silux si está instalada libappimage (en
Arch y derivadas, `sudo pacman -S libappimage`).

## Lo que necesita permisos de administrador

Algunos datos, como los módulos de memoria, la salud de los discos o el
voltaje, solo los puede leer el administrador. Silux los pide al pulsar un
candado y explica antes qué va a leer. Leer no cambia nada. Lo que sí cambia
el sistema (cargar un módulo del kernel, dejar los permisos instalados) lo dice
antes de hacerlo.

## Desde el código

Con [uv](https://docs.astral.sh/uv/), que trae Python 3.10 o posterior y
PySide6:

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

O desde la ventana: Ajustes → «Ver y guardar el informe…», que te lo enseña
antes de guardarlo.

Pide la contraseña para leer también lo que solo ve el administrador. Al final
lleva los datos en crudo que ha leído, que sirven para reproducir tu equipo en
las pruebas de Silux. El informe no lleva el nombre del equipo, ni direcciones,
ni números de serie: revísalo y adjúntalo en un
[issue](https://github.com/rcv11x/silux/issues) (para que Silux reconozca mejor
tu equipo, con la plantilla
[«Mi CPU y placa»](https://github.com/rcv11x/silux/issues/new?template=mi-cpu-y-placa.yml))
o en el canal #silux-app-chat del Discord de UniversoLinux.
