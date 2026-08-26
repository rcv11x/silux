# cpuz — contexto del proyecto

Perfilador de hardware para Linux en Python + PySide6. La idea es juntar en
un solo programa nativo lo que en Windows hacen **CPU-Z, GPU-Z y HWMonitor**:
identificación del hardware y monitorización de sensores, con buena pinta.

**Lo que este programa no es: un administrador de tareas.** Los procesos son
software, no hardware, y Linux ya tiene buenos monitores de procesos. El
hueco está en el otro lado.

## Cómo se ejecuta

```bash
python3 -m cpuz.ui.app                 # interfaz
python3 -m cpuz.cli                    # volcado en terminal
python3 -m cpuz.cli --json             # API para otros programas
python3 -m cpuz.cli --sensors          # el árbol de sensores
python3 tools/gen_cpu_db.py            # regenerar la base de datos de CPUs
python3 tools/install_desktop.py       # icono y entrada de menú
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .
```

Capturas sin pantalla: `python3 -m cpuz.ui.app --screenshot salida.png
--page Monitor --dark --compact --size 900x680`.

## Las reglas que sostienen el diseño

Estas no son preferencias de estilo. Cada una viene de un problema concreto:

1. **El modelo guarda números, no texto.** `freq_hz: int`, nunca `"2.90 GHz"`.
   Todo el formateo vive en `cpuz/render.py` y ocurre al pintar. De ahí salen
   gratis la salida JSON, las gráficas y unos tests que comparan cifras. Es
   donde CPU-X se ató las manos.

2. **`Snapshot` es inmutable.** Los proveedores escriben en un `Draft`
   mutable y este se congela. La interfaz compara fotos y repinta lo que
   cambió.

3. **`cpu.types` es una lista desde el primer commit.** Cualquier Intel de
   12ª en adelante tiene núcleos P y E con cachés y frecuencias distintas.
   Asumir «una CPU, un juego de valores» obliga a reescribirlo todo después.

4. **Nada se lee en el hilo de la interfaz.** `cpuz/ui/sampler.py` es un
   QThread; ahí dentro se fija la afinidad para CPUID y ahí se abre el
   diálogo de polkit, que bloquea.

5. **Cuando falta un dato se explica.** Un `Note` con su motivo —root,
   driver, base de datos, hardware— en vez de esconder la sección. Cada
   página enseña solo sus propias notas (`snapshot.notes_for("cpu")`).

6. **Los widgets que se refrescan a menudo reutilizan.** Crear widgets en
   cada muestreo dejaba miles vivos y hacía crecer la memoria medio megabyte
   por minuto. `ChipRow` y `Table` reescriben el texto de lo que ya existe;
   hay tests que lo vigilan.

7. **Presupuesto de memoria: 100 MB.** Ahora mismo se estabiliza en 98 con
   las siete secciones abiertas. Si algo lo sube, la salida es construir las
   páginas solo cuando se visitan (hoy se construyen las siete al arrancar,
   y eso son 31 de esos 98 MB).

## Cómo está repartido

```
cpuz/
├─ model.py        dataclasses congeladas: Snapshot, CpuType, Sensor, Board…
├─ render.py       ÚNICO sitio donde un valor se convierte en texto
├─ collector.py    orquesta los proveedores; separa estático de dinámico
├─ tracking.py     mínimos, máximos y medias por sensor
├─ rawcpuid.py     CPUID desde Python, sin root (mmap + ctypes)
├─ features.py     tabla declarativa de banderas de CPUID
├─ pciids.py       nombres de dispositivos PCI desde la base del sistema
├─ spd.py          decodifica el chip de identificación de la RAM
├─ providers/      una fuente cada uno; ninguno conoce a los demás
├─ privileged/     ayudante root mínimo (helper.py) + cliente + SMBIOS
├─ db/             cpu_ids.json (generado) + sockets.json (curado a mano)
└─ ui/             tema, hilo de muestreo, widgets, una página por sección
```

El orden de los proveedores en `collector.py` importa y está comentado ahí.

## Estado

Terminadas: **CPU, Monitor, Cachés, Placa base, Memoria, Sistema, Ajustes**.
Falta **Gráficos**, que es la parte ingrata: cada driver expone lo suyo por su
lado (amdgpu y nvidia con sysfs distintos, NVML para las NVIDIA propietarias)
más las versiones de OpenGL, Vulkan y OpenCL.

## Cosas que ya se probaron y no funcionaron

- **Reconstruir un dataclass congelado campo a campo** al actualizarlo: se
  come en silencio los campos añadidos después. Usar `dataclasses.replace`.
- **Preguntar a Qt por `sizeHint` justo después de añadir widgets**: devuelve
  el valor anterior. O se calcula a mano, o se deja pasar un ciclo de eventos.
- **`sizeHintForColumn` en un árbol**: solo mira las filas de primer nivel.
  Hay que medir el texto recorriendo los hijos.
- **Estirar la primera columna de una tabla**: en pantalla completa manda las
  cifras a un palmo del nombre. El hueco sobrante va al final.
- **Dibujar flechas con bordes CSS en Qt**: salen cuadrados. Hay que darle una
  imagen; se generan en tiempo de ejecución en `ui/theme.py`.

## Fuentes de datos y licencias

- [libcpuid](https://github.com/anrieff/libcpuid) — BSD-2 — tablas de identificación de CPU
- [CPU-X](https://github.com/TheTumultuousUnicornOfDarkness/CPU-X) — GPL-3.0 — tabla de sockets
- `pci.ids` del sistema (paquete hwdata) — nombres de dispositivos PCI
