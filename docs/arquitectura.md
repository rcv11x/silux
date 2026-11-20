# Cómo está hecho Silux

Qué hace cada parte, cómo viaja un dato desde el kernel hasta la pantalla,
las reglas que sostienen el diseño y cómo se ejecuta cada cosa. Se puede leer
entero o saltar a lo que interese.

- [Cómo se ejecuta cada cosa](#cómo-se-ejecuta-cada-cosa)
- [Cómo viaja un dato](#cómo-viaja-un-dato)
- [Las reglas, con su porqué](#las-reglas-con-su-porqué)
- [El reparto, comentado](#el-reparto-comentado)
- [Por qué no hace falta un compilador](#por-qué-no-hace-falta-un-compilador)
- [Los drivers que faltan](#los-drivers-que-faltan)
- [Familia, modelo y la firma CPUID](#familia-modelo-y-la-firma-cpuid)
- [El SPD: a cuánto puede ir la memoria](#el-spd-a-cuánto-puede-ir-la-memoria)
- [La placa base y el chipset](#la-placa-base-y-el-chipset)
- [El árbol de sensores](#el-árbol-de-sensores)
- [Las dos formas de contar la memoria usada](#las-dos-formas-de-contar-la-memoria-usada)
- [La base de datos de procesadores](#la-base-de-datos-de-procesadores)
- [Los equipos volcados](#los-equipos-volcados)
- [El informe de fallos](#el-informe-de-fallos)
- [Instalación en el escritorio](#instalación-en-el-escritorio)
- [El actualizador](#el-actualizador)

Los permisos y el ayudante tienen su propio documento,
[privilegios.md](privilegios.md); el AppImage, [empaquetado.md](empaquetado.md).

## Cómo se ejecuta cada cosa

El entorno de desarrollo se monta con [uv](https://docs.astral.sh/uv/), que
trae Python, PySide6 y pytest:

```bash
uv sync --extra gui
uv run python -m silux.ui.app           # la interfaz
uv run python -m silux.cli              # el volcado en terminal
uv run python -m silux.cli --json       # todo en JSON, para otros programas
uv run python -m silux.cli --sensors    # el árbol de sensores
uv run python -m silux.cli --report FICHERO   # el informe para un fallo
```

La suite, en dos pasadas como en el CI: tres tests comparan dos medidas de
rendimiento y van solos.

```bash
QT_QPA_PLATFORM=offscreen uv run pytest -n auto -m "not a_solas"
QT_QPA_PLATFORM=offscreen uv run pytest -m a_solas
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .   # sin instalar nada
```

Cada proceso de la suite carga Qt: con poca memoria, mejor `-n 4` que
`-n auto`. Los tests corren en una carpeta temporal propia y no tocan la
configuración ni el historial de quien los ejecuta.

Capturas sin pantalla, con lo que se fuerce por la línea de órdenes solo para
esa ejecución (no se guarda en los ajustes):

```bash
QT_QPA_PLATFORM=offscreen python3 -m silux.ui.app \
  --screenshot sensores.png --page Sensores --dark --compact --size 900x680
```

Acepta además `--font-scale`, `--anonymous` y `--samples N` (con
`--interval 1`, `--samples 65` captura tras un minuto de gráficas). Una
sección que el equipo no tiene —Batería en un sobremesa— sale con código 2.

Las herramientas de `tools/`:

```bash
python3 tools/gen_cpu_db.py            # regenerar la base de datos de procesadores
python3 tools/gen_memory_limits.py     # el máximo de memoria por modelo
python3 tools/gen_lang.py --write      # poner al día los archivos de idioma
python3 tools/medir_referencia.py      # rehacer la escala de puntuación
python3 tools/anadir_puntuacion.py INFORMES   # sumar medidas ajenas a la tabla
python3 tools/install_desktop.py       # entrada de menú del código fuente
python3 tools/volcar_gpu.py            # lo que publica el kernel de cada gráfica
python3 tools/volcar_equipo.py NOMBRE  # este equipo, anonimizado, a tests/fixtures/equipos/
python3 tools/montar_equipo.py NOMBRE ORDEN…   # ejecutar algo con un volcado montado
python3 tools/importar_informe.py INFORME NOMBRE  # el anexo de un informe, a volcado
python3 tools/comprobar_privacidad.py  # antes de publicar nada
python3 tools/medir_consumo.py         # lo que gasta, contra sus objetivos
python3 tools/capturas_readme.py       # las capturas del README, con permisos
python3 tools/build_appimage.py --container    # el AppImage que se reparte
python3 tools/probar_en_minimo.py --container  # la suite en Python 3.10
python3 tools/agitar_ventana.py --ventanas 6   # la ventana cambiando de forma sin parar
```

## Cómo viaja un dato

```
kernel (/sys, /proc, ioctl, CPUID)       ayudante root (SMBIOS, MSR, SMART, PMU)
          │                                        │ por un socket, tras pkexec
          ▼                                        ▼
   providers/*  ──── escriben en un Draft mutable ─────
          │
   Collector.snapshot()   lo estático se lee una vez y se clona;
          │               lo dinámico, en cada muestra
          ▼
   Snapshot congelado     números, nunca texto
          │
   ui/sampler.py          un QThread: nada se lee en el hilo de la interfaz
          │  señal `sampled`
          ▼
   MainWindow._on_sample → _distribute
          │                   la página a la vista: `apply(foto)`
          │                   las demás con gráficas: `record(foto)`
          ▼
   render.py              el único sitio donde un número se vuelve texto
```

Cada proveedor (`providers/`) lee una fuente y no conoce a los demás. Declara
si es estático (el modelo del procesador) o dinámico (su temperatura), y si
no puede trabajar dice por qué con un `Note`. El `Collector` los llama en un
orden que importa y que está comentado en `collector.py`: algunos completan
lo que dejó otro.

La foto que sale (`Snapshot`) es inmutable. La ventana guarda la última y la
pasa a la página abierta, que compara y repinta lo que cambió. Las páginas
que no se ven no se pintan: solo guardan su historia para que la gráfica esté
llena al volver.

Lo que cuesta memoria de forma permanente va en otro proceso que muere al
contestar: OpenGL, Vulkan, OpenCL y VA-API se preguntan en un hijo
(`gpuapi.consultar()`), y la medida de la memoria corre en otro
(`membench.py`).

Lo que solo puede leer el administrador lo lee un ayudante mínimo que se
lanza con `pkexec` y habla con el programa por un socket; cómo y por qué, en
[privilegios.md](privilegios.md).

## Las reglas, con su porqué

No son preferencias de estilo. Cada una viene de un problema concreto:

1. **El modelo guarda números, no texto.** `freq_hz: int`, nunca
   `"2.90 GHz"`. Todo el formateo vive en `silux/render.py` y ocurre al
   pintar. De ahí salen gratis la salida JSON, las gráficas y unos tests que
   comparan cifras. Vale igual para cualquier decisión: si ya hay una función
   que decide algo, no se reimplementa al lado.

2. **`Snapshot` es inmutable.** Los proveedores escriben en un `Draft`
   mutable y este se congela. La interfaz compara fotos y repinta lo que
   cambió.

3. **`cpu.types` es una lista desde el primer commit.** Cualquier Intel de
   12.ª en adelante tiene núcleos P y E con cachés y frecuencias distintas.
   Asumir «una CPU, un juego de valores» obliga a reescribirlo todo después;
   `tests/test_sysfs.py` monta un sysfs falso de un i7-12700K y comprueba el
   reparto.

4. **Nada se lee en el hilo de la interfaz.** `silux/ui/sampler.py` es un
   QThread; ahí dentro se fija la afinidad para CPUID y ahí se abre el
   diálogo de polkit, que bloquea.

5. **Cuando falta un dato se explica.** Un `Note` con su motivo —permisos,
   driver, base de datos, hardware— en vez de esconder la sección, y cada
   página enseña solo sus notas. Lo que no existe en ese hardware no se pinta
   con guion: se esconde y se nombra al pie. Lo que falta por permisos lleva
   un candado, que es otro estado: tiene arreglo.

6. **Los widgets que se refrescan a menudo reutilizan.** Crear widgets en
   cada muestreo dejaba miles vivos y hacía crecer la memoria medio megabyte
   por minuto. `ChipRow` y `Table` reescriben el texto de lo que ya existe;
   hay tests que lo vigilan.

7. **Presupuesto: 300 MB de memoria y unos pocos por ciento de un núcleo.**
   Las cifras, cómo se miden y qué se arregló para llegar, en
   [rendimiento.md](rendimiento.md); las comprueba `tools/medir_consumo.py`.
   Lo que no se ve no se pinta.

8. **Lo que cueste memoria de forma permanente, en otro proceso.** Preguntar
   a OpenGL, Vulkan y OpenCL carga sus drivers: 118 MB de residente, de los
   que 83 son de rusticl arrastrando LLVM entero para decir «OpenCL 3.1». De
   regalo, un driver que revienta solo se lleva al hijo.

9. **La interfaz responde al momento.** Lo que cambia —permisos, un disco que
   se conecta, un dato que aparece o desaparece— se ve en la página abierta
   sin salir y volver. Lo comprueba `tests/test_al_momento.py`: una página
   abierta que recibe una foto queda igual que montada directamente con ella.

## El reparto, comentado

```
silux/
├─ model.py        dataclasses congeladas: Snapshot, CpuType, Sensor, Board…
├─ render.py       ÚNICO sitio donde un valor se convierte en texto
├─ collector.py    orquesta los proveedores; su orden importa y está comentado
├─ cli.py          volcado en terminal, JSON, sensores e informe
├─ options.py      la ayuda de la línea de órdenes, traducida
├─ report.py       el informe corto en Markdown
├─ privacidad.py   qué identifica a alguien: lo usan el informe y las capturas
├─ desktop.py      la entrada de menú y sus iconos
├─ kernel.py       qué dato es de qué versión del kernel (kernel.md)
├─ settings.py     preferencias en ~/.config/silux
├─ tracking.py     mínimos, máximos y medias por sensor
├─ throttling.py   desde cuándo lleva frenándose algo, y por qué
├─ registro.py     graba la sesión a un CSV
├─ i18n.py         el idioma de la interfaz; el original es el español
├─ sysroot.py      leer un equipo volcado en vez del de verdad
├─ volcado.py      volcar este equipo, anonimizado: lo usan tools/ y el anexo
├─ annex.py        el anexo del informe: el volcado en texto, y de vuelta
├─ system_env.py   el entorno de un programa del sistema, sin lo que añade el
│                  AppImage: todo lo que Silux lanza pasa por ahí
├─ rawcpuid.py     CPUID desde Python, sin root (mmap + ctypes)
├─ features.py     tabla declarativa de banderas de CPUID
├─ gpuapi.py       OpenGL, Vulkan, OpenCL y VA-API, en otro proceso
├─ amdgpu.py, i915.py   ioctl DRM de cada fabricante
├─ nvml.py         NVIDIA propietaria, que no publica nada en sysfs
├─ gpumetrics.py   telemetría del firmware AMD: por qué se frena la tarjeta
├─ edid.py         la chapa del monitor, con sus extensiones CTA-861
├─ spd.py          el chip de identificación de la RAM (DDR4 y DDR5)
├─ smart.py        el diagnóstico de los discos
├─ pciids.py       nombres de dispositivos PCI desde la base del sistema
├─ benchmark.py    prueba de CPU que dice en qué condiciones midió
├─ membench.py     ancho de banda y latencia de la memoria, en otro proceso
├─ history.py      historial de pruebas de este equipo
├─ updates.py      buscar una versión nueva y sustituir el AppImage
├─ score.py        la puntuación comparable entre equipos, y su escala
├─ providers/      una fuente cada uno; ninguno conoce a los demás
├─ privileged/     el ayudante root mínimo, su cliente, el instalador y el
│                  cargador de módulos de una lista blanca fija
├─ db/             cpu_ids.json (generado), sockets.json y families.json,
│                  memory_limits.json, scores.json (la escala) y lang/
└─ ui/             tema, hilo de muestreo, una página por sección
```

Algunos proveedores, por lo que no es obvio de su nombre:

- `msr_voltage.py` pregunta el voltaje del núcleo al propio procesador, que
  es el único sitio donde está en cualquier equipo: los sensores de placa lo
  publican sin etiquetar.
- `imc.py` lee del PMU del controlador de memoria cuánto tráfico mueve ahora
  mismo. Es un sensor, no una prueba.
- `cppc.py` saca de ACPI CPPC, además de los relojes, **lo bien que salió
  cada núcleo de la oblea**: el firmware lo publica y el planificador lo usa
  para mandar ahí el trabajo de un hilo suelto. Sale con estrellas en la
  rejilla de núcleos de la página de CPU.
- `pci.py` da la plataforma (IOMMU, virtualización, BAR por encima de 4 GB) y
  el enlace de cada pieza PCIe, que se lee en cada muestra porque cambia solo.
- `devices.py` lista USB, sonido, cámaras y Bluetooth. No abre nunca un
  número de serie ni una dirección.
- `cpuidle.py` da el tiempo en cada estado de reposo, restando dos lecturas.

En `ui/`, `widgets.py` son las primitivas que usan varias páginas; el widget
que solo monta una vive en su propio módulo (`sensortree`, `corematrix`,
`cachemap`, `scorebar`), porque mezclados no se puede mirar la lista antes de
escribir uno nuevo. `full_report.py` monta las páginas sin pantalla para
sacar de ellas el informe; `guarda.py` corre antes de cargar Qt y, si el
procesador no da para él, lo dice y no abre; `tarjeta.py` es la imagen del
equipo para pegar en un chat, ya anonimizada.

**Un clic en un valor lo copia**, en las fichas y en las tablas. Se copia el
texto entero y no el que se ve: la fila que no cabe y sale con puntos
suspensivos es justo la que hace falta copiar. Un guion no se copia.

## Por qué no hace falta un compilador

Casi todo es leer archivos de `/sys` y emparejar identificadores contra una
tabla, y eso no necesita nada nativo. Donde sí hace falta, va como bytes
dentro del propio programa y no como algo que haya que compilar:

- **`CPUID`**, en `silux/rawcpuid.py`: veinte bytes de código máquina escritos
  en una página anónima, marcada como ejecutable y llamada con `ctypes`.
- **La latencia de la memoria**, en `silux/membench.py`: doce bytes que
  persiguen punteros —cada lectura da la dirección de la siguiente—, montados
  con la misma `rawcpuid.pagina_ejecutable`. Con lo que trae la biblioteca de
  C no se llega: los accesos sueltos se solapan y la latencia se esconde
  detrás del paralelismo.

Los dos van comentados instrucción a instrucción, y ninguno necesita
compilador, que es lo que permite que funcionen igual dentro de un AppImage.
El ancho de banda de lectura de la RAM se mide con `memchr` de la biblioteca
de C, en otro proceso.

## Los drivers que faltan

El límite de un monitor en Linux no es lo que el programa sepa leer: es qué
módulos tenga cargados el kernel. Una placa sin su driver de Super I/O no
publica ni un ventilador ni un voltaje, por muy bien que se lea
`/sys/class/hwmon`.

Por eso Silux no se limita a enseñar lo que hay: **detecta lo que falta** y
dice cómo cargarlo (`drivetemp` para la temperatura de los discos SATA, por
ejemplo). Para el Super I/O remite a `sensors-detect` en vez de proponer un
módulo concreto: cargar el que no es puede devolver lecturas falsas, y eso es
peor que no dar ninguna.

## Familia, modelo y la firma CPUID

CPUID reparte la familia y el modelo entre un campo base y otro extendido:
cuando los cuatro bits del campo original se agotaron, se añadieron los
extendidos y hay que recomponerlos. Por eso un i5-10400 tiene un «modelo
base» de 5 que por sí solo no significa nada, mientras Intel lo llama
modelo 165.

Se enseña lo que publica el fabricante —familia 6, modelo 165 (0xA5)— y una
fila con la firma en crudo, `0x000A0653`, cuyo globo desglosa de dónde sale
cada valor.

## El SPD: a cuánto puede ir la memoria

La tabla SMBIOS dice a qué velocidad **va** la memoria. El chip SPD que lleva
cada módulo dice a cuánto **puede** ir. Son datos distintos, y la diferencia
es lo que la gente busca: un módulo catalogado a 3200 que funciona a 2667.

Se lee **sin permisos**: en cuanto el kernel carga `ee1004` (DDR4) o
`spd5118` (DDR5), el chip queda accesible en el bus SMBus. Si no está cargado,
se avisa como cualquier otro driver que falte.

Dos detalles del formato que es fácil leer mal, y que por eso tienen test:

- **Los tiempos van en dos partes**: una gruesa en unidades de 125 ps y un
  ajuste fino con signo. Ignorar el fino convierte un CL22 en un CL21.
- **El código JEDEC de fabricante no es un número de banco**, sino cuántos
  códigos de continuación lo preceden, ambos con bit de paridad. Leerlo como
  un entero da bancos inexistentes y ningún fabricante.

La estructura de los perfiles XMP no la publica JEDEC y lo que circula viene
de ingeniería inversa, así que todo perfil decodificado pasa un filtro de
plausibilidad: si la velocidad o la latencia salen absurdas, se descarta. Es
preferible no enseñar un perfil a enseñar uno inventado.

Los tests usan volcados reales de módulos (con el número de serie a cero) en
`tests/fixtures/`. Un volcado de verdad vale más que cualquier tabla
sintética: los desplazamientos de este formato no fallan cuando se leen mal,
solo enseñan otra cifra.

## La placa base y el chipset

El chipset no sale de ninguna base de datos propia: **el puente LPC/eSPI del
bus 0 es el chipset**, y `pci.ids` (que ya está instalado en cualquier
distribución) le pone nombre. De «H510 Chipset eSPI Controller» se extrae
«Intel H510», que es como lo llama todo el mundo. En AMD el puente no lo
dice, y `providers/dmi.py` lleva una lista de chipsets por generación.

Los fabricantes dejan campos SMBIOS sin rellenar con textos de fábrica:
«Default string», «To be filled by O.E.M.», «System manufacturer». Se
filtran: enseñarlos como si fueran datos es peor que no enseñar nada. Lo
vigila `tests/test_nada_en_bruto.py` con cada volcado, junto con las razones
sociales («Micro-Star International Co., Ltd.» sale «MSI»).

## El árbol de sensores

La página de Sensores los presenta como HWMonitor y HWiNFO: un árbol por
aparato, cada rama una magnitud, y las columnas que importan (actual, mínimo,
máximo, media y el último minuto).

Los nodos se llaman como el aparato, no como el chip: «AMD Ryzen 7 5800X3D»
en vez de «k10temp», el modelo de la placa en vez de «it8688». Un árbol que
obliga a saber qué es cada driver no se lee.

Bajo el procesador conviven sensores de tres orígenes (el chip de
temperaturas, los contadores RAPL y `cpufreq`), porque en un monitor lo que
importa no es de dónde sale el dato sino a qué pertenece.

## Las dos formas de contar la memoria usada

Hay dos, y mezclarlas produce barras que mienten:

- **Usada** = total − disponible. Es la definición de `free`: «cuánta no
  podría recuperar aunque quisiera». Incluye la parte de la caché que no es
  recuperable, como tmpfs y la memoria compartida.
- **Aplicaciones** = total − libre − buffers − caché recuperable. Es la que
  permite dibujar una barra cuyos trozos suman exactamente el total.

La primera sale siempre algo mayor. La diferencia no es un error: es la caché
que el kernel no puede devolver. La página enseña las dos, y la barra usa la
segunda.

## La base de datos de procesadores

Ni el nombre en clave, ni el nodo de fabricación, ni el socket se pueden
deducir del hardware: son tablas que alguien mantiene. Silux no las escribe a
mano, las **genera**:

```bash
python3 tools/gen_cpu_db.py          # clona o actualiza libcpuid y CPU-X y regenera
python3 tools/gen_cpu_db.py --offline
python3 -m silux.cli --db-info       # de qué commit salieron los datos
```

`silux/db/cpu_ids.json` sale de las tablas de identificación de libcpuid y de
la tabla de sockets de CPU-X. El emparejado (puntuar cada fila por cuántos
campos coinciden y quedarse con la mejor) está reimplementado en
`silux/db/__init__.py` con los mismos pesos que libcpuid.

`silux/db/sockets.json` y `families.json` se editan a mano. Cubren por
microarquitectura en vez de por modelo, así que una regla vale para una
generación entera.

## Los equipos volcados

Un arreglo no se da por bueno con lo que dice la máquina donde se escribe.
`tools/volcar_equipo.py NOMBRE` (el código, en `silux/volcado.py`) copia en
`tests/fixtures/equipos/NOMBRE/` lo
que el `Collector` lee de `/sys`, `/proc` y `/etc` —lo decide el `Collector`
ejecutándose, no una lista—, graba en `grabado.json` lo que no sale de un
archivo (CPUID, ioctl, las APIs gráficas) y lo anonimiza. Con
`SILUX_SYSROOT` apuntando ahí, todos los proveedores leen ese equipo:
`sysroot.ruta` traduce cada camino y `sysroot.a_traves` devuelve lo grabado.

**Desde la terminal, un volcado se monta con `tools/montar_equipo.py NOMBRE
ORDEN…`**, no apuntando la variable a la carpeta del repositorio: git no
guarda carpetas vacías y un volcado tiene muchas que cuentan (el
`drm/renderD128` de una gráfica). La herramienta usa el mismo `montado()` que
los tests.

`tests/test_equipos.py` monta el `Collector` contra cada volcado y comprueba
lo que vale para cualquier equipo; lo que solo vale para uno va en el test
del arreglo, con el volcado donde se vio.

**El de otro equipo llega en su informe.** El informe completo acaba con un
anexo (`annex.py`): el mismo volcado, hecho en otro proceso y escrito en texto
carpeta a carpeta, que se puede leer antes de mandarlo.
`tools/importar_informe.py INFORME NOMBRE` lo convierte en
`tests/fixtures/equipos/NOMBRE/`, pasándolo antes por lo que
`tools/comprobar_privacidad.py` mira en un volcado. El anexo lleva lo que se
lee sin permisos: lo del ayudante está propuesto, no hecho. `manifiesto.json` dice qué no se
pudo grabar: NVML, lo que lee el ayudante y lo que sale de restar dos
lecturas. Qué equipos hay volcados, en [equipos-probados.md](equipos-probados.md).

Un proveedor nuevo que lea el sistema sin pasar por `sysroot` lo caza
`test_sysroot`: con una raíz vacía, el `Collector` no puede tocar ni un
camino del equipo de verdad.

## El informe de fallos

```bash
./silux-x86_64.AppImage --report informe.md
python3 -m silux.cli --report informe.md
```

Es lo primero que se pide cuando a alguien algo no le sale. Pide los permisos
al empezar (salvo con `--without-permissions`) y monta las páginas sin
pantalla para copiar de ellas lo que se ve, sección a sección: el informe dice
lo mismo que la ventana, y un test lo compara. Al final van las fuentes que
respondieron, los drivers que faltan y los datos que no se pudieron leer.
`--sections` elige secciones y `--short` saca el informe corto, que no monta
las páginas.

Si hay una prueba de rendimiento medida con la escala vigente, lleva también
su puntuación y las condiciones en que se tomó: así se juntan medidas de
piezas que no están a mano.

Omite el nombre del equipo, las direcciones y los números de serie —está
pensado para pegarlo en un issue público— y lo dice al terminar. Con
`--with-identifiers` se incluyen.

## El actualizador

`silux/updates.py` es lo único del programa que sale a la red, y solo cuando
alguien lo pide.

**Lo que no hace nunca:**

- Conectarse sin que nadie lo pida: «Buscar actualizaciones al iniciar»
  viene apagado, y sin él ni «Buscar ahora» no se abre ni un socket.
- Sustituir nada sin un clic: una versión nueva solo pinta un aviso.
- Mandar datos del equipo: la petición lleva una sola cabecera propia,
  `User-Agent: silux/<versión>`.
- Ejecutar algo que no coincide con lo publicado: lo bajado se compara con el
  SHA-256 de `SHA256SUMS` de la misma release; si no está o no coincide, se
  borra y el AppImage queda como estaba.

**A quién se conecta**, solo por HTTPS, también en las redirecciones:

| Paso | URL | Tope |
|---|---|---|
| Buscar | `https://api.github.com/repos/rcv11x/silux/releases` | 1 MB |
| Sumas | el `SHA256SUMS` de esa release | 64 kB |
| Bajar | el AppImage del mismo tipo que el que corre (normal o `-compat`) | 400 MB |

**Qué cuenta como nuevo:** solo las releases publicadas, nunca los
borradores. Las versiones de prueba (marcadas *prerelease*, o con «rcN» en la
etiqueta) solo en el canal «Pruebas» de Ajustes; sin elegir canal, una versión
de prueba busca en ese y una final, en «Estable» (`updates.channel_for`). Una
de prueba va por debajo de la siguiente y de su final (`0.4.0rc2` <
`0.4.0rc3` < `0.4.0`), así que quien tiene la 0.4-prueba2 recibe la prueba3 y,
en cualquier canal, la 0.4.

**Cómo se sustituye:** se baja a un temporal en la misma carpeta, se
comprueba la suma, y `os.replace` lo pone en la ruta de `$APPIMAGE`, que es a
donde apunta la entrada de menú. «Reiniciar» lanza el nuevo. Desde el código,
o si la carpeta no se puede escribir, solo se avisa con el enlace a la
release.

**Cómo se prueba de punta a punta sin publicar nada:**
`tools/probar_actualizador.py VIEJO.AppImage NUEVO.AppImage` lanza el AppImage
viejo, con su propio Python, contra un GitHub de mentira
(`tools/actualizador/github_falso.py`, un complemento de mitmproxy) que
publica el nuevo como versión siguiente. Pasa cuatro casos: bien, una suma
que no coincide, una redirección a `http://` y una carpeta de solo lectura.

## Instalación en el escritorio

```bash
python3 tools/install_desktop.py              # icono y entrada de menú
python3 tools/install_desktop.py --uninstall
```

Todo va a `~/.local/share`, sin root. Los PNG del icono a los tamaños que pide
freedesktop salen de rasterizar el SVG con Qt, así que no hacen falta ni
`rsvg-convert` ni Inkscape. El AppImage hace lo mismo desde Ajustes.

En Wayland el compositor no adivina qué ventana corresponde a qué entrada de
menú: si la aplicación no llama a `setDesktopFileName()`, la barra de tareas
enseña un icono genérico por muy bien instalado que esté el `.desktop`.
