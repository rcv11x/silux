# Lo que ya se probó y no funcionó

Cada entrada es algo que se hizo de una forma, salió mal y se cambió, con el
porqué. Está aquí para no volver a hacerlo: antes de tocar una zona, se lee su
apartado. El orden dentro de cada apartado es el cronológico.

- [El código](#codigo)
- [Los tests](#tests)
- [Procesador: CPUID, relojes, CPPC y cachés](#cpu)
- [Memoria: SPD, zócalos, canales y su medida](#memoria)
- [Contadores del kernel (PMU de perf)](#pmu)
- [Gráficas y pantallas](#graficas)
- [Discos](#discos)
- [Red](#red)
- [Batería](#bateria)
- [Placa base y sistema](#placa)
- [Sensores y hwmon](#sensores)
- [Benchmark y puntuación](#benchmark)
- [Interfaz y Qt](#interfaz)
- [Idioma y textos](#idioma)
- [Privilegios](#privilegios)
- [Privacidad](#privacidad)
- [Empaquetado y CI](#empaquetado)

<a id="codigo"></a>

## El código

- **Reconstruir un dataclass congelado campo a campo** al actualizarlo: se
  come en silencio los campos añadidos después. Usar `dataclasses.replace`.
- **`valor or otro` con lecturas de hardware**: una GPU parada marca 0 MHz y un
  ventilador quieto 0 RPM. Eso no es un dato ausente, es la respuesta. Hay que
  comparar contra `None`.
- **Llamar a una función de ctypes sin declararle `argtypes`**: libva devuelve
  enteros en casi todo y perdona, pero `vaQueryConfigProfiles` escribe en
  memoria de quien llama, y sin declarar los tipos el puntero del display se
  trunca a 32 bits y el proceso se cae de golpe. Un SIGSEGV limpio, sin
  excepción que atrapar.
- **Marcar como «no aplica a esta plataforma» cualquier fallo de un proveedor**:
  un permiso denegado dice lo contrario de eso. En un entorno enjaulado acababa
  informando de que la red no aplicaba a un equipo que tiene red. Un
  `PermissionError` pide permisos, un fichero ausente es hardware que no lo
  publica, y lo demás es un fallo nuestro y se dice así.
- **Interpolar un valor opcional directamente en una cadena**: `f"familia
  {x}"` con `x` a `None` escribe «familia None». No se arregla con `or "—"`
  porque un stepping 0 es un stepping de verdad; va por `render.dec`, que
  compara contra `None`.
- **Reutilizar un nombre de constante en un módulo de novecientas líneas**:
  `render.py` ya tenía `_CANAL` y `_CONTROLADOR` para contar canales de
  memoria, y la función que compone el título del zócalo los volvió a definir.
  Se llevó por delante la otra: diecisiete tests en rojo. No se ve al
  escribirlo, así que las dos lecturas del localizador llevan prefijo y hay un
  test que comprueba que no se pisan.

<a id="tests"></a>

## Los tests

- **Montar un test sobre un estado que la ejecución real no produce**: el que
  vigilaba justo esto le pasaba a `GpuApis` una NVIDIA con sus 2048 núcleos ya
  puestos y comprobaba que OpenCL no los pisara. Verde siempre, y sin valor:
  cuando ese proveedor corre de verdad, NVML todavía no ha pasado y el campo
  está vacío, que es el único caso donde había algo que decidir. Un test que
  fija a mano el estado de partida está eligiendo también qué rama se ejecuta.
- **Y un test que fabrica a mano los nombres que sí casan**: los cuatro del
  orden construían los sensores con el `device` igual al `brand` de CPUID y al
  modelo del disco sin prefijo, que es un estado que la ejecución real no
  produce nunca. Verdes desde el primer día sobre el caso que no ocurre,
  mientras el que sí ocurre llevaba un año mal. Es el mismo patrón que ya
  costó el test de los núcleos CUDA de OpenCL.
- **Que un test lea el hardware de quien lo ejecuta y además espere encontrar
  algo**: los del buscador de sensores montaban el árbol con
  `Collector().sample()` y luego exigían que filtrar por «temperatura» diera
  más de cero. En una máquina sin `hwmon` no hay ninguna, así que el filtro
  acierta al no devolver nada y el test lo llama fallo. Fallaba en el CI
  siempre y aquí de vez en cuando, según lo que publicara el equipo en ese
  momento, que es la peor mezcla: parece un fantasma. Comparar el árbol
  consigo mismo sí puede leer la máquina; exigir un resultado concreto, no.
- **Dar por probado lo que el `and` nunca llega a evaluar**: `_identidad` en
  `providers/drm.py` llamaba a `_igpu_de_la_cpu(draft)` sin tener `draft` en la
  firma, o sea un `NameError` escrito y esperando. No saltaba nunca aquí porque
  la condición de delante corta: solo se llega cuando una AMD **no** lleva
  «Radeon» en el nombre, y eso pasa en las APU —a las que `pci.ids` llama por
  su nombre en clave, «HawkPoint2»— y en cualquier equipo sin `hwdata`. Es
  decir, reventaba justo en los equipos que ese código intentaba mejorar, y en
  ninguno de los de casa. La suite lo cazaba, pero solo al ejecutarla donde
  falta `pci.ids`.
- **Dejar que la suite use la carpeta personal de quien la ejecuta**: dos
  módulos montaban la ventana sin aislar `XDG_CONFIG_HOME`, la ventana guarda
  sus preferencias al cerrarse y cada `unittest discover` reescribía las del
  autor con los valores por defecto. Se aísla una vez en `tests/__init__.py`
  para todos, no test a test, que es como se olvida.
- **Restaurar un archivo con `cp` y fiarse de lo que sale**: Python cachea el
  bytecode y decide si sirve por la fecha y el tamaño del fuente. Copiando de
  ida y vuelta para comprobar que un test caza el fallo, el `.pyc` se quedó y
  la ejecución siguiente midió el código anterior: se ve un resultado que ya no
  corresponde a lo que hay en disco. Al hacer esas comprobaciones se borra
  `__pycache__` en los dos sentidos.

<a id="cpu"></a>

## Procesador: CPUID, relojes, CPPC y cachés

- **Convertir el `highest_perf` de CPPC en una frecuencia**: la regla de tres
  que parece obvia —`nominal_freq × highest_perf ÷ nominal_perf`— da 4,96 GHz
  en un 5800X3D cuyo boost son 4,55. El número es creíble, comprobable y
  falso. Donde la plataforma ordena sus núcleos, ese campo deja de significar
  «hasta dónde llega la pieza» y pasa a ser el puesto de cada núcleo en el
  ranking. El techo lo da `amd_pstate_max_freq`, que es el cálculo ya hecho
  por quien conoce la curva. Y no vale suponer que el ranking solo aparece
  con amd-pstate: `acpi_cppc/` lo publica ACPI con cualquier driver, así que
  con `acpi-cpufreq` están las notas y falta quien dé el techo. Si los
  núcleos de un tipo traen notas distintas y nadie lo da hecho, no se calcula.
- **Enseñar la nota de silicio de un núcleo como si fuera comparable entre
  máquinas**: 196 no significa nada por sí solo; es la escala de rendimiento
  de esa pieza. Lo comparable es la fracción respecto al mejor núcleo de la
  misma. Y si el firmware devuelve el mismo número para todos, no está
  midiendo: está rellenando el campo con la constante de la familia, y pintar
  ocho núcleos «igual de buenos» daría a entender que se comprobó algo.
- **Dejar que el patrón de marca gane sobre el modelo de CPUID**: la familia y
  el modelo los pone el silicio y no admiten interpretación; el nombre
  comercial es texto. Un Ryzen 7 7445HS (modelo 0x7C) se identificaba como
  «Dragon Range» (modelo 0x61) porque el patrón «Ryzen 7 7###H» le casaba. Los
  campos que identifican el silicio descartan la entrada, no restan puntos.
- **Enseñar el «Unknown …» de libcpuid como nombre en clave**: es su comodín
  para lo que no reconoce. Vale como no-identificación, nunca como respuesta.
- **Enseñar un rango entre la base y el máximo**: en un Xeon con el turbo
  apagado los dos valen 2.60 GHz y el renglón dice «2.60 – 2.60 GHz», que es
  cierto y no informa. Lo que se recorre es de la mínima al máximo.
- **Deduplicar las cachés por su nivel**: en un Ryzen de dos chiplets con
  V-Cache en uno solo hay dos L3 del mismo nivel y el mismo tipo con tamaños
  distintos —96 MB y 32—, y quedarse con la primera enseñaba la buena para
  todo el procesador. Es justo el dato por el que se compra esa pieza y justo
  la mitad del chip donde no es cierto. El tamaño entra en la clave.
- **Deducir el V-Cache del tamaño de la L3**: crece por otros motivos según la
  familia. Quien lo dice es el fabricante en la cadena de marca («X3D»); la
  asimetría entre chiplets es un hecho aparte, que se describe aunque el
  nombre no lo confirme.
- **Comparar la nota de silicio entre tipos de núcleo distintos**: un E-core
  con la mitad de nota que un P-core no salió peor de la oblea; es otro
  núcleo, con otro tamaño y otro propósito, y la plataforma lo puntúa más bajo
  por diseño. Un 12900K decía que su núcleo más flojo se quedaba en el 35 %
  del mejor: cierto en el número y falso en lo que da a entender. La nota solo
  compara piezas equivalentes, así que se agrupa por `type_key`.
- **Contar núcleos donde el usuario cuenta estrellas**: la leyenda decía
  «núcleo 1 y núcleo 3» y en pantalla se veían cuatro marcas, porque cada
  núcleo bueno marca sus dos hilos. Las dos cosas ciertas y ninguna evidente.
- **Escribir la fuente de un dato y no mirar si hay dónde pintarlo**: el
  voltaje del núcleo se leía por MSR, llegaba al modelo y moría ahí, porque la
  ficha de procesador terminaba en el microcódigo y no tenía fila. Con permisos
  dados no salía ni el aviso —el proveedor no fallaba, así que no avisaba de
  nada— y la pantalla quedaba sin fila, sin aviso y sin botón. La suite entera
  en verde con el dato invisible.
- **Dar por imposible lo que otro programa sí enseña**: la ficha decía que
  ningún sensor publica el voltaje del núcleo, y era cierto por donde miraba
  —`k10temp` no publica ninguno y el Super I/O de la placa publica nueve sin
  etiquetar— pero no por donde había que mirar. El dato está en el propio
  procesador: el VID del P-state activo en AMD y `IA32_PERF_STATUS` en Intel,
  que llevaba permitido en la lista blanca del ayudante desde el principio y
  sin que lo usara nadie. Cuando un programa que hace lo mismo enseña un dato
  que aquí sale con su aviso, el aviso es lo primero que hay que revisar.
- **Escribir una tabla nueva sin mirar si la generada ya la tiene**:
  `cpu_ids.json` ya traía el MIDR de ARM —198 piezas con nombre en clave y
  litografía— y el contador de la pantalla de ajustes lo venía diciendo desde
  el principio. La tabla escrita a mano tenía 138 y ninguna de las dos cosas.
- **Suponer que una bandera con el mismo nombre es la misma instrucción**: la
  `aes` de un aarch64 es la extensión criptográfica de ARMv8, y pintarla como
  «AES-NI» le pone a un procesador una instrucción de Intel que no tiene. Cada
  arquitectura necesita su tabla de nombres, no una compartida.
- **Leer fielmente una máquina virtual y no decir que lo es**: un i5-10500T
  salía con «2 núcleos · 2 hilos · 2 sockets», la L3 de 12 MB contada dos veces
  y encapsulado LGA 1200. Todo cierto y nada de la máquina que hay delante:
  VMware le había dado dos vCPU en dos sockets de un núcleo —la pieza de abajo
  trae seis y doce, y un solo socket—, cada vCPU en su propio *package* hace
  que sysfs presente dos L3 que en el silicio son una compartida, y el
  encapsulado sale de la base de datos por familia y modelo, que el hipervisor
  pasa tal cual del anfitrión. Quien mandó la captura estaba convencido de que
  el programa contaba mal los núcleos, y era razonable pensarlo. El bit
  «hypervisor» de CPUID se leía desde el primer día y salía solo en una fila de
  la ficha, redactado como una capacidad del procesador —«VT-x · dentro de una
  máquina virtual»—, y en el informe no salía nunca: el archivo que se pide
  para diagnosticar describía una placa 440BX sin avisar de que no existe tal
  placa. Un dato que cambia cómo se lee todo lo demás va pegado a lo que
  contradice —la insignia delante del nombre en clave, la fila en la cabecera
  del informe— y no en un renglón suyo más abajo. Los números no se tocaron:
  son los que el kernel publica, y con la insignia al lado dejan de leerse como
  un error.
- **Preguntar por `supports()` si una hoja de CPUID existe**: la 0x40000000,
  donde el hipervisor escribe su firma de doce bytes, queda fuera del rango que
  anuncia la hoja 0, así que `supports` contesta que no. Y si se pregunta de
  todas formas sin hipervisor debajo, CPUID responde con el contenido de la
  hoja más alta que tenga: números creíbles donde se esperaba texto. Quien
  autoriza esa pregunta es el bit «hypervisor» de la hoja 1, y el orden de los
  registros tampoco es el de la hoja 0 —aquí es EBX-ECX-EDX y allí EBX-EDX-ECX—.
  Una firma que no esté en la tabla se enseña tal cual: identifica igual al
  hipervisor y llega al informe, que es de donde sale la entrada que falta.

<a id="memoria"></a>

## Memoria: SPD, zócalos, canales y su medida

- **Redondear al más cercano las latencias del SPD**: 16250 ps entre un ciclo
  de 357 son 45,5, y eso es un CL46: la memoria no puede responder antes de
  tiempo. Al más cercano sale un CL45 que no existe.
- **Copiar un código JEDEC tal y como se publica**: el byte que trae el SPD
  lleva paridad impar en el bit más alto, así que un módulo Crucial se presenta
  como 0x9B siendo 0x1B. Como la búsqueda quita ese bit, la tabla tiene que
  estar en la misma moneda; media lista estaba escrita con el byte completo
  —Samsung 0xCE, Kingston 0x98, SK Hynix 0xAD— y esas siete entradas no
  casaban nunca. Justo las tres marcas que más memoria venden salían sin
  fabricante. Hay un test que no deja entrar un código con el bit puesto.
- **Adivinar en qué canal está un módulo de memoria**: el firmware lo escribe
  de tres maneras distintas y ninguna es obligatoria. Donde no lo dice se
  calla: en canal único la memoria rinde la mitad, y decirlo al revés manda a
  alguien a abrir el equipo para nada.
- **Identificar un canal de memoria por su letra**: no es única. Un ThinkPad
  T14 con los dos módulos bien repartidos los llama «Controller0-ChannelA» y
  «Controller1-ChannelA-DIMM0»: dos canales, uno por controlador, y los dos «A».
  Contando letras salía «canal único» en una máquina que va en doble canal, y
  encima con el aviso de repartir los módulos, que ya estaban repartidos. El
  canal es el par controlador–letra cuando el firmware nombra el controlador.
- **Medir la latencia de memoria con lo que trae la libc**: no se llega, y se
  probaron dos caminos. Con muchos accesos aleatorios sueltos —`itemgetter`
  sobre un array— sale plana: 9,7 ns en 16 KB y 11,2 en 256 MB, cuando lo real
  va de uno a ochenta. El motivo es que esos accesos no dependen unos de otros,
  así que el procesador los solapa y la latencia se esconde detrás del
  paralelismo; lo que se mide ahí es cuántos accesos caben a la vez, no lo que
  tarda uno. Con búsqueda binaria sí hay dependencia y aparece la señal (22 ns
  por salto dentro de la caché, 42 fuera), pero para sacar un número hay que
  suponer cuántos niveles del árbol están cacheados y descontar el coste de la
  llamada: tres suposiciones sosteniendo una cifra.

  **Lo que sí funciona es escribir el bucle en código máquina**, que es lo que
  este programa ya hacía en `rawcpuid.py` desde el primer día. Doce bytes que
  persiguen punteros —`mov rax,[rax]`, y cada lectura da la dirección de la
  siguiente— dan 0,9 · 2,7 · 12,3 · 80,6 ns en el 5800X3D de casa, contra los
  0,9 · 2,7 · 12,4 · 66,1 que da AIDA64 en la misma pieza con memoria más
  rápida. Ya está integrado en `membench.py`, y la página ejecutable la monta
  `rawcpuid.pagina_ejecutable`, que es donde se aprendieron esos detalles.
- **Medir una caché con la mitad de su tamaño**: parece holgado y no lo es. La
  L3 de un Zen 3 es caché de víctimas —solo guarda lo que se expulsa de la L2—,
  así que recorrer 48 de sus 96 MB al azar da 66 ns donde tiene que dar 12. Con
  4, 8 y 16 MB salen 11,9, 12,0 y 13,2: el escalón está muy por debajo de la
  mitad, y el bloque lleva además un tope absoluto y no solo una fracción.
- **Perseguir punteros por cientos de megas sin pedir páginas grandes**: el TLB
  de datos guarda unas 2000 traducciones y 288 MB en páginas de 4 KB son 73728,
  así que cada acceso pagaba también un recorrido de tablas. `madvise` con
  `MADV_HUGEPAGE` baja de 94,7 a 82,1 ns, y para que el kernel pueda juntarlas
  el bloque tiene que estar alineado a 2 MB, que es por lo que se pide con
  `mmap` en vez de con un búfer de ctypes.
- **Medir un bloque más pequeño que el coste de pedirlo**: una llamada por
  ctypes cuesta 570 ns. En 32 KB —el tamaño de una L1— eso es casi todo el
  tiempo, así que la cifra hablaría de ctypes y no del equipo. Desde un mega
  baja al 2 %, y de ahí para arriba se mide. La L1 y la L2 se quedan sin medir
  y se dice, en vez de dar un número que parece bueno.
- **Suponer dos canales de memoria para calcular el teórico**: es la mitad de
  las veces falso y el porcentaje saldría al doble. Sin saber los canales no se
  calcula, que es la misma regla que ya valía para el aviso de al lado.
- **Redondear a la centena una velocidad de memoria**: los grados no van de cien
  en cien. El tCK del SPD viene en picosegundos enteros, así que la división no
  cae redonda —un DDR4-2133 guarda 938 ps y `2000000/938` da 2132,2— y
  redondeando a la centena salían once de los veintiocho grados conocidos mal:
  DDR4-2666 se convertía en «2700 MT/s», que no existe. Y no era solo feo: con
  el catalogado en 2700 y la BIOS poniendo 2667, el módulo parecía ir por
  debajo de lo suyo y encendía el aviso. Todas las velocidades que existen son
  múltiplos de 200/3 MT/s, en las tres generaciones y también en los XMP,
  porque el reloj de referencia va en tercios; se busca el más cercano y se
  trunca, que es como los nombra JEDEC. La cuenta va en enteros —`n * 200 // 3`—
  para que el truncado no dependa de cómo caiga un flotante. La fórmula estaba
  copiada tres veces y por eso el fallo era el mismo en las tres.
- **Tapar con un margen un número que está mal de origen**: al aviso de
  velocidad se le puso primero una tolerancia del 1 % para el redondeo del
  firmware, y no bastaba. El catalogado salía 2700 contra un 2667 real, que es
  un 1,2 %, así que se colaba igual. El margen estaba bien pero el problema no
  era la comparación: era el número de partida. Un margen que hay que ensanchar
  para que deje de fallar está tapando otra cosa.
- **Enseñar el localizador del firmware como si fuera un título**:
  «Controller0-ChannelA» son tres datos pegados sin espacios, y cada fabricante
  lo escribe a su manera —«DIMM_A1», «ChannelA-DIMM0»—, así que la misma
  pestaña se veía distinta en cada equipo. Con cuatro zócalos el nombre además
  se repite entre canales y salían dos «DIMM 0». Lo que se enseña es el mínimo
  que distingue un zócalo de otro en ese equipo, y lo que no se reconoce se
  deja crudo: inventarse una posición a partir de algo que no se entiende es
  peor que enseñar lo que puso el firmware.
- **Titular con un número que no es el que parece**: sin permisos las tarjetas
  de memoria salían como «Zócalo 0» y «Zócalo 2» mientras el subtítulo de dos
  líneas más arriba admitía que «el zócalo y la capacidad necesitan permisos».
  Ese número es la dirección del chip en el bus i2c —0x50 es 0 y 0x52 es 2—, no
  la posición en la placa, así que encima hacía pensar que el zócalo 1 estaba
  libre. Numerados por orden de lectura no afirman nada, y la dirección se va
  al tooltip, donde no se confunde con un zócalo.

<a id="pmu"></a>

## Contadores del kernel (PMU de perf)

- **Fiarse de un contador porque su suma cuadre**: los cinco del IMC de un
  Comet Lake encajan entre sí al 99,8 % —`ia + gt + io` es `reads + writes`
  visto por origen en vez de por dirección—, y de los tres de origen solo uno
  se sostiene. `ia_requests` clava los diez GiB que movieron los núcleos;
  `io_requests` marca 0,93 GiB/s idénticos en reposo y con la memoria a tope,
  que no es lo que hace un contador de tráfico; y `gt_requests` marca 4,6 GiB/s
  con una sola pantalla de 1080p conectada, diez veces lo que puede mover su
  refresco. Que el reparto sume dice que está completo, no que las etiquetas
  sean ciertas, y los dos que no se sostienen no se pintan.
- **Dar por sabida la unidad de un contador del kernel y leer solo su escala**:
  son dos datos y sysfs publica los dos, `.scale` y `.unit`. La escala sola no
  dice de qué es factor, así que multiplicar por un mega lo que viniera en otra
  cosa no daría un error: daría una cifra creíble. Se comprueba que ponga
  «MiB» y, si algún día pone otra cosa, no se convierte.
- **Un tope de descriptores que recorta sin que se note**: el ayudante abre un
  número máximo de contadores, y en la gráfica eso se ve —falta un motor—
  pero en el controlador de memoria no, porque los canales se suman: en un
  servidor con más canales de los que caben, el total sale bajo y con toda la
  pinta de ser correcto. El ayudante avisa de que la lista se quedó corta y
  entonces no se publica nada.
- **Dar por sabido cómo un PMU escribe sus eventos**: i915 los publica como
  `config=0x2000` y RAPL como `event=0x04`, que no es lo mismo. Cada PMU dice
  en `format/` en qué bits de `config` va cada campo (`event -> config:0-7`).
  Sin mirarlo, `energy-gpu` no se abre.

<a id="graficas"></a>

## Gráficas y pantallas

- **Dar por hecho que la gráfica `N` es el nodo `cardN`**: con una sola tarjeta
  dedicada el kernel la numera `card1` y no hay `card0`. Hay que guardarse el
  nombre del nodo.
- **Leer `pp_dpm_sclk` como una tabla DPM**: en RDNA3 y RDNA4 son tres líneas
  —mínimo, actual y máximo— y la primera llega como `S:` en vez de un número
  cuando la GPU está en reposo profundo.
- **Creerse el `enabled` y el `dpms` de los conectores DRM**: describen el
  modeset del kernel. Con un compositor Wayland al mando dicen «disabled» y
  «Off» de pantallas que están encendidas delante de uno.
- **Dar por perdida una gráfica porque su driver no diga nada**: con
  `simple-framebuffer` —el respaldo que pone el kernel al arrancar con
  nomodeset o sin driver instalado— la ficha salía entera a guiones, sin
  siquiera el nombre de la tarjeta. Ese driver cuelga de un dispositivo de
  plataforma y no de PCI, pero el bus sí la enumera aunque nadie sepa
  hablarle: de ahí salen la marca, el modelo y el enlace.
- **Dar una fila a cada conector vacío**: un MacBook Air de once pulgadas
  enseñaba cuatro filas seguidas con los seis campos a guiones —DP-1, DP-2,
  HDMI-A-1, HDMI-A-2— y solo la quinta, su pantalla, con datos. Son salidas
  que el chip expone y esa carcasa no trae. Van juntas en una línea.
- **Fiarse de `pci.ids` para el modelo exacto**: `7550` es «Radeon RX
  9070/9070 XT/9070 GRE», tres tarjetas. Quien desambigua es la línea de
  subsistema del propio fichero, y si no la hay, Vulkan.
- **Leer el enlace PCIe en el nodo de la gráfica**: las tarjetas modernas traen
  un conmutador dentro, y su lado interno negocia a la velocidad del chip
  aunque el puerto de la placa no dé para tanto. Una RX 9070 XT en una X570
  decía «PCIe 5.0» en una placa que no lo tiene. Vale el eslabón más lento de
  la cadena hasta el puerto raíz.
- **Enseñar el modo preferido del EDID como si fuera el máximo**: un OLED de
  240 Hz declara 60 como preferido. El rango real está en el descriptor 0xFD, y
  por encima de 255 Hz hay que sumarle unos bits de acarreo. Pero ese
  descriptor es opcional y los paneles de portátil casi nunca lo traen: sin
  respaldo, el eDP de un ThinkPad salía sin refresco teniendo el dato en su
  temporización detallada. Cuando no hay rango, el nativo es lo único que hay.
- **Confundir el reloj de la memoria de vídeo con su tasa de datos**: una GDDR6
  a 1258 MHz mueve 20 Gbps, dieciséis transferencias por ciclo. Los dos números
  son ciertos y hay que enseñar los dos.
- **Leer `gpu_metrics` sin mirar su versión**: el formato ha cambiado varias
  veces y no siempre añadiendo al final. Interpretar una v1.4 con las
  posiciones de una v1.3 no falla, devuelve cifras creíbles y equivocadas. Cada
  versión tiene su tabla de posiciones o se descarta entera.
- **Buscar el consumo de una iGPU Intel en `/sys/class/powercap`**: ahí están
  `package-0`, `core`, `uncore` y `dram`, y ninguno es la gráfica. El `uncore`
  es el falso amigo: se queda clavado en 3,2 W mientras el motor gráfico va de
  350 a 1050 MHz. El plano de la gráfica es RAPL PP1 y en estos Intel solo
  asoma por el PMU de perf, como evento `energy-gpu`. Contrastado contra
  `intel_gpu_top`, que enseña la misma cifra.
- **Juntar decodificar y codificar en un «soporta AV1»**: casi todas las
  tarjetas modernas lo leen y muy pocas lo escriben, así que esa frase sería
  falsa la mitad de las veces. Van en dos columnas.
- **Confundir el reposo con lo contrario del uso**: entre trabajar y dormir
  hay un término medio —encendida y sin trabajo— que gasta y que no cuenta
  como RC6. Un 40 % de uso no implica un 60 % de reposo.
- **Colgarle a la gráfica el ancho de banda del IMC**: `intel_gpu_top` lo
  enseña junto a la GPU porque en una integrada la RAM del sistema hace de
  VRAM, pero es el controlador de memoria entero, con el tráfico de la CPU
  dentro. Su sitio es la página de Memoria.
- **Contar en unidades de cómputo lo que cada fabricante cuenta a su manera**:
  64 CU de AMD y 2048 núcleos CUDA de NVIDIA no son la misma unidad, y bajo la
  misma etiqueta parece que una tarjeta tiene treinta veces más que la otra.
- **Llenar con lo que cuenta una API un campo que describe el silicio**: las
  «unidades de cómputo» de OpenCL son las de su modelo de programación, no las
  del chip. En una Intel son los subslices —5 en una Iris Xe de 80 EU, que
  agrupa dieciséis— y en una NVIDIA los multiprocesadores —16 en una RTX 3050
  de 2048 núcleos, 58 en una RTX 4080 Laptop de 7424—. Puestas en
  `compute_units`, `render` les pega la etiqueta del fabricante y salen «5 EU»
  y «16 núcleos CUDA»: el número no es inventado y la frase es falsa. Y como
  `GpuApis` corre justo detrás de `DrmGpus`, mucho antes que NVML y que el
  ioctl de i915, ocupaba el campo y los que sí cuentan el silicio ya no lo
  pisaban —solo escriben lo que está vacío—, así que el arreglo de
  `_nucleos_cuda` llevaba escrito desde agosto sin llegar a aplicarse nunca.
  Ese campo lo llena quien cuenta transistores: el ioctl de amdgpu, NVML y el
  de i915. La cifra de OpenCL no se pierde, vive en su renglón de la tabla de
  bibliotecas, que es donde se entiende de qué habla. En AMD las dos coinciden,
  y por eso la máquina de casa no lo enseñaba.
- **Enseñar que algo recorta sin decir cuánto lleva**: medio segundo de límite
  de potencia en un cambio de escena es el funcionamiento normal de cualquier
  tarjeta; un minuto contra el límite térmico es un problema de refrigeración.
  El motivo es el mismo y la conclusión es la contraria, así que hace falta la
  duración, y por debajo de un segundo y medio no se dice nada.
- **Callarse igual ante un dato que no existe y ante uno que no se sabe leer**:
  las versiones de `gpu_metrics` que no están en la tabla se descartan a
  propósito, y hasta ahora acababan en el mismo silencio que no tener
  telemetría. En una APU —que publica las 2.x— los motivos de recorte y los
  voltajes salían vacíos sin nada que lo explicara. Se descarta igual, pero se
  dice cuál es y se lleva al informe, que es de donde puede salir su tabla de
  posiciones sin tener la pieza delante.
- **Tomar por VRAM el montón de memoria que declara Vulkan**: en una integrada
  ese montón es la RAM del sistema. Una Iris Xe declaraba 11.5 GB en un equipo
  con 15.3 de RAM, y puesto como «Total» salía en la insignia y en la imagen de
  compartir como «Iris Xe · 11.5 GB», que se lee como una tarjeta con once giga
  y medio de VRAM. El modelo ya tenía el campo donde va —la GTT, que es RAM
  prestada— y hasta el comentario que dice por qué va aparte. Con `integrated`
  a None no se toca: quitarle la memoria a una dedicada es peor.
- **Escribir una etiqueta al revés de su propia explicación**: la fila de la
  GTT se llamaba «Prestada al sistema» y su ayuda decía «RAM del equipo que el
  driver le presta a la tarjeta», que es lo contrario. Pasó desapercibido
  mientras era una fila entre diez; en una integrada, donde es la única que
  queda, se lee de golpe.
- **Creer que los códigos de vídeo del EDID describen el panel**: los VIC de
  CTA-861 son códigos de TV y HDMI, y no llegan a 1440p a 240 Hz. El AORUS
  FO27Q2 declara como mucho 1080p a 120 por ahí, y sus 240 Hz solo están en el
  descriptor de rangos 0xFD. Lo que sí aportan las extensiones y no está en
  ningún otro sitio es el HDR y los espacios de color.
- **Buscar los datos de i915 en `card0/device/`**: ese es el enlace al nodo
  PCI, e Intel publica las frecuencias del motor gráfico en el nodo DRM, un
  nivel más arriba. Encima cambiaron de sitio en el kernel 6.2, que las metió
  en `gt/gt0/` con prefijo `rps_` sin quitar las viejas. Hay que mirar en las
  cuatro rutas: una UHD 630 salía con todos los relojes en blanco.
- **Decidir si una gráfica es integrada por si tiene VRAM**: no leerla no es
  no tenerla. Con nouveau no se lee ninguna, y una GTX 1050 Mobile —una
  tarjeta dedicada— salía marcada como integrada; al revés, una APU reserva
  un trozo de la RAM del sistema y parecía tener memoria propia. En AMD lo
  dice el bit FUSION del ioctl, la integrada de Intel vive en 0000:00:02.0, y
  una NVIDIA en un PC nunca lo es. Lo que no se pueda decidir se queda en
  `None`.
- **Colgar OpenGL y OpenCL de la tarjeta que el kernel marca como principal**:
  no publican su nodo PCI, pero sí dicen quién contesta. En un portátil
  híbrido la principal es la integrada, porque lleva la pantalla, mientras
  quien responde es la dedicada: la ficha de una Radeon 740M salía con «GLSL
  4.60 NVIDIA» y con 16 unidades de cómputo que eran los 16 SM de la RTX 3050
  de al lado. Se casa por el fabricante que aparece en el texto, y lo que no
  se pueda atribuir no se atribuye.

- **Leer el uso de una AMD una vez por muestra**: `gpu_busy_percent`,
  `mem_busy_percent` y `vcn_busy_percent` son lo que midió el firmware en
  sus últimos milisegundos. En la RX 9070 XT, una lectura suelta salta
  entre 59 y 100 con la gráfica haciendo lo mismo, y la ficha «Uso» bajaba
  de 85 a 42 jugando. MangoHud, que hace la media de muchas lecturas, daba
  80-86. Se leen cuatro veces por segundo entre muestra y muestra y la
  foto lleva la media (`GpuState.between_samples`). A diez por segundo daba
  71-87; a cuatro, la mediana es la misma y cuesta la mitad (0,24 puntos de
  un núcleo frente a 0,56). MangoHud
  solo escribe su registro si el programa acaba solo (`vkcube --c N`): con
  `timeout` lo mata antes.

<a id="discos"></a>

## Discos

- **Dar el enlace PCIe de un disco SATA**: quien negocia es su controladora, y
  la comparte con los demás discos del cable. Solo los NVMe tienen enlace
  propio.
- **Leer el registro de salud de un disco y no enseñar ni una línea**:
  `critical_warning` es el campo por el que un NVMe avisa de que va camino de
  perder datos —reserva agotada, modo solo lectura, respaldo fallido— y estaba
  ahí sin que lo mirara nadie. Los apagones bruscos, en cambio, no son un
  aviso: cuentan cortes de luz y botones de reinicio.
- **Quedarse con el fabricante que publica sysfs en un disco**: dice «ATA» en
  SATA y nada en NVMe. El nombre solo está dentro del modelo, y hay que
  buscar el prefijo más largo primero: «wd_black» antes que «wd », «sk hynix»
  antes que «hynix».
- **Restarle lo ocupado a la capacidad para saber lo libre**: eso da por
  montado todo el disco. Con un Windows al lado, 570 GB de otra partición se
  contaban como espacio libre, y el recuadro de al lado —que suma el hueco de
  las particiones montadas— decía otra cifra en la misma pantalla. Lo que no
  está montado no está libre y se dice aparte.

<a id="red"></a>

## Red

- **Dar por parada una interfaz cuyo `operstate` no dice «up»**: el bucle local
  y los túneles responden «unknown» porque su driver no informa del enlace.
- **Decir «sin cable» de lo que no lleva cable**: un puente de máquinas
  virtuales apagado está parado, no desenchufado.
- **Medir el tráfico de red en potencias de 1024**: en redes la convención es
  decimal. Con 1024 los mismos datos salen 976 Mb/s donde un test de velocidad
  dice 931, y no hay forma de explicar la diferencia.

<a id="bateria"></a>

## Batería

- **Leer el mismo aparato por dos caminos sin que ninguno lo sepa**: en un
  portátil, la batería y los puertos USB-C cuelgan a la vez de `hwmon` y de
  `/sys/class/power_supply`, con el mismo nombre de chip y los mismos valores.
  Un ThinkPad enseñaba «Alimentación · BAT0» y «Batería» como dos aparatos
  distintos con idénticas cifras, y los dos USB-C repetidos: seis sensores de
  cincuenta y cinco contados dos veces. Se queda `power_supply`, que es donde
  el kernel dice qué es cada archivo —sale «Tensión» y no «Tensión 0»—, y se
  comprueba que publique algo antes de descartar el de hwmon: si no, saltárselo
  perdería el dato en vez de deduplicarlo.
- **Enseñar un rango entero como si fuera un límite**: un ThinkPad sin tope de
  carga configurado publica 0 y 100, que es justamente no tener tope, y la
  ficha decía «empieza a cargar por debajo de 0 %, deja de cargar en 100 %»
  como si alguien lo hubiera puesto. Un Dell con 50 y 90 sí lo tiene, y ahí el
  dato vale. Lo mismo con la autonomía: con la batería llena salía «— · a 0.0 W
  de ahora», que es un ritmo de nada para una cuenta atrás que no existe.
- **Creer que todo lo que dice ser una batería es la del equipo**:
  `/sys/class/power_supply` mezcla el cargador, los puertos USB-C y cualquier
  periférico con pila, y el ratón Logitech publica `hidpp_battery_0` con
  `type=Battery`. Con mirar el tipo, este sobremesa —que no tiene batería
  ninguna— declaraba una, y habría salido una ficha de batería en una torre.
  Quien lo distingue es `scope`: los periféricos dicen «Device» y la del equipo
  «System», o nada en los portátiles antiguos.
- **Dar la capacidad de una batería en miliamperios-hora**: el kernel la
  publica en `charge_*` (µAh) o en `energy_*` (µWh) según el firmware, y los
  mAh no se pueden comparar entre equipos sin saber el voltaje de la celda:
  4000 mAh a 7,6 V y 4000 mAh a 11,4 V son baterías muy distintas. Todo entra
  en vatios-hora, y para convertir manda el voltaje de diseño y no el de ahora,
  que sube y baja con la carga y daría otra capacidad en cada muestreo.

<a id="placa"></a>

## Placa base y sistema

- **Titular la ficha de la placa con la placa en un portátil**: un IdeaPad 330
  lleva dentro una «LNVNB161216», que no le dice nada a nadie. Ahí manda el
  nombre del equipo, que es el de la pegatina; en un sobremesa es al revés,
  porque la placa es lo que se compró.
- **Leer `/etc/os-release` mirando solo las comillas dobles**: el formato es
  el de un fragmento de shell y las simples valen igual. Gentoo las usa, y su
  nombre aparecía en la ventana como `'Gentoo Linux'`, con las comillas.
- **Dar por hecho que el kernel lo compiló gcc**: CachyOS usa clang, y el
  respaldo del que no casaba devolvía «Linux version 6.18.35-gentoo», que es
  repetir el kernel en el renglón de al lado.
- **Preguntar por el chasis para saber si el equipo tiene nombre**: eran dos
  cosas distintas y la aproximación falló dos veces. `Board.display_name`
  titulaba con el nombre del equipo si `chassis_is_portable`, así que un
  IdeaPad 330 se arregló añadiendo portátiles y un ThinkCentre M80q volvió a
  salir como «Lenovo 316C» por ser un Mini PC. Ampliar la lista otra vez
  tampoco lo cerraba: los sobremesas de marca —ThinkCentre, OptiPlex,
  EliteDesk— suelen declararse «Desktop» a secas. La frontera nunca fue
  portátil contra sobremesa, sino placa con nombre comercial contra código
  interno: una X570 AORUS ELITE se compró por su nombre y una «316C» no la ha
  visto nadie. Y eso se responde con el propio dato, sin adivinar: una placa
  que se vende suelta deja en la versión del sistema un «1.0» o un relleno de
  fábrica, y un equipo de marca deja su nombre. Lo que protege al sobremesa
  montado es justamente el caso vacío: sin nombre de equipo manda la placa, que
  si no saldría «MSI 1.0».
- **Mirar `system_name` para eso mismo**: parece el sitio natural y es el peor
  de los tres. Trae el código de producto en un OEM —«11DQS0KM00»— y el de la
  propia placa en una suelta —«MS-7D23»—, así que las dos veces empeora lo que
  ya había. HP y Dell sí ponen ahí el nombre bueno, pero sin un informe de uno
  delante no hay forma de distinguir los dos casos, y adivinarlo rompe lo que
  funciona. Queda escrito en el código para cuando aparezca uno.
- **Arreglar el nombre de un equipo sin poder ver de dónde salía**: el informe
  no llevaba ni uno de los campos DMI del sistema, así que un «me sale un
  nombre raro» obligaba a pedir un `dmidecode` aparte. Los cinco campos y el
  chasis van en crudo, que es lo que convierte «esto puede volver a pasar» en
  «si pasa, se ve en un paso». Con cadenas que escribe cada fabricante como
  quiere, poder diagnosticar vale más que intentar acertar siempre.

<a id="sensores"></a>

## Sensores y hwmon

- **Leer solo `*_input` en hwmon**: amdgpu publica el consumo como
  `power1_average`. Sin mirar ese sufijo, la gráfica se quedaba sin vatios.
- **Redondear todos los sensores igual**: un voltaje a un decimal deja de ser
  un voltaje. 0,845 V se convierte en 0,8 y ya no dice nada.
- **Dejar que el árbol de sensores salga en el orden del kernel**: es el de
  los directorios de hwmon, un número arbitrario que cambia entre arranques.
  El procesador puede acabar debajo de la tarjeta de red. Se ordenan como se
  buscan: procesador, placa, memoria, gráficas, discos, red.
- **Y volver a deducir por el nombre lo que el proveedor ya había resuelto**:
  ese orden estuvo un año escrito y sin cumplirse. `hwmon.device_for` decide
  que un chip es de la CPU justamente para ponerle el nombre del procesador, y
  tiraba esa decisión; el árbol la reconstruía comparando ese nombre con otro
  compuesto en otro sitio, y no casaba ninguno: «Intel Core i5-10400» contra la
  cadena entera de CPUID, «ATA KIOXIA-EXCERIA S» contra el modelo sin el
  prefijo del bus. Los dos caían al cajón de la placa, y entre iguales manda el
  alfabeto, así que el árbol abría por el disco. **Solo se ve en Intel**, y por
  eso no lo vio nadie: `short_brand` deja «AMD Ryzen 7 5800X3D» igual que
  viene y a un Intel le quita el «(R)», el «(TM)» y el « CPU @ 2.90GHz». En la
  máquina de casa casaba. La clase la lleva escrita cada `Sensor` y no se
  adivina; además la mitad de esos nombres se traducen, así que ninguna
  comparación contra un literal español podía funcionar en inglés.
- **Llevar el voltaje del núcleo al árbol de sensores**: es un voltaje real y
  parece que le toca, pero el árbol guarda mínimo, máximo y media, y eso
  promete una medida continua. Lo que se lee por MSR es el VID del P-state
  activo, que cambia a saltos —1,100, 1,000 y 0,900 en este 5800X3D, que son
  sus tres escalones—, así que su historial saldría en escalera y el máximo
  sería siempre el mismo. Se queda en la ficha de CPU. Al árbol solo van
  voltajes que se midan de verdad; el del regulador de la placa lo sería, y ese
  es justo el que no se puede atribuir al procesador porque el driver no
  etiqueta sus canales.
- **Subir por sysfs hasta encontrar lo que se busca**: el sensor de una
  tarjeta de red cuelga del bus MDIO, así que hay que subir; pero subiendo a
  ciegas se llega a `/sys/devices/virtual`, que también tiene un `net/` dentro
  —con el bucle local— y un ThinkPad enseñaba «Red (lo)» a 34 °C. No vale
  parar donde se acaben los dispositivos: el propio bus MDIO es un contenedor
  sin `uevent` y está en medio del camino bueno. Lo que se descarta es la rama
  virtual.
- **Avisar de un umbral en algo que se enchufa por fuera**: un puerto USB-C
  sin nada conectado marca 0 V, y eso queda por debajo de cualquier mínimo que
  declare el chip. Cero ahí no es una avería: es que no hay nada puesto. Lo
  mismo que ya valía para los ventiladores.
- **Fiarse de los umbrales que publica un chip sin mirarlos**: devuelven de
  fábrica los campos que nadie configuró. Un nct6798 da `min = 127` y
  `max = 127` en sus seis temperaturas, y con eso una placa a 34 °C queda «por
  debajo del mínimo»: seis avisos falsos de golpe. Un NVMe da 65261.85 °C, que
  son 0xFFFF en kelvin. Se descarta lo implausible y los pares donde el mínimo
  supera al máximo, y de los ventiladores no se avisa nunca: ir a tope bajo
  carga es lo normal y estar parado en reposo también.
- **Esperar que el hardware publique sus límites**: de 28 temperaturas de un
  equipo corriente, solo 7 traen umbral, y el procesador no suele traer
  ninguno. Sin estimar nada, el aviso no salta donde más falta hace. Se
  estiman por chip conocido (k10temp, coretemp, nvme, drivetemp), del lado
  prudente, y se dice en la ventana que son estimados.

- **Dar por bueno el dominio `core` de RAPL en cualquier procesador**: en
  Intel es PP0, la suma de los núcleos. En AMD el kernel lo saca del contador
  de energía de cada núcleo y lo lee en uno solo, el primero, y sale con el
  mismo nombre. En el 5800X3D decía «núcleos 3,7 W» con el paquete en 64 W.
  Se distingue cargando un hilo cada vez: el dominio sube con el núcleo 0 y no
  se mueve con ningún otro. Donde eso pasa no se enseña, y se dice.

<a id="benchmark"></a>

## Benchmark y puntuación


- **Comprobar que una carga suelta el GIL midiendo cuánto rinde con N hilos**:
  mide también el hardware. Con cuatro hilos lógicos en dos núcleos con SMT,
  que es lo que da un runner de GitHub, cuatro hilos rinden como 2,4
  núcleos, y con la máquina compartida `compresion_dura` dio ×1,76 contra un
  umbral de ×1,8: falló tres veces en el CI sin que la carga cambiara. Lo
  que distingue «suelta el GIL» es el tiempo de CPU sumado de los hilos
  entre el tiempo de reloj: ×1 con el GIL atrapado (los demás esperan sin
  gastar CPU), ×N si no, haya SMT o no. Medido en el i5-10400 con `taskset`:
  ×3,9 en 0,6,1,7 y en 0,1,2,3, y ×1,0 con una carga en Python puro.
- **Atar la medida de un hilo al «mejor» núcleo**: se hizo para quitar ruido
  —un hilo que salta de núcleo tira la caché— y hacía lo contrario. Medido
  alternando: atarlo cuesta un 40 % en la compresión pesada y un 11 % en la
  derivación de clave, y la dispersión entre repeticiones sale igual o peor
  que dejándolo suelto. Como la afinidad solo se fijaba al medir con un hilo,
  esa penalización caía siempre en la misma cifra y la escala entre uno y
  todos salía en catorce veces con ocho núcleos. Sin atar nada: ocho veces,
  como las demás cargas.
- **Compilar la carga del benchmark al vuelo**: funciona desde el código fuente
  y no dentro de un AppImage, que no lleva compilador. `zlib` y `hashlib` dan
  la misma estabilidad y su bucle también está en C, ya compilado.
- **Usar SHA-256 para medir**: `sha_ni` la acelera y a SHA-512 no, así que un
  chip que la tenga sale inflado y deja de poder compararse con uno que no.
- **Dar por bueno lo que mide la primera vuelta de una carga**: la compresión
  pesada daba 1 780 operaciones por segundo la primera vez que corría en un
  proceso y 2 950 a partir de la segunda, un 65 % más, sin que cambiara nada
  del equipo. Lo que se paga ahí es del asignador: LZMA pedía un búfer holgado
  en cada llamada y glibc lo servía con `mmap` hasta subir su umbral por su
  cuenta. Y como el orden es un hilo primero y todos después, ese arranque lo
  pagaba siempre la medida de un hilo. Se arregla dejando rodar la carga unas
  centésimas antes de contar (`_rodar_en_vacio`); con ochenta vueltas basta.
  Ojo: por sí solo no bastaba, hacía falta quitar además la afinidad, y por
  eso costó encontrarlo —cada arreglo por separado parecía no servir—. Con
  bzip2, que es la carga desde la escala v4, el mismo efecto es del 2,7 %.
- **Achacar al calor una dispersión que no es térmica**: la puntuación
  multihilo se movía un 4,7 % entre repeticiones del mismo equipo sin tocar
  nada, y el calor era la explicación evidente. No lo era. Enfriando hasta los
  mismos grados antes de cada repetición seguía en un 4,2 %, así que la prueba
  que parecía confirmarlo era la que había que hacer para descartarlo. Era una
  sola carga: la compresión pesada con LZMA, que alterna entre 25 800 y 32 500
  operaciones por segundo —un 26 %— según le llueva o no una tormenta de
  fallos de página, 280 000 por segundo, de los búferes que pide en cada
  llamada. Quitándola, las otras cuatro dispersan un 0,29 %. Lo térmico existe
  y es de segundo orden: 1,74 % seguidas contra 0,29 % enfriando. El estado se
  decide por proceso y dentro de una medida es plano, así que alargarla no lo
  promedia: lo hereda entero.
- **Creerse una correlación sin mirar hacia dónde apunta la flecha**: la
  velocidad de esa misma carga correlacionaba con la temperatura a r = 0,98, y
  la lectura obvia —el calor la frena— era justo la contraria de lo que
  pasaba. El modo rápido corre a menos GHz que el lento (4,29 contra 4,34) y
  calienta más porque hace más trabajo por ciclo. La temperatura era la
  consecuencia, no la causa, y con r = 0,98 nadie lo habría dudado.
- **Medir la carga de fondo solo antes de empezar**: `_carga_de_fondo` toma
  tres décimas y se acabó, y una prueba de quince segundos por carga dura dos
  minutos y medio. Quien la lanzaba y se iba a hacer otra cosa, o tenía una
  actualización en marcha sin saberlo, salía con «0 % de carga de fondo» y una
  cifra baja sin explicación en ninguna parte. Ahora el vigilante muestrea
  también mientras se mide, y se guarda el pico y no la media: algo que se
  despierta a mitad se diluye promediado entre dos minutos.
- **Que una herramienta reescriba entero un archivo que no llena ella sola**:
  `medir_referencia.py` volcaba `scores.json` con lo que acababa de medir, y
  las medidas de otros equipos que va acumulando `anadir_puntuacion.py` vivían
  en ese mismo archivo. Remedir la escala las borraba todas, sin decirlo. No
  llegó a costar nada porque cuando se vio todavía no había ninguna guardada.
- **Buscar el ruido de fuera sin medir el de dentro**: con el navegador y el
  chat abiertos, lo ajeno se llevaba un 2,4 % de la máquina, pero de forma
  intermitente, que es lo que se confunde con una deriva. `/proc/stat` a secas
  no sirve mientras la prueba ocupa el equipo entero: lo que se busca es la
  resta, lo ocupado menos lo del propio proceso. Cerrar programas ayuda; poder
  demostrar que estaban cerrados es lo que deja concluir algo.
- **Sumar operaciones por segundo de cargas distintas para hacer una
  puntuación**: en un 5800X3D la compresión pesada da 28 494 op/s y la
  memoria 533, así que la primera pesaba el 82 % del total y las otras
  cuatro eran decoración. La cifra era, en la práctica, una sola carga.
  Cada una se divide por lo que da en la pieza patrón y así entran
  valiendo lo mismo.
- **Contar «operaciones» cuando una operación no es la misma cosa en dos
  máquinas**: la carga que recorre un bloque grande lo dimensiona con la
  caché de cada equipo —entre 64 y 192 MB—, y eso está bien para la carga y
  era veneno para la puntuación. Con el mismo ancho de banda real, un
  procesador con poca caché sacaba un **42,8 % más** solo por recorrer un
  bloque más pequeño; medido en la misma máquina cambiando únicamente el
  tamaño, las operaciones se multiplican por 3,14 y los bytes por segundo se
  quedan en ×1,05. Es el mismo error que el de la duración, con otro eje: lo
  que se compara tiene que ser trabajo, no vueltas de bucle. Ahora esa carga
  declara cuántos bytes recorre y se puntúa en bytes por segundo. Y de paso
  se descubrió que no medía lo que decía: con un bloque de 4 MB, que cabe de
  sobra en la caché, da lo mismo que con 384 —21 GB/s en los dos—, porque el
  cuello lo pone el cálculo del CRC y no la memoria (la RAM de esa pieza da
  48,5 GB/s medidos con `membench`). Por eso ya no se llama «Memoria» sino
  «Suma de verificación».
- **Medir el procesador con la biblioteca estándar mide la biblioteca**: las
  cinco cargas son `zlib`, `bz2` y `hashlib`, así que la cifra depende de qué
  trae cada distribución. La misma pieza da un **28 % menos** con la zlib
  clásica que con zlib-ng —medido alternando anfitrión y contenedor en la
  misma CPU y el mismo Python: ×2,75 en la compresión y ×4,07 en el CRC,
  mientras `hash` y `bz2` salían idénticos—, y el patrón está en el lado
  minoritario: CachyOS y Fedora traen zlib-ng; Debian, Ubuntu, Arch y
  openSUSE, la clásica. Peor aún, ese factor **no es una constante**:
  `libz.so.1` lleva dentro 344 instrucciones `vpclmul` y cuatro `cpuid`, o
  sea que elige ruta mirando el procesador, y la de 256 bits es de Ice Lake y
  Zen 3 en adelante. Por eso no bastaba con registrar la implementación de cada
  medida, que era el arreglo barato: desde la v6 esas tres no puntúan. Se
  siguen midiendo y enseñando con su biblioteca al lado —son buen diagnóstico,
  y son justamente las que delatan qué hay debajo—, pero no entran en una cifra
  que se compara entre equipos. Cuáles quedan y con qué medidas se decidió,
  en `score.PUNTUABLES`. **La salida buena sigue siendo un kernel propio en
  ensamblador**, reutilizando lo que `rawcpuid.py` ya hace para CPUID y
  `membench.py` para perseguir punteros: código que no cambia de una máquina
  a otra porque viaja dentro del programa. Iría **añadido a las cinco y no en
  su lugar**: las que hay miden trabajo real y eso también vale; lo que falta
  es una que mida solo la pieza. Se buscó sustituto en la biblioteca estándar
  y no lo hay: `bytes.translate` y `bytes.count` no sueltan el GIL (escalan
  ×1,0), `blake2b` sí lo suelta y es de CPython pero va a 0,6 GB/s contra los
  48,5 de la RAM, y `adler32` —que parecía el candidato porque da 48,2 GB/s—
  es aún peor, con un ×6,79 entre implementaciones.
- **La misma cuenta escrita en cuatro sitios**: `operations / seconds` vivía
  en `Medida`, en el historial, en `medir_referencia.py` y en un test. Tres de
  las cuatro estaban de acuerdo, y la que no —la de la escala— dejó la
  referencia en operaciones por segundo mientras las medidas ya iban en bytes:
  el cociente habría salido dos millones de veces mayor. Cada copia parecía
  correcta leyéndola sola, y no se vio hasta ejecutar la herramienta de verdad
  y mirar la cifra. Es la regla 1 —el formateo en un solo sitio— aplicada a
  las cuentas: la que decide qué se puntúa vive en `Medida` y en ningún otro
  lado. Son dos y no una a propósito —`per_second` es lo que escala con los
  hilos y lo que la interfaz etiqueta «op/s», `rate` es lo que se puntúa—, y
  fundirlas haría mentir a una de las dos. Hay un test que recorre el árbol de
  sintaxis de todo el repositorio y no deja escribir una quinta, con un límite
  que conviene saber: caza `m.operations / m.seconds` escrito así, y se le
  escapan formas triviales de lo mismo —pasar por una variable, `sum(…) / t`,
  `//`—.
- **Un estado intermedio que tapa tests es peor que uno que los rompe**: al
  subir `score.VERSION` a 5 sin haber regenerado todavía `scores.json`,
  `referencias()` devolvía vacío y `puntuar` contestaba `None` a todo. La
  suite pasaba entera, 1478 en verde, y varios tests de puntuación no estaban
  evaluando nada: el que comprueba que una prueba a la que le falta una carga
  no puntúa pasaba porque no puntuaba ninguna. En cuanto la tabla volvió a
  estar en la versión vigente, ese test empezó a mirar de verdad y cazó un
  `memoria/` que se había quedado sin renombrar. Por eso `VERSION` y
  `scores.json` van en el mismo commit: desparejados, la suite miente en
  verde, que es la peor forma de mentir.
- **Comparar dos pruebas de distinta duración**: tres segundos cogen el
  turbo entero y treinta lo pierden a mitad, así que la misma pieza da dos
  cifras muy distintas. Poder elegir la duración es lo que permite
  preguntar cuánto aguanta un equipo; puntuar con cualquiera de ellas es
  decir que uno es más lento cuando lo único que cambió fue la pregunta.
  Por eso solo se **comparan** con otros equipos las de quince segundos; la
  cifra se calcula para cualquier duración (`puntuar` no la mira, a
  propósito), y lo que decide si se pone al lado de otra máquina es
  `comparable`.
- **Comparar temperaturas de dos momentos sin saber la ambiente**: ocho grados
  entre febrero y agosto son normales y salen iguales que ocho de pasta seca.
  Ningún sensor del equipo mide la habitación. Lo que sí se puede comparar es
  la misma carga con la misma puntuación, y aun así el aviso dice lo que ve
  —«más caliente para el mismo trabajo»— sin diagnosticar la causa.
- **Meter una carga de benchmark sin comprobar que reparte**: `base64` escala
  ×1.0 con dieciséis hilos y la de coma flotante también. Si no suelta el GIL
  no mide el procesador, mide el candado, y hay un test que lo ejecuta de
  verdad para cada carga en vez de fiarse.

<a id="interfaz"></a>

## Interfaz y Qt

- **Preguntar a Qt por `sizeHint` justo después de añadir widgets**: devuelve
  el valor anterior. O se calcula a mano, o se deja pasar un ciclo de eventos.
- **`sizeHintForColumn` en un árbol**: solo mira las filas de primer nivel.
  Hay que medir el texto recorriendo los hijos.
- **Estirar la primera columna de una tabla**: en pantalla completa manda las
  cifras a un palmo del nombre. El hueco sobrante va al final.
- **Dibujar flechas con bordes CSS en Qt**: salen cuadrados. Hay que darle una
  imagen; se generan en tiempo de ejecución en `ui/theme.py`.
- **Medir en píxeles lo que va dentro de algo que se pinta a mano**: la caja
  del texto de cada núcleo estaba fija en 12 px. Con la letra al máximo las
  letras medían 18 y se comían la gráfica por arriba dejando un hueco por
  abajo. Lo de dentro se mide contra la altura de línea de la fuente, que es
  lo único que crece cuando alguien pide letra grande.
- **Volver a medir una columna con la tabla recién montada**: el fallo del
  árbol de sensores, repetido en `Table`. «Uso» se quedaba con el ancho de su
  cabecera y enseñaba «12…» en vez de «12.4 %». Se mide el texto que de verdad
  lleva y se ensancha; nunca se encoge.
- **Pintar todos los avisos del mismo color**: la banda de `Notice` era ámbar
  para todo, así que «esta gráfica no trae sensor de temperatura» —que no va a
  cambiar nunca— se leía igual de urgente que algo que sí se arregla. Va por
  tono: azul lo accionable (`ROOT`, `DRIVER`, `DATABASE`), gris lo que es así
  y ya está (`HARDWARE`, `PLATFORM`), rojo lo que es un fallo nuestro.
- **Dar a lo accionable el color de la marca**: lo accionable y sus candados
  fueron ámbar hasta que el ámbar pasó a ser el acento y el color del logo.
  Con los dos iguales, la banda de un aviso, un candado y el botón principal
  eran del mismo color, y un aviso del color de un botón no avisa de nada. El
  ámbar es la marca y lo que se puede pulsar; lo que falta y tiene arreglo va
  en azul (`Palette.info`, tono `action`). El amarillo (`warn`) se queda para
  lo que es un estado del equipo y no una tarea del usuario: un disco que
  avisa, una lectura cerca de su límite. El interruptor de Ajustes nació
  azul porque «lo accionable» se leyó como «lo que se pulsa», y quedaba
  azul al lado de un botón principal ámbar. Encendido es una elección del
  usuario, como una casilla marcada: va en el acento. El azul es de lo que
  falta, no de los controles.
- **Bordear un control con el mismo filo que una tarjeta**: `line` separa
  superficies que ya se distinguen por su tono, pero el relleno de un
  desplegable apenas se aparta de la tarjeta (1.1:1), así que su borde es lo
  único que dice dónde está. Con `line` quedaba en 1.2:1 en oscuro: en Ajustes
  el interruptor apagado y el contorno de los desplegables casi no se veían.
  Lo que dibuja un control en reposo va en `muted` (5.4:1 y 5.0:1), por
  encima del 3:1 de WCAG 1.4.11; lo vigila `tests/test_contraste.py`.
- **Explicar que hace falta un permiso sin poner el botón al lado**: el aviso
  de Gráficos decía «Requiere permisos» y el único botón estaba en Memoria y
  en Almacenamiento. Quien lee por qué falta un dato es quien quiere
  arreglarlo, así que el botón va dentro del propio aviso.
- **Escalar la tipografía y los márgenes al mismo ritmo**: quien pide letra
  grande quiere leer mejor, no que quepa la mitad. Los márgenes crecen a mitad
  de paso que el texto (`_escalar` en `ui/theme.py`).
- **Sacar la paleta con `theme.resolve` en vez de `theme.palette_for`**: la
  primera no aplica el color de acento elegido, así que el color llegaba a la
  hoja de estilos pero no a lo que se pinta a mano —gráficas, barras, matriz de
  núcleos— y el tema salía a medias.
- **Juntar un dato ausente con otro presente en el mismo renglón**: el
  ventilador salía como «—   (0.0 %)», que se lee como si faltara una cifra y
  sobrara otra. Las dos decían lo mismo: está parado.
- **Animar contra el intervalo que se pidió y no contra el que se cumple**:
  recorrer sysfs, hwmon y los discos lleva entre 330 y 450 ms, así que entre
  muestra y muestra pasan 1200 y no 1000. La animación llegaba al final y se
  quedaba parada esperando el dato: eso es lo que se ve como un tirón. El
  ritmo se mide sobre la marcha, con una media corrida para que un muestreo
  lento suelto no descoloque.
- **Un atajo de teclado que no aparece en ninguna parte**: no existe para
  quien no lo sabe. La barra de estado es donde se mira sin buscar.
- **Dar el respiro de una columna ensanchándola**: con el texto alineado a la
  derecha, ese hueco cae por la izquierda y la cifra sigue terminando pegada
  al borde, que es donde el árbol dibuja su marca de arrastre. El aire donde
  hace falta lo pone el relleno del propio renglón.
- **Tomar por un arrastre lo que estira Qt**: la última columna absorbe el
  sobrante, así que se redimensiona sola con la ventana y emite la misma señal
  que un arrastre. Con eso, maximizar una vez dejaba los anchos guardados como
  si alguien los hubiera puesto a mano y el árbol no volvía a ajustarse nunca.
- **Reajustar anchos en el `resizeEvent`**: cambiar los valores recalcula la
  altura del árbol, y eso es un resize. Una columna estrechada a mano volvía a
  estirarse sola en el muestreo siguiente.
- **Aplicar una preferencia solo cuando cambia**: el idioma se cargaba al
  tocarlo en Ajustes y no al arrancar, así que guardarlo y volver a abrir el
  programa devolvía la interfaz al español.
- **Declarar `color` en `QTreeWidget::item`**: pisa el que cada celda pide con
  `setForeground`, en silencio y sin error. Con él puesto no llegaba a la
  pantalla ni el rojo de un sensor pasado de vueltas ni el ámbar del que se
  acerca: el árbol salía entero del mismo gris. El color base lo pone el árbol
  al montar cada fila, no la hoja.
- **Probar un color renderizando el widget suelto**: fuera de la ventana no se
  pinta como dentro —el estilo no se aplica igual— y la prueba dice cosas que
  no pasan de verdad. Lo que se vigila es la causa: que la hoja no declare ese
  color.
- **Escribir el mismo relleno en la hoja de estilos y en quien mide**: se
  desincronizan. Al subirlo de 6 a 10 px solo en el CSS, las cifras cabían en
  la cuenta y no en la columna, y los relojes de núcleo salían «4374.4 …».
- **Mezclar dos colores linealmente**: el ojo no los ve así. Entre el blanco
  de las cifras y el ámbar, el primer tercio del recorrido no se distingue de
  nada: una CPU a 78 grados de 95 salía igual que una a 50.
- **Teñir solo el valor de ahora**: quien lanza una prueba de dos minutos va a
  mirar después, y para entonces la columna «Actual» ya se ha enfriado. Lo que
  sobrevive al pico es el máximo, y es el que hay que teñir también.
- **Teñir un valor por su fracción del umbral**: un procesador a 45 grados de
  90 no está «medio caliente», está bien. Si el color empieza en el cero es
  decoración; empezando a tres cuartos del límite, avisa.
- **Rellenar una rejilla con lo que quepa y ya**: dieciséis hilos salían doce
  arriba y cuatro abajo. Se elige el reparto con menos huecos en la última
  fila, y quitar columnas ensancha las celdas, así que hay suelo: el 60 % de
  lo que cabía.
- **Pintar «sin dato» con la tipografía de las cifras**: el guion a treinta y
  seis píxeles es una raya gruesa, y en una Intel con cuatro de los seis
  cuadros vacíos la fila entera parecía tachada.
- **Contestar con un guion a lo que no existe**: un guion dice «no lo sé», y en
  la ficha de una integrada eso era falso diez veces seguidas. No falta el tipo
  de memoria de una Iris Xe: es que no hay chip de memoria del que decirlo, y
  no lo va a haber. Salía con un dato de once en «Memoria de video» y dos de
  catorce en «Sensores», toda ella rayas. Son tres estados y no dos: hay dato,
  no lo sé —guion— y sé que no existe, que se esconde y se nombra al pie de su
  tarjeta, como ya se hacía con los conectores sin nada enchufado. Cambiar los
  diez guiones por diez «no aplica» no valía: deja la ficha igual de vacía y
  con más letra. Y el pie no es decoración, es lo que evita que algo
  desaparezca en silencio: a quien le falte un campo que su tarjeta sí tiene,
  lo lee ahí. En la tabla solo entra lo que se puede afirmar; el enlace PCIe se
  queda con su guion porque la Radeon 740M también es integrada y publica su
  «PCIe 4.0 × 16».
- **Poner una marca de color sin nada que la traduzca**: el punto que señala
  los mejores núcleos no significa nada por sí solo. Su leyenda va debajo de
  la propia rejilla, no en la ficha de al lado: separadas, el punto se queda
  sin explicar y la frase sin a qué referirse.
- **Reorganizar un widget sin avisar al layout de arriba**: la fila de
  insignias pasa a dos líneas cuando la ventana se estrecha, pero sin
  `updateGeometry` nadie le da la altura nueva y acababa pintada encima de la
  barra. Se arreglaba sola al mover la ventana otra vez, que es la pista de
  que faltaba un recálculo y no espacio.
- **Compartir el estilo de un título con el de una cabecera de columna**: no
  pesan lo mismo. Un título nombra la tarjeta entera; una cabecera nombra una
  columna y tiene que quedarse por detrás del dato.
- **Medir el coste de repintar sobre widgets que no están a la vista**: la
  primera medida del movimiento fluido dio un 117 % de un núcleo, y era falsa:
  forzaba el dibujo de las dieciséis gráficas montadas cuando Qt no repinta
  las de las páginas cerradas. A la vista hay cuatro, y el coste real es un
  2 %. Un número así de malo conviene comprobarlo antes de rendirse.
- **Medir el ancho de una columna cuando aún no hay nada que medir**: los
  anchos del árbol de sensores se calculan al montarlo, con las celdas
  vacías, y luego llegan los valores. La columna del reloj enseñaba
  «800.0 M…». Al cambiar un valor se ensancha si hace falta; nunca se encoge,
  o la tabla bailaría a cada muestreo.
- **Elegir columnas sin preguntar a los hijos cuánto necesitan**:
  `ResponsiveRow` repartía por su `min_item_width`, la rejilla exigía después
  el mínimo real de cada tarjeta y la fila se ensanchaba para dárselo, por
  fuera de la ventana. Un reparto vale si la suma de lo que pide cada columna
  cabe; y la fila no puede pedirle a quien la contiene el ancho de la rejilla
  montada, o su propia anchura le dirá siempre que caben.
- **Dejar que un nombre que no casa se vaya por el desagüe**: `select_section`
  recorría el menú, no encontraba la sección y volvía sin decirlo. Con
  `--screenshot --page Rendimiento` —que entonces no era el nombre de ninguna,
  porque la sección se llamaba «Benchmark»— eso
  es un PNG de la página de Inicio, escrito en disco, y un «captura guardada»
  en la salida. Una bandera que solo existe para automatizar capturas no puede
  entregar la equivocada en silencio: peor que fallar es fallar diciendo que
  todo fue bien, porque lo que se rompe está en un documento que alguien mira
  meses después. Lo mismo se comía un test de memoria que pedía «Monitor»
  —nombre de la clase, no de la sección— y llevaba tiempo visitando dos
  páginas de las tres que decía.
- **Escribir la regla del color en una sola de las cuatro páginas que la
  aplican**: `NEED_TONES` vivía en `graphics.py`, así que CPU, Memoria y Placa
  base nunca pasaban `tone` y caían en el `warn` por omisión de `Notice`. La
  regla de que lo inarreglable va en gris llevaba escrita desde el día que se
  decidió y solo se cumplía en una pantalla de cuatro. Se vio al reclasificar a
  `HARDWARE` el aviso de que un hipervisor no expone la frecuencia y mirar el
  píxel de la banda: seguía en (214,175,78), el mismo ámbar que un permiso por
  dar. Lo que decide un color vive al lado de quien lo pinta, no en la primera
  página que lo necesitó.
- **Sacar a un widget de un layout con `takeAt` para volver a meterlo**:
  desde Python `takeAt` no destruye la celda, y el widget sigue avisando de
  sus cambios de tamaño a la primera que tuvo. La celda nueva se queda con la
  altura que midió al nacer: en Inicio, un nombre de red que pasaba a dos
  líneas salía cortado por abajo, y la fila medía 195 px cuando sus tarjetas
  pedían 221. Se reproduce con una rejilla y una etiqueta. Para recolocar,
  `removeWidget`, que sí la destruye.
- **Dar por pintado lo que está en la hoja de estilos**: la raya bajo la
  cabecera de las tablas era un `border-bottom` en `QLabel#ColumnTitle`. Qt
  no la pintaba, y además sangraba 3 px cada etiqueta. Un test que mirase la
  hoja habría pasado; el que vale pinta la ventana y busca el color en la
  imagen. La raya es un `QFrame` colocado sobre la rejilla.
- **Creer que la suite pinta**: sin pantalla Qt no llama a ningún
  `paintEvent` hasta que alguien pide la imagen. El mapa de cachés reventaba
  en cada repintado (`value_font = value_font(…)`, una local con el nombre de
  la función) con mil novecientos tests en verde y el CI también. Lo vio
  `--screenshot`. `tests/test_todo_se_pinta.py` pinta las trece secciones
  con cada volcado.
- **Contar con que en el equipo de quien ejecuta la suite no hay ayudante
  instalado**: con uno de una versión anterior sale un botón más, y un test
  que contaba botones y otro que medía anchos fallaban solo en esa máquina.
  El segundo tenía razón: la página se salía. El primero fija ahora el
  estado del que habla.
- **Fiarse de la ventana sin pantalla para el tamaño con que abre un
  diálogo**: en Wayland el compositor abre la ventana con su tamaño mínimo,
  y el mínimo que calcula Qt cuenta cada párrafo como una línea. «Qué pasa
  al dar permisos» abría a 573×299 donde hacían falta 425, y sin pantalla
  abría bien. Un diálogo con párrafos fija como alto mínimo el que pide su
  contenido a su ancho más estrecho. Se comprueba abriéndolo de verdad.
- **Guardar como elección del usuario lo que el programa abre y cierra**:
  al montar el árbol de sensores, `setExpanded` dispara las mismas señales
  que un clic. Se guardaba el estado entero, así que tras el primer arranque
  todas las ramas eran «del usuario» y una regla nueva (plegar lo inactivo)
  no llegaba a nadie con preferencias. Se guarda solo lo que se aparta de la
  regla, y montar o filtrar no apuntan nada.
- **Montar un volcado apuntando `SILUX_SYSROOT` a su carpeta**: git no
  guarda carpetas vacías y el volcado tiene muchas que cuentan. La captura
  de la integrada salía sin sus unidades de ejecución y los tests las veían.
  `tools/montar_equipo.py` monta como los tests.
- **Un ancho escrito a mano para algo que lleva texto**: la barra lateral
  medía 140 px en compacto y «Almacenamiento» no cabía. El número es un
  suelo; el ancho lo pide el texto más largo, con su letra y su idioma.
- **Preguntar `isHidden` para saber si alguien escondió un widget**: también
  es cierto para uno recién creado que todavía no se ha enseñado. Con eso,
  `ResponsiveRow` dejaba fuera de la rejilla las tarjetas que nacían con la
  página ya abierta, y los módulos de memoria no salían al dar permisos
  hasta cambiar de página. Escondido a propósito es `isHidden` y
  `WA_WState_ExplicitShowHide`.
- **Probar cada página solo recién montada**: es el único momento en que
  crear las tarjetas y enseñarlas es lo mismo. Lo que se rompe es la
  página que ya está abierta cuando llega el dato, y eso solo lo ve un test
  que le da dos fotos seguidas (`tests/test_al_momento.py`).
- **Animar una barra con la fase del muestreo**, la que mueve las gráficas
  de 0 a 1 durante el intervalo: la barra llegaba a su dato justo cuando
  venía el siguiente. Con un video en la RX 9070 XT, la cifra decía 38 % y
  la barra se arrastraba un segundo entero hasta ahí, siempre por detrás. Y
  como solo se avanzaban las barras a la vista, la de una página cerrada se
  quedaba en el cero con que nació, y al abrir la página subía desde ahí.
  Una curva sí va con la fase, porque lo que se desliza es el tiempo; una
  barra es un valor y va por el reloj: 180 ms frenando al final, desde
  donde se ve (`Deslizador`). El 90 % del camino pasó de 990 ms a 89.
- **Dejar que una columna de cifras mida lo que dice ahora**: en «Ahora
  mismo», la columna de «4.6 GB de 15.9 GB» es una para todos los renglones,
  y al pasar el bus de «97 GB/s» a «116 GB/s» el fondo de todas las barras
  encogía 8 px. Cada renglón reserva lo más largo que puede llegar a decir
  (`render.possible_texts`: justo antes de cada cambio de unidad, «1023.9
  MB»). Y se mide como mide la etiqueta, con `fontMetrics().size()`:
  `horizontalAdvance` se queda a veces un píxel corto, y ese píxel también
  movía la columna.
- **Medir lo que gasta silux a ojo**: se sospechaba de las gráficas, y con
  la ventana escondida y sin movimiento fluido silux seguía gastando el 7 %
  de un núcleo. py-spy (`py-spy record --threads -f raw -- python …`; con
  `ptrace_scope` a 1 tiene que lanzar él el proceso) lo repartió: el 69 %
  era el hilo de muestreo, y de eso, recorrer `pci.ids` entero en cada
  muestreo para nombrar la tarjeta de red, leer los códecs de sonido (el
  kernel genera el volcado entero del códec al abrir `codec#N`), resolver
  cuatro veces la cadena de puentes PCIe de cada tarjeta y leer una docena
  de archivos de cada una de las 41 interfaces que crea Docker. Nada de eso
  cambia de un segundo a otro.
- **Rehacer en cada fotograma lo que solo cambia con cada muestra**: la
  curva de una gráfica (`curva_suave`, en Python) se rehacía treinta veces
  por segundo para correrla una décima de píxel, y las dieciséis curvas de
  historial de la matriz de núcleos, en cada fotograma de sus barras. Se
  calcula con la muestra y se mueve con `translate`. Y una gráfica
  transparente repinta todo lo que tiene detrás: la barra de memoria
  repintaba su leyenda entera (casi cien insignias por segundo en Inicio)
  porque iba dentro del mismo widget; se repinta solo su franja.
- **Pintar lo que no se ve**: cada foto se aplicaba entera a las catorce
  páginas, y el temporizador del movimiento fluido latía treinta veces por
  segundo en páginas sin nada que mover y con la ventana minimizada. La
  foto entera va a la página que se ve; las que guardan historia reciben
  solo eso, una vez por foto (`record`), y las demás se ponen al día al
  abrirlas. Ojo con «escondida»: sin pantalla, una ventana recién enseñada
  todavía no está expuesta; escondida es la que se llegó a ver y ya no.
- **Dejar un `QPainter` abierto sobre una imagen si algo falla al
  pintarla**: el fondo de la matriz de núcleos se pinta en un `QPixmap`, y
  un `KeyError` a mitad dejaba el pintor vivo. Con PySide6 6.11 y Python
  3.10 tumbaba el proceso dos tests más tarde, con un `Segmentation fault`
  sin un solo marco de silux; con 6.12 y 3.14, nada. Se cierra con
  `try/finally`. Y el CI de las dos puntas es lo que lo vio: aquí se
  reproduce con `uv run --python 3.10` (que rehace `.venv`; luego, `uv
  sync --extra gui --python 3.14`).
- **`QTimer.singleShot(0, self.metodo)` en un widget que puede morir**: el
  temporizador no muere con él. La ventana lo usaba al recibir un `Expose`,
  y en la suite —que abre y borra muchas— saltaba sobre una ventana ya
  borrada: «Internal C++ object (MainWindow) already deleted», y en el CI
  con PySide6 6.11, de vez en cuando, un `Segmentation fault` en otro test.
  Un `QTimer` hijo del widget sí muere con él.
- **Enseñar una fila y esconderla después en la misma muestra**: al final
  queda igual, pero Qt recoloca la página entera dos veces, y el área de
  desplazamiento la mide en medio. Gráficos crecía de 1740 a 1763 px y
  volvía, cada segundo: parpadeo y letras que se mueven, solo con la ventana
  de verdad. Lo mismo poner un dato y luego su candado. Cada fila se decide
  una vez (un conjunto de lo que se esconde, un estado de candado) y se
  aplica en una pasada. Lo vigila `tests/test_nada_se_mueve.py`.
- **Una cifra grande sin ancho reservado**: la unidad de al lado salta con
  cada dígito, y si la ficha está en una `ResponsiveRow`, la fila entera se
  reparte de nuevo. `StatTile.reserve` con lo más largo que puede decir,
  como `LevelList.reserve`.
- **Buscar un parpadeo en las capturas de final de muestra**: salen todas
  iguales, porque lo que parpadea es un estado intermedio. Se ve con un
  filtro de eventos: los `Show`/`Hide` de la página mientras se aplica una
  muestra, y una captura (`grab`) cada vez que la página cambia de tamaño.
  Con un volcado quieto las cifras no cambian de ancho: el test hace avanzar
  sus contadores (`avanzar`).
- **Fiarse de lo que se ve en la pantalla de una ventana lanzada desde la
  terminal de Claude**: tras el primer fotograma no se repinta, aunque por
  dentro tenga los datos; le pasa igual a una ventana de Qt de diez líneas.
  Para saber si una ventana tiene sus datos, una sonda dentro (un
  `sitecustomize` en `PYTHONPATH` que mira los widgets a los pocos
  segundos); lo que se ve, lo mira el autor.

<a id="idioma"></a>

## Idioma y textos

- **Que una herramienta borre lo que no entiende**: `gen_lang --write`
  reescribía los archivos de idioma solo con lo que su extractor veía, y el
  menú lateral se traduce con `_(name)` sobre una variable. Se perdieron doce
  traducciones en una pasada, sin aviso. Lo que ya está traducido se conserva
  aunque no se encuentre.
- **La raya de inciso en un texto de interfaz**: funciona en un párrafo largo y
  estorba en una frase corta, sobre todo cuando el inciso solo enumera. Y hay
  dos formas de que salga mal que no se ven al escribirla: pegar la raya de
  cierre a una coma —«a secas—,»— y abrir un inciso en una cadena que se
  concatena con otra, donde la raya se queda sin cerrar y el resto de la frase
  llega en medio. Los paréntesis no tienen ninguno de los dos problemas.

<a id="privilegios"></a>

## Privilegios

- **Mandar al usuario a bajar `/proc/sys/kernel/perf_event_paranoid`**: es un
  cerrojo de toda la máquina, no un permiso para este programa; a 0 —el único
  valor que sirve, con 1 sigue denegado— cualquier proceso sin privilegios
  puede perfilar el equipo entero. El ayudante privilegiado que ya pide la
  contraseña una vez para los discos abre el contador sin que el usuario toque
  nada del sistema. Hay un test que vigila que ningún aviso vuelva a nombrarlo.
- **Poner en una tabla estática un aviso que depende de los permisos**: el
  de i915 vivía en `DRIVERS_CIEGOS`, que lee un proveedor `static`, o sea que
  corre una vez. Seguía pidiendo permisos después de que el usuario los diera.
  Lo que cambia a mitad de sesión lo pone un proveedor dinámico.
- **Un cliente del ayudante por proveedor**: cada uno lanza su proceso y abre
  su propio diálogo de polkit, así que dos serían dos veces la contraseña para
  lo mismo. El colector crea uno y lo reparte.
- **Poner un botón para arreglar algo que el ayudante no sabe arreglar**: el
  aviso de que el consumo del procesador «requiere permisos» lo pone el
  proveedor de RAPL, porque desde el kernel 5.10 `energy_uj` no se lee sin
  privilegios. Pero el ayudante sabía leer SMBIOS, MSR, SMART y el PMU de la
  gráfica, y no RAPL: el usuario daba los permisos, el ayudante arrancaba y
  nadie leía eso, así que la nota no se iba nunca. Lo reportó alguien con un
  Ryzen 7 7445HS —«le di permisos pero aún dice que 1 dato requiere permisos, y
  al tocarlo no abre el polkit»— y lo segundo también encaja: ya estaba
  conectado, no había nada que autorizar. Un contador de lo que falta solo vale
  si lo que cuenta se puede resolver.
- **Confiar en que una copia instalada se actualiza sola**: no se actualiza
  nadie. El ayudante que dejan los permisos permanentes en `/usr/local/libexec`
  se queda congelado en la fecha en que se instaló, de root y con su acción de
  polkit apuntándole. En la máquina del autor era del 28 de agosto: le faltaba
  `read_rapl` desde el 30 —o sea que el consumo del procesador no se leía por
  mucho que se dieran permisos— y era anterior a los tres arreglos de escalada
  del 31. Lo comprometido ahí no es un fallo dentro del archivo, que no cambió
  ni una línea en esos tres commits, sino por qué camino llegó: el instalador
  anterior aceptaba una ruta que el usuario puede escribir. Y no basta con
  dejar de ejecutarlo, hay que sustituirlo, porque el archivo se queda puesto.
- **Pasarle a `pkexec` la ruta de un guion que el usuario puede escribir**: lo
  avisa su propio manual —«pkexec does no validation of the ARGUMENTS passed to
  PROGRAM»— y aquí estaba hecho en tres sitios, todos copiando a
  `~/.cache/silux` y lanzando desde ahí. Lo que se comprueba es el *programa*,
  que era `/usr/bin/python3` y está bien; el guion es un argumento y no lo mira
  nadie. Cualquier proceso del propio usuario —un navegador comprometido, un
  paquete de pip con sorpresa— cambia el archivo antes de que root lo abra y se
  queda con ejecución como root. El peor de los tres era el instalador, y no
  por la carrera: la ventana iba desde la copia hasta que root leía, con el
  diálogo de la contraseña en medio, o sea segundos; y lo que se ganaba no era
  ejecutar una vez, era que `instalar.py` dejara *eso* en
  `/usr/local/libexec`, de root y con una acción de polkit `auth_admin_keep`
  apuntándole. Una puerta permanente que sobrevive a desinstalar el programa.
  Lo que se pasa por `argv` queda fijado por el `exec()` y no se puede tocar
  después, así que los guiones viajan enteros ahí (`client.en_linea`) y no
  existen como archivo en ningún momento. El ayudante son 21 KB y el límite del
  kernel por argumento son 128. Se paga que la fuente salga en `ps`, que es
  código público, y que `-c` compile como `<string>`: eso segundo sí importaba,
  porque deja los informes de fallo sin archivo ni línea, y se arregla
  compilando con nombre y cebando `linecache`.
- **Comprobar el hash de un archivo justo antes de ejecutarlo**: parece el
  arreglo evidente de lo anterior y no cierra nada. Entre el hash y el `open()`
  de quien lo ejecuta hay una ventana que controla quien ataca, y en el caso
  del instalador la comprobación caería antes del diálogo de la contraseña y el
  cambiazo durante. El fondo es que **nada que el usuario pueda escribir se
  asegura comprobándolo desde un proceso del propio usuario**: no hay orden de
  las operaciones que lo salve. Un directorio que solo escriba root sí valdría,
  pero crearlo exige root, que es justo el momento atacado. La opción que
  funciona es que no haya archivo. Ojo con esta: es barata de escribir y deja
  el código con pinta de arreglado.
- **Poner la defensa dentro de lo que se sustituye**: `cargar_modulo.py`
  comprueba el nombre del módulo contra una lista cerrada, y su propia cabecera
  explica por qué —«un ayudante que carga el módulo que le digan es un ayudante
  que carga cualquier módulo del sistema»—. Pero la lista vivía dentro del
  archivo que se copiaba a la carpeta del usuario, así que quien cambiara el
  archivo se llevaba también la comprobación. Una validación solo cuenta si
  está en el lado que no puede tocar quien ataca.

<a id="privacidad"></a>

## Privacidad

- **Tapar el nombre del equipo solo en su campo**: `privacidad.anonimizar`
  cambiaba `system.hostname` y ya, y el nombre no vive solo ahí. Una interfaz
  de Tailscale, de ZeroTier o un puente hecho a mano se llaman como la máquina,
  así que el informe seguía enseñando «alex_portatil (virtual)» en la lista de
  red, en el archivo que se le pide a la gente para pegar en público. Se vio en
  el primer informe de un portátil, o sea la primera vez que alguien lo usó
  donde tenía sentido. Ojo al arreglarlo: buscado como subcadena, un equipo
  llamado «lan» convierte `wlan0` en `wequipo0`. Se busca como nombre entero y
  sin mayúsculas, y así uno de dos letras se tapa sin romper nada.
- **Tapar solo lo que se sabe que identifica**: una interfaz de WireGuard
  llamada con el nombre de una persona no es el hostname, y ningún sustituto
  del hostname la ve. Lo que se enumera es lo que se deja —los nombres que
  pone el sistema, con patrones estrictos— y lo demás se sustituye. Con `en*`
  a secas, «enrique-vpn» pasaría por una tarjeta de red.
- **Buscar texto dentro de una imagen**: `comprobar_privacidad.py` recorre lo
  versionado buscando el nombre del equipo y las MAC, y por eso daba por buenas
  las capturas: lo que se ve en pantalla no está escrito en el archivo. Publicó
  su visto bueno a una que enseñaba la dirección física de esta máquina y su
  IPv6 pública, que es un prefijo global y dice de quién es la conexión. Como
  no se puede leer lo que enseña la imagen, se comprueba cómo se hizo: la
  captura escribe dentro del PNG si tapó los identificadores, y el comprobador
  exige esa marca. El valor va en ASCII, y tampoco es un descuido del idioma:
  con «sí», Qt lo escribe en Latin-1 —`s\xed`— y quien lo busque en UTF-8 no
  encuentra la marca que sí está.

- **Dar por limpio un volcado porque la foto lo está**: el primer volcado de
  equipo pasó las dos comprobaciones —anonimizar no encontraba qué tapar en la
  foto, y ningún identificador de `comprobar_privacidad` salía en los bytes— y
  llevaba los números de serie de los dos módulos de RAM dentro del SPD. silux
  no los decodifica, así que ninguna de las dos podía verlos. Un archivo
  binario se limpia por posición conociendo su formato (SPD, EDID), y lo
  quitado se busca después como bytes, no como texto.

<a id="empaquetado"></a>

## Empaquetado y CI

- **Dar por empaquetado lo que no hace ruido al faltar**: el empaquetador
  copiaba de `imageformats` los archivos «qsvg.so» y se llaman
  «libqsvg.so». La carpeta salía vacía sin aviso, y el AppImage arrancaba
  sin un solo icono: el CI solo comprobaba `--help`. Lo que falta detiene la
  construcción, y se abre el AppImage con `--screenshot` antes de fiarse.
- **Dejar en `tools/` algo que ejecuta el usuario final**: el AppImage copia
  `silux/` entero y no copia `tools/`, así que el botón de permisos permanentes
  se quedaba sin instalador que lanzar justo en la única forma del programa que
  se reparte. `tools/` es para quien desarrolla.
- **Probar la interfaz solo con `QT_QPA_PLATFORM=offscreen`**: ese plugin
  apenas necesita bibliotecas, así que un AppImage al que le falte medio Qt
  arranca igual. El fallo aparece en la primera máquina ajena con pantalla.
- **Recorrer solo las dependencias del ejecutable de Python**: los módulos de
  extensión de su biblioteca estándar tienen las suyas y viven aparte, en
  `lib-dynload`. Así `_hashlib` se quedaba sin `libcrypto` y `_lzma` sin
  `liblzma`, y dos de las cinco cargas del benchmark reventaban en cualquier
  máquina que no las trajera puestas: en las distribuciones con OpenSSL 1.1,
  siempre. De paso, los módulos que el programa no usa se borran antes de
  mirar de qué dependen: `nis` se lleva Kerberos entero detrás.
- **Tomar por normal un aviso del comprobador del AppImage**: decía que trece
  bibliotecas se cogían del sistema «y son normales», y dos de ellas hacían
  falta de verdad.
- **Avisar en el registro de una construcción que termina bien**: el
  comprobador sí veía las siete `libxcb-*` que le faltaban al AppImage de la
  v0.2.0, y lo escribía en stderr mientras la construcción seguía y devolvía
  cero. Así se publicó. Un aviso que no para nada no lo lee nadie: ahora el
  empaquetador no empaqueta un AppDir al que le falta algo. Y ese paquete salía
  del runner y no del contenedor, que era el que sí las llevaba: lo que se
  reparte se construye con la receta que se prueba, o la receta no prueba nada.
- **Tener el CI atado a los tags**: la acción del AppImage solo corría con
  `v*`, y como no hubo tag hasta la 0.2.0, la primera vez que se ejecutó
  llevaba meses sin probarse y falló entera. Enterarse el día que se publica es
  enterarse tarde. Ahora corre en cada empujón a master; publicar sigue
  dependiendo del tag.
- **Probar en un contenedor que corre como root y sin `hwdata`**: al buscar por
  qué fallaba el CI, cuatro de los fallos eran del entorno de pruebas y no del
  programa. Como root, el proveedor de memoria lee la tabla DMI directamente en
  vez de pedir permisos, así que sale `HARDWARE` donde el test espera `ROOT`; y
  sin `pci.ids` no hay nombres de dispositivo que buscar. Reproducir el CI es
  reproducir también quién lo ejecuta.
- **Dejar que cada comprobación recorra el AppDir por su cuenta**: la del juego
  de instrucciones lo miraba entero y la de glibc solo `usr/lib/*.so*`, y de
  esas, las sesenta primeras de sesenta y cinco. Así el informe decía «exige
  glibc 2.34» de un paquete que exige 2.35, que es la diferencia entre que RHEL
  9 valga o no valga: el símbolo más alto, `hypot@GLIBC_2.35`, lo pide el
  propio `python3`, que cuelga de `usr/bin` y no se miraba. Los módulos de
  extensión de `lib-dynload` tampoco, que es el mismo agujero por el que
  `_hashlib` se quedó sin `libcrypto`. Equivocarse aquí solo cae hacia un lado
  —decir que hace falta menos de lo que hace falta—, y es el lado que manda a
  alguien a descargar algo que no le arranca. Ahora la lista es una,
  `objetos_del_appdir()`, y hay tests que vigilan que las dos la compartan y
  que nadie le vuelva a poner tope.
- **Dar por hecho que una dependencia sigue donde estaba**: el `pip install`
  del AppImage pedía `PySide6>=6.6`, sin techo, y durante un año eso fue
  inofensivo. Qt 6.10 subió su mínimo a x86-64-v2 y el AppImage dejó de
  arrancar en cualquier procesador anterior a 2008, sin que cambiara una línea
  del programa. Lo que no se fija cambia solo, y lo hace en la máquina de otro.
  **Y volvió a pasar**: el normal se quedó sin techo a propósito, PySide6
  6.12.0 salió un mes después del último commit y rompía el Python 3.10 que va
  dentro. Nadie lo habría visto hasta el siguiente empujón, porque aquí se
  desarrolla con el PySide6 de la distribución.
- **Contar instrucciones para saber si un binario es compatible**: libcrypto
  lleva AVX-512 y funciona en un Pentium 4, porque pregunta antes. Lo que hay
  que mirar es dónde caen: en una función con el juego en el nombre
  —`qt_convert_rgb888_to_rgb32_ssse3`— no se ejecutan salvo que toque; en
  `QString` no hay escapatoria. `.dynsym` sobrevive al `strip`, así que se
  puede saber cuál es cuál.
- **Fiarse de `ldd` en la máquina donde se construye**: resuelve contra lo que
  esa máquina tiene instalado, que es justo lo que se está empaquetando. Lo
  que no esté puesto no aparece como dependencia y se cae del paquete en
  silencio. `tools/build_appimage.py` termina comprobando que cada objeto del
  AppDir resuelve dentro o contra la lista de lo que se deja al anfitrión.
- **Filtrar bibliotecas por subcadena**: «libxcb» en la lista de lo que pone
  el sistema también descartaba `libxcb-cursor` y las nueve auxiliares que el
  plugin xcb necesita y que muchas distribuciones no traen. Se comparan por
  principio de nombre.
