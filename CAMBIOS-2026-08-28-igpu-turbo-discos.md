# Sesión del 28 de agosto de 2026 — iGPU Intel, turbo y discos

Trabajo hecho en el PC de Fedora del trabajo (Intel i5-10400, UHD 630, KIOXIA
EXCERIA SATA 240 GB), que es hardware distinto al de casa. El encargo eran
tres cosas concretas y no tocar nada más.

**No se ha hecho ningún commit.** El árbol tiene los cambios sin confirmar,
para que se revisen antes.

Suite: **751 tests en verde** (eran 740 antes de esta sesión; 11 nuevos).

> Nota al margen: `CLAUDE.md` dice «los tests son 582 y tardan quince
> segundos». Ya son 740 y tardan cincuenta. Conviene actualizar esa frase,
> porque tal y como está invita a pensar que falta algo cuando no falta.

---

## 1. Discos — el TBW de un Kioxia salía 65 536 veces más pequeño

### El síntoma

Un KIOXIA-EXCERIA con 3 834 horas de encendido declaraba **367 MB escritos**.

### Qué se comprobó

El atributo SMART 241 en crudo:

```
241  Lifetime_Writes_GiB   RAW_VALUE = 752 881
752 881 × 512 B = 367,6 MB      ← exactamente lo que enseñaba el programa
```

O sea, **el parseo era correcto**: leía bien el valor crudo. Lo que estaba mal
era la unidad. El atributo se llama «LBAs escritas» y casi todo el mundo cuenta
sectores de 512 bytes, pero no es obligatorio.

Las dos herramientas de referencia **no coinciden entre sí**:

| Fuente | Unidad que asume | Total que daría |
| --- | --- | --- |
| `smartctl` | GiB (lo llama `Lifetime_Writes_GiB`) | 735 TiB — imposible |
| libatasmart / UDisks | 32 MiB | 23,0 TiB |
| silux hasta hoy | 512 B | 367 MB — absurdo |

Como no hay forma de deducirlo del propio atributo, se midió contra el
hardware: escribir una cantidad conocida y ver cuánto sube el contador.

```
Antes:   752 881
Escrito: 4,09 GiB   (confirmados por /sys/block/sda/stat, no por el fichero)
Después: 753 014

753 014 − 752 881 = 133 unidades
4 192,9 MiB / 133 = 31,5 MiB por unidad   →   la unidad es 32 MiB
```

Dos detalles de la medición que casi la estropean y conviene recordar:

- **`/tmp` en Fedora es tmpfs**, o sea RAM. Escribir ahí no habría tocado el
  disco y el contador no se habría movido.
- **El home va en btrfs con `compress=zstd:1`.** Escribir ceros se habría
  comprimido a casi nada. Se usaron 4 GiB de datos aleatorios, verificados
  como incompresibles antes de escribirlos.

### Qué se cambió

**`silux/smart.py`**

- Tabla nueva `ATA_UNIDAD_ESCRITURA` con las marcas cuya unidad se ha medido:
  `kioxia` y `toshiba` a 32 MiB. Toshiba entra porque son los mismos discos de
  antes de que la división de memorias cambiara de nombre.
- Función nueva `_unidad_escritura(vendor, model)`, que busca la marca en el
  fabricante o en el modelo (unos discos la ponen en un sitio y otros en otro).
- `parse()` acepta ahora `vendor` y `model` **opcionales**. NVMe no los usa: su
  registro de salud está definido por la especificación.
- `_parse_ata()` multiplica por la unidad que toque en vez de por 512 fijo.

**`silux/providers/storage.py`**

- Una línea: pasarle a `parse()` el fabricante y el modelo del disco, que ya
  los tenía delante.

### Lo importante: los demás discos no cambian

**Lo que no esté en la tabla sigue contando en sectores de 512 bytes**, que es
exactamente lo que hacía el programa hasta hoy. El NVMe y el Crucial SATA de
casa dan lo mismo que antes. Hay un test que lo fija:

```python
def test_lo_normal_siguen_siendo_sectores(self):
    for fabricante, modelo in (("Crucial", "CT500MX500SSD1"),
                               ("Samsung", "SSD 870 EVO"),
                               ("WDC", "WD Blue SA510"),
                               (None, None)):
        self.assertEqual(smart._unidad_escritura(fabricante, modelo),
                         smart.ATA_SECTOR)
```

Resultado en el disco de esta máquina: **23,0 TiB** en vez de 367 MB.

### Cómo añadir una marca nueva cuando aparezca

La receta está en el comentario del código, pero por si acaso:

1. `pkexec smartctl -A /dev/sdX` y apuntar el crudo del atributo 241.
2. Escribir una cantidad conocida **en disco de verdad** (ojo con tmpfs y con
   la compresión del sistema de ficheros) y comprobarla contra
   `/sys/block/sdX/stat`.
3. Volver a leer el 241. `cantidad_escrita / delta` es la unidad.
4. Añadir la marca a `ATA_UNIDAD_ESCRITURA` con el número medido en el
   comentario, para que se sepa que está comprobado y no supuesto.

---

## 2. Gráfica integrada de Intel — tres fallos y un límite real

### 2.1 «En uso: 11,6 GB» era mentira

`render.gpu_memory_summary()` devolvía el **total** cuando el driver no
publicaba la memoria ocupada, y la página lo pintaba bajo el renglón **«En
uso»**. Resultado: la integrada declaraba tener sus 11,6 GB ocupados al
completo, permanentemente.

**Cambiado en `silux/render.py`**: si no se sabe cuánta se usa, devuelve «—».

Los dos sitios que sí querían el total lo piden ahora por su nombre:

- `silux/ui/pages/graphics.py`: la ficha de VRAM pone «de 11,6 GB» como
  detalle, que acompaña al porcentaje en vez de suplantarlo.
- `silux/cli.py`: el renglón «VRAM» enseña el total cuando no hay ocupación,
  pero explícitamente, no por efecto colateral de otra función.

### 2.2 El enlace PCIe traía basura

La integrada publicaba `current_width = 0` y `max_width = 255`. Sysfs dice
literalmente `Unknown` en las velocidades y 255 es 0xFF, el centinela de «no se
sabe». Se colaban al modelo y a la salida JSON, y la gráfica integrada
declaraba un enlace de **255 carriles**.

**Cambiado en `silux/providers/drm.py`**: constante `ANCHOS_PCIE` con los
únicos anchos que existen en PCIe (1, 2, 4, 8, 12, 16, 32); cualquier otra
cifra se descarta. Comprobado que un puerto raíz de verdad sigue leyéndose
bien (x1 a 2.5 GT/s, gen 1).

### 2.3 Uso, temperatura y consumo: no se pueden leer, y ahora se explica

Esto **no es un fallo del programa**, es un límite de la plataforma, pero
dejarlo en blanco sin más incumple la regla 5 del proyecto.

Lo que se comprobó:

- El nodo DRM de la UHD 630 **no tiene hwmon**: no hay temperatura ni vatios
  propios. (Las Arc dedicadas sí lo tienen; las integradas de esta generación
  no.)
- La ocupación por motor **sí existe**, pero solo por el PMU de perf. Con
  `/proc/sys/kernel/perf_event_paranoid` en 2 hace falta `CAP_PERFMON`:
  `perf_event_open` devuelve `EACCES`, y **ni siquiera `intel_gpu_top` puede
  leerla** como usuario normal («Failed to initialize PMU! Permission denied»).

**Cambiado en `silux/providers/drm.py`**: entrada nueva en `DRIVERS_CIEGOS`
para `i915` y `xe`, siguiendo el mismo patrón que ya existía para `nvidia` y
`nouveau`. Ahora la página explica por qué faltan esos datos en vez de enseñar
cuatro fichas vacías sin motivo.

### Un atajo que probé y resultó falso

Parecía obvio que el dominio **«uncore» de RAPL** fuera el plano de potencia de
la gráfica en los Intel de sobremesa. **No lo es.** Se queda clavado en
3,2 W mientras el reloj del motor gráfico va de 350 a 1050 MHz:

```
ocupación    uncore   reloj GT
    50.6%     3.32W       350MHz
    51.4%     3.27W       983MHz
    49.7%     3.22W      1000MHz
    53.1%     3.16W      1050MHz
```

Habría sido un dato creíble y equivocado, que es justo lo que el proyecto
evita. Queda anotado en el comentario del código para que nadie lo intente
otra vez.

### Lo que sí funciona y no hacía falta tocar

Las frecuencias estaban bien. Los 350 MHz que se veían eran reales: la GPU
estaba en reposo. Con `glxgears` sube a 1100 MHz y el programa lo refleja.

---

## 3. Turbo — aquí no se reproduce, y por qué

En esta máquina el turbo sale **correcto**: `no_turbo=0`, activado, techo
4,3 GHz, base 2,9 GHz, BCLK 100 MHz. No hay nada que arreglar en un Intel.

Los tres `cat` que mencionó el Claude de casa son casi seguro estos, y son de
**AMD**:

```bash
cat /sys/devices/system/cpu/cpu0/acpi_cppc/highest_perf
cat /sys/devices/system/cpu/cpu0/acpi_cppc/nominal_perf
cat /sys/devices/system/cpu/cpufreq/boost
```

Revisado `silux/providers/cppc.py`: **solo lee `cpufreq/amd_pstate_max_freq` y
`boost`**. No mira `acpi_cppc/` en ningún momento, que es donde un Ryzen
publica el techo real. En esta máquina Intel esa carpeta existe y da
`highest_perf=255`, `nominal_perf=29`.

**No se ha tocado nada de esto**, porque sin un AMD delante cualquier cambio
sería a ciegas y el proyecto no funciona así. Es lo primero que conviene mirar
en casa.

---

## Un hallazgo que no se ha implementado

**UDisks2 ya tiene el SMART leído y lo entrega sin pedir contraseña.** Sin
ningún privilegio:

```
SmartPowerOnSeconds = 13 802 400  →  3 834 h
atributo 241: pretty = 25 261 890, unidad = MB
```

Hoy la pestaña de discos exige elevar permisos para las horas y el desgaste.
Con UDisks se podrían enseñar sin pedir nada, dejando el ayudante privilegiado
solo para lo que de verdad lo necesite.

No se ha hecho porque es un cambio de arquitectura y el encargo era no tocar
más de lo pedido. Queda apuntado como propuesta.

Dos avisos si algún día se aborda: libatasmart tiene sus **propias** ideas
sobre las unidades (asume 32 MiB para el 241, que en este disco acierta pero no
tiene por qué en otros), y no expone el valor crudo, solo el ya convertido. Así
que serviría para las horas y la temperatura sin discusión, pero para lo
escrito habría que seguir midiendo por marca igual que ahora.

---

# Segunda ronda: dos fallos vistos ya con la app corriendo

Con los cambios de arriba puestos aparecieron dos cosas que solo se ven en
pantalla, y las dos están arregladas.

## 4. La temperatura del disco salía un instante y desaparecía

**Lo que se veía:** al pulsar el botón de permisos, la temperatura del KIOXIA
aparecía durante un muestreo y en el siguiente volvía a «—». Los TBW y las
horas se quedaban; la temperatura no.

**Por qué:** el disco se reconstruye entero desde `/sys/block` en **cada**
muestreo, y `Disk` es un dataclass congelado. El diagnóstico SMART, en cambio,
se leía **una sola vez** —`if nombre not in self._salud`— porque son horas y
terabytes, que no cambian de un segundo a otro. La temperatura venía dentro de
esa lectura única y se asignaba dentro de ese mismo `if`, así que sobrevivía
exactamente a la muestra en la que se leyó.

En el Crucial de casa no se nota porque tiene `drivetemp` cargado y la
temperatura llega por hwmon en cada vuelta. Aquí no, y por eso solo se ve con
este equipo.

**Lo que se ha hecho** (`silux/providers/storage.py`):

- `self._temperatura` guarda la última temperatura que vino con el SMART, y se
  vuelve a poner en el disco en **cada** muestreo.
- Manda hwmon si publica algo: se relee siempre, así que es más fresca. La del
  SMART solo rellena el hueco.
- `self._leido_en` + `INTERVALO_SALUD = 30.0` + `_toca_releer()`: el
  diagnóstico deja de leerse una única vez y pasa a refrescarse cada 30 s. Así
  la temperatura no se queda congelada en el valor del arranque, y de paso los
  TBW se mueven mientras la ventana está abierta. Sigue sin ser un dato de
  cada segundo, que es lo que se quería evitar: son 2 lecturas por minuto
  contra 60.
- Un refresco que falla ya **no** borra lo que se sabía. Antes cualquier
  `OSError` metía el disco en `_sin_salud` para siempre; ahora solo se da por
  mudo el que **nunca** llegó a contestar, y al que ya contestó una vez se le
  deja el dato anterior y se reintenta al rato.

Ese último punto lo encontró un test, no yo: la primera versión sí perdía la
salud al fallar el refresco.

## 5. En la iGPU «no salía nada, ni ningún dato abajo»

**Lo que se veía:** las cuatro fichas de arriba de la UHD 630 —uso,
temperatura, consumo, VRAM— todas a «—», y aparentemente ninguna explicación.

**Por qué:** la explicación *sí* estaba —es el aviso de i915/`CAP_PERFMON` que
se añadió en la primera ronda— pero se pintaba al **final** de la página, por
detrás de todas las tarjetas. Para leer por qué las fichas de arriba están
vacías había que bajar hasta el fondo pasando por delante de todo lo demás. En
la práctica, no se lee.

**Lo que se ha hecho** (`silux/ui/pages/graphics.py`):

- `GpuSection` tiene ahora su propio hueco de avisos, justo debajo de las
  fichas, que es donde está el vacío que explican.
- `GraphicsPage._apply_notices` reparte: un aviso con ruta `gpus.N` va a la
  sección N; el que no lleva número —o lleva uno que no existe— se queda al
  pie de la página como antes. Nada se pierde por el camino.
- Se conserva la firma de avisos por sección, así que no se reconstruyen
  widgets en cada muestreo (regla 6 del CLAUDE.md).

Con dos gráficas —el caso del portátil híbrido— cada una enseña solo lo suyo.

## Tests

De 751 a **761**. Los diez nuevos:

- 6 en `tests/test_storage.py` — que la temperatura del diagnóstico sobrevive
  al muestreo siguiente, que hwmon manda sobre ella, que pasado el intervalo
  se vuelve a preguntar, que un refresco fallido no borra lo anterior y que un
  disco que nunca contestó se da por mudo sin insistir cada vuelta.
- 4 en `tests/test_gpu.py` — que el aviso de una gráfica va en su tarjeta y no
  al pie, que con dos gráficas cada una recibe el suyo, y que un aviso sin
  número o con un número que no existe no se pierde.

La cifra de `CLAUDE.md` está actualizada.

---

# Tercera ronda: la iGPU ya da uso y consumo de verdad

La segunda ronda dejó el aviso de Intel donde se ve, pero el aviso decía algo
que no había que hacer. Esta ronda lo quita y trae el dato.

## 6. El aviso mandaba al usuario a aflojar un cerrojo del kernel

El texto anterior decía que el contador «exige el permiso CAP_PERFMON o bajar
`/proc/sys/kernel/perf_event_paranoid`». Tres cosas mal, las tres comprobadas
en la máquina:

1. **Bajar `perf_event_paranoid` es una rebaja de seguridad de todo el
   sistema**, no un permiso para silux. A 0 cualquier proceso sin privilegios
   puede perfilar la máquina entera. Para ver un porcentaje no compensa.
2. **No decía a qué valor, y el intermedio no sirve.** Medido:

   ```
   perf_event_paranoid=1 → FALLA  rcs0-busy: errno 13 (Permission denied)
   perf_event_paranoid=0 → OK     rcs0-busy: delta 121941593 en 0.50s
   ```

3. **Aunque se bajara, seguiría saliendo «—»**: nadie en el código abría el
   PMU. El aviso mandaba a hacer algo que no cambiaba nada en pantalla.

## 7. El PMU se lee por el ayudante privilegiado, que ya existía

Silux ya tenía la solución montada: el ayudante que corre como root por polkit
y que ya pide la contraseña una vez para el SMART de los discos. Es un proceso
que sigue vivo hablando por tubería, así que puede abrir el contador una vez,
mantenerlo abierto entre muestreos y devolver el acumulado en cada vuelta.

Coste para el usuario: **cero**. Ni un diálogo nuevo —se aprovecha el de los
discos— ni un solo cambio en la configuración del sistema. Quien no eleve
permisos ve lo de siempre.

**En el ayudante** (`silux/privileged/helper.py`), acción `gpu_pmu`. Es la
única que **no lleva parámetros**: el cliente no manda ni rutas, ni nombres de
evento, ni números. El ayudante enumera `/sys/bus/event_source/devices`, se
queda con lo que encaja en dos patrones cerrados y traduce el nombre a un
`config` leyendo el propio sysfs del kernel. Lo que puede abrir:

- `i915` y `xe_<ranura>` → solo eventos `(rcs|bcs|vcs|vecs|ccs)N-busy`.
  Quedan fuera `-sema`, `-wait`, `interrupts`, `rc6-residency` y las
  frecuencias, que ya salen por sysfs.
- `power` (RAPL) → **solo** `energy-gpu`. Los otros tres planos —paquete,
  núcleos y memoria— ya se leen por powercap sin privilegios.

Y `sample_period` va a cero, o sea que los eventos **cuentan y no muestrean**:
no hay búfer de muestras, ni pilas de llamadas, ni direcciones, ni actividad
de ningún proceso concreto. Es exactamente lo que enseña `intel_gpu_top`.

**En el proveedor** (`silux/providers/drm.py`), `GpuState` recibe el cliente
compartido —el colector ya lo inyecta solo a quien declare el parámetro— y
resta contra la vuelta anterior. La primera lectura solo fija la referencia y
no da número, igual que el uso de CPU.

## 8. El consumo sí existía, y me lo había dado por perdido

En la primera ronda escribí que una Intel no publica su consumo «de ninguna
forma». **Era falso**, y lo cazó `intel_gpu_top`, que enseña una columna
`Power W / gpu` siguiendo la carga.

El motivo del error: miré `/sys/class/powercap/`, que en este equipo publica
`package-0`, `core`, `uncore` y `dram` — y ninguno de los cuatro es la
gráfica. (El `uncore` fue el falso amigo de la primera ronda: se queda clavado
en 3,2 W mientras el motor gráfico va de 350 a 1050 MHz.)

El plano de la gráfica es **RAPL PP1**, y en estos Intel **solo asoma por el
PMU**, como evento `energy-gpu`. Por sysfs no está.

De paso salió un detalle del formato: i915 escribe sus eventos como
`config=0x2000`, pero RAPL los escribe como `event=0x04`, que no es lo mismo.
Cada PMU publica en `format/` en qué bits de `config` va cada campo
(`event -> config:0-7`), y hay que mirarlo en vez de darlo por sabido. Sin
eso, `energy-gpu` no se abría y las escalas salían vacías.

## Contrastado contra la referencia

Con `glxgears` delante, `intel_gpu_top` y silux midiendo a la vez sobre la
misma máquina:

| | `intel_gpu_top` | silux |
|---|---|---|
| Render/3D | 37,2 – 65,0 % (≈40 en régimen) | 38,4 – 42,8 % |
| Consumo GPU | 1,89 – 4,72 W (≈2,2 en régimen) | 2,25 W |

Coinciden. No es un número plausible: es el mismo número.

## 9. El aviso ahora sigue al estado

Se sacaron `i915` y `xe` de `DRIVERS_CIEGOS`, que la lee un proveedor
**estático** —corre una sola vez— y por tanto no podía cambiar cuando el
usuario eleva permisos a mitad de sesión. El aviso lo pone ahora `GpuState`,
que es dinámico, y dice una de tres cosas:

- **Sin permisos** (`Need.ROOT`): el uso y el consumo los llevan contadores
  del kernel que no se leen sin permisos, y la temperatura no la publica.
- **Leyendo** (`Need.HARDWARE`): solo falta la temperatura, y se explica por
  qué —el nodo DRM no trae hwmon y el PMU no tiene evento térmico—.
- **Kernel sin contadores** (`Need.DRIVER`): para gráficas cuyo PMU no
  publique ocupación.

Hay un test que vigila que **ninguno** de los tres vuelva a nombrar
`paranoid`, `CAP_PERFMON` ni `sysctl`.

## Lo que sigue sin salir, y por qué

**La temperatura.** Es lo único que una Intel no da por ningún camino: el nodo
DRM no tiene `hwmon` y su PMU no publica ningún evento térmico. La del paquete
del procesador incluye físicamente la iGPU, pero no es un sensor de la
gráfica, y ponerla ahí sería inventarse un dato.

## Cuidado con no romper lo que ya iba

- **AMD y NVIDIA no cambian.** `_uso_intel` solo actúa si el driver es `i915`
  o `xe`; `gpu_busy_percent` de amdgpu se sigue leyendo antes y por su cuenta.
- **Una máquina sin contadores deja de preguntarse.** El primer `unsupported`
  enmudece al proveedor: en un equipo AMD es **una** petición en toda la
  sesión, no una por muestreo. Hay un test que lo cuenta.
- **Un fallo suelto no lo da por perdido**, que no es lo mismo: la tubería se
  puede cortar y el usuario volver a autorizar.
- **Los vatios solo se le cuelgan a la integrada.** RAPL PP1 es el plano que
  el procesador reserva para su gráfica; dárselos a una dedicada sería
  atribuirle el consumo de otra.
- **Un solo cliente.** `GpuState` recibe el que reparte el colector y nunca
  crea uno: dos serían dos veces la contraseña para lo mismo.

## Tests

De 761 a **793**. Los 32 nuevos, en dos sitios:

- `tests/test_privileged.py` — que la acción está en el contrato, que los
  patrones del ayudante y del contrato coinciden (como ya se hacía con los
  MSR), que el patrón del PMU no deja salirse del directorio (`..`,
  `i915/../cpu`, `tracepoint`…), que solo se abren eventos de ocupación y no
  `-sema`, `-wait` ni `rc6-residency`, que de RAPL solo pasa `energy-gpu`, y
  que el `event=`/`config=` se traduce con el formato que publica el kernel.
- `tests/test_gpu.py` — la cuenta completa: primera lectura sin número,
  segunda con porcentaje, contador reiniciado, recorte al 100 %, los vatios
  desde la escala, que la energía no se cuela como un motor más, que sin
  permisos no se pregunta nada, que una máquina sin contadores enmudece, que
  un fallo suelto no, el reparto render/video, el máximo en vez de la suma, el
  nombre del PMU de `xe` con su ranura, y que el aviso sigue al estado.

---

# Cuarta ronda: el botón que faltaba, más datos y el amarillo

Tres cosas vistas con la app delante.

## 10. En Gráficos no había forma de dar los permisos

El aviso decía «Requiere permisos» y **no traía botón**. Los únicos botones
estaban en Memoria y en Almacenamiento, así que había que ir a otra página, dar
los permisos allí y volver — adivinando dónde estaban.

`Notice` acepta ahora un botón dentro del propio aviso, que es donde hace
falta: quien lee por qué falta un dato es quien quiere arreglarlo. Solo lo
lleva `Need.ROOT`; un botón que no arregla nada es peor que ninguno.

La señal sube de `GpuSection` a `GraphicsPage` y de ahí a `app.py`, que ya la
tenía cableada para las otras dos páginas. Como los avisos se crean y se
destruyen, los botones se preguntan cada vez en vez de guardarse (propiedad
`elevation_buttons`), y al pulsar cualquiera de los tres se quedan los tres
esperando: es un solo ayudante para todos.

## 11. Todos los avisos se pintaban del mismo amarillo

`QFrame#Notice` llevaba `border-left: 3px solid warn` sin distinguir nada. Así,
«esta gráfica no trae sensor de temperatura» —que no va a cambiar nunca— se
leía igual de urgente que algo que sí se arregla.

Ahora la banda va por tono:

| Motivo | Tono | Por qué |
|---|---|---|
| `ROOT`, `DRIVER`, `DATABASE` | ámbar | el usuario puede hacer algo |
| `HARDWARE`, `PLATFORM` | gris | es así y ya está |
| `ERROR` | rojo | eso es un fallo nuestro |

Se hace con una propiedad dinámica de Qt puesta **antes** de que se aplique la
hoja de estilos, para no tener que repintar a mano.

## 12. Más datos de la iGPU, comparando con `intel_gpu_top`

De lo que enseña la herramienta de referencia, lo que faltaba y ya está:

**El reposo (RC6).** El porcentaje del intervalo que la gráfica pasa dormida
del todo. Sale de `gt/gt0/rc6_residency_ms` y **no cuesta permisos**: es lo que
evita que la página esté vacía del todo antes de autorizar nada. Aquí marca
71-81 % en escritorio parado.

Ojo con esto: **no es «cien menos el uso»**. Entre trabajar y dormir hay un
término medio —encendida y sin trabajo— que gasta y que no cuenta como reposo.
Juntarlos haría que el dato dejara de significar nada, y hay un test que lo
deja escrito.

**Los motores, uno por uno.** Una tarjeta moderna no es un bloque «al 40 %»:
son varias unidades independientes. Tarjeta nueva «Motores gráficos» con el
nombre, la función, el uso y lo que sabe hacer cada uno:

```
  En reposo            81.4 %
    bcs0               —  copia
    rcs0               —  render
    vcs0               —  video · hevc, sfc
    vecs0              —  video-enhance
```

Las capacidades salen de `engine/*/capabilities` y **no las publica nadie
más**: `hevc` dice que decodifica H.265 por hardware y `sfc` que trae
escalador. Ni Vulkan ni OpenGL lo cuentan.

La tarjeta se esconde entera en AMD y NVIDIA, donde el kernel no enumera
motores: una tabla vacía no explica nada.

El resumen de arriba sigue cogiendo el **máximo** y no la suma, que con varios
motores pasaría del 100 % sin que la tarjeta esté a tope de nada.

### Lo que se ha dejado fuera, y por qué

- **El ancho de banda del IMC** (1427 MiB/s de lectura en la captura). Es el
  controlador de memoria **entero**, con el tráfico de la CPU dentro.
  `intel_gpu_top` lo enseña porque en una integrada la RAM del sistema hace de
  VRAM, pero colgárselo a la gráfica sería atribuirle tráfico que no es suyo.
  Su sitio sería la página de Memoria, y eso es otra función.
- **El desglose por proceso.** Es la regla del proyecto: esto no es un
  administrador de tareas.
- **`irqs/s` y `MI_SEMA`/`MI_WAIT`.** Muy de nicho para el hueco que ocupan.

### Comprobado de paso: la frecuencia estaba bien

Los 350 MHz que se ven en reposo son `gt_act_freq_mhz`, la que va de verdad;
`gt_cur_freq_mhz` marcaba 833, que es la pedida. `_intel_hz` ya prefiere `act`.
No era un fallo.

## Tests

De 793 a **814**. Los 21 nuevos: los motores con su función y sus capacidades,
que un motor desconocido no se invente una, que el uso del PMU se pega a cada
motor y que un motor parado marca 0 y no un hueco; el reposo con su primera
lectura sin número, su porcentaje, su recorte y su contador reiniciado; que el
aviso de permisos trae botón y los demás no, que pulsarlo pide los permisos y
que desaparece solo cuando ya los hay; y el reparto de tonos con su
comprobación de que la hoja de estilos define los tres.

---

# Quinta ronda: la tabla que se cortaba y los códecs

## 13. La columna «Uso» enseñaba «12…»

Es el mismo fallo que ya estaba escrito en `CLAUDE.md` para el árbol de
sensores, cometido otra vez en `Table`: los anchos se calculan al montar la
tabla, **con las celdas vacías**, y los valores llegan después. La columna se
quedaba con el ancho de su cabecera —«USO», tres letras— y `ElidingLabel`
recortaba a «12…».

Arreglado igual que allí: `_ajustar_anchos` mide el texto que de verdad lleva
cada columna, con la fuente de esa columna (la primera va en la tipografía de
la interfaz y las demás en monoespaciada), y ensancha si hace falta. **Nunca
encoge**, o la tabla bailaría a cada muestreo. Hay un tope para que un valor
absurdo no estire la tabla sin fin.

Esto arregla de paso todas las demás tablas del programa.

## 14. «En reposo» estaba pegado a la cabecera de la tabla

Se leía como una fila más, justo encima del encabezado. Ahora van separados
por un `Divider` con aire a los dos lados: el reposo habla de la tarjeta
entera y la tabla de cada motor, que son dos cosas distintas.

## 15. Los códecs de video, que es lo que se pedía

Nueva tarjeta **«Códecs de video por hardware»**. Sale de **VA-API**, que es
lo que contesta `vainfo`, preguntado por ctypes desde el proceso aparte que ya
existía para OpenGL, Vulkan y OpenCL.

En esta UHD 630:

| Códec | Decodifica | Codifica | Profundidad |
|---|---|---|---|
| HEVC | ✓ | ✓ | 10 bits |
| H.264 | ✓ | ✓ | 8 bits |
| VP9 | ✓ | · | 10 bits |
| VP8 | ✓ | ✓ | 8 bits |
| MPEG-2 | ✓ | ✓ | 8 bits |
| VC-1 | ✓ | · | 8 bits |
| JPEG | ✓ | ✓ | 8 bits |

Coincide con `vainfo` renglón a renglón. Sin AV1, que esta generación no lo
trae — y eso también es un dato.

**Decodificar y codificar se enseñan por separado a propósito**: casi todas
las tarjetas modernas leen AV1 y muy pocas lo escriben, así que juntarlo en un
«soporta AV1» sería mentir la mitad de las veces.

### Lo bueno de VA-API: no hay que adivinar de quién habla

`vaGetDisplayDRM` se abre sobre **un nodo de render concreto**, y ese nodo
cuelga del dispositivo PCI de la tarjeta. Así que el resultado va atado a una
gráfica sin ambigüedad — justo lo contrario de OpenGL y OpenCL, que no dicen
de quién hablan y obligaron a casar por el nombre del fabricante en un
portátil híbrido. El reparto usa `amdgpu.render_node()`, que ya existía y pese
al nombre vale para cualquier driver.

Vale para las tres marcas: Intel con iHD, AMD con radeonsi y NVIDIA con
`nvidia-vaapi-driver`. Donde no haya VA-API, la tarjeta se esconde entera: una
tabla vacía se leería como «esta gráfica no acelera nada», que es lo contrario
de lo que quiere decir.

### Un susto por el camino

La primera versión **tiraba el proceso con SIGSEGV**. `vaQueryConfigProfiles`
y `vaQueryConfigEntrypoints` se llamaban sin declarar `argtypes`, así que
ctypes truncaba el puntero del display a 32 bits. El resto de la biblioteca
perdona porque solo devuelve enteros; estas dos escriben en memoria de quien
llama. Está apuntado en un comentario justo encima.

### Memoria

Sigue en **165 MB** con todo desplegado, de 300 de techo: el driver iHD se
carga en el proceso hijo y muere con él, que es exactamente para lo que está
montado así.

## Tests

De 814 a **827**. Los 13 nuevos: que decodificar y codificar no se confunden,
que los perfiles de un mismo códec se juntan en una fila, que la profundidad
es la mayor que admita, que un punto de entrada que no es ni leer ni escribir
no cuenta, que un perfil que no está en la tabla se ignora en vez de
inventarse un nombre, el orden de presentación, que cada tarjeta recibe los
códecs de **su** nodo y no los del de al lado, y los tres del ancho de columna
—que se ensancha, que no se encoge y que un valor desmesurado no estira la
tabla sin fin—.

Se corrigió además `tests/test_gpu_apis.py`, que comparaba contra el
diccionario vacío de `consultar()` y ahora lleva `vaapi` dentro. Si faltara
una clave, quien la lea se llevaría un `KeyError` justo en el camino de «no se
pudo preguntar».

---

## Ficheros tocados

```
silux/smart.py                  unidad de escritura por fabricante
silux/providers/storage.py      pasar fabricante y modelo; caché de temperatura
                                y refresco del diagnóstico cada 30 s
silux/render.py                 el resumen de VRAM ya no rellena con el total
silux/ui/pages/graphics.py      la ficha de VRAM pide el total por su nombre;
                                los avisos, debajo de las fichas de su gráfica
silux/cli.py                    lo mismo en el volcado de terminal; reposo y
                                motores en la sección de gráficas
silux/model.py                  GpuEngine, VideoCodec y sus campos en Gpu
silux/gpuapi.py                 VA-API por ctypes, en el proceso de siempre
silux/providers/gpu_apis.py     reparte los códecs por nodo de render
silux/ui/widgets.py             Notice con botón y con tono; anchos de Table
silux/ui/theme.py               la banda del aviso, por tono
silux/ui/app.py                 conecta el botón de Gráficos
silux/providers/drm.py          centinelas del enlace PCIe; GpuState lee el PMU
                                por el ayudante y el aviso sigue al estado
silux/privileged/helper.py      acción gpu_pmu: contadores de ocupación y el
                                plano de energía de la gráfica
silux/privileged/protocol.py    la acción y sus dos patrones, para auditarlos
silux/privileged/client.py      gpu_pmu() y la excepción PmuUnsupported
tests/test_smart.py             5 tests de la unidad de escritura
tests/test_gpu.py               6 tests de memoria, enlace y aviso
                                + 4 de dónde se pinta cada aviso
tests/test_storage.py           6 tests de la temperatura del diagnóstico
tests/test_privileged.py        10 tests del contrato del PMU
tests/test_gpu.py               22 de la cuenta y del aviso, y 21 más de
                                motores, reposo, botón y tonos
CLAUDE.md                       la cifra de tests: 827
```

## Lo que NO se ha tocado, a propósito

- **Nada de AMD ni del CPPC**, por lo dicho arriba.
- **No se ha añadido la ocupación por RC6.** Funciona —da 99,9 % con carga y
  55-71 % en reposo— pero como «Uso» mentiría: un escritorio parado no está al
  60 %. Sería honesto solo con otra etiqueta, algo como «tiempo despierto», y
  eso ya es una decisión de producto, no un arreglo.
- **No se ha cambiado la etiqueta «Memoria de video»** en las integradas. Esos
  11,6 GB salen de sumar los *heaps* `DEVICE_LOCAL` de Vulkan, y en una
  integrada la RAM del sistema **es** device-local: son memoria compartida, no
  VRAM. Llamarlo «Memoria de video» despista, pero cambiarlo toca la página y
  se sale del encargo.
- **La temperatura de la iGPU**, que no existe por ningún camino.
- **Ningún commit.**
