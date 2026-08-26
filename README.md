# cpuz

Perfilador de hardware para Linux con interfaz Qt. Alternativa a
[CPU-X](https://github.com/TheTumultuousUnicornOfDarkness/CPU-X), escrita en
Python puro.

Estado: **CPU, Monitor, Cachés, Placa base, Memoria y Sistema terminadas**.
Falta Gráficos.

## Qué es y qué no

Dos preguntas, y solo dos:

- **Qué hardware es este.** Procesador, cachés, placa base, memoria, gráfica.
  Es el terreno de CPU-Z, y en Linux está mal cubierto.
- **Qué está haciendo ahora.** Todos los sensores del equipo con sus mínimos,
  máximos y medias. Es el terreno de HWMonitor y HWiNFO64, y en Linux está
  peor cubierto todavía.

Las dos son la misma pregunta sobre el mismo hardware, leyendo las mismas
fuentes, y por eso viven en el mismo programa: HWiNFO64 lleva años
demostrándolo.

**Lo que este programa no es: un administrador de tareas.** Los procesos son
software, no hardware; se leen de otro sitio, se presentan de otra forma y
—a diferencia de todo lo que hay aquí— exigen actuar sobre el sistema y no
solo leerlo. Además Linux ya tiene buenos administradores de tareas. El hueco
está en el otro lado.

```bash
python3 -m cpuz.ui.app                 # interfaz gráfica
python3 -m cpuz.cli --sensors          # solo el árbol de sensores
python3 -m cpuz.ui.app --compact       # densidad compacta
python3 -m cpuz.ui.app --size 700x520  # tamaño concreto para esta ejecución
python3 -m cpuz.cli                    # volcado en el terminal
python3 -m cpuz.cli --json             # el mismo dato, para otros programas
python3 -m cpuz.cli --watch            # refresco continuo en texto
```

La ventana abre a 900×680 y recuerda el tamaño al cerrarla. El suelo depende
de la densidad —470×400 en normal, 400×340 en compacta— y no es el mínimo
técnico, que ronda los 270 px: es el punto por debajo del cual los nombres de
campo se recortan tanto que dejan de identificar nada.

Para llegar hasta ahí sin romperse: las filas de tarjetas se reparten en
menos columnas, los textos largos se recortan con puntos suspensivos —el
completo queda en el tooltip—, la tabla de cachés se desplaza dentro de su
propia tarjeta, y por debajo de 620 px la barra lateral se cambia por un
selector compacto en la barra de estado.

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

## Ajustes

En la sección **Ajustes**, que se guarda en `~/.config/cpuz/settings.json`:

| Ajuste | Qué hace |
| --- | --- |
| Refrescar cada | 0,2 a 10 s. Se aplica en caliente, sin reiniciar el muestreo |
| Mostrar todas las instrucciones | Todas las banderas de CPUID en vez de solo las relevantes |
| Tema | Seguir al sistema, claro u oscuro |
| Densidad | Amplia, normal o compacta: márgenes, tipografía, filas y columnas |
| Unidad de temperatura | Celsius o Fahrenheit |

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

## Consumo

Medido con la ventana abierta y muestreo cada 300 ms:

```
intérprete Python            9,7 MB
+ PySide6                   40,9 MB     ← el coste fijo de Qt
+ cpuz (7 secciones)        53,4 MB
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
segundos **sin aplanarse nunca** —unos 37 MB por hora—. La causa: la fila de
insignias y la tabla simple creaban widgets nuevos en cada muestreo en vez de
reescribir los que ya tenían, y dejaban miles de etiquetas vivas. Ahora ambas
reutilizan, y hay tests que comprueban que cuarenta refrescos seguidos no
crean ni un widget.

## Por qué no hace falta C ni ensamblador

CPU-X necesita C++ porque se apoya en librerías de C (libcpuid, libpci,
libprocps) y porque lleva embebido un benchmark de ancho de banda de memoria
escrito en ensamblador. Pero el trabajo de fondo —leer ficheros de sysfs y
emparejar identificadores contra una tabla— no necesita nada de eso.

El único punto que parecía exigir código nativo es la instrucción `CPUID`, y
se resuelve en unas sesenta líneas: `cpuz/rawcpuid.py` escribe **20 bytes** de
código máquina en una página anónima, la marca como ejecutable y la llama con
`ctypes`. Es todo el ensamblador del proyecto, va comentado instrucción a
instrucción, y no hace falta compilador para usarlo.

Lo que sí queda fuera del alcance de Python es un benchmark de ancho de banda
de memoria como el de CPU-X, que necesita bucles de carga y almacenamiento con
SSE/AVX. Es una función que este proyecto no persigue.

## Qué se lee y de dónde

| Dato | Fuente | ¿Permisos? |
| --- | --- | --- |
| Fabricante, marca, familia, modelo, stepping | `CPUID` en espacio de usuario | no |
| Juego de instrucciones | `CPUID` hojas 1, 7, 0x80000001 | no |
| Nombre en clave, nodo de fabricación | `CPUID` + base de datos | no |
| Encapsulado (socket) | base de datos por microarquitectura | no |
| BCLK, reloj base, techo de turbo del silicio | `CPUID` hoja 0x16 | no |
| Núcleos, hilos, topología, núcleos P/E | `/sys/devices/system/cpu/*/topology` | no |
| Jerarquía de caché | `/sys/devices/system/cpu/*/cache` | no |
| Frecuencias, driver, gobernador, turbo | `cpufreq`, `intel_pstate` | no |
| Preferencia de energía (EPP) | `cpufreq` | no |
| Virtualización y si se corre dentro de una VM | `CPUID` | no |
| Carga media a 1, 5 y 15 minutos | `/proc/loadavg` | no |
| Distribución, kernel, escritorio, sesión | `/etc/os-release`, `uname` | no |
| Memoria, intercambio, procesos, hilos | `/proc/meminfo`, `/proc/loadavg` | no |
| Uso total y por núcleo | `/proc/stat` | no |
| Temperaturas | `hwmon` (coretemp, k10temp…) | no |
| Consumo en vatios, por dominio | `powercap` / RAPL | según distribución |
| Límites de potencia PL1 y PL2 | `powercap` / RAPL | no |
| Voltaje del núcleo | Super I/O por `hwmon`, o MSR | driver o root |
| Todos los sensores del equipo | `hwmon` y `power_supply` | no |
| Placa, BIOS, versión y fecha del firmware | `/sys/class/dmi/id` | no |
| Módulos de RAM: fabricante, chips, referencia, fecha | SPD por SMBus | no |
| Velocidad catalogada y temporizaciones JEDEC/XMP | SPD por SMBus | no |
| UEFI o BIOS heredada, arranque seguro, TPM | `/sys/firmware`, `/sys/class/tpm` | no |
| Chipset y controlador de memoria | bus PCI + `pci.ids` | no |
| Umbrales de alarma de cada sensor | `hwmon` (`*_max`, `*_crit`) | no |

Cuando algo no se puede leer, la aplicación **lo dice y explica por qué** en
lugar de dejar el campo vacío o esconder la sección.

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

Los tests usan el volcado real de un módulo —con el número de serie a cero—
en `tests/fixtures/`. Un volcado de verdad vale más que cualquier tabla
sintética: los desplazamientos de este formato no fallan cuando se leen mal,
solo enseñan otra cifra.

## El ayudante privilegiado

Dos cosas necesitan root y no hay forma de evitarlo: la tabla SMBIOS completa
—donde están los módulos de memoria— y los registros MSR del procesador. El
programa **nunca corre como root**. Cuando el usuario pide esos datos, lanza
por polkit un ayudante mínimo y le habla por una tubería.

El ayudante está escrito para poder leerse de una sentada, y de ahí sus tres
reglas:

- **No importa nada del propio programa**, solo la biblioteca estándar. Un
  fallo en cualquier otro módulo no puede llegar hasta él.
- **No interpreta lo que lee.** Devuelve los bytes crudos de la tabla SMBIOS
  y el análisis se hace sin privilegios. Analizar formatos binarios es de
  donde salen la mayoría de los fallos de memoria, y hacerlo como root sería
  regalar el problema.
- **No acepta rutas ni órdenes.** Las dos rutas que abre son constantes en su
  código, y los registros MSR admitidos son una lista cerrada de diez.

Hay tests que comprueban que el ayudante no contiene `subprocess`, `eval`,
`exec` ni importaciones del paquete, y que las dos listas blancas de MSR —la
del contrato y la suya— no se han separado.

Tampoco se pide nada al arrancar: la pestaña de Memoria enseña lo que sabe,
explica qué falta y pone un botón. Un programa de diagnóstico que abre un
diálogo de contraseña nada más abrirse es un programa que se desinstala.

`data/org.cpuz.helper.policy.in` es la política de polkit para quien empaquete
el programa. Es opcional: sin ella pkexec pide la contraseña igual, solo que
con un mensaje genérico y sin recordar la autorización durante la sesión.

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

## La pestaña de placa base

Veinte campos, todos de ficheros que el kernel expone sin permisos:

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
bus 0 es el chipset**, y `pci.ids` —que ya está instalado en cualquier
distribución— le pone nombre. De «H510 Chipset eSPI Controller» se extrae
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

Bajo el procesador conviven sensores de tres orígenes distintos —el chip de
temperaturas, los contadores RAPL y `cpufreq`— porque en un monitor lo que
importa no es de dónde sale el dato sino a qué pertenece. Es lo mismo que
hace HWiNFO.

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
confundía. Ahora se enseña lo que publica el fabricante —familia 6,
modelo 165 (0xA5)— y una fila con la firma en crudo, `0x000A0653`, cuyo
tooltip desglosa de dónde sale cada valor.

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

## Arquitectura

```
cpuz/
├─ rawcpuid.py     CPUID desde Python, con fijación de afinidad por núcleo
├─ features.py     tabla declarativa de banderas: hoja, registro, bit, nombre
├─ model.py        dataclasses congeladas — valores tipados, nunca texto
├─ render.py       ÚNICO sitio donde un valor se convierte en texto
├─ collector.py    orquesta los proveedores; separa lo estático de lo dinámico
├─ providers/      una fuente cada uno; ninguno conoce a los demás
├─ db/             cpu_ids.json (generado) + sockets.json (propio)
├─ tracking.py     mínimos, máximos y medias por sensor a lo largo de la sesión
├─ pciids.py       resuelve nombres de dispositivos PCI contra la base del sistema
├─ spd.py         decodifica el chip de identificación de los módulos de RAM
├─ privileged/    ayudante root: helper.py (mínimo), client.py, smbios.py
├─ providers/derived.py   convierte relojes, uso y potencia en sensores del árbol
├─ cli.py          volcado, JSON y modo continuo
└─ ui/             Qt: tema, hilo de muestreo, widgets y páginas
                   pages/cpu.py      ← qué hardware es
                   pages/monitor.py  ← qué está haciendo
                   pages/caches.py, pages/settings.py
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

## La base de datos

Ni el nombre en clave, ni el nodo de fabricación, ni el socket se pueden
deducir del hardware: son tablas que alguien mantiene. Este proyecto no las
escribe a mano, las **genera**:

```bash
python3 tools/gen_cpu_db.py          # clona/actualiza libcpuid y CPU-X y regenera
python3 tools/gen_cpu_db.py --offline
python3 -m cpuz.cli --db-info        # de qué commit salieron los datos
```

`cpuz/db/cpu_ids.json` sale de las tablas de identificación de libcpuid (517
filas de Intel, 371 de AMD, 198 piezas ARM) y de la tabla de sockets de CPU-X.
El algoritmo de emparejado —puntuar cada fila por cuántos campos coinciden y
quedarse con la mejor— está reimplementado en `cpuz/db/__init__.py` con los
mismos pesos que libcpuid.

`cpuz/db/sockets.json` es tabla propia y **se edita a mano**. Cubre por
microarquitectura en vez de por modelo concreto, así que una regla vale para
una generación entera: donde la tabla heredada de CPU-X tiene 125 entradas de
modelos sueltos, aquí bastan 49 reglas para cubrir mucho más.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

Ninguno necesita hardware concreto: los proveedores se prueban contra árboles
de sysfs sintéticos y el generador contra fragmentos de C.

## Licencias de las fuentes de datos

- [libcpuid](https://github.com/anrieff/libcpuid) — BSD 2 cláusulas — tablas de identificación
- [CPU-X](https://github.com/TheTumultuousUnicornOfDarkness/CPU-X) — GPL-3.0 — tabla de sockets
