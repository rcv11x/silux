# Propuesta: el uso de las gráficas Intel que hoy no se lee

18 de noviembre de 2026. Solo propuesta, sin código. Son dos cosas
distintas:

- **A.** Dos cambios en el ayudante de permisos. **Tocan privilegios**: los
  revisa el autor antes de escribir nada (CLAUDE.md).
- **B.** El uso por programa sacado de DRM fdinfo, sin permisos.

Viene de los fallos 6 y 16 de [propuesta-graficas.md](propuesta-graficas.md)
(I2 e I9). La parte que no toca el ayudante ya está en `oficina`: la Arc pide
su propio PMU y, mientras el ayudante no lo abre, se queda sin uso, con una
nota que lo dice. No enseña el de la integrada.

## A. El ayudante

Hoy (`silux/privileged/helper.py:98-99`):

```python
PMU_GPU = re.compile(r"^(i915|xe_[0-9a-f]{4}_[0-9a-f]{2}_[0-9a-f]{2}\.[0-9a-f])$")
PMU_EVENT = re.compile(r"^(rcs|bcs|vcs|vecs|ccs)\d+-busy$")
```

### A1. El PMU de una Arc con `i915`

**Qué falla.** i915 llama «i915» solo al PMU de la integrada. Cualquier otra
tarjeta se llama «i915_» más su ranura, con los dos puntos cambiados por
guiones bajos: «i915_0000_03_00.0». Lo hace `i915_pmu.c`: `is_igp()` mira
si la ranura es 0000:00:02.0, y si no lo es usa `kasprintf("i915_%s",
dev_name(...))` y `strreplace(':', '_')`. El patrón de arriba no la admite.

**Propuesta.** Una línea en el patrón:

```python
PMU_GPU = re.compile(
    r"^(i915|i915_[0-9a-f]{4}_[0-9a-f]{2}_[0-9a-f]{2}\.[0-9a-f]"
    r"|xe_[0-9a-f]{4}_[0-9a-f]{2}_[0-9a-f]{2}\.[0-9a-f])$")
```

- Los eventos son los mismos (`rcs0-busy`…), igual que con la integrada.
- El nombre sigue saliendo de enumerar `/sys/bus/event_source/devices`
  dentro del ayudante. El cliente no puede pedir uno a mano.
- El número de descriptores sigue con el mismo tope por familia.

**Riesgo.** El mismo que hoy con «i915»: solo lectura de contadores de
ocupación, y un PMU más por cada Arc.

**Cómo se comprueba.** Con un volcado del portátil con Arc A e integrada,
el número 5 de la lista de propuesta-graficas.md. El volcado tiene que
llevar `/sys/bus/event_source/devices/*/{type,format,events}`, que es lo que
graba la fase 0.

### A2. El PMU de `xe`

**Qué falla.** El PMU de xe (Linux 6.15) no tiene eventos `*-busy`. Tiene
`engine-active-ticks` y `engine-total-ticks`, y se elige el motor con
`engine_class`, `engine_instance` y `gt` dentro de `config`; los campos
salen de `format/`. Además cuenta en ticks, no en nanosegundos: el uso es
activos entre totales, en la misma ventana. El patrón de eventos de hoy no
casa con ninguno, y con xe no hay uso nunca.

**Propuesta.**

- Admitir en la familia `gpu`, solo para un PMU `xe_*`, los eventos
  `engine-active-ticks` y `engine-total-ticks`.
- El ayudante arma `config` leyendo `format/engine_class`,
  `format/engine_instance` y `format/gt` del propio PMU. No viene nada del
  cliente.
- Los motores, de la enumeración que xe publica en el nodo PCI.
- El cliente calcula, para cada motor, la diferencia de activos entre la
  diferencia de totales.

**Riesgo.** Sigue siendo solo lectura. Pero hay más código dentro del
ayudante (leer `format/` y armar `config`), y está **sin probar**: no hay
aquí ninguna gráfica con xe. Las rutas y los nombres salen de
`Documentation/gpu/xe/xe_pmu.rst` y de `xe_pmu.c` (6.15); **es dudoso** que
`gt` vaya en el mismo campo en todas las versiones.

**Cómo se comprueba.** Con el volcado de una B580 o un Lunar Lake (números
4 y 6 de la lista), que lleve `format/` y `events/`.

**Recomendación.** A1 sí, ya: es una línea, está en el código del kernel
desde hace años y deja de esconder un dato que existe. A2, cuando llegue el
volcado de una gráfica con xe, no antes.

## B. El uso por programa, sin permisos (DRM fdinfo)

**Qué es.** Desde Linux 5.19 en i915, y también en amdgpu, xe y nouveau, cada
descriptor abierto de `/dev/dri/*` publica en `/proc/PID/fdinfo/FD` cuánto ha
usado ese cliente cada motor (`Documentation/gpu/drm-usage-stats.rst`). Se lee
sin permisos para los procesos del propio usuario.

**Medido aquí** (i5-10400, UHD 630, i915, kernel 7.3.3), sin permisos:

```
plasmashell, fd 18 → /dev/dri/renderD128
drm-driver:     i915
drm-pdev:       0000:00:02.0
drm-engine-render:          1300038628 ns
drm-engine-copy:            0 ns
drm-engine-video:           0 ns
drm-engine-video-enhance:   0 ns
```

Son nanosegundos acumulados por motor, con los mismos cuatro nombres de las
barras de «Ahora mismo». Restando entre dos muestreos sale el porcentaje de
ese programa. En 2 s en reposo, plasmashell dio 0,0 %.

**El límite, medido también.** **kwin no se deja leer**:
`/proc/3031/fd` da «Permission denied». kwin_wayland tiene `CAP_SYS_NICE`
(CapEff `0x800000`), y un proceso con capacidades no es «dumpable», así que
su `/proc/PID/fd` es de root aunque sea de tu usuario. Y el compositor es
justo quien más dibuja. Tampoco se ven los programas de otros usuarios ni
los de sistema.

**Qué se propone enseñar.**

- En Gráficos, plegado y solo sin permisos: «Lo que usan tus programas», con
  una fila por programa y motor (render, video…) y el porcentaje de cada uno.
- El pie dice de dónde sale y lo que falta: «De los programas de tu usuario
  que se dejan leer; el compositor y los de otros usuarios no salen. El
  total de la gráfica, con permisos.»
- **No** se suma para rellenar las barras de «Ahora mismo» sin permisos:
  sin el compositor, el total sale por debajo del real, y sería una cifra
  creíble y falsa. Las barras se quedan con su candado.

**Coste.** Recorrer `/proc/*/fd` en cada muestreo son unos cientos de
`readlink`. Se haría solo con la sección plegable abierta, y como el resto,
fuera del hilo de la interfaz.

**Privacidad.** Son nombres de programas del usuario: no van al informe ni a
la imagen para compartir, y `--anonimo` no los enseña.

**Recomendación.** Útil para responder «¿qué está usando la gráfica?» sin
contraseña, que es una pregunta que se hace de verdad. Pero es más un
monitor de procesos que un dato del hardware, y CLAUDE.md dice que silux no
es un administrador de tareas. El autor decide si cabe; si cabe, después de
la 0.4.
