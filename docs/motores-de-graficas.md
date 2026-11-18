# Los motores de cada gráfica: qué se mide y de dónde sale

Lo que enseña «Ahora mismo» en Gráficos, debajo de la memoria, el consumo y
el bus: una barra por motor que **esa** gráfica deja medir. Lo decide
`render.engine_levels`; lo que el driver no publica lo nombra al pie
`render.engine_gaps`; lo que está y guarda un permiso lleva candado. Tests:
`tests/test_barras_de_motores.py`.

Las barras, con sus nombres:

| Barra | Qué cuenta |
|---|---|
| Render / 3D | el motor gráfico: juegos, el escritorio, también el cómputo que va por él |
| Video (codificar y decodificar) | el motor de video entero, cuando ver y grabar van por el mismo y con una cifra |
| Decodificar video / Codificar video | cada uno aparte, donde son motores distintos y se miden aparte |
| Cómputo, Mejora de video, Copia | los que Intel enumera además |

Nunca se reparte un dato entre dos barras: si el driver da una cifra para
codificar y decodificar juntos, sale una barra.

## Qué da cada driver

| Driver | Render / 3D | Video | Permisos | Al pie, si falta |
|---|---|---|---|---|
| `amdgpu` (dedicada o APU) | `gpu_busy_percent` | una barra: `vcn_busy_percent` (Linux 6.10) o, antes, `average_mm_activity` de `gpu_metrics` | no | el video, si no hay ninguna de las dos fuentes |
| `radeon` (AMD antiguas) | — | — | — | los dos |
| `i915` (integrada) | un motor por tipo (`engine/` del nodo DRM): render, video, mejora de video, copia y cómputo | el motor `vcs`: decodifica y codifica | sí: el uso sale del PMU del kernel | nada: lo que falta es por permisos y lleva candado |
| `i915` (Arc dedicada) | los motores se enumeran | igual | el PMU propio de la Arc, que el ayudante todavía no abre | nada: lo dice su aviso (`prov.drm.arcusage`) |
| `xe` | no se lee todavía | no se lee todavía | — | nada: el uso existe y silux no lo lee (`docs/propuesta-uso-de-graficas.md`, A2) |
| `nvidia` (propietario, NVML) | `utilization.gpu` | dos barras: NVDEC y NVENC (`nvmlDeviceGetDecoderUtilization`, `…EncoderUtilization`) | no | el codificador o el decodificador, si NVML no lo da |
| `nouveau` | — | — | — | los tres |

Una gráfica dormida (`power/runtime_status` en `suspended`) no tiene barras
ni pie: no se le ha preguntado nada, y la página dice «En reposo».

### AMD: por qué el video es una sola barra

Desde el VCN 4.0 (RDNA 3), amdgpu manda la decodificación por la misma cola
que la codificación (la «cola unificada»). Comprobado en la RX 9070 XT
(VCN 5.0, el 18 de noviembre), mirando el `fdinfo` de cada proceso:

- mpv decodificando por VA-API sube `drm-engine-enc` (762 ms en 2 s), y
  `drm-engine-dec` no aparece;
- ffmpeg codificando con `hevc_vaapi` sube el mismo `drm-engine-enc`.

Y las cifras de toda la tarjeta, `vcn_busy_percent` y `average_mm_activity`,
son una sola. No hay de dónde sacar ver y grabar por separado: una barra. En
una RDNA 1 o 2 (VCN 2 o 3) el `fdinfo` sí separa `dec` y `enc`, pero es por
proceso y la cifra de la tarjeta sigue siendo una; no se ha probado.

La copia (SDMA) y el JPEG no tienen cifra de tarjeta en amdgpu, solo por
proceso: no salen.

### NVIDIA

NVENC y NVDEC son motores físicos distintos y NVML los mide por separado, de
ahí las dos barras. **Escrito sin una NVIDIA delante**: la llamada lleva dos
punteros (el uso y su periodo de medida), y el test comprueba que se pasan
los dos. Para contrastar con una tarjeta puesta: `nvidia-smi dmon -s u`,
columnas `sm`, `enc` y `dec`.

## Cómo se saca el uso medio en cada uno

Una barra que se refresca cada segundo tiene que decir cómo fue ese segundo,
no un instante suelto. Cada driver lo da de una forma, y se lee lo justo para
eso:

- **AMD**: `gpu_busy_percent`, `mem_busy_percent` y `vcn_busy_percent` son lo
  que midió el firmware en sus últimos milisegundos. En la RX 9070 XT, una
  lectura suelta salta entre 59 y 100 con la gráfica haciendo lo mismo. El
  hilo de muestreo los lee varias veces entre muestra y muestra
  (`GpuState.between_samples`) y la foto lleva la media. Solo despierta el
  hilo si hay una AMD despierta, y nunca lee una tarjeta dormida. Es lo que
  hace MangoHud: con vkcube, MangoHud dio 80-86 % y la media de silux lo
  mismo, cuando una lectura por segundo iba de 15 a 93.
- **Intel**: el PMU del kernel da contadores acumulados (nanosegundos de
  motor ocupado). Se lee una vez por muestra y se resta la anterior: la media
  exacta del intervalo, sin lecturas de más.
- **NVIDIA**: NVML ya devuelve una media, la de su propio periodo (entre 1/6
  y 1 s según la tarjeta; el de NVENC y NVDEC viene con la cifra). Una
  lectura por muestra.

## Lo que no se lee, a propósito

- El uso **por programa** (`fdinfo`): es otra pregunta, cuál de mis programas
  usa la gráfica, y está en `docs/propuesta-uso-de-graficas.md`, B.
- MangoHud 0.8.4, en amdgpu, mira además el `fdinfo` del propio juego; su
  «GPU» es la de la tarjeta entera, la misma que lee silux.
