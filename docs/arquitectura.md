# Cómo funciona Silux

Lo que no cabe en el README sin convertirlo en un libro: por qué el programa
está hecho así, de dónde sale cada dato y qué se intentó antes que no salió
bien. Se puede leer entero o saltar a lo que interese.

- [Arquitectura](#arquitectura)
- [Por qué no hace falta un compilador](#por-qué-no-hace-falta-un-compilador)
- [El cuello de botella real de un monitor en Linux](#el-cuello-de-botella-real-de-un-monitor-en-linux)
- [Familia, modelo y la firma CPUID](#familia-modelo-y-la-firma-cpuid)
- [El SPD: a cuánto puede ir la memoria](#el-spd-a-cuánto-puede-ir-la-memoria)
- [La pestaña de placa base](#la-pestaña-de-placa-base)
- [El árbol de sensores](#el-árbol-de-sensores)
- [Consumo](#consumo)
- [Sobre el consumo](#sobre-el-consumo)
- [Las dos formas de contar la memoria usada](#las-dos-formas-de-contar-la-memoria-usada)
- [El ayudante privilegiado](privilegios.md)
- [La base de datos](#la-base-de-datos)
- [Ajustes](#ajustes)
- [Instalación en el escritorio](#instalación-en-el-escritorio)

## Arquitectura

```
silux/
├─ model.py        dataclasses congeladas: valores tipados, nunca texto
├─ render.py       ÚNICO sitio donde un valor se convierte en texto
├─ collector.py    orquesta los proveedores; separa lo estático de lo dinámico
├─ tracking.py     mínimos, máximos y medias por sensor a lo largo de la sesión
├─ rawcpuid.py     CPUID desde Python, sin root (mmap + ctypes)
├─ features.py     tabla declarativa de banderas: hoja, registro, bit, nombre
├─ gpuapi.py       OpenGL, Vulkan y OpenCL por ctypes, en un proceso aparte
├─ amdgpu.py       ioctl DRM: tipo de VRAM, bus, unidades de cómputo, ROP
├─ gpumetrics.py   telemetría del firmware AMD: por qué se frena la tarjeta
├─ nvml.py         NVIDIA propietaria, que no publica nada en sysfs
├─ edid.py         decodifica la chapa de identificación del monitor
├─ spd.py          decodifica el chip de identificación de la RAM (DDR4 y DDR5)
├─ smart.py        interpreta el diagnóstico de los discos
├─ pciids.py       nombres de dispositivos PCI desde la base del sistema
├─ benchmark.py    prueba de CPU que reporta en qué condiciones midió
├─ report.py       informe en Markdown para reportar fallos
├─ providers/      una fuente cada uno; ninguno conoce a los demás
├─ privileged/     ayudante root mínimo (helper.py) + cliente + SMBIOS
├─ db/             cpu_ids.json (generado, con la tabla de MIDR de ARM)
│                  + sockets.json y families.json, curados a mano
├─ cli.py          volcado, JSON, informe y modo continuo
└─ ui/             Qt: tema, hilo de muestreo, widgets y una página por sección
```

Dos decisiones sostienen el resto:

**El modelo guarda números, no cadenas.** `freq_hz: int`, no `"2.90 GHz"`. El
formateo ocurre al pintar. De ahí salen gratis la salida JSON, las gráficas y
unos tests que comparan números en vez de texto. Es justo donde CPU-X se ató
las manos: su modelo guarda cadenas ya formateadas, y por eso su `--dump` es
texto plano y no una interfaz para otros programas.

**`Snapshot.cpu.types` es una lista desde el primer commit.** Cualquier Intel
de 12ª generación en adelante tiene núcleos P y E con cachés y frecuencias
distintas. Asumir «una CPU, un juego de valores» obliga a reescribir el modelo
entero más tarde; `tests/test_sysfs.py` monta un sysfs falso de un i7-12700K y
verifica el reparto sin necesidad de tener uno delante.

## Por qué no hace falta un compilador

CPU-X necesita C++ porque se apoya en librerías de C (libcpuid, libpci,
libprocps) y porque lleva embebido un benchmark de ancho de banda de memoria
escrito en ensamblador. Pero el trabajo de fondo (leer archivos de sysfs y
emparejar identificadores contra una tabla) no necesita nada de eso.

Donde sí hace falta código nativo, va como bytes dentro del propio programa y
no como algo que haya que compilar. Son dos sitios:

- **`CPUID`**, en `silux/rawcpuid.py`: veinte bytes de código máquina escritos
  en una página anónima, marcada como ejecutable y llamada con `ctypes`.
- **La latencia de la memoria**, en `silux/membench.py`: doce bytes que
  persiguen punteros —cada lectura da la dirección de la siguiente—, montados
  con la misma `rawcpuid.pagina_ejecutable`. Con lo que trae la biblioteca de
  C no se llega: los accesos sueltos se solapan y la latencia se esconde
  detrás del paralelismo.

Los dos van comentados instrucción a instrucción, y ninguno necesita
compilador, que es lo que permite que funcionen igual dentro de un AppImage.
El ancho de banda de lectura de la RAM se mide con `memchr` de la biblioteca de
C, en otro proceso; el de las cachés, que pediría un bucle propio como el de la
latencia, sigue pendiente.

## El cuello de botella real de un monitor en Linux

No es lo que el programa sepa leer: es qué módulos tenga cargados el kernel.
Una placa sin su driver de Super I/O no publica ni un ventilador ni un
voltaje, por muy bien que se lea `/sys/class/hwmon`.

Por eso el Monitor no se limita a enseñar lo que hay: **detecta lo que falta**.
En el equipo de desarrollo, una MSI H510M PRO-E, pasa de 8 sensores a poder
tener fácilmente el triple con dos módulos que ya están en el sistema:

```
Falta un driver de sensores
  (Super I/O) → ventiladores, voltajes de la placa, temperaturas del chipset
  sudo sensors-detect
  No conviene adivinar el módulo: cada placa lleva un chip distinto.

Falta un driver de sensores
  drivetemp → la temperatura de los discos SATA
  sudo modprobe drivetemp
```

Para el Super I/O se remite a `sensors-detect` en vez de proponer un módulo
concreto: cargar el que no es puede devolver lecturas falsas, y eso es peor
que no dar ninguna.

## Familia, modelo y la firma CPUID

CPUID reparte la familia y el modelo entre un campo base y otro extendido:
cuando los cuatro bits del campo original se agotaron, se añadieron los
extendidos y hay que recomponerlos. Por eso el i5-10400 tiene un "modelo
base" de 5 que por sí solo no significa nada, mientras Intel lo llama
modelo 165.

La primera versión de la interfaz enseñaba las dos formas en cuatro filas, y
confundía. Ahora se enseña lo que publica el fabricante (familia 6,
modelo 165 (0xA5)) y una fila con la firma en crudo, `0x000A0653`, cuyo
tooltip desglosa de dónde sale cada valor.

## El SPD: a cuánto puede ir la memoria

La tabla SMBIOS dice a qué velocidad **va** la memoria. El chip SPD que lleva
cada módulo pegado al circuito dice a cuánto **puede** ir. Son datos distintos
y la diferencia es lo que la gente busca:

```
Zócalo 0   Crucial · chips de Micron · CT8G4DFRA32A.M8FR
           DDR4 UDIMM · 1 rango × 8 bits · fabricado la semana 37 de 2023
           Catalogado a  3200 MT/s
           Funcionando a 2667 MT/s  ⚠

PERFIL              VELOCIDAD   CL  tRCD  tRP  tRAS  tRC   VOLTAJE
Zócalo 0 · JEDEC    3200 MT/s   22    22   22    51   73   1.20 V
```

Se lee **sin permisos**: en cuanto el kernel carga `ee1004` (DDR4) o
`spd5118` (DDR5), el chip queda accesible en el bus SMBus. Si no está cargado,
el Monitor lo avisa como cualquier otro driver que falte.

Dos detalles del formato que es fácil leer mal, y que por eso tienen test:

- **Los tiempos van en dos partes**: una gruesa en unidades de 125 ps y un
  ajuste fino con signo. Ignorar el fino convierte un CL22 en un CL21.
- **El código JEDEC de fabricante no es un número de banco**, sino cuántos
  códigos de continuación lo preceden, ambos con bit de paridad. Leerlo como
  un entero da bancos inexistentes y ningún fabricante.

La estructura de los perfiles XMP no la publica JEDEC y lo que circula viene
de ingeniería inversa, así que todo perfil decodificado pasa un filtro de
plausibilidad: si la velocidad o la latencia salen absurdas se descarta en
silencio. Es preferible no enseñar un perfil a enseñar uno inventado.

Los tests usan el volcado real de un módulo (con el número de serie a cero)
en `tests/fixtures/`. Un volcado de verdad vale más que cualquier tabla
sintética: los desplazamientos de este formato no fallan cuando se leen mal,
solo enseñan otra cifra.

## La pestaña de placa base

Veinte campos, todos de archivos que el kernel expone sin permisos:

```
MSI H510M PRO-E (MS-7D23)
Intel H510 · UEFI (64 bits) · Sobremesa

PLACA BASE                          FIRMWARE
  Fabricante   Micro-Star …           Tipo             UEFI (64 bits)
  Modelo       H510M PRO-E            Fabricante       American Megatrends …
  Revisión     1.0                    Versión          1.80
  Chasis       Sobremesa              Fecha            06/08/2023
                                      Revisión SMBIOS  5.19
CHIPSET                               Arranque seguro  desactivado
  Chipset      Intel H510             TPM              TPM 2.0
  Ident. PCI   H510 Chipset eSPI Controller
  Contr. mem.  Comet Lake-S 6c Host Bridge/DRAM Controller
```

El chipset no sale de ninguna base de datos propia: **el puente LPC/eSPI del
bus 0 es el chipset**, y `pci.ids` (que ya está instalado en cualquier
distribución) le pone nombre. De «H510 Chipset eSPI Controller» se extrae
«Intel H510», que es como lo llama todo el mundo.

Los fabricantes dejan campos SMBIOS sin rellenar con textos de fábrica:
«Default string», «To be filled by O.E.M.», «System manufacturer». Se
filtran. Enseñarlos como si fueran datos es peor que dejar el hueco vacío, y
esta misma placa trae tres.

## El árbol de sensores

La página de Monitor presenta los sensores como lo hacen HWMonitor y HWiNFO:
un árbol por aparato, cada rama una magnitud, y las columnas que importan.

```
▼ MSI H510M PRO-E (MS-7D23)
  ▼ Temperaturas          Actual      Mín      Máx    Media
      Temperatura 1      27.8 °C     27.8     28.3     27.9
▼ Intel Core i5-10400
  ▼ Temperaturas
      Package id 0       37.0 °C     34.0     40.0     35.1
      Core 0 … Core 5
  ▼ Potencias
      Paquete            11.0 W      10.5     32.4     14.3
      Núcleos · Uncore · DRAM
  ▼ Relojes
      Core #0 … Core #11
  ▼ Uso
      Total · Core #0 … Core #11
```

La última columna del árbol está vacía a propósito: absorbe el ancho
sobrante. Sin ella la columna de nombres se estiraba hasta llenar la ventana
y, en pantalla completa, dejaba las cifras a un palmo del nombre que uno
quiere comparar. La columna de nombres se arrastra a gusto y el ancho elegido
se recuerda entre sesiones.

Los nodos se llaman como el aparato, no como el chip: «Intel Core i5-10400»
en vez de «coretemp», «MSI H510M PRO-E» en vez de «nct6683». Un árbol que
obliga a saber qué es cada driver no se lee.

Bajo el procesador conviven sensores de tres orígenes distintos (el chip de
temperaturas, los contadores RAPL y `cpufreq`) porque en un monitor lo que
importa no es de dónde sale el dato sino a qué pertenece. Es lo mismo que
hace HWiNFO.

## Consumo

Medido con la ventana abierta y muestreo cada 300 ms:

```
intérprete Python            9,7 MB
+ PySide6                   40,9 MB     ← el coste fijo de Qt
+ silux (7 secciones)        53,4 MB
+ ventana construida        84,4 MB
+ las 7 secciones visitadas 89,3 MB
estabilizado                98,1 MB
```

Unos 98 MB con todas las secciones abiertas y muestreando cada 250 ms. Dos
quintas partes son el coste fijo de cargar Qt. La medición es en modo
*offscreen*: con una ventana real en Wayland hay que sumarle los búferes de la
superficie.

**Estable, no creciente.** Es la diferencia que importa, y se vigila con un
soak de tres minutos que mide la media de RSS por tramos de treinta segundos:

```
    0-30  s   97,8 MB
   30-60  s   98,1 MB  (+0,23)   ← se llenan las colas de las gráficas
   60-90  s   98,1 MB  (+0,05)
   90-180 s   98,1 MB  (+0,01)   ← plano
```

Antes de encontrarla, una fuga hacía subir esa cifra 0,31 MB cada treinta
segundos **sin aplanarse nunca** (unos 37 MB por hora). La causa: la fila de
insignias y la tabla simple creaban widgets nuevos en cada muestreo en vez de
reescribir los que ya tenían, y dejaban miles de etiquetas vivas. Ahora ambas
reutilizan, y hay tests que comprueban que cuarenta refrescos seguidos no
crean ni un widget.

## Sobre el consumo

El vatiaje se lee del contador de energía RAPL y se desglosa por dominio,
junto con los límites que declara el propio procesador. Un número suelto no
deja saber si está bien; con el contexto, sí:

```
paquete 7,9 W  ·  12 % de 65 W sostenidos
núcleos 6,9 W · uncore 0,3 W · DRAM 0,8 W
límites: 65 W sostenido (PL1) · 115 W de pico (PL2)
```

Cifras bajas en reposo son normales, no un error de medición: un procesador
de escritorio moderno con estados C activos baja a un dígito de vatios sin
carga. Bajo `stress-ng --cpu 12` este mismo equipo sube a 57 W, justo por
debajo de su PL1. Coincide con lo que reporta Mission Center.

## Las dos formas de contar la memoria usada

Hay dos, y mezclarlas produce barras que mienten:

- **Usada** = total − disponible. Es la definición de `free` y la de cualquier
  monitor: «cuánta no podría recuperar aunque quisiera». Incluye la parte de
  la caché que no es recuperable, como tmpfs y la memoria compartida.
- **Aplicaciones** = total − libre − buffers − caché recuperable. Es la que
  permite dibujar una barra cuyos trozos suman exactamente el total.

La primera sale siempre algo mayor. La diferencia no es un error: es la caché
que el kernel no puede devolver. La página enseña las dos, y la barra usa la
segunda porque es la única con la que los segmentos cuadran al 0,000 %.

## El ayudante privilegiado

Está en **[privilegios.md](privilegios.md)**.

## La base de datos

Ni el nombre en clave, ni el nodo de fabricación, ni el socket se pueden
deducir del hardware: son tablas que alguien mantiene. Este proyecto no las
escribe a mano, las **genera**:

```bash
python3 tools/gen_cpu_db.py          # clona/actualiza libcpuid y CPU-X y regenera
python3 tools/gen_cpu_db.py --offline
python3 -m silux.cli --db-info        # de qué commit salieron los datos
```

`silux/db/cpu_ids.json` sale de las tablas de identificación de libcpuid (517
filas de Intel, 371 de AMD, 198 piezas ARM) y de la tabla de sockets de CPU-X.
El algoritmo de emparejado (puntuar cada fila por cuántos campos coinciden y
quedarse con la mejor) está reimplementado en `silux/db/__init__.py` con los
mismos pesos que libcpuid.

`silux/db/sockets.json` es tabla propia y **se edita a mano**. Cubre por
microarquitectura en vez de por modelo concreto, así que una regla vale para
una generación entera: donde la tabla heredada de CPU-X tiene 125 entradas de
modelos sueltos, aquí bastan 49 reglas para cubrir mucho más.

## Ajustes

En la sección **Ajustes**, que se guarda en `~/.config/silux/settings.json`:

| Ajuste | Qué hace |
| --- | --- |
| Refrescar cada | 0,2 a 10 s. Se aplica en caliente, sin reiniciar el muestreo |
| Mostrar todas las instrucciones | Todas las banderas de CPUID en vez de solo las relevantes |
| Tema | Seguir al sistema, claro u oscuro |
| Densidad | Amplia, normal o compacta: márgenes, tipografía, filas y columnas |
| Unidad de temperatura | Celsius o Fahrenheit |
| Tamaño de la letra | Normal, grande, mayor o máximo. Las tarjetas y columnas crecen con él |
| Color de acento | Naranja, azul, verde, morado, rojo o cian |
| Velocidad de red | Bytes o bits por segundo: los mismos datos son 116 MB/s o 931 Mb/s |

En el árbol de sensores **todas las columnas se arrastran** y el ancho se
recuerda entre sesiones. Con el botón derecho sobre la cabecera se vuelve a
los anchos automáticos, que se calculan midiendo el texto real de cada columna
y añadiendo un margen que sigue a la densidad elegida.

Cada separador lleva un par de rayitas que se iluminan al pasar por encima.
Qt ya cambia el cursor ahí, pero eso solo se descubre por accidente: una marca
visible es la diferencia entre una función que existe y una que se usa.

Cambiar tema o densidad reconstruye la interfaz en lugar de repintarla pieza
a pieza. Es cosa de milisegundos, solo pasa cuando el usuario toca un ajuste,
y evita el fallo clásico de que algún widget se quede con el color anterior.
El hilo de muestreo no se toca: no se pierde ni una lectura ni el histórico
de las gráficas.

## Instalación en el escritorio

```bash
python3 tools/install_desktop.py              # icono + entrada de menú
python3 tools/install_desktop.py --uninstall
```

Todo va a `~/.local/share`, sin root y sin tocar nada del sistema. Genera los
PNG del icono a los nueve tamaños que pide freedesktop rasterizando el SVG con
Qt, así que no hacen falta ni `rsvg-convert` ni Inkscape.

Un detalle que cuesta encontrar: en Wayland el compositor no adivina qué
ventana corresponde a qué entrada de menú. Si la aplicación no llama a
`setDesktopFileName()`, la barra de tareas de Plasma enseña un icono genérico
por muy bien instalado que esté el `.desktop`.

## Las reglas, con su porqué

Estas no son preferencias de estilo. Cada una viene de un problema concreto:

1. **El modelo guarda números, no texto.** `freq_hz: int`, nunca `"2.90 GHz"`.
   Todo el formateo vive en `silux/render.py` y ocurre al pintar. De ahí salen
   gratis la salida JSON, las gráficas y unos tests que comparan cifras. Es
   donde CPU-X se ató las manos.

2. **`Snapshot` es inmutable.** Los proveedores escriben en un `Draft`
   mutable y este se congela. La interfaz compara fotos y repinta lo que
   cambió.

3. **`cpu.types` es una lista desde el primer commit.** Cualquier Intel de
   12ª en adelante tiene núcleos P y E con cachés y frecuencias distintas.
   Asumir «una CPU, un juego de valores» obliga a reescribirlo todo después.

4. **Nada se lee en el hilo de la interfaz.** `silux/ui/sampler.py` es un
   QThread; ahí dentro se fija la afinidad para CPUID y ahí se abre el
   diálogo de polkit, que bloquea.

5. **Cuando falta un dato se explica.** Un `Note` con su motivo —root,
   driver, base de datos, hardware— en vez de esconder la sección. Cada
   página enseña solo sus propias notas (`snapshot.notes_for("cpu")`).

6. **Los widgets que se refrescan a menudo reutilizan.** Crear widgets en
   cada muestreo dejaba miles vivos y hacía crecer la memoria medio megabyte
   por minuto. `ChipRow` y `Table` reescriben el texto de lo que ya existe;
   hay tests que lo vigilan.

7. **Presupuesto de memoria: 300 MB.** Era de 100 y lo subió el autor a la
   vista de que la máquina de escritorio va sobrada: entre gastar memoria y
   enseñar un dato más, gana el dato. Ahora ronda los 130 MB con las ocho
   secciones y el árbol de sensores entero desplegado. Sigue sin ser excusa
   para malgastarla: el techo está para que alguien lo mire de vez en cuando,
   y la salida conocida es construir las páginas solo cuando se visitan.

8. **Lo que cueste memoria de forma permanente, en otro proceso.** Preguntar
   a OpenGL, Vulkan y OpenCL carga sus drivers: 118 MB de residente, de los
   que 83 son de rusticl arrastrando LLVM entero para decir «OpenCL 3.1».
   `gpuapi.consultar()` lanza `python3 -m silux.gpuapi`, lee el JSON y lo deja
   morir. De regalo, un driver que revienta ya solo se lleva al hijo.

## El reparto, comentado

```
silux/
├─ model.py        dataclasses congeladas: Snapshot, CpuType, Sensor, Board…
├─ render.py       ÚNICO sitio donde un valor se convierte en texto
├─ collector.py    orquesta los proveedores; separa estático de dinámico
├─ cli.py          volcado en terminal, JSON, sensores e informe
├─ settings.py     preferencias del usuario en ~/.config/silux
├─ tracking.py     mínimos, máximos y medias por sensor
├─ rawcpuid.py     CPUID desde Python, sin root (mmap + ctypes)
├─ gpuapi.py       OpenGL, Vulkan, OpenCL y VA-API por ctypes, en otro proceso
├─ amdgpu.py       ioctl DRM: tipo de VRAM, bus, unidades, ROP
├─ i915.py         ioctl DRM: las unidades de ejecución de una Intel
├─ edid.py         la chapa del monitor, con sus extensiones CTA-861
├─ report.py       informe en Markdown para reportar fallos
├─ gpumetrics.py   telemetría del firmware AMD: por qué se frena la tarjeta
├─ nvml.py         NVIDIA propietaria, que no publica nada en sysfs
├─ features.py     tabla declarativa de banderas de CPUID
├─ pciids.py       nombres de dispositivos PCI desde la base del sistema
├─ spd.py          decodifica el chip de identificación de la RAM (DDR4 y DDR5)
├─ smart.py        interpreta el diagnóstico de los discos, sin privilegios
├─ benchmark.py    prueba de CPU que reporta en qué condiciones midió
├─ membench.py     lo que la memoria mueve de verdad, medido en otro proceso
├─ history.py      historial de pruebas de este equipo
├─ score.py        la puntuación comparable entre equipos, y su escala
├─ privacidad.py   qué se omite de un informe público y qué no
├─ sysroot.py      leer /sys, /proc y /etc de un equipo volcado en vez del
│                  de verdad, y repetir lo grabado al volcarlo (CPUID, ioctl)
├─ ui/tarjeta.py  la imagen del equipo para pegar en un chat, ya anonimizada
├─ ui/guarda.py   para antes de Qt: si el procesador no da, lo dice y no abre
├─ i18n.py        el idioma de la interfaz; el original es el español
├─ throttling.py  desde cuándo lleva frenándose algo, y por qué
├─ registro.py    graba la sesión a un CSV, fila a fila
├─ providers/      una fuente cada uno; ninguno conoce a los demás.
│                  `msr_voltage.py` pregunta el voltaje del núcleo al propio
│                  procesador, que es el único sitio donde está en cualquier
│                  equipo: los sensores de placa lo publican sin etiquetar.
│                  `imc.py` lee del PMU del uncore cuánto tráfico mueve la
│                  memoria ahora mismo, que es un sensor y no una prueba
├─ privileged/     ayudante root mínimo (helper.py) + cliente + SMBIOS.
│                  Lee DMI, MSR, el SMART de los discos y dos PMU: el de la
│                  iGPU y el del controlador de memoria. Del PMU solo cuenta;
│                  el cliente pide una familia y nunca un número de evento.
│                  instalar.py le da su acción de polkit para no pedir la
│                  contraseña en cada arranque; cargar_modulo.py carga un
│                  driver de sensores de una lista blanca fija
├─ db/             cpu_ids.json (generado; incluye la tabla de MIDR de ARM) +
│                  sockets.json y families.json (curados a mano; el segundo
│                  cubre lo que libcpuid no tiene)
└─ ui/             tema, hilo de muestreo, widgets, una página por sección.
                   `widgets.py` son las primitivas —las que usan varias
                   páginas—; el widget que solo monta una vive en su
                   propio módulo (`sensortree`, `corematrix`, `cachemap`,
                   `scorebar`), porque mezclados no se puede mirar la
                   lista antes de escribir uno nuevo
```

El orden de los proveedores en `collector.py` importa y está comentado ahí.

`providers/cppc.py` saca de ACPI CPPC, además de los relojes, **lo bien que
salió cada núcleo de la oblea**: los núcleos de una misma pieza no son
iguales, el firmware lo publica y el planificador lo usa para mandar ahí el
trabajo de un hilo suelto. Ryzen Master lo enseña en Windows con estrellitas;
en Linux no lo enseñaba nadie. Sale en la rejilla de núcleos de la página de
CPU y en el volcado del terminal.

## Los equipos volcados

Un arreglo no se da por bueno con lo que dice la máquina donde se escribe.
`tools/volcar_equipo.py NOMBRE` copia en `tests/fixtures/equipos/NOMBRE/` lo
que el Collector lee de `/sys`, `/proc` y `/etc` —lo decide el Collector
ejecutándose, no una lista—, graba en `grabado.json` lo que no sale de un
archivo y lo anonimiza. Con `SILUX_SYSROOT` apuntando ahí, todos los
proveedores leen ese equipo: `sysroot.ruta` traduce cada camino y
`sysroot.a_traves` devuelve lo grabado en vez de preguntar a la CPU, al
driver o al proceso de las APIs.

`tests/test_equipos.py` monta el Collector contra cada volcado y comprueba lo
que vale para cualquier equipo; lo que solo vale para uno va en el test del
arreglo, con el volcado donde se vio. `manifiesto.json` dice qué no se pudo
grabar: NVML, lo que lee el ayudante privilegiado y el uso de cada hilo, que
sale de restar dos lecturas de `/proc/stat` y el volcado guarda una.

Un proveedor nuevo que lea el sistema sin pasar por `sysroot` lo caza
`test_sysroot`: con una raíz vacía, el Collector no puede tocar ni un camino
del equipo de verdad.

## Copiar un valor

**Un clic en un valor lo copia**, en las fichas y en las tablas. Se copia el
texto entero y no el que se ve: la fila que no cabe y sale con puntos
suspensivos es justo la que hace falta copiar. Un guion no se copia, porque es
la marca de un dato que falta.

## El informe de fallos

`python3 -m silux.cli --report informe.md` recoge el hardware detectado y, sobre
todo, la sección de diagnóstico: qué fuentes respondieron, qué módulos del
kernel faltan y qué datos no se pudieron leer. Es lo primero que hay que pedir
cuando alguien dice que algo no le sale.

Desde el AppImage es `./silux-x86_64.AppImage --report informe.md`: el punto de
entrada reparte entre la interfaz y el volcado en terminal según con qué se le
llame, porque quien lo usa así no tiene otra forma de sacarlo.

Si hay alguna prueba de rendimiento medida con la escala vigente, el informe
lleva también su puntuación y las condiciones en que se tomó. Es lo que permite
juntar medidas de piezas que no están a mano: sin eso, quien manda un informe
manda su hardware pero no lo que rinde, y la tabla de puntuaciones no se llena
nunca.

Omite por defecto el nombre del equipo, las IP, las MAC y los números de serie
—está pensado para pegarlo en un issue público— y lo dice al terminar. Con
`--with-identifiers` se incluyen. Hay tests que vigilan que no se cuele nada.
