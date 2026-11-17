# Propuesta: límites de potencia de AMD (PPT, TDC, EDC)

Solo propuesta: no hay código. Toca privilegios, así que se propone y se
espera respuesta (`CLAUDE.md`, «Flujo de trabajo»).

Lo que se pide valorar: enseñar en CPU, para AMD, el **límite y el uso** de
PPT (potencia del paquete), TDC (corriente sostenida) y EDC (corriente de
pico), como función experimental, leyendo `ryzen_smu`.

**Mi recomendación, por delante: no ahora, y si se hace, en dos pasos y
empezando por el que no enseña ninguna cifra.** El porqué está al final,
después de lo que hace falta saber para decidir.

## Qué se ha comprobado y qué no

Escrita el 18 de noviembre de 2026 en el 5800X3D (CachyOS, kernel 7.3.4).

- **Comprobado aquí**: en este equipo `ryzen_smu` **no está instalado**
  (`/sys/kernel/ryzen_smu_drv` no existe, `modinfo ryzen_smu` no lo
  encuentra, y el repositorio de la distribución no lo trae). El kernel no
  publica PPT, TDC ni EDC por ningún otro camino: ni `k10temp`, ni
  `amd-pstate`, ni powercap (la carpeta `intel-rapl:0` de este equipo no
  tiene ningún `constraint_*`).
- **No comprobado**: todo lo que sigue sobre `ryzen_smu` y sobre el orden
  de su tabla. Sale de lo que sé del proyecto y de `ryzen_monitor`, no de
  haberlo leído en esta máquina. **Antes de escribir una línea hay que
  instalarlo aquí y mirar la tabla de verdad.** Donde digo un número de
  versión o una posición, es una pista para saber dónde mirar, no un dato.
- **No comprobado**: nada de Intel más allá de lo que ya lee silux.

## De dónde saldría

`ryzen_smu` es un módulo de fuera del kernel (se instala con DKMS) que habla
con el microcontrolador del procesador (el SMU) por su buzón de órdenes. No
está en el árbol del kernel ni lo mantiene AMD. Publica en
`/sys/kernel/ryzen_smu_drv/`, entre otros:

| Archivo | Qué es |
|---|---|
| `version` | la versión del firmware del SMU |
| `codename` | un número que dice la generación (Matisse, Vermeer…) |
| `pm_table_version` | la versión de la tabla de telemetría |
| `pm_table_size` | su tamaño en bytes |
| `pm_table` | la tabla: una fila de números de coma flotante de 32 bits |

Lo que hay que saber de esa tabla:

1. **No está documentada.** AMD no publica qué hay en cada posición. Lo que
   se sabe viene de comparar con Ryzen Master en Windows, posición a
   posición, y lo mantienen proyectos como `ryzen_monitor`.
2. **Cambia con la versión**, que depende de la generación *y* de la
   versión de AGESA de la BIOS. Una actualización de BIOS puede cambiarla.
   Para Zen 3 de sobremesa circulan varias (las que recuerdo empiezan por
   `0x3809` y `0x3808`); cuál lleva esta placa con su BIOS F40 no lo sé.
3. **Los archivos son de root** (`0600`). Hace falta el ayudante.
4. **Leerla no es inocuo.** Cada lectura de `pm_table` hace que el módulo
   mande una orden al SMU para que refresque la tabla (el propio módulo lo
   limita a una vez por segundo, si no recuerdo mal). No es escribir en un
   registro, pero tampoco es lo que hoy promete el ayudante: su lista de
   registros dice «ninguno tiene efectos secundarios al leerlo»
   (`privileged/helper.py`). Esto sí los tiene, aunque sean los mismos que
   provoca cualquier otro programa que lea esa tabla.

En las tablas de Zen 3 que conozco, los límites y sus valores van al
principio y por parejas: límite de PPT y PPT, límite de TDC y TDC, un límite
térmico y su valor, y más adelante límite de EDC y EDC. Es justo lo que se
quiere enseñar. Pero «al principio y por parejas» no es una especificación.

## Cómo se leería con el ayudante

Sería una acción nueva del ayudante, y es la parte que hay que decidir con
cuidado.

**Lo que haría, y nada más:**

- Abrir cuatro rutas fijas, escritas como constantes:
  `/sys/kernel/ryzen_smu_drv/pm_table_version`, `pm_table_size`, `codename`
  y `pm_table`. Ningún argumento del cliente entra en la ruta.
- Leer como mucho un tope fijo de bytes (las tablas conocidas no llegan a
  dos kilobytes; un tope de 4096 sobra) **antes** de reservar nada. Ese
  fallo ya existe en otras acciones (F-M24) y aquí no se repetiría.
- Devolver los bytes tal cual. **El ayudante no interpreta la tabla**: no
  sabe de versiones ni de posiciones. Eso lo hace el cliente, sin
  privilegios, igual que con el SMART y con la tabla SMBIOS.
- No escribe en ningún archivo de ese directorio. `ryzen_smu` también
  publica `smu_args` y `rsmu_cmd`, que sirven para mandar órdenes
  arbitrarias al SMU: **el ayudante no los abre nunca**, ni para leer.

**Lo que no haría:**

- **Cargar el módulo.** `privileged/cargar_modulo.py` tiene una lista
  blanca de módulos del propio kernel. `ryzen_smu` no entraría: es código
  de terceros corriendo en el núcleo, y silux no lo instala, no lo carga y
  no lo recomienda. Si está, se usa; si no, se dice que existe y nada más.
- **Leer con la cadencia del muestreo sin más.** Como cada lectura manda
  una orden al SMU, la cadencia la fija el ayudante (una vez por segundo
  como mucho), no el cliente. Es el mismo problema que F-M27 con RAPL, y
  habría que resolverlo aquí desde el principio.

**Lo que cambia para quien ya dio permisos para siempre:** el ayudante
instalado se compara por contenido, así que al añadir la acción pasaría a
estar «atrasado» y habría que reinstalarlo. Es lo normal, pero conviene
saberlo: cada acción nueva es una reinstalación para todos.

## Las condiciones para enseñar algo

Las que pide el encargo, y dos más:

1. **Solo si `ryzen_smu` está cargado.** Si no, la fila no sale, y la nota
   que ya hay («los límites de potencia de AMD no los publica el kernel»)
   puede añadir que existen con ese módulo. Sin botón, sin instrucciones de
   instalación: no es algo que silux deba empujar a nadie a instalar.
2. **Solo en generaciones con tabla conocida**, empezando por Zen 3.
3. **Solo si la versión de la tabla es exactamente una de las conocidas.**
   Ni «la más parecida» ni «la última de esa generación»: si no cuadra, no
   se enseña ninguna cifra y se dice «tabla 0x… sin identificar». Es la
   condición que más importa. Una tabla leída con el mapa de otra da
   números que parecen buenos.
4. **(Añadida) Solo si el tamaño también cuadra** con el de esa versión.
5. **(Añadida) Solo si lo leído es verosímil.** Los límites de fábrica son
   conocidos por TDP: un procesador AM4 de 105 W trae 142 W de PPT, 95 A de
   TDC y 140 A de EDC. No se exige ese valor (quien usa PBO lo cambia),
   pero un PPT de 0, de 3 o de 4000 W significa que el mapa está mal, y
   entonces tampoco se enseña nada. Y el valor nunca puede ser negativo.
6. **Marcado como experimental**, en la pantalla y no solo en el tooltip, y
   con su fuente al pasar el ratón: «ryzen_smu, tabla 0x…; no es una
   interfaz oficial del kernel».
7. **Apagado por omisión**: una casilla en Ajustes, «Leer los límites de
   AMD con ryzen_smu (experimental)». Sin ella, el ayudante no recibe esa
   petición aunque el módulo esté.

Con todo eso, lo que se vería en CPU, en «Potencia y reposo»: tres filas,
«PPT 87 W de 142 W», «TDC 54 A de 95 A», «EDC 96 A de 140 A», cada una con
su barra, y la marca de experimental. Es lo que enseñan Ryzen Master y
HWiNFO, y es lo que quien ajusta PBO quiere ver.

## En Intel: qué hay y cómo se lee

| Dato | De dónde | Permisos | Estado |
|---|---|---|---|
| PL1 y PL2 | `/sys/class/powercap/intel-rapl:0/constraint_{0,1}_power_limit_uw` | no | **ya se enseña** desde esta noche (65 y 115 W en el i5-10400, de su volcado) |
| Las ventanas de tiempo de PL1 y PL2 (tau) | `constraint_{0,1}_time_window_us`, mismo sitio | no | no se lee; es añadir dos archivos |
| Si los límites están activos y bloqueados | registro `0x610`, que **el ayudante ya tiene en su lista** | sí | no se decodifica; sin tocar el ayudante |
| PL4 (pico absoluto) | en los procesadores que lo tienen, powercap lo publica como una tercera restricción, `constraint_2_name` = `peak_power` | no | sin comprobar: el i5-10400 no la tiene (su volcado solo trae dos) |
| IccMax | no está en ningún registro que se lea sin más: sale del buzón de overclocking (registro `0x150`), que funciona **escribiendo** una orden y leyendo la respuesta | sí, y escribiendo | **no se propone**: el ayudante solo lee |

Es decir: en Intel lo equivalente a PPT ya está, sin permisos y por una
interfaz del kernel. PL4 es mirar si existe un archivo más. Lo único que no
se puede hacer con las reglas de hoy es IccMax, por el mismo motivo de
fondo que hace dudar de `ryzen_smu`: leerlo exige mandar órdenes.

Lo que Intel no da y AMD sí daría es el **uso** de la corriente (TDC y EDC
como valores, no solo como límites). En Intel el uso que hay es el de
potencia, que es el consumo de RAPL que ya se enseña.

## Lo que cuesta

- **Una acción más en el ayudante**, con todo lo que eso arrastra: su
  propuesta, sus tests de que no abre nada fuera de sus cuatro rutas, y la
  reinstalación para quien lo tenga instalado.
- **Un mapa por versión de tabla**, que hay que sacar de `ryzen_monitor` y
  **verificar**. El autor solo puede verificar uno: el de su 5800X3D con su
  BIOS. Cualquier otro entra sin que nadie de este proyecto lo haya visto.
- **No se puede probar en el CI** ni con un volcado: lo que lee el
  ayudante no se graba. Los tests serían sobre tablas guardadas como
  bytes, que es lo que se pueda conseguir de quien las mande.
- **Se rompe solo.** Una BIOS nueva cambia la versión de la tabla y la
  función deja de enseñar nada (que es lo correcto) hasta que alguien
  añada el mapa nuevo. Es mantenimiento para siempre, por generación y por
  AGESA.
- **Poca gente lo tiene.** Hay que instalar un módulo con DKMS, y con
  Secure Boot además firmarlo. Quien llega hasta ahí suele tener ya
  `ryzen_monitor`.

## Recomendación

**No lo metería ahora, y no lo metería entero.** Tres razones, por orden de
peso:

1. **Va contra la regla que más pesa en este proyecto**: «mejor un dato
   que falta y se explica que uno que parece bueno y no lo es»
   (`docs/en-curso.md`). Una tabla sin documentar, con posiciones sacadas
   por comparación y que cambian con la BIOS, es exactamente la fuente de
   un número que parece bueno. Las condiciones de arriba lo acotan mucho,
   pero no lo eliminan: dos versiones de tabla pueden compartir número y
   diferir en una posición.
2. **Cambia lo que el ayudante es.** Hoy lee registros y tablas sin
   efectos. Esto le haría provocar órdenes al firmware a través de un
   módulo de terceros. Es poco, pero es cruzar una línea que hasta ahora
   se ha podido explicar en una frase («solo lee»), y esa frase está en
   «Qué pasa al dar permisos».
3. **El beneficio es para muy pocos**, y esos pocos ya tienen con qué
   verlo.

**Si aun así se quiere, lo haría en dos pasos:**

- **Paso 1, sin privilegios y sin cifras** (media tarde): detectar que
  `ryzen_smu` está cargado (la carpeta existe; eso se ve sin root) y
  decirlo en la nota de CPU: «ryzen_smu está cargado; silux todavía no lee
  sus límites». No toca el ayudante, no enseña ningún número, y sirve para
  saber si a alguien le importa.
- **Paso 2, experimental y solo para la tabla del autor**: la acción del
  ayudante con las condiciones de arriba, **un solo mapa** (el de su
  5800X3D, verificado en su máquina contra los límites de fábrica y contra
  lo que diga su BIOS), y nada más hasta que alguien mande otra tabla con
  su verificación. Antes de este paso: instalar `ryzen_smu` aquí, volcar
  la tabla y comprobar posición a posición que cuadra. Si no cuadra con lo
  que digo arriba, esta propuesta se rehace con lo que salga.

Y hay algo que merece más la pena y cuesta menos, **ya**: en Intel, añadir
las ventanas de tiempo de PL1 y PL2, mirar PL4 donde exista, y decodificar
del registro `0x610` (que el ayudante ya lee) si los límites están
bloqueados. Es una interfaz oficial, no toca privilegios nuevos y se puede
probar con un volcado. Eso sí lo haría en la próxima tanda.

## Lo que tendría que decidir el autor

1. Si se hace algo de esto, o se cierra aquí.
2. Si se hace: si el ayudante puede leer una fuente cuya lectura manda
   órdenes al firmware. Es una decisión de principio, no de implementación.
3. Si se instala `ryzen_smu` en el 5800X3D para volcar la tabla: sin eso no
   hay con qué escribir ni el primer mapa.
4. Si lo de Intel (ventanas, PL4, bloqueo) entra en la próxima tanda.
