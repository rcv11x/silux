# Propuesta: la página de Gráficos con las gráficas que no se han probado

Investigación y propuesta del 18 de noviembre de 2026, sin tocar el código
de la aplicación. No es el estado del programa: es lo que habría que hacer y
por qué.

Hoy Gráficos está probado con dos piezas: una Radeon RX 9070 XT (`amdgpu`,
RDNA4) y una UHD 630 (`i915`, Comet Lake). Aquí se mira qué pasa con el
resto:

- **AMD:** las APU, y las GCN con `radeon` y con `amdgpu`.
- **Intel:** `xe` frente a `i915`, y las Arc dedicadas.
- **NVIDIA:** el driver propietario por NVML, y nouveau.
- **Equipos con dos gráficas.**

**Cómo está hecho.** Cuatro investigaciones en paralelo, cada una leyendo el
código de silux y contrastando con el código del kernel por etiqueta, con su
documentación (docs.kernel.org y los ABI de `Documentation/ABI/testing`) y,
en NVIDIA, con `nvml.h` y la documentación de NVML. Cada afirmación lleva su
fuente. Lo que no se pudo confirmar va marcado **dudoso** y no se da por
bueno. Los fallos más graves los he vuelto a mirar en el código antes de
ponerlos arriba. Ningún dato de equipo es inventado: aquí no hay ninguna
NVIDIA, Arc, APU ni GCN, y por eso nada de esto lleva fixture.

**Cómo citar los fallos.** Cada informe numera los suyos: **AMD-n** (AMD),
**In** (Intel), **Nn** (NVIDIA) y **B-n** (equipos con dos gráficas y
revisión general del código). La sección 2 los junta y los ordena.

## Resumen

1. **Lo que más urge no depende del fabricante.** En un portátil con dos
   gráficas, silux despierta la dedicada en cada muestreo. Lee el enlace
   PCIe, que desde el kernel 6.18 saca la tarjeta de D3cold, y además
   consulta NVML. Después enseña la temperatura y el consumo de una tarjeta
   que solo está encendida porque silux la ha despertado. No se mira
   `power/runtime_status` en ningún sitio (B-1, N1, AMD-15).
2. **Hay datos falsos en pantalla con piezas muy comunes:**
   - En una APU, «Consumo» es el del procesador entero (AMD-1).
   - El «punto caliente» de una APU es la temperatura del SoC (AMD-3).
   - El uso de video de una APU con un kernel anterior a 6.10 sale cien
     veces mayor (AMD-2).
   - Cualquier Arc dice «PCIe 1.0 × 1» (I1).
   - Una Arc con `i915` junto a una integrada enseña el uso de la integrada
     (I2).
   - Una Arc con `xe` dice que no publica su temperatura (I3).
   - `gpu_metrics` 1.0 se lee con las posiciones de la 1.1 (B-2).
3. **La gráfica «principal» sale solo de `boot_vga`.** Inicio y la imagen
   de compartir usan siempre `gpus[0]`, así que en un portátil para jugar
   enseñan la integrada (B-9). switcheroo-control ya lo dice por D-Bus y sin
   permisos.
4. **Datos que existen y no se leen:**
   - Casi todo lo de `xe`: la frecuencia real, motivos de freno, reposo,
     motores, uso y unidades (I5-I9, I12).
   - Las tablas `gpu_metrics` de las APU más vendidas: Renoir, Cezanne,
     Steam Deck y Strix (AMD-7).
   - El reloj y el voltaje con `radeon` (AMD-8).
   - El consumo de las Arc, que solo publican energía (I10).
   - La VRAM ocupada de una Arc (I13).
5. **NVIDIA (NVML) está bien escrita en lo delicado:** firmas, estructuras y
   errores que dan `None` y no 0. Pero calla cuando NVML falla (N2), tiene
   los motivos de recorte sin traducir (N3) y usa funciones obsoletas desde
   NVML 13 (N5, N6). Con nouveau la página promete una temperatura que desde
   Turing con GSP no existe (apartado 1.3, «nouveau en Turing y posteriores»).
6. **No se puede validar casi nada de esto sin volcados reales.** Antes hay
   que arreglar las herramientas:
   - `tools/volcar_gpu.py` y `volcar_equipo.py` despiertan la tarjeta al
     volcarla.
   - Están ciegas a `xe`.
   - No graban NVML.

## 1. Qué se lee de cada gráfica

Las tablas de cada informe, tal como salieron, con la fuente de cada dato.
Cada informe tiene sus propias referencias internas («sección 3», «punto
1»), que remiten a su propio texto. Los números de fallo van con el prefijo
del informe (AMD-n, In, Nn, B-n).

### 1.1 AMD: APU, y GCN con `radeon` y con `amdgpu`
Investigado el 18 de noviembre de 2026, solo leyendo: el código de silux en
la rama `oficina` (7ff2f73) y el fuente del kernel. Del kernel se bajaron los
archivos de `master` (en ese momento, v7.4-rc3) y de `v5.15`, y se buscó en
ellos con grep. Las versiones salen de comparar etiquetas: un dato «existe
desde vX» porque está en vX y no en la etiqueta anterior.

Abreviaturas de las fuentes:

- **K** = `https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/`
  (con `@v5.15` cuando la fuente es esa etiqueta).
- **T** = `https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=`
- **D-thermal** = https://docs.kernel.org/gpu/amdgpu/thermal.html
- **D-misc** = https://docs.kernel.org/gpu/amdgpu/driver-misc.html
- **D-apu** / **D-dgpu** = `Documentation/gpu/amdgpu/apu-asic-info-table.csv` y
  `dgpu-asic-info-table.csv`: qué IP (GC, MP1) lleva cada producto.

Lo que no tiene fuente va marcado **dudoso**.

#### Qué familia es cada cosa (D-apu, D-dgpu, K`amd/pm/swsmu/amdgpu_smu.c` `smu_set_funcs`)

| Producto | GC | MP1 → backend | `gpu_metrics` |
|---|---|---|---|
| Kaveri/Kabini/Mullins (CIK APU) | 7 | `legacy-dpm/kv_dpm.c` | no (GC < 9.1) |
| Carrizo/Stoney | 8 | powerplay smu8 | no |
| Raven/Picasso/Raven2 (Ryzen 2000G/3000G) | 9.1.0/9.2.2 | powerplay `smu10_hwmgr.c` | el archivo existe y su lectura falla: smu10 no implementa `get_gpu_metrics` (`amd_powerplay.c` `pp_get_gpu_metrics` → `-EOPNOTSUPP`) |
| Renoir/Lucienne/Cezanne/Barcelo (Ryzen 4000/5000) | 9.3 | `smu12/renoir_ppt.c` | **v2.2** (también en 5.15) |
| Van Gogh (Steam Deck) | 10.3.1 | `smu11/vangogh_ppt.c` | v2.2, v2.3 o v2.4 según el firmware |
| Rembrandt (6000), Mendocino (7x20) | 10.3.3 / 10.3.7 | `smu13/yellow_carp_ppt.c` | **v2.1** (en 5.15) |
| Raphael, Granite Ridge, Dragon Range (iGPU de AM5) | 10.3.6 | `smu13/smu_v13_0_5_ppt.c` (desde 5.18) | **v2.1** |
| Phoenix, Hawk Point (780M/760M/740M) | 11.0.1/11.0.4 | `smu13/smu_v13_0_4_ppt.c` (desde 5.19) | **v2.1** |
| Strix Point, Strix Halo, Krackan, Gorgon | 11.5.x | `smu14/smu_v14_0_0_ppt.c` (desde 6.7) | **v3.0** (ya en 6.7) |
| SI: Tahiti, Pitcairn, Verde, Oland, Hainan | 6 | `legacy-dpm/si_dpm.c` | no |
| CIK dedicada: Bonaire, Hawaii | 7 | powerplay smu7 (`hwmgr.c`: `AMDGPU_FAMILY_CI` → `ci_smu_funcs` + `smu7_init_function_pointers`) | no |
| Tonga, Fiji, Polaris 10/11/12 | 8 | powerplay `smu7_hwmgr.c` | no |
| Vega 10 (Vega 56/64) | 9.0.1 | powerplay `vega10_hwmgr.c` | no (GC < 9.1.0) |
| Vega 12, Vega 20 (Radeon VII) | 9.2.1 / 9.4.0 | powerplay `vega12/vega20_hwmgr.c` | v1.0 |

La regla de `gpu_metrics` está en K`amd/pm/amdgpu_pm.c` `default_attr_update`:
`if (gc_ver < IP_VERSION(9, 1, 0)) unsupported`. En v5.15 la condición era
`asic_type < CHIP_VEGA12`, que deja el mismo conjunto fuera.

**Quién maneja SI y CIK.** Hasta v6.18, si el kernel trae `radeon`, SI y CIK van con
`radeon` (en v6.18, `amdgpu_si_support = 0` cuando `CONFIG_DRM_RADEON` está
compilado). En v7.0, `amdgpu_drv.c` pasa a `support_by_default = true` para SI
y para Bonaire/Hawaii; en v7.1, también para Kaveri/Kabini/Mullins. Las dos
cosas salen de leer `amdgpu_drv.c` en cada etiqueta. Aun así hace falta que la
distribución compile `CONFIG_DRM_AMDGPU_SI`/`_CIK`; qué distribuciones lo
hacen es **dudoso**, no se miró. En v6.19 cambia el parámetro a `-1`, pero no
se comprobó qué hace por defecto: **dudoso**. TeraScale (HD 2000 a 6000)
sigue siempre con `radeon`.

---

#### 1. APU con `amdgpu`

| Dato que enseña la página (o que faltaría) | De dónde sale | ¿Permisos? | Desde | Qué hace silux hoy | Fuente |
|---|---|---|---|---|---|
| Integrada sí/no | ioctl `AMDGPU_INFO_DEV_INFO`, `ids_flags & AMDGPU_IDS_FLAGS_FUSION` (lo pone si `adev->flags & AMD_IS_APU`) | no (nodo render) | ≤ 5.15 | **bien**, si el ioctl contesta. Si no contesta, se queda en `None` (drm.py:342-372) y no se esconde nada | K`amd/amdgpu/amdgpu_kms.c` (`ids_flags`) |
| VRAM total | `mem_info_vram_total` = **lo que la BIOS reserva (UMA carve-out)**, no una memoria propia | no | ≤ 5.15 | **mal**: se trata como VRAM dedicada. Sale en la insignia (graphics.py:697), en la barra «Ahora mismo» (graphics.py:782-785) y en toda la ficha de memoria; `NA_SIN_VRAM` solo se aplica con `total_bytes` vacío (graphics.py:192) | D-misc; K`amd/amdgpu/gmc_v9_0.c` (`real_vram_size`) |
| VRAM visible / Resizable BAR | `mem_info_vis_vram_total`. En una APU, `gmc_v9_0_mc_init` hace `aper_size = real_vram_size` («For APUs, VRAM is just the stolen system memory») | no | ≤ 5.15 | **mal**: visible = total, así que `GpuMemory.resizable_bar` da True y la página dice que **ReBAR está activo** sin que haya BAR (model.py:872-878, graphics.py:824) | K`amd/amdgpu/gmc_v9_0.c` `gmc_v9_0_mc_init` |
| Memoria del sistema prestada (GTT) | `mem_info_gtt_total/used` | no | ≤ 5.15 | **bien** («Compartida»). En una APU es la memoria que de verdad usa la gráfica, y sale como dato secundario | D-misc |
| Fabricante de los chips | `mem_info_vram_vendor`. `gmc_v9` solo lo rellena si `!(adev->flags & AMD_IS_APU)` en el camino de la 9.4.3; en el camino general lo toma de atomfirmware, y lo que da en una APU es **dudoso** | no | en 5.15–6.7 el archivo dice `unknown` si no se conoce; desde 6.8 se esconde (T`89a7c0bd74918f723c94c10452265e25063cba9b`, con Cc a la 6.7.x estable) | **mal** con 5.15–6.7: pinta «unknown» tal cual (graphics.py:826) | K`amd/amdgpu/amdgpu_vram_mgr.c` (`amdgpu_vram_attrs_is_visible`) |
| Tipo de memoria y bus | ioctl `vram_type`, `vram_bit_width`: en una APU es la **RAM del sistema** (DDR4/DDR5/LPDDR5) | no | LPDDR4/LPDDR5 entran en la uapi en 5.19; qué devuelve una LPDDR con 5.15–5.18 es **dudoso** | **engañoso**: se pinta bajo «VRAM» | K`include/uapi/drm/amdgpu_drm.h` en v5.18 y v5.19 |
| Tasa de datos y ancho de banda | silux multiplica `max_memory_clock` (= `amdgpu_dpm_get_mclk`) × 2 × bus | no | ≤ 5.15 | **dudoso**: no se sabe si en LPDDR5 el MCLK de la SMU es el de comando o el de WCK. Además es el ancho de banda de la RAM, compartido con la CPU, y sale como si fuera de la gráfica | amdgpu.py:64-67, 109-121; K`amd/amdgpu/amdgpu_kms.c` |
| Unidades de cómputo | ioctl `cu_active_number` | no | ≤ 5.15 | **bien** | K`amdgpu_kms.c` |
| ROP | ioctl `num_rb_pipes`, que **ya es el total**: `max_backends_per_se * max_shader_engines` | no | ≤ 5.15 | **mal**: silux lo vuelve a multiplicar por SE × SA (amdgpu.py:100-106). Carrizo (1 SE, 1 SH, 2 RB por SE) da 2 donde son 8; Stoney da 1. En Raven y Renoir la configuración sale del VBIOS: que den 2 en vez de 8 es **dudoso**, aunque es lo esperable | K`amd/amdgpu/amdgpu_kms.c`; K`amd/amdgpu/gfx_v8_0.c` (Carrizo y Stoney, valores fijos) |
| Uso de la gráfica | `gpu_busy_percent` (la SMU lo da en centésimas y el kernel divide entre 100) | no | ≤ 5.15 | **bien** por sysfs | K`smu12/renoir_ppt.c`, `smu13/*_ppt.c`: `*value = metrics->GfxActivity / 100` |
| Uso de la memoria | `mem_busy_percent`: **no existe** en APU (salvo la 9.4.3) | — | — | bien: la barra «bus» no sale | K`amdgpu_pm.c` `default_attr_update` |
| Uso del vídeo | `vcn_busy_percent` (GC 9.3.0, 10.3.1, 10.3.3, 10.3.6, 10.3.7, 11.0.1, 11.0.4, 11.5.x…); si no está, `gpu_metrics.average_mm_activity` | no | sysfs 6.10 (T`d1b2703cc28769d4bb61d7750a9a74acc916cebe`) | **mal** antes de 6.10: lo toma de `gpu_metrics` v2.1, que en APU va **en centésimas** (Phoenix: `UvdActivity //[centi]`). `porcentaje()` acepta ≤ 100 como porcentaje: un 0,45 % sale «45 %» y cualquier cosa por encima del 1 % sale «—» (gpumetrics.py:93, 192; drm.py:968-977) | K`amd/pm/swsmu/inc/pmfw_if/smu13_driver_if_v13_0_4.h`, `smu13_driver_if_v13_0_5.h`, `smu12_driver_if.h` |
| Temperatura (borde) | hwmon `temp1_input`, etiqueta `edge`; en APU es la de la GFX (`GfxTemperature`) | no | ≤ 5.15 | **bien** | D-thermal; K`amdgpu_pm.c` (`temp_label[]`) |
| Punto caliente / memoria | hwmon `temp2`/`temp3`: «supported on SOC15 dGPUs only» | — | — | **mal**: para v2.1 silux lee `temperature_soc` como `temp_hotspot` (gpumetrics.py:91). La «Punto caliente 31,4 °C» de la 740M que da por validada `docs/hardware-validado.md` es **la temperatura del SoC**, no un punto caliente de la gráfica | D-thermal; K`amd/include/kgd_pp_interface.h` (`gpu_metrics_v2_1`: `temperature_soc // soc temperature on APUs`) |
| Consumo | hwmon `power1_average` (Renoir y posteriores; nunca en APU con GC < 9.3.0) y/o `power1_input` | no | `power1_input` desde 6.6 (T`bb9f7b6826257390a847abb39c719dca0de41a18`). En master, Renoir, Rembrandt, Mendocino y Raphael **solo** tienen `power1_input`; Phoenix y Strix, los dos | **mal, y es lo más grave**: D-thermal dice «**On APUs this includes the CPU**». Los backends leen `METRICS_CURR/AVERAGE_SOCKETPOWER`. silux lo enseña como consumo de la gráfica en la ficha, en la barra, en Inicio (home.py:307) y en el CLI (cli.py:198) (drm.py:914-916). En un Raphael de escritorio es el paquete entero de 8-16 núcleos | D-thermal; K`smu12/renoir_ppt.c`, `smu13/yellow_carp_ppt.c`, `smu13/smu_v13_0_4_ppt.c`, `smu13/smu_v13_0_5_ppt.c`, `smu14/smu_v14_0_0_ppt.c` (`read_sensor`) |
| Consumo de la gráfica sola (faltaría) | `gpu_metrics` v2.x `average_gfx_power` (Phoenix, Rembrandt y Raphael lo llenan con `Power[0]`, «[mW] indices: VDDCR_VDD, VDDCR_SOC»); v3.0 `average_gfx_power` [mW] | no | según la versión de la tabla | **nada**. Que `Power[0]` (VDDCR_VDD) sea solo la gráfica es **dudoso**: en Renoir, `Power[0]` va a `average_cpu_power` | K`kgd_pp_interface.h`; drivers `*_driver_if*.h` |
| Consumo leído de `gpu_metrics` (respaldo) | v2.x `average_socket_power`: Renoir en W (`CurrentSocketPower //[W]`); Rembrandt, Raphael y Phoenix en **mW**; v3.0 en mW | no | — | **mal, latente**: solo se usa si hwmon no da consumo, y entonces 15 W salen «15000 W» (gpumetrics.py:94, 217; drm.py:974) | `smu13_driver_if_yellow_carp.h`, `_v13_0_4.h`, `_v13_0_5.h`: `CurrentSocketPower //[mW]` |
| Límite de consumo | `power1_cap*`: oculto en APU salvo Van Gogh y la 9.4.3 | — | — | bien: sin tope no sale la barra | K`amdgpu_pm.c` `hwmon_attributes_visible` |
| Ventilador | `pwm1`/`fan1_*`: «Skip fan attributes on APU» | — | — | **bien**: `NA_INTEGRADA` lo esconde y lo nombra al pie | K`amdgpu_pm.c` |
| Voltaje | `in0` vddgfx; `in1` **vddnb, solo APU** | no | ≤ 5.15 | bien. Raven (smu10) no implementa `VDDGFX` y la lectura falla, así que sale «—» | D-thermal; K`smu10_hwmgr.c` `read_sensor` |
| Reloj del núcleo | hwmon `freq1_input` (sclk) y `pp_dpm_sclk` | no | ≤ 5.15 | bien | D-thermal |
| Reloj de memoria | hwmon `freq2` oculto en APU («no mclk on APUs»); `pp_dpm_mclk` sí existe y da el MEMCLK del sistema | no | ≤ 5.15 | **engañoso**: sale como «Memoria» de la gráfica. Desde v2.1, «Memoria (efectiva)» es `average_uclk_frequency`, que en Phoenix es `MemclkFrequency` (drm.py:963); que sea la «efectiva» es **dudoso** | K`amdgpu_pm.c`; K`smu_v13_0_4_ppt.c` |
| Motivos de recorte | v2.1 `throttle_status` (depende del ASIC); v2.2 añade `indep_throttle_status` (u64 en el byte 120) | no | — | v2.1 da solo sí/no. **v2.2 no se lee** | K`kgd_pp_interface.h` |
| Tabla v2.2 (Renoir/Cezanne/Van Gogh) | `gpu_metrics` | no | ≤ 5.15 | **nada**, solo la nota «metricsnew» (gpumetrics.py:104-110; drm.py:944-948). La v2.2 es la v2.1 con `indep_throttle_status` al final: las posiciones de la v2.1 valen tal cual | K`kgd_pp_interface.h` |
| Tabla v3.0 (Strix y posteriores) | `gpu_metrics` | no | 6.7 | **nada**, solo la nota. Trae `temperature_skin`, `average_gfx_power`, `stapm_power_limit` y residencias de recorte | K`kgd_pp_interface.h` (`gpu_metrics_v3_0`) |
| Enlace PCIe | `current_link_*` del nodo y de los puentes | no | ≤ 5.15 | se pinta (es a propósito, por la 740M). Que ese enlace interno al puente GPP signifique algo para el usuario es **dudoso** | — |

#### 2. GCN y TeraScale con `radeon`

Ni `pp_dpm_*`, ni `gpu_busy_percent`, ni `mem_info_*`, ni `gpu_metrics`, ni
`vbios_version`, ni `unique_id`: todo eso es solo de `amdgpu`. Lo que sí
publica:

| Dato | De dónde sale | ¿Permisos? | Desde | Qué hace silux hoy | Fuente |
|---|---|---|---|---|---|
| Identidad PCI, salidas, EDID, enlace | genérico de PCI/DRM | no | ≤ 5.15 | bien | — |
| Temperatura | hwmon `radeon` `temp1_input`, **sin etiqueta**; solo con sensor interno (`THERMAL_TYPE_RV6XX` a `_KV`) | no | ≤ 5.15 | **bien** (cae a `temp1_input`, drm.py:910-912) | K`radeon/radeon_pm.c` (`hwmon_attributes`, `radeon_hwmon_init`) |
| Reloj del núcleo | hwmon `freq1_input` en Hz, **sin etiqueta**, solo con DPM | no | ≤ 5.15 (está en v5.15) | **mal**: `_etiquetadas()` solo encuentra canales con etiqueta, así que «Núcleo» sale «—» teniendo el dato (drm.py:766, 772) | K`radeon/radeon_pm.c` `radeon_hwmon_show_sclk` |
| Voltaje | hwmon `in0_input` (vddc, mV), sin etiqueta; con DPM y `get_current_vddc` | no | ≤ 5.15 | **nada**: mismo motivo (drm.py:925-927) | K`radeon/radeon_pm.c` |
| Ventilador | `pwm1` (0-255), con DPM y si el ASIC sabe leerlo; **no hay `fan1_input`** | no | ≤ 5.15 | bien (porcentaje) | K`radeon/radeon_pm.c` `hwmon_attributes_visible` |
| Consumo | no existe | — | — | sale «—» sin explicación | ídem |
| Perfil | `power_dpm_force_performance_level` (auto/low/high) y `power_dpm_state`, solo con DPM; `power_method`/`power_profile` | no (lectura) | ≤ 5.15 | bien | K`radeon/radeon_pm.c` `radeon_pm_late_init` |
| ¿Hay DPM? | `radeon_pm_init`: con firmware RLC, DPM por defecto desde RV730 hasta Hawaii; RV6xx/RV770 y anteriores, «profile» | — | — | — | K`radeon/radeon_pm.c` |
| VRAM total, visible, GTT | ioctl `DRM_RADEON_GEM_INFO` (`vram_size`, `vram_visible`, `gart_size`) | no (nodo render) | ≤ 5.15 | **nada** | `include/uapi/drm/radeon_drm.h` (**no se descargó**, dudoso el detalle), K`radeon/radeon_gem.c` |
| VRAM y GTT usadas, CU activas, temperatura, sclk/mclk actuales, sclk máximo | `DRM_RADEON_INFO`: `RADEON_INFO_VRAM_USAGE`, `GTT_USAGE`, `ACTIVE_CU_COUNT`, `CURRENT_GPU_TEMP`, `CURRENT_GPU_SCLK`, `CURRENT_GPU_MCLK`, `MAX_SCLK` | no | ≤ 5.15 | **nada** | K`radeon/radeon_kms.c` `radeon_info_ioctl` |
| Uso de la gráfica | no hay interfaz estable (radeontop lee registros) | — | — | nada, y está bien | **dudoso** (no se comprobó el camino de radeontop) |
| Aviso de por qué falta todo | — | — | — | **nada**: `radeon` no está en `DRIVERS_CIEGOS` (drm.py:55-61). La ficha sale llena de rayas sin explicación, y no se dice que `amdgpu.si_support=1`/`cik_support=1` desbloquea lo demás | — |
| Integrada (Kaveri, Kabini, Trinity, Llano con radeon) | no hay ioctl de amdgpu | — | — | `None`: no se esconde el ventilador ni lo demás (drm.py:342-372) | — |

#### 3. GCN, Polaris y Vega con `amdgpu`

Columnas por familia: **SI** = si_dpm (legacy); **CI** = Bonaire/Hawaii con
smu7; **VI** = Tonga/Fiji/Polaris con smu7; **V10** = Vega 10; **V12/20** =
Vega 12 y Vega 20.

| Dato | De dónde sale | SI | CI | VI | V10 | V12/20 | ¿Permisos? | Qué hace silux hoy | Fuente |
|---|---|---|---|---|---|---|---|---|---|
| VRAM total/usada/visible, GTT | `mem_info_*` | sí | sí | sí | sí | sí | no | bien | D-misc |
| Fabricante de los chips | `mem_info_vram_vendor` | `unknown` (≤ 6.7) / no hay archivo (≥ 6.8) | ídem | ídem | gmc9: sí | sí | no | **mal** con 5.15–6.7: «unknown» crudo (graphics.py:826). gmc_v6/v7/v8 no rellenan nunca `vram_vendor` | K`amd/amdgpu/gmc_v{6,7,8}_0.c` (sin `vram_vendor`); T`89a7c0bd…` |
| Tipo, bus, tasa, ancho de banda | ioctl DEV_INFO | sí | sí | sí | sí (HBM ×2) | sí | no | bien; la cuenta de GDDR5 ×4 está contrastada con una RX 580 en los tests | amdgpu.py:64-67 |
| ROP | ioctl `num_rb_pipes` (total) | | | | | | no | **mal fuera de los casos con SE×SH = 4** (amdgpu.py:100-106). Con valores fijos en el driver: Verde 4 RB → silux 8, son 16; Oland 2 → 2, son 8; Hainan 1 → 1. Tahiti, Pitcairn, Tonga y Fiji aciertan por casualidad. Bonaire, Polaris 11/12 y Vega toman la configuración del VBIOS: lo esperable es que fallen Bonaire y Polaris 11/12, pero es **dudoso** | K`amd/amdgpu/gfx_v6_0.c`, `gfx_v8_0.c` (`*_gpu_early_init`); K`amdgpu_kms.c` |
| `vbios_version` | sysfs | sí | sí | sí | sí | sí | no | bien | — |
| `unique_id` | sysfs | no | no | no | sí (9.0.1) | Vega 20 sí, Vega 12 no | no | bien: la fila se va | K`amdgpu_pm.c` `default_attr_update` |
| Uso de la gráfica | `gpu_busy_percent` (sensor `GPU_LOAD`) | **no** (si_dpm no lo implementa: la lectura falla) | sí | sí | sí | sí | no | bien (sale «—» en SI) | K`legacy-dpm/si_dpm.c`, `smu7_hwmgr.c`, `vega10_hwmgr.c` `read_sensor` |
| Uso de la memoria | `mem_busy_percent` | no | sí | sí | **oculto** (9.0.1) | sí | no | bien | K`amdgpu_pm.c` |
| Uso del vídeo | `vcn_busy_percent`: solo GPUs con VCN | no | no | no | no | no | — | bien («—»; no se atribuye al kernel) | K`amdgpu_pm.c` |
| Niveles DPM | `pp_dpm_sclk/mclk` | **la lectura falla** (si_dpm sin `emit_clock_levels`) | sí | sí (8 escalones) | sí | sí | no | bien. En SI la tabla sale vacía y el máximo del núcleo, «—»; `DeviceInfo.max_engine_hz` del ioctl existe y no se usa | K`legacy-dpm/si_dpm.c` (`si_dpm_funcs`) |
| Perfil | `power_dpm_force_performance_level` | sí | sí | sí | sí | sí | no | bien | — |
| Temperatura del borde | hwmon `temp1` `edge` | sí | sí | sí | sí | sí | no | bien | D-thermal |
| Punto caliente / memoria | hwmon `temp2` junction / `temp3` mem: solo SOC15 dedicadas (GC ≥ 9) | no | no | no | sí | sí | no | SI/CI/VI: «—» en vez de esconderlo y nombrarlo al pie (incumple la regla 5) | D-thermal; K`amdgpu_pm.c` |
| Consumo | hwmon `power1_average` / `power1_input` | **no** (familia SI oculta) | sí | sí (los dos) | `power1_average` en 5.15; en master solo `power1_input` | sí | no | bien (lee los dos) | K`amdgpu_pm.c`; `smu7_hwmgr.c`/`vega10_hwmgr.c` `read_sensor` |
| Límite de consumo | `power1_cap` | no (SI) | sí | sí | sí | sí | no | bien | ídem |
| Ventilador | `fan1_input` + `pwm1` | `pwm1` sí; `fan1_input` falla (si_dpm sin `get_fan_speed_rpm`) | sí | sí | sí | sí | no | bien | K`legacy-dpm/si_dpm.c`; `smu7_hwmgr.c` (`.get_fan_speed_rpm`) |
| Voltaje del núcleo | hwmon `in0` vddgfx | **oculto** (SI y KV) | sí | sí | sí | sí | no | bien | K`amdgpu_pm.c` |
| Relojes hwmon | `freq1` sclk / `freq2` mclk | sí (sensores `GFX_SCLK`/`GFX_MCLK`) | sí | sí | sí | sí | no | bien | `si_dpm.c` `read_sensor` |
| `gpu_metrics` (VR, SoC, recortes, efectiva) | sysfs | no | no | no | no | v1.0 | no | sin tabla, silux no dice nada, y está bien. Pero los campos del firmware (VR, voltaje del SoC/memoria, «Estado», «SoC», memoria efectiva) se quedan en «—» en vez de esconderse como «no existe en esta familia» | K`amdgpu_pm.c`; K`powerplay/hwmgr/vega12_hwmgr.c`, `vega20_hwmgr.c` (`gpu_metrics_v1_0`) |
| Kaveri/Kabini con amdgpu (KV) | `kv_dpm`: solo `GFX_SCLK` y `GPU_TEMP`; sin `in0` | | | | | | no | integrada bien por FUSION; consumo y voltaje, «—» | K`legacy-dpm/kv_dpm.c` |

---

### 1.2 Intel: `i915` frente a `xe`, integradas y Arc
Investigado el 18 de noviembre de 2026 contra el código de silux en la rama
`oficina` (commit 7ff2f73) y el árbol de Linux en `master` (7.4-rc3) y en las
etiquetas que se citan. Las versiones de kernel salen de descargar el archivo
en cada etiqueta o de la comparación de etiquetas de GitHub (`compare/vX...SHA`
= `behind`): el commit está en esa etiqueta y no en la anterior. **No se ha
visto ninguna de estas piezas**: todo lo que dice «silux hoy» es lectura del
código, no una ejecución.

Abreviaturas de fuentes:

- **K** = `https://github.com/torvalds/linux/blob/master/` + ruta (líneas de `master`).
- **C** = `https://github.com/torvalds/linux/commit/` + SHA.
- **ABI-xe** = K`Documentation/ABI/testing/sysfs-driver-intel-xe-hwmon`;
  **ABI-i915** = K`Documentation/ABI/testing/sysfs-driver-intel-i915-hwmon`.
  Ojo: el `KernelVersion` de esos ABI **no siempre es cierto** (abajo, en cada fila).

#### 0. Qué driver lleva cada pieza

| Pieza | Driver por defecto | Desde | El otro driver | Fuente |
|---|---|---|---|---|
| Integradas Gen9–Gen12 (Skylake … Raptor Lake) | i915 | ≤ 5.15 | xe solo con `xe.force_probe` (Tiger Lake en adelante) | K`drivers/gpu/drm/xe/xe_pci.c` (tgl/rkl/adl: `require_force_probe = true`) |
| Meteor Lake / Arrow Lake (integradas) | i915 | MTL: 6.7 sin `force_probe` (en 6.6 aún lo pedía) | xe con `force_probe` (ARL usa `mtl_desc` en xe desde 6.13) | `i915_pci.c` en v6.6/v6.7; `xe_pci.c` |
| **Lunar Lake** (Arc 130V/140V, integrada) | **xe** | 6.12 (en 6.11 pedía `force_probe`) | i915 no la admite | `xe_pci.c` en v6.11/v6.12 |
| Panther Lake (integrada) | xe | 6.17 (en 6.16 pedía `force_probe`) | — | `xe_pci.c` en v6.16/v6.17 |
| **Arc A (Alchemist, DG2)** dedicada | **i915** | 6.2 (en 5.15 los ID ni están; 5.19–6.1 con `force_probe`) | xe con `force_probe` | `i915_pci.c` en v6.1/v6.2 |
| **Arc B (Battlemage, B570/B580)** dedicada | **xe** | 6.12 (en 6.11 pedía `force_probe`) | i915 no la admite | `xe_pci.c` en v6.11/v6.12 |

Con un kernel anterior a la columna «Desde» la tarjeta no tiene driver y silux
cae en `_identidad_del_bus` (`silux/providers/drm.py:206`), que da nombre y
enlace pero lo achaca a «sin driver», no al kernel.

**Dónde publica cada driver** (lo que más confunde):

- i915: frecuencias, RC6 y motivos de freno en el **nodo DRM**
  (`/sys/class/drm/cardN/gt/gt0/…`, `cardN/engine/…`); hwmon en el nodo PCI.
- xe: todo en el **nodo PCI** (`/sys/bus/pci/devices/BDF/tile0/gt0/…`, `…/hwmon/`).
  `xe_tile_sysfs.c` cuelga `tile%d` de `&dev->kobj`, el dispositivo PCI
  (K`drivers/gpu/drm/xe/xe_tile_sysfs.c`). En `cardN/` no hay nada de xe salvo
  lo común de DRM.

---

#### 1. Integrada con i915 (UHD/Iris Xe/Meteor Lake/Arrow Lake)

Es el caso validado (UHD 630). Lo nuevo frente a Comet Lake es lo que cambia
con la generación.

| Dato | De dónde sale | ¿Permisos? | Desde | silux hoy | Fuente |
|---|---|---|---|---|---|
| Frecuencia actual / máx / mín | `cardN/gt/gt0/rps_{act,cur,max,min}_freq_mhz`; antes, `cardN/gt_*_freq_mhz` | no | gt/gt0: 5.19; legado ≤ 5.15 | **bien** (`drm.py:852-861`) | docs/kernel.md; K`drivers/gpu/drm/i915/gt/intel_gt_sysfs_pm.c:404-422` |
| RP0 / RP1 / RPn | `gt/gt0/rps_RP0/RP1/RPn_freq_mhz` | no | 5.19 (legado antes) | **bien** | ídem |
| Motivos de freno | `gt/gt0/throttle_reason_{status,pl1,pl2,pl4,thermal,prochot,ratl,vr_thermalert,vr_tdc}` | no | 5.19 **y Gen11 en adelante** (Ice Lake+); el registro `GT0_PERF_LIMIT_REASONS` no existe antes | **bien** (`drm.py:803-817`); el pie «Esta generación no publica…» acierta en Gen9 | K`drivers/gpu/drm/i915/gt/intel_gt.c:235-243`, K`…/intel_gt_sysfs_pm.c:537-556,916-920` |
| Reposo (RC6) | `gt/gt0/rc6_residency_ms`, `rc6_enable` | no | 5.19 (legado `power/` antes) | **bien** | docs/kernel.md. En MTL hay además `gt/gt1` (GT de medios): silux mira solo gt0, que es el de dibujo |
| Motores y capacidades | `cardN/engine/<motor>/capabilities` | no | ≤ 5.15 | **bien** | docs/kernel.md |
| Uso por motor | PMU `i915`, eventos `<motor>-busy` | CAP_PERFMON (ayudante) | ≤ 5.15 | **bien** si es la única i915; ver §5-I2 si además hay una Arc con i915 | K`drivers/gpu/drm/i915/i915_pmu.c:1162-1172` |
| Vatios | PMU `power`, evento `energy-gpu` (RAPL PP1) | CAP_PERFMON | — | **bien** en CML (validado). El kernel lo declara también para TGL/ADL/RPL/MTL/ARL/LNL (`model_skl`); que el firmware lo rellene en esos, **dudoso** | K`arch/x86/events/rapl.c:814-819,871-888` |
| EU | `DRM_IOCTL_I915_GETPARAM` `I915_PARAM_EU_TOTAL` | no (nodo render) | ≤ 5.15 | **bien**; en MTL/ARL **probable, sin comprobar** | `silux/i915.py` |
| Temperatura | no existe: el hwmon de i915 es solo para dedicadas | — | — | **bien** (se esconde y se dice) | K`drivers/gpu/drm/i915/i915_hwmon.c:916-918` |
| VRAM | no hay; Vulkan da RAM del sistema → GTT | no | — | **bien** (`gpu_apis.py:166-170`) | — |

Nada se rompe aquí que no esté ya en `pendientes.md`. Lo único nuevo: en
Meteor/Arrow Lake con i915 el GT de medios (`gt1`) tiene sus propios relojes y
RC6 y silux no los enseña (no es un error, es un dato más).

---

#### 2. Integrada con xe (Lunar Lake y Panther Lake de serie; MTL/ARL/TGL/ADL forzadas)

| Dato | De dónde sale | ¿Permisos? | Desde | silux hoy | Fuente |
|---|---|---|---|---|---|
| Frecuencia actual | `device/tile0/gt0/freq0/act_freq` (la que decide PCODE); `cur_freq` es la **pedida** por GuC | no | 6.8 | **mal**: lee `cur_freq`, la pedida (`drm.py:863-867`, `_XE.get("cur","cur")`); con i915 prefiere `act` (`drm.py:855`) | K`drivers/gpu/drm/xe/xe_gt_freq.c` (DOC: «act_freq: The actual resolved frequency decided by PCODE», «cur_freq: The current one requested by GuC PC») |
| Máx / mín puestos | `freq0/max_freq`, `min_freq` | no (lectura) | 6.8 | **bien** | ídem |
| RP0 / RPe / RPn (+ RPa) | `freq0/rp0_freq`, `rpe_freq`, `rpn_freq`, `rpa_freq` | no | 6.8 | **bien** (RP0/RPe/RPn, `drm.py:821,866`); RPa no se lee (la «alcanzable», calculada en marcha) | ídem; C`bef52b5c7a1904fc6e1bdda4a0e6dc460f562856` |
| Motivos de freno | `freq0/throttle/status`, `reason_{pl1,pl2,pl4,thermal,prochot,ratl,vr_thermalert,vr_tdc}`; `throttle/reasons` (lista atómica, «none» si nada) | no | 6.8 (`status`/`reason_*`); `reasons`: 6.19 | **nada**: solo mira `cardN/gt/gt0/throttle_reason_*` (`drm.py:809`). Y como `throttled` queda en None, el pie dice «Esta generación de Intel no publica si se frena…; las más recientes sí» (`graphics.py:206`, `es.json:497`): **falso** en la más reciente | K`drivers/gpu/drm/xe/xe_gt_throttle.c:18-61,168-177`; `xe_gt_throttle_sysfs.c` en v6.8; C`83ccde67a3f7` (`reasons`, 6.19) |
| Reposo (equivalente a RC6) | `tile0/gt0/gtidle/idle_residency_ms`, `idle_status` (`gt-c0`/`gt-c6`), `name` | no | 6.8 | **nada**: mira `gt/gt0/rc6_*` y `power/rc6_*` (`drm.py:420-422,497-498`) | K`drivers/gpu/drm/xe/xe_gt_idle.c` (kobject `gtidle`) |
| Motores | sysfs por **clase**: `tile0/gt0/engines/{rcs,bcs,vcs,vecs,ccs}/` (solo tiempos de planificación, sin `capabilities`); por instancia, `DRM_XE_DEVICE_QUERY_ENGINES` | no | 6.8 | **nada**: lee `cardN/engine/` (`drm.py:188,527-547`), que es de i915 → `()` y la tarjeta de motores se esconde (`graphics.py:647`), con ella la fila de reposo | K`drivers/gpu/drm/xe/xe_hw_engine_class_sysfs.c:639,655`; K`include/uapi/drm/xe_drm.h:756` |
| Capacidades del motor (hevc, sfc) | no las publica xe | — | — | — (ni existen) | — |
| Uso por motor | PMU `xe_0000_00_02.0`, eventos `engine-active-ticks` / `engine-total-ticks` con `gt`, `engine_class`, `engine_instance` en `config`; además `gt-c6-residency`, `gt-actual-frequency`/`gt-requested-frequency` (6.16) | CAP_PERFMON | 6.15 | **nada**: el ayudante acepta el nombre del PMU pero solo eventos `^(rcs|bcs|vcs|vecs|ccs)\d+-busy$` (`privileged/helper.py:98-99`) | K`drivers/gpu/drm/xe/xe_pmu.c:22-58,85-89`; C`011c1e246a1d` (6.15) |
| Uso, alternativa sin el PMU | `/proc/PID/fdinfo/N`: `drm-cycles-<clase>`, `drm-total-cycles-<clase>` por cliente | los procesos propios sin permisos; los ajenos, root | 6.11 | nada | `drivers/gpu/drm/xe/xe_drm_client.c` en v6.10 (no) / v6.11 (sí) |
| Vatios | PMU `power/energy-gpu` (RAPL PP1) | CAP_PERFMON | — | **bien** si el evento existe (solo integrada, `drm.py:428`); que LNL lo rellene, **dudoso** | K`arch/x86/events/rapl.c:888` |
| Unidades (Xe-cores / EU) | `DRM_XE_DEVICE_QUERY_GT_TOPOLOGY`: máscaras `DSS_GEOMETRY`/`DSS_COMPUTE` (Xe-cores) y `EU_PER_DSS` (SIMD8) o `SIMD16_EU_PER_DSS` (Xe2: LNL, BMG) | no (nodo render) | 6.8; `SIMD16_EU_PER_DSS`: 6.12 | **nada**: solo se pregunta a i915 (`drm.py:237`) → «Unidades —» | K`include/uapi/drm/xe_drm.h:536-564`; `xe_drm.h` en v6.11 (no) / v6.12 (sí) |
| Temperatura | no existe: hwmon de xe solo en dedicadas | — | — | **bien** (`no_temperature_sensor`) | K`drivers/gpu/drm/xe/xe_hwmon.c:1654-1656` |
| Memoria | Lunar Lake lleva la LPDDR5X **en el encapsulado**, pero es RAM del sistema: xe no da región VRAM (`IS_DGFX` falso); Vulkan da un montón que es RAM | no | — | **bien**: va a GTT (`gpu_apis.py:166-170`) y la ficha esconde la VRAM | K`drivers/gpu/drm/xe/xe_query.c` (`query_mem_regions`: solo SYSMEM sin VRAM) |
| Textos del pie | — | — | — | **mal (baja)**: «i915 no cuenta unidades de rasterizado…» (`es.json:493`) sale también con xe (`graphics.py:198` incluye `"xe"`) | — |

---

#### 3. Arc dedicada con xe (B570/B580 de serie desde 6.12; A-series con `xe.force_probe`)

| Dato | De dónde sale | ¿Permisos? | Desde | silux hoy | Fuente |
|---|---|---|---|---|---|
| Nombre | `pci.ids` («Battlemage G21 [Arc B580]», «DG2 [Arc A770]») | no | — | **bien** | — |
| **Enlace PCIe** | La tarjeta trae un conmutador propio; el **extremo (la GPU) y el puerto de bajada interno publican siempre 2.5 GT/s × 1**. El dato cierto está en el puerto de subida del conmutador de la tarjeta (y en el puerto raíz), es decir, en el enlace con la placa | no | — | **mal (alta)**: `_enlace` coge el mínimo de la cadena (`drm.py:654-712`) → «PCIe 1.0 × 1» en Enlace, Enlace máx. y el subtítulo; sin aviso de «va por debajo» porque actual = máximo. Intel lo documenta para A380…A770 **y B570/B580** | Intel, artículo 000094587; foro openSUSE (A380: GPU `LnkCap 2.5GT/s x1` con puerto raíz a 8GT/s x16) |
| Variante del enlace (BMG) | `device/auto_link_downgrade_capable` / `auto_link_downgrade_status` | **root** (`DEVICE_ATTR_ADMIN_RO`) | **dudoso** (no fechado) | nada | K`drivers/gpu/drm/xe/xe_device_sysfs.c` |
| VRAM total | `DRM_XE_DEVICE_QUERY_MEM_REGIONS`, región `VRAM`, `total_size` | no | 6.8 | **a medias**: no se pregunta a xe; sale del montón de Vulkan (`gpu_apis.py:149-171`, suma de montones `DEVICE_LOCAL`, `gpuapi.py:230-232`). Que ANV sume exactamente la VRAM, **dudoso** | K`include/uapi/drm/xe_drm.h:315-370`; K`drivers/gpu/drm/xe/xe_query.c` |
| VRAM ocupada | ídem, `used` | CAP_PERFMON hasta 6.18; **libre desde 6.19** | 6.8 | **nada** (barra de «Ahora mismo» oculta) | C`4d0b035fd6da` «drm/xe/uapi: loosen used tracking restriction» (6.19); `xe_query.c` en v6.17 con `perfmon_capable()` |
| VRAM visible por la CPU | ídem, `cpu_visible_size` / `cpu_visible_used` | no / como `used` | 6.8 | **nada** | `xe_drm.h:345-370` |
| **Resizable BAR** | `cpu_visible_size` frente a `total_size`; o, sin driver, el tamaño de la BAR 2 en `device/resource` (línea 3) frente a la VRAM. `resource2_resize` da el mapa de tamaños admitidos | no (`resource` 0444; `resourceN_resize` 0644) | `resource` ≤ 5.15; `resourceN_resize` 6.1 | **nada**: `GpuMemory.resizable_bar` pide `visible_bytes` (`model.py:873-879`) → «—» | K`drivers/gpu/drm/xe/regs/xe_bars.h:9` (`LMEM_BAR 2`); ABI `sysfs-bus-pci` `resourceN_resize`; `pci-sysfs.c` en v6.0/v6.1 |
| Tipo y canales de memoria | blob GuC `DRM_XE_DEVICE_QUERY_HWCONFIG`: atributos `MAX_MEMORY_CHANNELS` (10), `MEMORY_TYPE` (11; enum LPDDR4/LPDDR5/HBM2/HBM2e/GDDR6) | no | 6.8 | nada. Qué rellena el GuC de cada Arc, **dudoso** | K`include/uapi/drm/xe_drm.h:703,760`; Mesa `src/intel/dev/intel_hwconfig_types.h` |
| Anchura de bus, tasa, ancho de banda | no lo publica el kernel | — | — | «—» (correcto como «no lo sé»; solo saldría de una tabla por modelo) | — |
| **Temperatura** | hwmon `xe`: `temp2_input` (label `pkg`), `temp3_input` (`vram`); 7.0 añade `temp4` (`mctrl`), `temp5` (`pcie`), `temp6..21` (`vram_ch_N`) y `tempX_crit/emergency/max` | no (0444) | **6.15** (pkg y vram; el ABI dice 6.15 y lo es); 7.0 el resto | **mal (alta)**: `_sensores` busca la etiqueta `edge` o `temp1_input` (`drm.py:904-912`); xe no tiene `temp1_input` (canal 0 = `card` sin temperatura) → `temp_c` None, y con `no_temperature_sensor=True` (`drm.py:192`) la ficha esconde la temperatura y dice «no publica su temperatura» (`graphics.py:164,196,599`). La de la VRAM sí sale (etiqueta `vram`, `drm.py:907`): la página enseña la de la memoria y niega la del chip | ABI-xe; K`drivers/gpu/drm/xe/xe_hwmon.c:45-52,1542-1572`; C`dac328dea701` (6.15), C`c332fba805d6`/C`49a498338417` (7.0) |
| Temperatura con DG2 forzada a xe | `temp2` = `PCU_CR_PACKAGE_TEMPERATURE`; `temp3` lee el registro de VRAM de BMG | no | 6.15 | igual que arriba; que `temp3` dé algo en DG2, **dudoso** | K`xe_hwmon.c:305-318` |
| Ventilador | `fan1_input`…`fan3_input` (RPM). En DG2 siempre dos canales y el segundo puede marcar 0 con el ventilador girando | no | **6.16** | **a medias**: solo `fan1_input` (`drm.py:920`); sin `pwm1` → sin %. Bien para una sola curva | ABI-xe; C`28f79ac609de` (6.16) |
| **Consumo** | no hay `power1_input`/`power1_average`: solo `energy1_input` (tarjeta, µJ, acumulado) y `energy2_input` (paquete) → vatios = ΔE/Δt | no (0444) | 6.8 (BMG: visible solo si el contador no es 0) | **nada**: lee `power1_average`/`power1_input` (`drm.py:914-916`); el RAPL no se le cuelga a una dedicada (bien, `drm.py:428`) | ABI-xe; K`xe_hwmon.c:1364-1380` |
| Límite de consumo | `power1_max` = PL1 sostenido (label `card`), `power1_rated_max` = TDP por defecto (no en BMG, que va por buzón), `power1_cap` = **PL2 de ráfaga**, `power1_crit` = I1 | no (lectura) | `power1_max` 6.8; `power1_cap` en BMG: **6.17** (el ABI dice 6.15) | **mal (media)**: `power_cap_w` = `power1_cap` (`drm.py:917-918`), que en xe es PL2 y no el límite de la tarjeta; la ficha pinta «— W» con «de X W» de PL2 debajo (`graphics.py:771-774`) | ABI-xe; K`xe_hwmon.c:1197-1240`; C`c713b9a23c73` (6.17) |
| Voltaje | `in1_input` (label `pkg`), **solo en DG2** (`REG_GT_PERF_STATUS`); BMG no lo publica | no | 6.8 | **nada**: busca etiquetas `vddgfx`/`vddnb` (`drm.py:925-927`) → «Voltaje —» en DG2 forzada | ABI-xe; K`xe_hwmon.c:338-341` |
| Frecuencia, RP0/RPe/RPn | `tile0/gt0/freq0/…` | no | 6.8 | igual que §2 (`cur_freq` en vez de `act_freq`) | §2 |
| Reloj de la VRAM | `tile0/memory/freq0/{max,min}_freq`, **solo en PVC** (Ponte Vecchio) | no | — | — (no existe en Arc) | K`drivers/gpu/drm/xe/xe_vram_freq.c:109` |
| Motivos de freno, reposo, motores, uso, unidades | como §2 | | | **nada** en todos; en la dedicada, «Estado —» porque `NA_INTEL_SIN_MOTIVOS` solo se aplica a integradas | §2 |
| Nota de permisos/temperatura | `INTEL_AVISOS` en cada Intel (`drm.py:430,511-521`) | | | **mal (media)**: sin permisos dice «Con permisos aparecen el uso de cada motor» (`es.json:887`) y no aparecen; con permisos y CPU Intel, `energy-gpu` abre y la nota es «hardware»: «El nodo DRM no trae hwmon… el uso de cada motor ya se está leyendo» (`es.json:885`), las dos cosas falsas | — |
| Firmware (VBIOS) | no hay `vbios_version`; versiones de GuC/HuC por `DRM_XE_DEVICE_QUERY_UC_FW_VERSION` | no | **dudoso** (6.9-6.10) | «—» | `xe_drm.h:763` |

---

#### 4. Arc dedicada con i915 (A310…A770, de serie desde 6.2)

| Dato | De dónde sale | ¿Permisos? | Desde | silux hoy | Fuente |
|---|---|---|---|---|---|
| Frecuencias, RP0/RP1/RPn | `cardN/gt/gt0/rps_*_freq_mhz` | no | DG2 sin `force_probe`: 6.2 | **bien** (mismo camino que la integrada) | §1 |
| Motivos de freno | `gt/gt0/throttle_reason_*` (DG2 es Gen12.55 ≥ 11) | no | 6.2 | **bien** | `intel_gt.c:235-243` |
| Reposo (RC6) | `gt/gt0/rc6_residency_ms` | no | 6.2 | **bien** | §1 |
| Motores y capacidades | `cardN/engine/` | no | 6.2 | **bien** | §1 |
| **Uso por motor** | PMU de nombre **`i915_0000_03_00.0`** en una dedicada (con `:` cambiado por `_`); `i915` a secas solo en la integrada | CAP_PERFMON | 6.2 | **mal (alta)**: el ayudante no acepta ese nombre (`helper.py:98`) y `_pmu_de` devuelve `"i915"` para cualquier i915 (`drm.py:557-558`). Con la integrada también en i915 —**todo portátil con Arc A-series móvil**, y los sobremesas con la iGPU activa— la Arc **se queda con el uso de la integrada**, motor a motor por nombre (`rcs0`, `vcs0`…, `drm.py:573-586`). Sin integrada: sin uso, y con CPU AMD la nota dice «el kernel tampoco publica contadores de ocupación» (`es.json:884`), falso | K`drivers/gpu/drm/i915/i915_pmu.c:1162-1172` |
| EU | `I915_PARAM_EU_TOTAL` | no | 6.2 | **bien, probable** (A770 = 512; sin comprobar en pieza) | `silux/i915.py` |
| **Enlace PCIe** | como §3: el extremo dice 2.5 GT/s × 1 | no | — | **mal (alta)**, igual que §3 | Intel 000094587 |
| VRAM total y visible | `DRM_I915_QUERY_MEMORY_REGIONS`: `probed_size`; `probed_cpu_visible_size` | no | regiones ≤ 5.15; `probed_cpu_visible_size` **6.0** | **a medias**: total por Vulkan; visible no → ReBAR «—» | `include/uapi/drm/i915_drm.h` en v5.19 (no) / v6.0 (sí); K`drivers/gpu/drm/i915/i915_query.c` (`query_memregion_info`) |
| VRAM ocupada | `probed_size − unallocated_size` | **CAP_PERFMON** (sin él, `unallocated_size = probed_size`) | ≤ 5.15 | **nada** | ídem |
| Resizable BAR | como §3 (BAR 2, `GEN12_LMEM_BAR`); i915 intenta además agrandarla al cargar | no | — | **nada** | K`drivers/gpu/drm/i915/gt/intel_region_lmem.c:51-105` |
| Tipo/canales de memoria | `DRM_I915_QUERY_HWCONFIG_BLOB` (mismo blob GuC) | no | **dudoso** | nada | — |
| **Temperatura** | hwmon `i915`: `temp1_input` **sin etiqueta** («GPU package temperature») | no | **6.13** (el ABI dice 6.12, y no está en v6.12) | **bien** desde 6.13: sale por el respaldo `temp1_input` (`drm.py:910-912`). Pero la nota de Intel (`drm.py:430`) sigue diciendo «Esta gráfica Intel no publica su temperatura» con la cifra en pantalla (**media-alta**). De 6.2 a 6.12 la falta es del kernel y no se dice así | ABI-i915; K`drivers/gpu/drm/i915/i915_hwmon.c:287,319-326`; C`0f47fed5c30f` (6.13) |
| Ventilador | `fan1_input` | no | **6.12** | **bien** desde 6.12 | ABI-i915; C`727eb1e3f014` (6.12) |
| Consumo | solo `energy1_input` (µJ); no hay `power1_input` | no (0444) | 6.2 | **nada** (`drm.py:914-916`) | ABI-i915 |
| Límite | `power1_max` (PL1), `power1_rated_max` (TDP), `power1_crit`; no hay `power1_cap` | no | 6.2 | **nada**: `power_cap_w` None | ABI-i915 |
| Voltaje | `in0_input`, **sin etiqueta** (`HWMON_I_INPUT` sin `LABEL`) | no | 6.2 | **nada**: solo busca por etiqueta (`drm.py:925-927`) | K`i915_hwmon.c:288` |
| Temperatura de VRAM, punto caliente | no existen en i915 | — | — | «—» | — |

---

### 1.3 NVIDIA: propietario, nvidia-open y nouveau
Investigación de solo lectura del 18-11-2026, sobre la rama `oficina` (7ff2f73).
No se ha tocado nada del repositorio. Aquí no hay ninguna NVIDIA: nada de esto se
ha ejecutado contra una tarjeta. Lo que viene del código fuente o de la cabecera
está comprobado leyéndolo. Lo que no se ha podido confirmar va marcado **dudoso**.

#### Fuentes que se han leído de verdad

| Clave | Qué es | Dónde |
|---|---|---|
| [nvml.h] | Cabecera de NVML sincronizada con CUDA 13.4.2 (`NVML_API_VERSION 13`), con todo su historial desde 2019 | https://github.com/NVIDIA/go-nvml/blob/main/gen/nvml/nvml.h (commit 6b38eea, 16-09-2026). Las versiones de «desde NVML x.y» salen de `git log -S` sobre ese archivo: es la primera versión de la cabecera en la que aparece el símbolo |
| [nvml-doc] | Referencia de la API | https://docs.nvidia.com/deploy/nvml-api/ (lo mismo que dicen los comentarios de [nvml.h], que es lo que se ha leído) |
| [readme-rtd3] | README del driver, cap. 22, RTD3 | https://download.nvidia.com/XFree86/Linux-x86_64/575.64/README/dynamicpowermanagement.html |
| [readme-proc] | README del driver, cap. 20, /proc | https://download.nvidia.com/XFree86/Linux-x86_64/595.84/README/procinterface.html |
| [nv-hwmon] | `drivers/gpu/drm/nouveau/nouveau_hwmon.c` (mainline) | https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/nouveau/nouveau_hwmon.c |
| [nv-dev] | `nvkm/engine/device/base.c`: qué subdispositivos tiene cada chip | https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/nouveau/nvkm/engine/device/base.c |
| [nv-gp100] | `nvkm/subdev/therm/gp100.c` | https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/nouveau/nvkm/subdev/therm/gp100.c |
| [nv-fanpwm] | `nvkm/subdev/therm/fanpwm.c` | https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/nouveau/nvkm/subdev/therm/fanpwm.c |
| [nv-gsp] | `nvkm/subdev/gsp/tu102.c` (`NvGspRm`, por defecto `true`) | https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/nouveau/nvkm/subdev/gsp/tu102.c |
| [nv-uapi] | `include/uapi/drm/nouveau_drm.h` | https://github.com/torvalds/linux/blob/master/include/uapi/drm/nouveau_drm.h |
| [nv-debugfs] | `nouveau_debugfs.c` (`pstate`) | https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/nouveau/nouveau_debugfs.c |
| [nv-pm] | Página de gestión de energía de nouveau | https://nouveau.freedesktop.org/PowerManagement.html |
| [kernel-ark MR 3058] | «redhat/configs: Enable DRM_NOUVEAU_GSP_DEFAULT everywhere» | https://gitlab.com/cki-project/kernel-ark/-/merge_requests/3058 (solo el título, visto en la búsqueda) |
| [pci-pm] | Commit 48991e493507 «PCI/sysfs: Ensure devices are powered for config reads» | https://github.com/torvalds/linux/commit/48991e493507 (en v6.18; marcado para stable) |

Los commits del kernel se han ubicado con `gh api repos/torvalds/linux/compare/vX...SHA`. Si sale «behind», el commit ya está en esa etiqueta:

| Commit | Qué hace | Primera versión |
|---|---|---|
| 176fdcbddfd2 | nouveau arranca GSP-RM (r535) | 6.7 |
| 1d492944d3d0 | Kconfig `DRM_NOUVEAU_GSP_DEFAULT` (la distribución decide) | 6.8 |
| 3f4d8aac6e76 / 72fa02fdf833 | `NOUVEAU_GETPARAM_VRAM_BAR_SIZE` / `_VRAM_USED` | 6.8 |
| 53dac0623853 / 284ad706ad2f | GSP r570 y Blackwell GB20x en nouveau | 6.16 |
| e0ed674acbac | Se quita el Kconfig: GSP-RM pasa a ir **siempre** por defecto en Turing y Ampere (`nouveau.config=NvGspRm=0` lo desactiva) | 6.18 |
| 48991e493507 | Leer `current_link_speed`/`current_link_width`/`max_link_width` **despierta** el dispositivo | 6.18 (+ stable) |

---

#### 0. Lo que más importa, antes de las tablas

1. **(alta, todos los drivers, sobre todo portátiles con NVIDIA) Leer el enlace PCIe en cada muestreo despierta la gráfica dedicada.**
   - Desde el kernel 6.18, y en los stable a los que se lleve el parche, leer `current_link_speed`, `current_link_width` y `max_link_width` hace `pci_config_pm_runtime_get()`, que saca el dispositivo de D3cold [pci-pm].
   - `GpuState.collect` llama a `_enlace()` en cada vuelta (`silux/providers/drm.py:413`), y recorre toda la cadena de puentes (`drm.py:654-708`).
   - En un portátil Optimus con RTD3 la dedicada no llega a dormir nunca mientras silux está abierto. RTD3 va por defecto en portátiles Ampere o posteriores [readme-rtd3].
   - Con NVML pasa probablemente lo mismo: cada llamada habla con el RM de la tarjeta. **Dudoso**: el README no dice expresamente que NVML o `nvidia-smi` despierten la GPU; solo que todo acceso MMIO exige encenderla antes.
   - silux no mira el estado de energía en ningún sitio: `grep runtime_status` sale vacío. El arreglo obvio es mirar antes `/sys/bus/pci/devices/<bdf>/power/runtime_status` (que sea `suspended`) o `power_state` (`D3cold`). Ninguna de las dos lee el espacio de configuración (**dudoso** para `power_state`: devuelve el estado guardado). Si duerme, se enseña «en reposo (D3)» y no se pregunta nada más, ni a sysfs ni a NVML.
   - Ojo: esto también afecta a `PciDevices` si lee esos ficheros. No se ha revisado.
2. **(media) NVML no avisa cuando falla.** `NvidiaGpus.unavailable_reason()` devuelve `None` siempre (`providers/nvidia.py:46-47`). `Nvml.open()` no guarda por qué falló (`nvml.py:117-133`) y lo vuelve a intentar en cada muestreo: un `dlopen` y un `nvmlInit_v2` por segundo.
   - El caso típico es «Driver/library version mismatch» después de actualizar el driver sin reiniciar. En ese caso la página se queda con el aviso genérico «el driver propietario no publica nada en sysfs» y ninguna cifra.
3. **(media) Con nouveau, la página promete datos que no existen.** La pista `prov.drm.nouveau.hint` (`db/lang/es.json:898`) dice «quedan la temperatura, el enlace PCIe y la memoria». No es verdad desde Ampere, ni en Turing con GSP: ahí nouveau no registra ningún hwmon (sección 3).
4. **(media) Los motivos de recorte de NVIDIA están en español fijo** (`nvml.py:34-44`) y no pasan por `_()`. Con la interfaz en inglés salen en español; es un caso más de F-M8. Además, un motivo que la tabla no conoce hace que la tarjeta diga «no se frena» (sección 4).

---

#### 1. Driver propietario y nvidia-open (NVML)

**Contexto común:**
- Los dos módulos se llaman `nvidia`, así que en sysfs `driver → nvidia` en los dos casos. Lo que los distingue es la línea de `/proc/driver/nvidia/version`. **Dudoso** el texto exacto: «NVIDIA UNIX Open Kernel Module…» frente a «NVIDIA UNIX x86_64 Kernel Module…».
- NVML es el mismo en ambos.
- El módulo abierto solo existe para Turing y posteriores. Según los anuncios de NVIDIA es el que se instala por defecto desde la rama r560, y r580 es la última rama para Maxwell, Pascal y Volta. **Dudoso**: no se ha comprobado aquí.
- La rama r470 es la última para Kepler.

Lo que el kernel deja en sysfs es solo lo genérico del nodo PCI (vendor/device/subsystem, enlace, `boot_vga`) y, si `nvidia-drm` está cargado, el nodo `cardN` con sus conectores.
- **No hay hwmon**: en `open-gpu-kernel-modules` no se encuentra ningún `hwmon_device_register*`. La búsqueda de código de GitHub no devolvió nada, así que es **dudoso** que no exista en algún rincón.
- En `/proc/driver/nvidia/` hay `version`, `warnings`, `gpus/<bus>/information` (modelo, IRQ, VBIOS…) y `gpus/<bus>/power` (estado de RTD3) [readme-proc]. Se leen sin permisos y sin cargar NVML. Sirven de respaldo para el nombre y el VBIOS, y `power` dice si la tarjeta duerme. **Dudoso** si leer `information` despierta la tarjeta: el README dice que algunos campos solo están «después de inicializar la GPU».

`nvmlInit_v2` no pide root. Necesita poder abrir `/dev/nvidiactl` y `/dev/nvidiaN`, que normalmente son 0666. Si no puede, devuelve `NVML_ERROR_NO_PERMISSION`; si el driver no está, `NVML_ERROR_DRIVER_NOT_LOADED` [nvml.h, doc de `nvmlInit_v2`]. Ninguna lectura de esta tabla pide root: las funciones que lo piden son las de escritura (`Set*`) y algunas de centro de datos (`GetCPER`, `GetSramEccErrorStatus`, `GetClkMonStatus`).

Las GeForce tienen soporte «limitado» en NVML; el «completo» es para Tesla, Quadro y Titan [nvml.h, cabecera]. En la práctica, todo lo de la tabla devuelve dato en GeForce salvo donde se indica.

| Dato que enseña la página (o que faltaría) | De dónde sale | ¿Permisos? | Desde qué versión | Qué hace silux hoy | Fuente |
|---|---|---|---|---|---|
| Nombre | `nvmlDeviceGetName` (búfer 96 = `NVML_DEVICE_NAME_V2_BUFFER_SIZE`) | no | siempre | **bien** lo lee, pero solo rellena si `name` está vacío (`nvidia.py:126-128`). El de `pci.ids` («GeForce RTX 3050 Mobile / Max-Q») gana al de NVML («NVIDIA GeForce RTX 3050 Laptop GPU»), que es más preciso. Lo afina Vulkan solo si hay «/» (`gpu_apis.py:256-264`). Baja | [nvml.h] |
| VBIOS | `nvmlDeviceGetVbiosVersion` (búfer 32) | no | siempre | **bien** (`nvml.py:243`) | [nvml.h] |
| Versión del driver | `nvmlSystemGetDriverVersion` (búfer 80) | no | siempre | **bien** (`nvml.py:157`). No dice si es el módulo abierto; eso sale de `/proc/driver/nvidia/version` | [nvml.h], [readme-proc] |
| UUID | `nvmlDeviceGetUUID` (búfer 96) | no | siempre | **bien** (`nvml.py:246`), va a `unique_id` | [nvml.h] |
| Número de serie de la placa | `nvmlDeviceGetSerial` | no | siempre; en GeForce `NOT_SUPPORTED` | **mal (higiene)**: se lee y no se usa (`nvml.py:245`). En una Quadro trae el serial real. Va contra el criterio de «no abrir nunca un número de serie». Baja | [nvml.h] |
| Ranura PCI | `nvmlDeviceGetPciInfo_v3` → `busId` «%08X:%02X:%02X.0» | no | `_v3` ya está en la cabecera de 2019 (r418+) | **bien** con `_v3` (`nvml.py:58-66` coincide con `nvmlPciInfo_t`: 16+5×4+32 = 68 bytes). Los respaldos `_v2`/v1 tienen otra disposición (`busId` de 16 al principio): con esa estructura `busId` caería sobre basura. Hoy es código muerto, porque ningún driver que corra en 5.15 carece de `_v3`. Baja | [nvml.h] |
| Arquitectura | `nvmlDeviceGetArchitecture` (Kepler=2 … Blackwell=10) | no | ya en 2019; `ARCH_BLACKWELL` desde NVML 12.6 | **nada**. `_nucleos_cuda` deduce la arquitectura de las dos primeras letras del `codename` de `pci.ids` (`nvidia.py:106`). Sin `pci.ids`, o con una NVIDIA sin nodo DRM, se queda en `None`. Con esta llamada no haría falta `pci.ids` | [nvml.h] |
| Núcleos CUDA | `nvmlDeviceGetNumGpuCores` | no | NVML 11.6 (r510) | **bien** con el arreglo de los SM (`nvidia.py:90-108`) | [nvml.h] |
| Anchura de bus de memoria | `nvmlDeviceGetMemoryBusWidth` | no | NVML 11.6 (r510); en r470 no existe → `None` | **bien** | [nvml.h] |
| Tipo de memoria (GDDR6, GDDR6X…) | — | — | NVML no lo publica (no hay `GDDR` ni `RamType` en [nvml.h] 13.4) | nada (correcto; ya está en hardware-validado) | [nvml.h] |
| VRAM total / usada | `nvmlDeviceGetMemoryInfo` (v1) o `nvmlDeviceGetMemoryInfo_v2` (`version = sizeof \| 2<<24`, 40 bytes: version, total, reserved, free, used) | no | `_v2` desde NVML 11.6 (r510) | **mal, leve** (`nvml.py:223`): usa v1, cuyo `used` es «la suma de lo reservado y lo asignado». En v2, `used` es lo asignado y lo reservado va aparte. Con r510+ silux da varios cientos de MB más que `nvidia-smi` en «Used». **Dudoso** el tamaño de la diferencia, y el comentario de la propia función v2 es ambiguo | [nvml.h] |
| Uso del núcleo y del controlador de memoria | `nvmlDeviceGetUtilizationRates` (`gpu`, `memory`: % del periodo, de 1/6 s a 1 s) | no | siempre | **bien** (`nvml.py:224,251-252`) | [nvml.h] |
| Uso del codificador y el decodificador | `nvmlDeviceGetEncoderUtilization` / `GetDecoderUtilization` (`utilization`, `samplingPeriodUs`); `GetJpgUtilization`/`OFA` desde NVML 12.2 | no | Kepler+; ya en 2019 | **nada**: la fila «Uso del motor de video» (`video_busy_percent`) queda con guion en NVIDIA. Valdría `max(enc, dec)` o dos filas | [nvml.h] |
| Reloj del núcleo (actual / máximo) | `nvmlDeviceGetClockInfo` / `GetMaxClockInfo` con `NVML_CLOCK_GRAPHICS=0` | no | siempre | **bien** (`nvml.py:259-260`), salvo que 0 MHz → `None` (`nvml.py:228`, F-M20) | [nvml.h] |
| Reloj SM | igual, con `NVML_CLOCK_SM=1` | no | siempre | **nada**. En GeForce coincide con el gráfico (**dudoso**); no hace falta | [nvml.h] |
| Reloj de memoria (actual / máximo) | igual, con `NVML_CLOCK_MEM=2` | no | siempre | **bien** como dato, **dudoso** como cifra. NVML da la mitad de la tasa de datos (un GDDR6 de 14 Gbps sale ~7000 MHz): no es comparable con el `mclk` de amdgpu de la fila de al lado. **Dudoso**: hay que contrastarlo con `nvidia-smi -q -d CLOCK` en un volcado. Si se confirma, `memory.data_rate_hz = 2×reloj` y el ancho de banda se calculan (hoy nada: `nvidia.py:132-139`) | [nvml.h] |
| Reloj de video | igual, con `NVML_CLOCK_VIDEO=3` | no | siempre | **se lee y se tira** (`nvml.py:263`; `_rellenar` no lo usa). `GpuClocks` no tiene ese campo | [nvml.h] |
| Reloj de boost de fábrica | `nvmlDeviceGetClock(dev, GRAPHICS, NVML_CLOCK_ID_CUSTOMER_BOOST_MAX)` | no | ya en 2019 | **nada**. Sería el «Boost» de GPU-Z; `GetMaxClockInfo` da el techo del VBIOS, que suele estar más alto. **Dudoso** en GeForce | [nvml.h] |
| P-state | `nvmlDeviceGetPerformanceState` → `nvmlPstates_t` (0–15; 32 desconocido) | no | Fermi+ | **nada**. `clocks.performance_level` existe (es el perfil de AMD) y podría llevar «P8» | [nvml.h] |
| Temperatura del núcleo | `nvmlDeviceGetTemperature(dev, NVML_TEMPERATURE_GPU=0)`; desde NVML 12.8, `nvmlDeviceGetTemperatureV` (estructura `{version, sensorType, int temperature}`, versión `12 \| 1<<24`) | no | v1 siempre, pero **obsoleta en NVML 13.0** (sigue en la cabecera 13.4); `TemperatureV` desde 12.8 (r570) | **bien hoy** (`nvml.py:253-254`). Riesgo a futuro: si quitan el símbolo, `_sim` devuelve `None` y se pierde en silencio. Conviene `TemperatureV` primero | [nvml.h] |
| Punto caliente (hotspot) | `NVML_TEMPERATURE_GPU_MAX = 1` («hottest part of the GPU die») por `TemperatureV` | no | **solo en la cabecera de CUDA 13.4** (sept. 2026); qué driver lo trae y si va en GeForce, **dudoso** | **nada**. Antes de 13.4 NVML no lo publicaba para GeForce: confirmado, el enum solo tenía `GPU`. Probar `TemperatureV(GPU_MAX)` y quedarse con `None` si da `NOT_SUPPORTED` | [nvml.h], historial de go-nvml (13faa2c) |
| Temperatura de la memoria | `nvmlDeviceGetFieldValues` con `NVML_FI_DEV_MEMORY_TEMP = 82` | no | ya en 2019 | **nada**. En GeForce con GDDR se espera `NOT_SUPPORTED` (**dudoso**: está pensado para HBM). Si contesta, va a `memory_temp_c` | [nvml.h] |
| Margen hasta el frenado térmico | `nvmlDeviceGetMarginTemperature`; umbrales con `GetTemperatureThreshold` (en Ada+, mejor `FieldValues` `NVML_FI_DEV_TEMPERATURE_*_TLIMIT` 193-196, NVML 12.2) | no | `Margin` desde NVML 12.8 | **nada**. Útil al lado de «Estado» | [nvml.h] |
| Ventilador (%) | `nvmlDeviceGetFanSpeed` → % de «la velocidad máxima por ruido»; **puede pasar de 100** y es la velocidad **pedida**, no la medida | no | siempre; `NOT_SUPPORTED` si no hay ventilador (portátiles) | **bien** a medias (`nvml.py:257-258`): solo el ventilador 0, y no avisa de que es la velocidad pedida | [nvml.h] |
| Varios ventiladores | `nvmlDeviceGetNumFans` + `nvmlDeviceGetFanSpeed_v2(dev, i, &pct)` | no | `NumFans` desde NVML 11.6; `_v2` ya en 2019 | **nada**. La doc de `_v2` dice «NOT_SUPPORTED… si es más nueva que Maxwell», que parece una errata (**dudoso**) | [nvml.h] |
| Ventilador (RPM) | `nvmlDeviceGetFanSpeedRPM(dev, {version, fan, speed})`, versión `12 \| 1<<24` | no | NVML 12.8 (r570); Maxwell+ | **nada** (`fan_rpm` queda vacío). `render.fan` ya sabe juntar RPM y % | [nvml.h] |
| Consumo | `nvmlDeviceGetPowerUsage` (mW). En Ampere+ (menos GA100) es la **media de 1 s**; antes, instantáneo. `NVML_FI_DEV_POWER_INSTANT` (186) y `_AVERAGE` (185) por `FieldValues` desde NVML 12.2 | no | Fermi+; solo si hay gestión de energía | **bien** (`nvml.py:255`) | [nvml.h] |
| Energía acumulada | `nvmlDeviceGetTotalEnergyConsumption` (mJ, `unsigned long long`) | no | Volta+ | **nada**. Sería la vía para una media exacta entre muestreos, como RAPL | [nvml.h] |
| Límite de consumo | `nvmlDeviceGetEnforcedPowerLimit` (mW, el que de verdad se aplica); `GetPowerManagementLimitConstraints` (mín/máx); `GetPowerManagementDefaultLimit` | no | Kepler+ | **bien** (`nvml.py:256`) | [nvml.h] |
| Enlace PCIe actual / máximo | `nvmlDeviceGetCurrPcieLinkGeneration/Width`, `GetMaxPcieLinkGeneration/Width`; `GetGpuMaxPcieLinkGeneration` (lo que admite la GPU, NVML 12.0) | no | siempre | **bien**, solo de respaldo. Manda sysfs, que vale igual con el driver propietario y además mira toda la cadena. Ver 0.1: la lectura de sysfs despierta la tarjeta | [nvml.h], [pci-pm] |
| Motivos de recorte | `nvmlDeviceGetCurrentClocksEventReasons` (NVML 12.2, r535); el nombre viejo `…ThrottleReasons` es **obsoleto desde 13.0** (sigue declarado). Bits: 0x1 idle, 0x2 app clocks (obsoleto, «no longer used»), 0x4 SW power cap, 0x8 HW slowdown, 0x10 sync boost, 0x20 SW thermal, 0x40 HW thermal, 0x80 power brake, 0x100 display clock, **0x200 BoardLimit, 0x400 Reliability (NVML 13.4)** | no | siempre | **mal, media-baja** (`nvml.py:232-234, 268, 282-285`): usa el símbolo obsoleto sin respaldo al nuevo; ignora los bits que no conoce, así que con solo 0x200 activo sale `throttled=False`; textos sin traducir. Ver sección 4 | [nvml.h] |
| Estado de RTD3 (dormida o no) | `/proc/driver/nvidia/gpus/<bus>/power` («Runtime D3 status», «Video Memory…»); genérico: `power/runtime_status` | no | RTD3 en Turing+; por defecto solo en portátiles Ampere+ (`NVreg_DynamicPowerManagement=0x03`) | **nada**: ver 0.1 | [readme-rtd3], [readme-proc] |
| VRAM visible / ReBAR | `nvmlDeviceGetBAR1MemoryInfo` (total de la BAR1) | no | ya en 2019 | **nada**. La fila «ReBAR» queda con guion; con BAR1 = VRAM, ReBAR está activo (**dudoso** en portátiles) | [nvml.h] |
| Integrada | — | — | — | **bien** para GeForce y Quadro (`nvidia.py:142`, `drm.py:367-370`); ver nouveau para los chipsets MCP | — |

---

#### 2. nouveau en chips anteriores a Turing (y Turing con `NvGspRm=0`)

nouveau registra un hwmon llamado `nouveau` colgado del dispositivo PCI (`cardN/device/hwmon/hwmonX`), que es donde lo busca `_hwmon()`. Solo lo registra si el chip tiene alguno de `therm`, `volt` o `iccsense` [nv-hwmon, `nouveau_hwmon_init`]. Lo que hay en cada chip sale de la tabla de [nv-dev]:

| Generación | `therm` (temp1, ventilador) | `volt` (in0) | `iccsense` (power1) | `clk` (cambiar de reloj) |
|---|---|---|---|---|
| NV40–NV50, G8x–GT21x, MCP7x/89 | sí | sí | no | sí |
| Fermi GF1xx | sí | sí | sí* | sí |
| Kepler GK1xx | sí | sí | sí* | sí |
| Maxwell 1 GM107/108 | sí | sí | sí* | sí |
| Maxwell 2 GM20x | sí | sí | sí* | **no** |
| Pascal GP10x, Volta GV100 | sí (solo `temp_get`) | **no** | **no** | **no** |
| Turing TU10x/11x **sin** GSP | sí (`gp100_therm`) | no | no | no |

\* `power1_*` solo aparece si la placa lleva sensores de corriente (INA2xx) y el VBIOS los describe: `iccsense->data_valid && !list_empty(rails)` [nv-hwmon, `nouveau_power_is_visible`]. Muchas tarjetas no los llevan.

**Lo que no depende del permiso de nadie:** las lecturas del hwmon de nouveau devuelven `-EINVAL` si la GPU no está encendida (`switch_power_state != DRM_SWITCH_POWER_ON`), así que no la despiertan [nv-hwmon, líneas de `nouveau_temp_read`, `fan_read`, `in_read`, `power_read`]. La lectura del enlace sí la despierta (0.1).

| Dato | De dónde sale | ¿Permisos? | Desde qué kernel | Qué hace silux hoy | Fuente |
|---|---|---|---|---|---|
| Nombre, IDs, subsistema, enlace | nodo PCI genérico | no | todos | **bien** (`DrmGpus._identidad`, `_enlace`) | — |
| Temperatura | `temp1_input` (m°C), **sin** `temp1_label`; también `temp1_max/crit/emergency` (+ `_hyst`) | no | ≤ 5.15 | **bien**: cae al `temp1_input` sin etiqueta (`drm.py:910-912`) | [nv-hwmon] |
| Umbral térmico (aviso / crítico) | `temp1_max`, `temp1_crit` (del VBIOS) | no | ≤ 5.15 | **nada** | [nv-hwmon] |
| Ventilador RPM | `fan1_input`; solo si hay tacómetro (`nvkm_therm_fan_sense ≥ 0`) | no | ≤ 5.15 | **bien** (`drm.py:920`) | [nv-hwmon] |
| Ventilador % | `pwm1` **en tanto por ciento (0–100), no en 0–255** (`fanpwm.c:52`: `duty*100/divs`). `pwm1_min`/`pwm1_max` son los **topes de ciclo** configurados, también en % | no | ≤ 5.15 | **mal, media** (`drm.py:921-923`): divide `pwm1` entre `pwm1_max`. Si el VBIOS pone el ciclo máximo en 80 %, un ventilador al 80 % sale «100 %»; si `pwm1_max` no se puede leer, divide entre 255 y sale «31 %». En nouveau, `pwm1` ya es el porcentaje. Pascal y posteriores no tienen `pwm` (no hay `pwm_get` en `gp100_therm`), y en GM20x nouveau no controla el ventilador [nv-pm] | [nv-hwmon], [nv-fanpwm], [nv-gp100] |
| Voltaje del núcleo | `in0_input` (mV), `in0_label = "GPU core"`, `in0_min/max` | no | ≤ 5.15 | **mal, baja** (`drm.py:925-926`): solo busca las etiquetas `vddgfx`/`vddnb` de amdgpu; «GPU core» se pierde y la fila queda con guion | [nv-hwmon] (`input_label`) |
| Consumo | `power1_input` (µW) | no | ≤ 5.15 | **bien** (`drm.py:914-916`) cuando existe | [nv-hwmon] |
| Límite de consumo | `power1_cap_max` y `power1_crit` (de `iccsense->power_w_max/crit`). **No** existe `power1_cap` | no | ≤ 5.15 | **nada** (`drm.py:917` busca `power1_cap`) | [nv-hwmon] (`HWMON_P_CAP_MAX \| HWMON_P_CRIT`) |
| Uso del núcleo | — | — | nouveau no tiene `gpu_busy_percent` (solo amdgpu lo define) ni fdinfo de motores (**dudoso**: la búsqueda de `show_fdinfo` en nouveau no encontró nada) | nada (correcto: no hay de dónde) | búsqueda en el árbol |
| Relojes actuales y tabla de estados | debugfs `/sys/kernel/debug/dri/N/pstate`: una línea por estado «`0f: core 405-1124 MHz memory 3004 MHz …`» y la actual «`AC: core … *`» | **root** (debugfs) | ≤ 5.15 | **nada**. Sería trabajo del ayudante privilegiado, y eso, según CLAUDE.md, se propone antes de escribirlo | [nv-debugfs] |
| Cambio de reloj | escribir en `pstate` | root | NV40/NV50 «mostly», Fermi y Kepler a medias; GM20x+ no se puede (firmware firmado) | no aplica a un perfilador: basta con decir que la tarjeta está **clavada en los relojes de arranque** en Pascal sin GSP | [nv-pm], [nv-dev] |
| VRAM total | ioctl `DRM_IOCTL_NOUVEAU_GETPARAM` con `NOUVEAU_GETPARAM_FB_SIZE` (8) sobre `renderD*` | no (nodo de render) | ≤ 5.15 | **nada**. Lo cubre Vulkan si hay NVK; sin NVK (Kepler y anteriores, o sin Mesa reciente) se queda vacío. El patrón de `amdgpu.py`/`i915.py` con `sysroot.a_traves` sirve igual | [nv-uapi] |
| VRAM usada | `NOUVEAU_GETPARAM_VRAM_USED` (19) | no | **6.8** | nada | [nv-uapi], commit 72fa02fdf833 |
| BAR visible (ReBAR) | `NOUVEAU_GETPARAM_VRAM_BAR_SIZE` (18) | no | **6.8** | nada | [nv-uapi], commit 3f4d8aac6e76 |
| Unidades (GPC/TPC) | `NOUVEAU_GETPARAM_GRAPH_UNITS` (13) | no | ≤ 5.15 | nada. **Dudoso** qué empaqueta exactamente; no sustituye a los núcleos CUDA | [nv-uapi] |
| VBIOS | debugfs `vbios.rom` (la imagen entera) | root | — | nada; la versión no está en sysfs | [nv-debugfs] |
| Integrada | — | — | — | **mal, baja** (`drm.py:367-370`): «una NVIDIA nunca es integrada», pero nouveau maneja chipsets que sí lo son: C51, C61, C67, C68, C73, MCP77/78, MCP79/7A (GeForce 9400M, ION) y MCP89 (GeForce 320M) [nv-dev]. Se arregla con una lista de `device_id` o con la clase de chipset | [nv-dev] |

---

#### 3. nouveau en Turing y posteriores con GSP-RM

Con GSP-RM el firmware gestiona la energía, los relojes y el ventilador por su cuenta [nv-pm: «Managed by firmware»]. El driver de nouveau se queda sin los subdispositivos que alimentaban el hwmon:
- `gp100_therm_new()` devuelve `-ENODEV` si `nvkm_gsp_rm()` [nv-gp100].
- Ampere, Ada, Hopper y Blackwell ni siquiera tienen `therm`, `volt` ni `iccsense` en la tabla [nv-dev].

**Resultado: en Turing con GSP y en todo lo posterior, nouveau no registra ningún hwmon.**

Cuándo va GSP:

| Chip | Kernel | GSP |
|---|---|---|
| Ada (AD10x) | 6.7+ | siempre (no hay otra vía) |
| Turing / Ampere | 6.7 | opcional, con `nouveau.config=NvGspRm=1` |
| Turing / Ampere | 6.8–6.17 | según el Kconfig `DRM_NOUVEAU_GSP_DEFAULT` de la distribución (Fedora/RHEL lo activan [kernel-ark MR 3058]) |
| Turing / Ampere | **6.18+** | siempre por defecto (`NvGspRm` vale `true` en [nv-gsp]) |
| Blackwell GB20x | **6.16+** | siempre (r570) |

| Dato | De dónde sale | ¿Permisos? | Desde qué kernel | Qué hace silux hoy | Fuente |
|---|---|---|---|---|---|
| Identidad y enlace | nodo PCI | no | todos | **bien** | — |
| Temperatura, ventilador, voltaje, consumo | — (sin hwmon) | — | — | **la página no lo explica**: el tile de temperatura y la tarjeta de sensores salen a guiones y la pista dice que «queda la temperatura» (`es.json:898`, `en.json:898`). Hay que distinguir «nouveau + GSP» (se ve en `dmesg` o por el chip: TU1xx con kernel ≥ 6.18, GA/AD/GB siempre) y esconderlo con su frase al pie (regla 5), como `no_temperature_sensor` en Intel | [nv-gp100], [nv-dev] |
| Relojes | ni sysfs ni debugfs (`pstate` sin `clk` no tiene estados) | — | — | nada (correcto) | [nv-dev] |
| VRAM total / usada / BAR | getparam `FB_SIZE`, `VRAM_USED`, `VRAM_BAR_SIZE` | no | `FB_SIZE` siempre; los otros dos 6.8 | **nada**; con NVK lo cubre Vulkan (el total) | [nv-uapi] |
| Uso | — | — | — | nada (correcto) | — |

---

### 1.4 Equipos con dos gráficas
Revisión de solo lectura, 18-11-2026, sobre la rama `oficina` (`7ff2f73`). No se ha tocado
ningún archivo del repositorio. Leyenda:

- **[código]**: confirmado leyendo el código de silux.
- **[fuente]**: confirmado con la documentación, el código del kernel o la lista de correo que se cita.
- **[medido]**: visto en el i5-10400 de la oficina (Fedora 44, kernel 7.3.3, UHD 630).
- **dudoso**: deducido, sin confirmar. Lleva al lado lo que haría falta para confirmarlo.

---

#### 0. Lo que hay que saber antes de la tabla

##### Cómo decide Linux cuál es la «principal»

Son cuatro preguntas distintas, y cada fuente contesta solo una:

| Pregunta | Fuente | Sin root | ¿Despierta la dedicada? |
|---|---|---|---|
| ¿Con cuál arrancó el firmware? | `/sys/bus/pci/devices/X/boot_vga` | sí | no: es `vga_default_device()`, sin acceso a la tarjeta |
| Lo mismo, para tarjetas que no son de clase VGA | `boot_display` (serie de Limonciello, 2025) | sí | no |
| ¿Cuál lleva una pantalla ahora? | `/sys/class/drm/cardN-*/status` = `connected` | sí | no: `status_show` devuelve el estado guardado |
| ¿Cuál dibuja un programa si no se le dice nada? | renderer de OpenGL/EGL sin `DRI_PRIME` | sí | **sí**, si la que contesta es la dedicada |
| ¿Cuál es la integrada y cuál la dedicada, y qué variables hay que poner para elegir? | switcheroo-control por D-Bus: `GPUs` (`aa{sv}`) con `Name`, `Environment`, `Default`, `Discrete` | sí | no lo creo, pero es **dudoso**: no se ha mirado cómo calcula `Discrete` |
| ¿Cuál tiene el mux? (solo equipos con mux o del tipo anterior a runtime PM) | `/sys/kernel/debug/vgaswitcheroo/switch` | **no** (debugfs) | no |

Lo que se sabe de cada fuente:

- **`boot_vga`** solo existe en dispositivos de **clase VGA (0x0300)**. Una dedicada de portátil
  que se anuncia como «controlador 3D» (0x0302) no lo tiene. **[fuente]**: en el hilo de LKML
  de junio de 2026 Limonciello y Zimmermann acuerdan que `boot_vga` significa «el firmware
  inicializó este dispositivo VGA» y que no hay que exportarlo en dispositivos que no son VGA.
- **`boot_vga` puede señalar la tarjeta equivocada**. Hay firmwares que ponen el framebuffer en
  una tarjeta de clase 0x0380 («Display controller», el caso de algunas iGPU de AMD). vgaarb solo
  registra las de clase VGA, así que `boot_vga=1` acaba en la dedicada. **[fuente]**: parche
  «PCI: vgaarb: Include 0x0380 devices in boot VGA selection» (Aaron Ma, junio de 2026). Su
  descripción dice que eso hace que «boot_vga point at the wrong GPU».
- **`boot_display`** se propuso en julio de 2025 (v9) y la entrada de su ABI es de octubre de
  2025. **Dudoso** que esté en todos los kernels: **[medido]** en el kernel 7.3.3 de la oficina
  no existe en `0000:00:02.0`, y esa tarjeta tiene `boot_vga=1`. Puede que solo aparezca en
  tarjetas que no son VGA, o que no entrara así. Mientras tanto, se lee si existe y si no se
  vuelve a `boot_vga`, como hace la MR !2242 de Xorg.
- **switcheroo-control 3.0** (el de Fedora 44, **[medido]**) contesta en
  `net.hadess.SwitcherooControl` con `HasDualGpu`, `NumGPUs` y `GPUs`. En la oficina devuelve
  `Name "Intel® UHD Graphics 630"`,
  `Environment ["DRI_PRIME","pci-0000_00_02_0","VK_LOADER_DRIVERS_SELECT","*intel*"]`,
  `Default true` y `Discrete false`. Su NEWS de la 3.0 dice que la clave `Discrete` funciona con
  amdgpu, nouveau, i915, xe y el driver propietario de NVIDIA. Que `Default` salga de
  `boot_vga` en x86 es **dudoso**: la 2.6 dice «fixes non-x86 platforms not having a default
  GPU», que encaja con eso, pero no se ha leído su código. Es la mejor segunda opinión que hay
  sin root, y además da las variables de entorno para cada tarjeta.
- **PRIME / offload**. Con Mesa, `DRI_PRIME=1` elige «la primera que no es la de por omisión»,
  y también acepta `DRI_PRIME=pci-0000_01_00_0`. Con el driver propietario de NVIDIA son
  `__NV_PRIME_RENDER_OFFLOAD=1` y `__GLX_VENDOR_LIBRARY_NAME=nvidia`; en Vulkan,
  `__VK_LAYER_NV_optimus=NVIDIA_only`. Sin variables dibuja la tarjeta en la que corre el
  compositor, que casi siempre es la de `boot_vga`. **Dudoso** en un caso: con EGL
  surfaceless y glvnd, si el proveedor de NVIDIA se adelanta al de Mesa. Así pregunta silux
  (`gpuapi.py:350`), y no se ha comprobado en un Optimus.
- **vga_switcheroo** (docs.kernel.org/gpu/vga-switcheroo.html) es para los equipos con mux y
  para el apagado del modelo anterior (`DynOff`/`DynPwr`). En `debugfs` el `+` marca la tarjeta
  activa. Pide root y debugfs montado, así que no le sirve a silux.

##### Qué pasa al leer una dedicada dormida

Los estados (**[fuente]**: `Documentation/ABI/testing/sysfs-devices-power` y `sysfs-bus-pci`):

- `device/power/runtime_status` vale `active`, `suspended`, `suspending`, `resuming`, `error` o
  `unsupported`. Leerlo no despierta nada.
- `device/power_state` (desde noviembre de 2020, kernel 5.11, por debajo del suelo de 5.15) vale
  `D0`, `D3hot`, `D3cold`… Lee `pdev->current_state` y tampoco despierta.
- `device/power/control` vale `auto` (puede dormir) u `on`.
- NVIDIA propietaria: `/proc/driver/nvidia/gpus/<bus>/power` lleva «Runtime D3 status» y «Video
  Memory» (README de NVIDIA, cap. 22).

Lo que despierta y lo que no, fuente por fuente:

| Lo que se lee | Kernel o driver | Comportamiento | Estado |
|---|---|---|---|
| `current_link_speed`, `current_link_width`, `max_link_width` | **≥ 6.18** y llevado a las ramas estables | `pci_config_pm_runtime_get()`: **despierta** una tarjeta en D3cold para leer el espacio de configuración | **[fuente]** parche de Brian Norris, «PCI/sysfs: Ensure devices are powered for config reads», aplicado para 6.18 |
| lo mismo | < 6.18 | no despierta, pero devuelve `-EINVAL` o valores falsos | **[fuente]** el mismo parche, que lo dice en su mensaje |
| `max_link_speed` | todos los de ≥ 6.12 | valor guardado: ni despierta ni miente | **[fuente]** el mismo hilo |
| `gpu_busy_percent`, `pp_dpm_*`, `gpu_metrics`, hwmon de amdgpu | **actual** | `amdgpu_pm_get_access_if_active()`: si está suspendida, **`-EPERM`**, sin despertarla | **[fuente]** `amdgpu_pm.c` actual |
| lo mismo | 5.15 – 6.1x | `pm_runtime_get_sync()`: **despierta** | **dudoso** en la versión exacta del cambio (serie de Lazar, febrero de 2025; antes, Limonciello en 2024: «Don't wake dGPUs while reading sensors») |
| `mem_info_vram_*` | amdgpu | no pasa por runtime PM | probable |
| abrir `/dev/dri/renderD*` de amdgpu (ioctl, VA-API, Vulkan) | amdgpu | `amdgpu_driver_open_kms` llama a `pm_runtime_get_sync`: **despierta** | **dudoso** (de memoria del código; falta mirar `amdgpu_kms.c`) |
| hwmon de nouveau | nouveau | `-EINVAL` sin despertarla (commit de Lyude de 2018) | **dudoso** |
| NVML (`nvmlInit` + consultas) | NVIDIA propietaria | El README dice «Whenever an application requiring NVIDIA GPU access is started, the GPU is put into an active state», y que vuelve a dormir cuando la aplicación sale. Una sesión de NVML abierta casi seguro la mantiene despierta. Hay además un informe en el foro de NVIDIA (550.163, RTX 5000 Ada Laptop) de NVML dando **588–593 W** con la tarjeta en RTD3 | NVML en concreto **dudoso**; el informe del foro, sin confirmar |
| `cardN-*/status`, `edid`, `modes` | DRM | se devuelve lo guardado | **[fuente]** `drm_sysfs.c` `status_show` |

**Cómo no despertarla solo por mirar.** En cada muestreo y para cada tarjeta, leer primero
`device/power/runtime_status` y, si existe, `device/power_state`. Si dice `suspended`, o
`D3hot`/`D3cold`, no tocar enlace, hwmon, `gpu_metrics`, `pp_dpm_*` ni NVML. Se conserva lo
estático y se dice «apagada por el sistema para ahorrar; se enciende cuando un programa la
usa». Es un estado nuevo: ni guion, ni candado, ni «no existe» (regla 5). Con NVML hay que
**medir** si tener la sesión abierta impide RTD3 (§ volcados). Si la impide, solo se consulta
con `runtime_status=active` y se cierra al terminar, y hay que medir también si reabrirla en
cada intervalo basta para tenerla despierta (el retardo de autosuspensión de amdgpu son 5 s; el
de NVIDIA no se sabe).

---

#### A) Casos con dos gráficas

| Caso | Cómo se sabe cuál es la principal | Qué hace silux hoy | Qué debería hacer | Fuente |
|---|---|---|---|---|
| **Portátil Intel + NVIDIA propietaria (Optimus, PRIME offload, RTD3)** | `boot_vga=1` en la Intel (00:02.0). La NVIDIA suele ser de clase 0x0302 y **no tiene `boot_vga`**. El eDP cuelga de la Intel. switcheroo da `Default` a la Intel y `Discrete` a la NVIDIA. Sin variables dibuja la Intel | `primary` = `boot_vga==1` (`drm.py:182`): la chapa «principal» en la Intel (`graphics.py:700`). **Inicio enseña `gpus[0]`** (`home.py:284`, `:327`, `:388`, `:396-398`) y la imagen de compartir también (`ui/tarjeta.py:167`), así que si la Intel es `card0` el portátil «tiene» una UHD. **NVML abierta todo el rato** (`nvidia.py:44`) y consultada en cada muestreo (`nvidia.py:50`). **Enlace leído en cada muestreo** (`drm.py:413`, y otra vez en `pci.py:78`). No se mira `runtime_status` en ninguna parte (grep: 0 resultados) | Inicio y la imagen de compartir eligen la dedicada si la hay; si no, la de `boot_display`/`boot_vga`; si no, la primera. Ordenar las secciones de Gráficos igual, para que no dependa de `cardN`. Mirar `runtime_status` antes de leer, y enseñar «dormida» en vez de despertarla. Distinguir dos chapas, «arrancó con esta» y «dedicada» | sysfs-bus-pci (power_state); LKML 2606.2 (boot_vga solo VGA); README NVIDIA cap. 22 (RTD3); parche de Norris (6.18) |
| **Portátil Intel + NVIDIA con nouveau/NVK** | Igual que el anterior; la de nouveau duerme con runtime PM | Lo mismo con el enlace y el hwmon (`hwmon.py` lee todos los chips en cada muestreo). Si OpenGL sale por la NVIDIA (`DRI_PRIME=1`), con Mesa nouveau el renderer es «NVxxx» con fabricante «nouveau», y `_MARCAS` no lo reconoce (`gpu_apis.py:197`), así que **cae en la principal: se le atribuye a la Intel**. Con NVK, OpenGL va por zink y `_POR_SOFTWARE` lo descarta como software (`gpu_apis.py:203`): la fila desaparece | Añadir `nouveau`, `nvk` y `nv1`/`nv` + dígitos a las marcas de NVIDIA. Tratar `zink` como el driver de debajo, mirando lo que va entre paréntesis («zink Vulkan 1.3(NVIDIA …)») | Mesa envvars (`DRI_PRIME`) |
| **Portátil con mux en modo dedicada / Advanced Optimus** | El firmware arranca con la dedicada: `boot_vga=1` en ella. La iGPU puede no estar en el bus | `boot_vga` lo resuelve bien. Si la iGPU no está, hay una sola tarjeta | Nada especial; comprobar con un volcado que la dedicada sale como clase VGA | **dudoso**: sin volcado |
| **Portátil Intel + AMD dedicada (BOCO/D3cold)** | `boot_vga` en la Intel; la AMD duerme | Enlace en cada muestreo: con 6.18 o más la despierta. En kernels anteriores al cambio de amdgpu, hwmon, `gpu_busy_percent` y `pp_dpm_sclk` también. En los actuales esas lecturas dan `-EPERM` y `read_text` lo traga (`base.py:196`): la ficha sale **a guiones sin explicación**, aunque `mem_info_vram_used` sí se lee | Igual que con NVIDIA: comprobar `runtime_status` y enseñar el estado | `amdgpu_pm.c` (`_if_active` devuelve `-EPERM`) |
| **APU AMD + AMD dedicada (dos amdgpu)** | `boot_vga` donde arrancó el firmware. En algunas APU la iGPU es de clase **0x0380** y **no tiene `boot_vga`**, y vgaarb puede darle `boot_vga=1` a la dedicada aunque el framebuffer esté en la APU | `primary` puede caer en la dedicada sin serlo. F-M17: sin `pci.ids` (o con uno viejo sin el ID de la dedicada) **las dos** se llaman como la iGPU de la marca de la CPU (`drm.py:335-339`). Los dos hwmon se llaman `amdgpu` y chocan en el árbol de sensores (pendiente de `hwmon.py`). `_graficas_del_bus` no conoce la clase 0x0380 (`drm.py:626`) | Leer `boot_display` si existe. Decidir el nombre de la iGPU **después** del ioctl y solo si `_is_apu`. Separar los hwmon por ranura PCI | LKML 2606.2/11467 (0x0380) |
| **APU AMD + NVIDIA** | `boot_vga` en la APU (o en la NVIDIA por lo de 0x0380) | Lo de NVIDIA del primer caso. Además, en la APU el **consumo es el del paquete entero** (CPU incluida) y el «punto caliente» es la temperatura del SoC (ver B) | Ver B-3 y B-4 | docs.kernel.org/gpu/amdgpu/thermal.html |
| **Sobremesa con la integrada habilitada + dedicada** | Lo decide la BIOS («Primary display»: PEG o IGFX). Quien lleva el monitor se ve en los `cardN-*/status` | Si la BIOS dice IGFX y el monitor va a la dedicada, la chapa «principal» la lleva una tarjeta **sin ninguna pantalla conectada**. Inicio enseña `gpus[0]`, que es la que haya cogido `card0` al arrancar; con dos módulos (`i915` + `amdgpu`/`nvidia`) el orden depende de cuál cargue antes (**dudoso** que cambie entre arranques; se sabe que pasa por lo que se aconseja con `/dev/dri/by-path`) | Inicio: la dedicada. La chapa «principal» con su globo: «el firmware arrancó con esta». Añadir «lleva la pantalla» cuando tenga conectores conectados | sysfs-bus-pci |
| **Intel integrada + Intel Arc dedicada** | `boot_vga` donde arrancó; integrada en 00:02.0 | **El PMU de la dedicada se llama `i915_<ranura>` y silux pide siempre `i915`** (`drm.py:557-558`): la Arc enseña el uso de la integrada. Las dos llevan `no_temperature_sensor=True` y el aviso «Intel no da temperatura» (`drm.py:187-192`), y una Arc sí tiene hwmon | Ver B-6 y B-7 | Tvrtko Ursulin, «drm/i915/pmu: Support multiple GPUs» (2019): la integrada se queda con «i915», las demás llevan la ranura PCI |
| **`nomodeset` / framebuffer de respaldo con dos tarjetas** | El framebuffer lo deja el firmware en la de `boot_vga` | `_identidad_del_bus` le da al framebuffer **la primera del bus** (`drm.py:175`, `:217`): la integrada 00:02.0, aunque el firmware arrancara con la dedicada. La segunda tarjeta, si no tiene nodo DRM, no aparece | Dárselo a la de `boot_vga`/`boot_display`, y si no hay, a la primera. Las que estén en el bus sin nodo DRM, enumerarlas igual, con su nota | código |
| **NVIDIA < 570 (o `nvidia-drm.fbdev=0`) con `simpledrm` todavía en `card0`** | `card0` = simpledrm, `card1` = nvidia | `card0` toma la identidad de la **misma** NVIDIA, así que sale **dos veces**, una de ellas con la nota «El kernel no tiene driver para …», que es falsa (`drm.py:224-227`). NVML casa por ranura y solo rellena una (`nvidia.py:53`) | `_identidad_del_bus` no debe coger un dispositivo que ya tiene `drm/` propio o driver | Que simpledrm sobreviva junto a nvidia en esa configuración es **dudoso** (lo cuentan foros; falta un volcado) |
| **eGPU por Thunderbolt** | No es la de arranque; puede conectarse con el programa abierto | `DrmGpus` es estático (`drm.py:152`): una eGPU conectada después no sale hasta reiniciar el programa (regla 9). Si se desconecta y vuelve como otro `cardN`, `GpuState` lee del `drm_node` guardado y podría estar leyendo otra tarjeta (**supuesto**) | Volver a enumerar cuando cambie `/sys/class/drm`, y casar por ranura, no por `cardN` | código |

---

## 2. Los fallos del código actual, por gravedad

**Gravedad:**

- **Alta:** sale un dato falso en pantalla, o se cambia el comportamiento
  del equipo.
- **Media:** un dato que existe y no se lee, un 0 falso, o una frase que
  miente.
- **Baja:** texto, rendimiento o un caso raro.

La columna «Visto» dice qué está confirmado:

- **código**: leyendo silux.
- **fuente**: con el kernel o la documentación.
- **dudoso**: falta una pieza para confirmarlo.

El detalle de cada uno, con su archivo y línea, está en el apartado 2.2.

### 2.1 La lista

| # | Gravedad | Qué pasa | Dónde | Casos | Visto | Detalle |
|---|---|---|---|---|---|---|
| 1 | alta | Se despierta la dedicada dormida en cada muestreo (el enlace PCIe la saca de D3cold desde 6.18; NVML probablemente también) y se mide despierta | `drm.py:413`, `pci.py:78`, `nvidia.py:44-50` | portátiles con dos gráficas y runtime PM | código y fuente; NVML, dudoso | B-1, N1, AMD-15 |
| 2 | alta | En una APU AMD, «Consumo» es el del procesador entero | `drm.py:914-918`, `home.py:307`, `cli.py:198` | todas las APU desde Renoir; Ryzen 7000/9000 de escritorio | código y fuente | AMD-1, B-3 |
| 3 | alta | `gpu_metrics` 1.0 se lee con las posiciones de la 1.1: cifras creíbles sacadas de un contador de tiempo | `gpumetrics.py:105` | quien publique la 1.0 (Vega 20, dudoso) | código y fuente | B-2 |
| 4 | alta | El uso de video de una APU con `gpu_metrics` 2.1 viene en centésimas: 0,45 % sale «45 %» | `gpumetrics.py:192` | Rembrandt, Raphael, Phoenix con kernel < 6.10 | código y fuente | AMD-2 |
| 5 | alta | Cualquier Arc dice «PCIe 1.0 × 1»: su puente interno publica 2.5 GT/s × 1 y silux se queda con el eslabón más lento | `drm.py:654-712` | todas las Arc A y B | código y fuente (Intel 000094587) | I1 |
| 6 | alta | Una Arc con `i915` junto a una integrada enseña el uso de la integrada: el contador se pide siempre como `i915` | `drm.py:557`; el ayudante, `helper.py:98` | portátiles con Arc A | código y fuente; el nombre exacto del contador, dudoso | I2, B-6 |
| 7 | alta | Una Arc con `xe` dice que no publica su temperatura, con la de la VRAM al lado; con `i915` ≥ 6.13 la temperatura sale y la nota dice que no existe | `drm.py:187-192`, `904-912`, `430` | Arc A y B | código; las etiquetas del kernel, fuente con fechas dudosas | I3, I4, B-7 |
| 8 | alta | Con un framebuffer de respaldo, una tarjeta sale dos veces o con la identidad de otra, y la nota «sin driver» es falsa | `drm.py:175`, `217` | `simpledrm` junto a `nvidia`, o `nomodeset` con dos gráficas | código; la frecuencia del caso, dudosa | B-5 |
| 9 | alta | Con nouveau, la página promete «queda la temperatura», y desde Turing con GSP no hay ningún hwmon | `es.json` `prov.drm.nouveau.hint` | nouveau en Turing (GSP de serie desde 6.18), Ampere, Ada, Blackwell | fuente | apartado 1.3 |
| 10 | alta | En un híbrido con nouveau, OpenGL se le pone a la integrada; con NVK (zink) la fila desaparece | `gpu_apis.py:197`, `203` | Intel + NVIDIA con nouveau | código; las cadenas de Mesa, dudosas | B-8 |
| 11 | media | Inicio, su temperatura y la imagen de compartir usan `gpus[0]`; la principal solo sale de `boot_vga` | `home.py:284`, `388`; `tarjeta.py:167`; `drm.py:182` | portátiles con dos gráficas | código | B-9, apartado 1.4 |
| 12 | media | El «punto caliente» de una APU es la temperatura del SoC, y su globo dice otra cosa | `gpumetrics.py:91` | APU con `gpu_metrics` 2.1 (también la 740M «validada») | código y fuente | AMD-3, B-4 |
| 13 | media | La reserva de la BIOS de una APU se enseña como VRAM propia, con tipo, bus y ancho de banda de la RAM, y «Resizable BAR activo» | `model.py:872-878`, `graphics.py:192`, `824` | todas las APU | código y fuente | AMD-4, AMD-5 |
| 14 | media | Las tablas `gpu_metrics` 2.2, 2.3, 2.4 y 3.0 no se leen; la 2.2 es la 2.1 con un campo más | `gpumetrics.py:104-110` | Renoir, Cezanne, Steam Deck, Strix | fuente | AMD-7 |
| 15 | media | Los ROP salen de multiplicar un total por motores y *arrays*: aciertan en la 9070 XT y fallan en GCN pequeñas | `amdgpu.py:100-106` | Verde, Oland, Carrizo; RDNA2/3 dudoso | fuente; dudoso en RDNA | AMD-6, B-15 |
| 16 | media | Con `xe`, «Núcleo» es la frecuencia pedida y no la real; los motivos de freno, el reposo, los motores, el uso y las unidades no se leen, y el pie lo atribuye a «esta generación» | `drm.py:803-867`, `527-547`, `237` | Lunar Lake, Panther Lake, B580 | código y fuente | I5-I9, I12 |
| 17 | media | Las Arc solo publican energía (`energy1_input`): no hay consumo; en `xe`, `power1_cap` es PL2 y no el límite de la tarjeta; tampoco voltaje ni VRAM ocupada | `drm.py:914-927`, `715-730` | Arc A y B | fuente | I10, I11, I13 |
| 18 | media | Cuando NVML falla, no hay nota y se reintenta cada segundo (el caso típico: driver actualizado sin reiniciar) | `nvidia.py:46`, `nvml.py:117-133` | NVIDIA propietaria | código | N2 |
| 19 | media | Los motivos de recorte de NVIDIA, en español fijo; dos motivos de NVML 13.4 se ignoran y dice «no se frena» | `nvml.py:34-44`, `268` | NVIDIA propietaria | código y fuente | N3, N4 |
| 20 | media | Con `radeon`, el reloj y el voltaje están y no se leen (no llevan etiqueta), y no hay aviso del driver | `drm.py:766`, `925`, `55-61` | SI, CIK y TeraScale con `radeon` | fuente | AMD-8, AMD-9 |
| 21 | media | Con nouveau, el ventilador puede salir en un porcentaje falso, el voltaje se pierde y el límite de consumo no se encuentra | `drm.py:917-926` | nouveau antes de Turing | fuente; cuánto se desvía el ventilador, dudoso | apartado 1.3 |
| 22 | media | Los tres pendientes ya anotados: F-M17 (la dedicada AMD sin `pci.ids` toma el nombre de la integrada), F-M20 (`if v` con relojes, en cinco sitios) y F-M21 (`_pmu_ok`) | ver `docs/pendientes.md` | — | código | B-12, B-13, B-14 |
| 23 | media | Con NVIDIA propietaria, Sensores no tiene temperatura, consumo ni reloj de la gráfica | `derived.py` | NVIDIA propietaria | código | B-11 |
| 24 | media-baja | Con 5.15-6.7, el fabricante de los chips de VRAM sale «unknown» tal cual; lo que no existe en una familia sale con guion | `drm.py:720`, `graphics.py:176-216` | SI, CIK, Polaris, Fiji | fuente | AMD-10, AMD-11, I15 |
| 25 | baja | Varios: la VRAM usada de NVML incluye lo reservado (N7), NVML se relee entero cada segundo (N11), se lee el número de serie sin usarlo (N10), una tarjeta sin nodo DRM no aparece (B-10), el estático no ve una eGPU (B-18), las integradas de chipset de NVIDIA se toman por dedicadas | ver detalle | — | código | N7-N18, B-10, B-16-B-18, AMD-12-17, I14-I19 |

### 2.2 El detalle de cada informe

#### AMD
| # | Dónde | Qué pasa | Casos | Gravedad |
|---|---|---|---|---|
| AMD-1 | drm.py:914-916 (y home.py:307, cli.py:198) | En una APU, `power1_average/input` es el **socket entero, CPU incluida** (D-thermal lo dice así). Se pinta como consumo de la gráfica | todas las APU desde Renoir; en un Raphael o Granite Ridge de escritorio es el paquete de 8-16 núcleos | **alta** |
| AMD-2 | gpumetrics.py:92-93, 192 + drm.py:968-977 | Las APU dan la actividad en `gpu_metrics` **en centésimas**. `porcentaje()` toma ≤ 100 como porcentaje: el 0,45 % de uso de vídeo sale «45 %», y por encima del 1 % sale «—» | v2.1 (Rembrandt, Mendocino, Raphael, Phoenix) con kernel < 6.10, que no tiene `vcn_busy_percent` | **alta** |
| AMD-3 | gpumetrics.py:91 | `temperature_soc` se enseña como «Punto caliente». La validación de la 740M que recoge `docs/hardware-validado.md` validó la cifra, no lo que significa | todas las v2.1 | media |
| AMD-4 | model.py:872-878, graphics.py:824 | En una APU, `vis_vram_total == vram_total` por construcción, y la página dice «Resizable BAR activo» | todas las APU (gmc_v9 y posteriores) | media |
| AMD-5 | graphics.py:192, 697, 782-785, 813-826 | La reserva de la BIOS se trata como VRAM propia: insignia «512 MB», barra «VRAM ocupada» que se ve llena aunque la gráfica tire de GTT, y tipo, bus y ancho de banda (que son de la RAM del sistema) bajo «VRAM» | todas las APU | media |
| AMD-6 | amdgpu.py:100-106 (y test_amdgpu.py:62-64, que lo da por bueno) | `num_rb_pipes` ya es el total de RB; multiplicarlo por SE×SA solo acierta cuando eso coincide con los ROP de cada RB (4 en GCN, 8 en la 9070 XT). Verde sale 8 en vez de 16, Oland 2 en vez de 8, Carrizo 2 en vez de 8 | GCN pequeñas y APU; en RDNA2/3 **dudoso** | media |
| AMD-7 | gpumetrics.py:104-110 | Las versiones 2.2 (Renoir, Cezanne, Lucienne, Barcelo y Van Gogh: las APU más comunes), 2.3, 2.4 y 3.0 (Strix y posteriores) solo dejan la nota. La 2.2 es la 2.1 más `indep_throttle_status` en el byte 120 | Ryzen 4000/5000 móviles y G, Steam Deck, Ryzen AI 300 | media |
| AMD-8 | drm.py:766, 772, 925-927 | `_etiquetadas()` exige etiqueta: con `radeon`, `freq1_input` e `in0_input` no la llevan, así que reloj y voltaje salen «—» habiendo dato | toda tarjeta con `radeon` y DPM | media |
| AMD-9 | drm.py:55-61 | `radeon` no tiene aviso: ficha llena de rayas sin motivo, y sin la pista de `amdgpu.si_support/cik_support` | SI/CIK hasta 6.18/7.0, TeraScale siempre | media |
| AMD-10 | drm.py:720, graphics.py:826 | Con 5.15–6.7, `mem_info_vram_vendor` dice `unknown` y se pinta tal cual (además, es «en bruto») | SI, CIK, Tonga, Fiji, Polaris; APU (**dudoso**) | media-baja |
| AMD-11 | graphics.py:176-216 (`no_aplica`) | Lo que no existe en una familia sale con guion: punto caliente y memoria (GC < 9), VR, SoC, «Estado» y memoria efectiva (sin `gpu_metrics`), consumo (SI) | Polaris, Fiji, Tonga, CI, SI, Vega 10 | media-baja (regla 5) |
| AMD-12 | gpumetrics.py:94, 217; drm.py:974 | `average_socket_power` va en mW en Rembrandt, Raphael, Phoenix y v3.0, y en W en Renoir. silux lo toma siempre como W. Latente: solo se usa si hwmon no da consumo | v2.1 sin hwmon de consumo | baja (latente) |
| AMD-13 | drm.py:963 | En una APU v2.1, «Memoria (efectiva)» es `average_uclk_frequency` = `MemclkFrequency` de la RAM del sistema | Phoenix y otras v2.1 | baja, **dudoso** |
| AMD-14 | drm.py:342-372 | Sin el ioctl de amdgpu, una APU AMD queda como `integrated=None`: no se esconde el ventilador ni los VR | APU con `radeon` (Kaveri, Trinity, Llano), o si el ioctl falla | baja |
| AMD-15 | drm.py:398-416 | Una dedicada AMD dormida por runtime PM (portátil con APU + dGPU) devuelve `-EPERM` en todo lo de `amdgpu_pm.c` (`amdgpu_pm_get_access_if_active`), y la ficha sale a guiones sin nota. Se podría mirar `device/power/runtime_status` | portátiles híbridos AMD+AMD | media |
| AMD-16 | amdgpu.py:53-56 | Faltan los tipos 13 (HBM3E) y 14 (HBM4) | solo Instinct | baja |
| AMD-17 | drm.py:119-120 | `_IGPU_EN_LA_MARCA` solo encaja con «w/»; los de escritorio y los Cezanne dicen «with Radeon Graphics». No cambia nada porque pci.ids ya trae «Radeon», pero la regex no hace lo que dice su comentario | Ryzen 5000G | baja |

Lo que **está bien** y conviene no tocar: la detección de integrada por
FUSION; `NA_INTEGRADA` (ventilador y VR) en APU; la lectura de `power1_average`
y `power1_input` a la vez; los centigrados de la v2.1 (lo cubre el filtro
`> 200`); que las tablas sin versión conocida se callen en vez de inventar; el
`temp1_input` sin etiqueta de `radeon`; y que `gpu_metrics` ilegible (Raven)
acabe en `None` sin reventar (`raw_of` captura el `OSError`).

#### Intel
Gravedad: **alta** = dato falso en pantalla; **media** = dato que existe y no se
lee, o una frase que miente; **baja** = cosmético o caso raro.

##### Alta

- **I1. Enlace PCIe de cualquier Arc: «PCIe 1.0 × 1».** `silux/providers/drm.py:654-712`
  (`_cadena_pcie` + `_enlace`, mínimo de la cadena). El extremo de la Arc y su
  puerto de bajada interno publican 2.5 GT/s × 1 siempre; Intel lo reconoce para
  A-series y B570/B580. Sale en «Enlace», «Enlace máx.» y el subtítulo
  (`ui/pages/graphics.py:484`), con los dos drivers y también sin driver
  (`drm.py:222`). Es la lección «vale el eslabón más lento» aplicada a una
  tarjeta cuyo eslabón interno miente hacia abajo. Arreglo propuesto (sin
  escribir): descartar los enlaces internos de la tarjeta —los dos extremos del
  mismo fabricante que la GPU, es decir, su propio conmutador— y quedarse con el
  mínimo del resto. Vale igual para la RX 9070 XT (su lado interno va más rápido
  y también se descarta) y no esconde un cuello de botella del chipset de la
  placa, que sí es de otro fabricante.
- **I2. Arc A-series con i915 + integrada i915: el uso de una se pinta en la
  otra.** `drm.py:550-562` (`_pmu_de` → `"i915"` para cualquier i915) y
  `privileged/helper.py:98` (el patrón no acepta `i915_0000_BB_DD.F`). La
  dedicada recibe la ocupación de la integrada, motor a motor. Arreglo en dos
  partes; la del ayudante **toca privilegios** y va como propuesta.
- **I3. Arc con xe (B580 de serie, ≥ 6.15): «no publica su temperatura» con la
  de la VRAM al lado.** `drm.py:192` (marca `no_temperature_sensor` en xe),
  `drm.py:904-912` (busca `edge` o `temp1_input`; xe usa `temp2` `pkg`),
  `ui/pages/graphics.py:164,196,599` (esconde la ficha y pone el pie
  `gpu.na.notemp`). Además la nota `prov.drm.inteltemp` de `drm.py:430`.

##### Media-alta

- **I4. Arc con i915 ≥ 6.13: la temperatura sale y la nota dice que no existe.**
  `drm.py:430` llama a `_avisar_de_intel` para toda i915/xe sin mirar si hay
  `temp_c`; los tres textos de `INTEL_AVISOS` (`drm.py:81-85`, `es.json:884-888`)
  afirman que no hay temperatura.

##### Media

- **I5. xe: «Núcleo» es la frecuencia pedida, no la real.** `drm.py:863-867`
  traduce `cur` a `cur_freq`; la real es `act_freq`. Con i915 se prefiere
  `act` (`drm.py:855`). Una gráfica en C6 puede salir con la frecuencia
  que GuC pidió (**dudoso** qué devuelve `cur_freq` exactamente en C6).
- **I6. xe: motivos de freno sin leer, y el pie lo atribuye a la generación.**
  `drm.py:803-817` solo conoce `gt/gt0/throttle_reason_*`; xe los tiene en
  `device/tile0/gt0/freq0/throttle/` desde 6.8. En una Lunar Lake el pie dice
  «Esta generación de Intel no publica si se frena…; las más recientes sí»
  (`graphics.py:138-140,206`, `es.json:497`), que es lo contrario. Además, en
  i915 la condición real es Gen ≥ 11 (`intel_gt.c:237`): sirve para afinar el
  pie sin deducirlo de la ausencia del archivo.
- **I7. xe: sin reposo.** `drm.py:419-422,497-498`; xe publica
  `tile0/gt0/gtidle/idle_residency_ms` desde 6.8.
- **I8. xe: sin motores.** `drm.py:188,527-547` lee `cardN/engine/`, que es de
  i915; xe → tupla vacía → la tarjeta de motores y la fila de reposo se van
  (`graphics.py:647`). Las clases están en `tile0/gt0/engines/`, las instancias
  en `DRM_XE_DEVICE_QUERY_ENGINES`.
- **I9. xe: el uso no aparece nunca, y las notas prometen que sí.**
  `privileged/helper.py:99` (eventos solo con nombre de i915). El PMU de xe
  (6.15) exige `engine_class`/`engine_instance`/`gt` en `config` y da ticks
  activos y totales, no nanosegundos ocupados: otra cuenta. Las notas
  (`drm.py:511-521`; `es.json:884-887`) dicen «con permisos aparecen el uso de
  cada motor» o «el kernel tampoco publica contadores». **Toca privilegios.**
  Alternativa sin root para los procesos propios: `fdinfo` `drm-cycles-*` (6.11).
- **I10. Consumo de cualquier Arc: nada, y en xe el «límite» es PL2.**
  `drm.py:914-918`. i915 y xe solo dan `energy1_input` (0444, no se restringió
  como RAPL); hace falta restar entre muestreos, como ya se hace con RC6.
  `power1_cap` en xe es PL2 (6.17 en BMG), no el límite de la tarjeta: el que
  corresponde a «de X W» es `power1_max` (PL1) o `power1_rated_max`.
- **I11. Voltaje de Arc: nada.** `drm.py:925-927` solo busca etiquetas de AMD;
  i915 publica `in0_input` sin etiqueta y xe `in1_input` con etiqueta `pkg`
  (solo DG2). La fila «Voltaje» queda «—» en una dedicada.
- **I12. Unidades con xe: nada.** `drm.py:237` solo pregunta a i915. Falta la
  consulta de topología de xe (con `SIMD16_EU_PER_DSS` en Xe2, 6.12). En Xe2
  Intel llama XVE a lo que `render.compute_units` etiqueta como «EU»
  (`render.py:600-620`): con xe convendría contar Xe-cores.
- **I13. VRAM de Arc: total por Vulkan, sin ocupada ni visible ni ReBAR.**
  `drm.py:715-730` lee archivos de amdgpu; `gpu_apis.py:149-171` rellena el
  total. «VRAM ocupada» y la barra de «Ahora mismo» no salen;
  «Resizable BAR —» en la pieza donde más importa (Intel exige ReBAR para las
  Arc). Fuentes sin permisos: consulta de xe/i915 (`cpu_visible_size`,
  `probed_cpu_visible_size`) o la BAR 2 de `device/resource`.
- **I14. `tools/volcar_gpu.py` es ciego a xe.** Busca `tile0/gt0/freq0/*` y el
  árbol `tile0/` en el **nodo DRM** (`tools/volcar_gpu.py:30-31,101-107`); xe
  los cuelga del nodo PCI. Un volcado de una B580 hecho con él saldría sin
  frecuencias. Tampoco recorre la cadena de puentes (necesaria para I1), ni
  `/sys/bus/event_source/devices/*/events` (I2, I9), ni `cardN/engine/`.

##### Baja

- **I15.** En una Arc dedicada quedan a guion filas que en Intel no existen:
  ROP, motores de sombreado, reloj de SoC, perfil, reguladores, voltaje de SoC
  (`graphics.py:129-136,198`: `NA_INTEL_INTEGRADA` solo se aplica a
  integradas). Choca con la regla 5.
- **I16.** Textos con el driver equivocado: `gpu.na.intel.card` («i915 no
  cuenta…», `es.json:493`) sale con xe.
- **I17.** Árbol de sensores: las etiquetas de xe pasan en bruto
  (`pkg`, `vram`, `card`, `mctrl`, `pcie`, `vram_ch_0`;
  `providers/hwmon.py:221-233`), y la energía sale como julios acumulados.
  Que `tests/test_nada_en_bruto.py` lo cace sin un volcado de xe, **dudoso**.
- **I18.** Solo `fan1_input` (`drm.py:920`); BMG publica hasta tres.
- **I19. Detección de «integrada».** `drm.py:362-365` (ranura `:00:02.0`)
  acierta en Arc A/B (van detrás de un puente, en otro bus), Meteor Lake,
  Lunar Lake y Panther Lake (00:02.0). Falla en casos raros: una función
  virtual SR-IOV de la integrada (00:02.1…) sale como dedicada, y en una
  máquina virtual la ranura la pone el hipervisor. Lo que decide de verdad, sin
  permisos: xe `DRM_XE_QUERY_CONFIG_FLAG_HAS_VRAM` (`xe_drm.h:431`) o una
  región `VRAM` en la consulta de memoria; i915, una región
  `INTEL_MEMORY_LOCAL`. Lunar Lake **no** cambia nada: su memoria en el
  encapsulado es RAM del sistema y xe la trata como tal (no hay región VRAM),
  así que su sitio es GTT, como ya hace silux.

##### Lo que no se rompe

- No hay ningún sitio que dé **0 en vez de nada** por culpa de xe: todos los
  caminos que fallan devuelven None. El único cero posible es legítimo:
  `act_freq` a 0 con el GT en C6, que silux pinta como «en reposo».
- `_pmu_de` para xe (`xe_` + ranura con `_`) coincide con el nombre real del
  PMU de xe (`xe_0000_00_02.0`, `xe_pmu.c:28`).
- `_hwmon` busca en `device/hwmon/`, que es donde i915 y xe registran el suyo.

---

#### NVIDIA
| # | Dónde | Gravedad | Qué pasa |
|---|---|---|---|
| N1 | `providers/drm.py:413` y `drm.py:654-708` | **alta** (portátiles) | El enlace se lee en cada muestreo y, desde 6.18, despierta la dedicada (0.1). Igual con NVML (**dudoso**). Falta mirar `power/runtime_status` antes de preguntar |
| N2 | `providers/nvidia.py:46-47`, `nvml.py:117-133` | media | `open()` falla en silencio y se reintenta en cada vuelta. No se guarda el código de `nvmlInit_v2` (`DRIVER_NOT_LOADED`=9, `NO_PERMISSION`=4, `LIB_RM_VERSION_MISMATCH`=18), así que no hay `Note` con su motivo (regla 5) ni forma de saber que basta con reiniciar. **Dudoso** si un `nvmlInit` fallido lanza `nvidia-modprobe` cada vez |
| N3 | `nvml.py:34-44` | media | `MOTIVOS` son literales en español sin `_()`: con la interfaz en inglés salen en español (F-M8). Tienen que ser claves, como `MOTIVOS_INTEL` en `drm.py:791-800` |
| N4 | `nvml.py:268`, `nvml.py:282-285` | media-baja | `throttled = bool(motivos)` solo cuenta los bits conocidos. Con NVML 13.4, `BoardLimit` (0x200) y `Reliability` (0x400) están definidos y silux los ignora: con uno de ellos activo dice «no se frena». Debería ser `banderas & ~0x1 != 0`, más un «otro (0x…)» para lo desconocido. Además, 0x2 (app clocks, «no longer used») y 0x100 (display) cuentan como recorte; lo de 0x100 es discutible |
| N5 | `nvml.py:232` | baja (futuro) | `nvmlDeviceGetCurrentClocksThrottleReasons` es obsoleto desde NVML 13.0. Conviene pedir antes `nvmlDeviceGetCurrentClocksEventReasons` (12.2+) y caer al viejo |
| N6 | `nvml.py:253-254` | baja (futuro) | `nvmlDeviceGetTemperature` es obsoleto desde 13.0. `TemperatureV` (12.8+) primero, y de paso `GPU_MAX` para el punto caliente (13.4) |
| N7 | `nvml.py:223` | baja-media | `GetMemoryInfo` v1: `used` incluye lo reservado y no cuadra con `nvidia-smi` en r510+. Hay que usar `_v2` con la estructura `{uint version; ull total, reserved, free, used}` (40 bytes con el relleno tras `version`; `version = 40 \| 2<<24`) y caer a v1. Ojo: con `_v2` el «version» lo comprueba el driver; si no cuadra devuelve `NVML_ERROR_ARGUMENT_VERSION_MISMATCH` (25), que `_estructura` ya trata como `None` |
| N8 | `nvml.py:228` | media (es F-M20) | `v * 1_000_000 if v else None`: 0 MHz llega como `None`. El reloj de video en reposo puede ser 0 (**dudoso**). Con `_primero` de `drm.py` se resuelve |
| N9 | `nvml.py:263` + `nvidia.py:111-164` | baja | `video_hz` se lee y no se guarda en ningún sitio: llamada gastada en cada muestreo |
| N10 | `nvml.py:245` | baja (privacidad) | Se lee el número de serie y no se usa. Hay que quitarlo |
| N11 | `nvml.py:145-164`, `nvidia.py:50` | baja (rendimiento) | `NvidiaGpus` no es estático, y `devices()` relee en cada muestreo lo que no cambia: nombre, VBIOS, UUID, serial, PCI, núcleos, bus, relojes máximos y enlace máximo. Son unas 25 llamadas por tarjeta y segundo. Se puede partir en estático y dinámico, como `DrmGpus`/`GpuState` |
| N12 | `nvml.py:225-226` con `_Pci` (58-66) | baja | Los respaldos `nvmlDeviceGetPciInfo_v2`/v1 rellenarían una estructura con otra disposición (`busId[16]` al principio y `reserved` al final), y `busId` saldría de bytes que no son. Hoy es inalcanzable (`_v3` existe desde mucho antes de r470). Lo limpio es quitar los respaldos o leer `busIdLegacy` en ese caso |
| N13 | `nvml.py:279` | baja | `int(dominio, 16)` puede lanzar `ValueError` con una cadena rara. Lo recoge el colector como «prov.crashed» y se pierde toda la tarjeta. Basta un `try` |
| N14 | `nvml.py:201-208` | baja | `_cadena_global` no tiene el `try` que sí tienen `_entero`/`_cadena`/`_estructura` |
| N15 | `nvml.py:111-141` (en el proceso) | por medir | Regla 8: NVML se carga en el proceso de la interfaz y vive toda la sesión; si el driver revienta dentro de NVML, se lleva el programa. **Dudoso** cuánta RSS cuesta: medir con y sin NVML en un equipo con NVIDIA. Lo que se haga ahí, tras proponerlo |
| N16 | `nvidia.py:67-69` | baja | El aviso de «driver ciego» se quita buscando «NVIDIA» en el texto traducido. Hoy funciona en `es` y `en`, pero se rompe si una traducción no nombra la marca. Mejor por `path` y `need`, o con una marca en la nota |
| N17 | `nvidia.py:106` | baja | Núcleos CUDA según `codename[:2]` de `pci.ids`: sin `pci.ids`, o sin nodo DRM (`nvidia-drm` sin cargar, la ficha que se crea en `nvidia.py:59-63` no tiene `codename`), una tarjeta que contesta SM se queda sin núcleos. `nvmlDeviceGetArchitecture` lo evita |
| N18 | `ui/pages/graphics.py:111-112` | cosmética | El comentario dice que NVML no publica el ventilador. Sí publica el % (y RPM desde 12.8); lo que no publica son los VR |

**Lo que está bien y conviene no tocar:**
- Firmas: `restype` por defecto `int` = `nvmlReturn_t`. El asa es un `c_void_p` que se pasa por valor. Los enums se pasan como `c_uint`. Los punteros, con `byref`. Las longitudes de los búferes coinciden o sobran respecto a `NVML_*_BUFFER_SIZE` (nombre 96, VBIOS 32, UUID 96, versión 80; serial 30, que se pide con 32).
- Tamaños: `_Memoria` 24 bytes = `nvmlMemory_t`; `_Uso` 8 = `nvmlUtilization_t`; `_Pci` 68 = `nvmlPciInfo_t` v3.
- Biblioteca ausente → `open()` devuelve `False` sin excepción. Función ausente → `_sim` devuelve `None`, y el dato también. Cualquier código distinto de `SUCCESS` (incluido `NOT_SUPPORTED`=3) → `None`, nunca 0. Salvo N8, ningún dato no soportado acaba en 0.
- `nvmlInit_v2` con respaldo a `nvmlInit`; `nvmlShutdown` al cerrar.

---

#### Revisión del código y equipos con dos gráficas
Ordenados por gravedad. **Alta** = miente o tumba; **media** = dato perdido o un 0 falso;
**baja** = texto.

##### Alta

**B-1. Se despierta la dedicada dormida en cada muestreo, y luego se mide despierta.**
- Dónde: `providers/drm.py:413` (`_enlace` lee `current_link_speed/width` del dispositivo y de
  su cadena), `providers/pci.py:78` (lo mismo para todo lo de `EN_RANURA`, gráficas incluidas),
  `providers/nvidia.py:44` y `:50` (NVML abierta y consultada en cada muestreo),
  `providers/drm.py:409-416` y `providers/hwmon.py` (en kernels anteriores al cambio de amdgpu).
  **[código]**: no hay ninguna lectura de `runtime_status` ni de `power_state` en el
  repositorio.
- Escenario: un portátil híbrido con runtime PM (Optimus RTD3, AMD BOCO) y kernel ≥ 6.18 o una
  estable con el parche, o NVIDIA propietaria en cualquier kernel.
- Qué sale mal: la tarjeta deja de dormir mientras silux está abierto (vatios de batería, el
  ventilador). Lo que se enseña (temperatura, consumo, reloj) es el de una tarjeta que solo está
  encendida porque silux la ha despertado. En kernels anteriores a 6.18, la misma lectura en
  D3cold da `-EINVAL` o el enlace del puerto raíz, que se toma por el de la tarjeta.
- Confirmado: el código, y el parche de 6.18. **Dudoso**: el efecto exacto de NVML y el
  retardo de autosuspensión de NVIDIA. Ver volcados.
- `tools/volcar_gpu.py:34-41` tiene el mismo problema: lee el enlace y `gpu_busy_percent`
  **antes** que nada, así que el volcado de un híbrido grabaría la tarjeta despierta. Tiene que
  leer `power/runtime_status` y `power_state` lo primero.

**B-2. `gpu_metrics` v1.0 se lee con las posiciones de la v1.1.** **[código + fuente]**
- Dónde: `gpumetrics.py:105` (`(1, 0): _V1_0`). `_V1_0` pone `temperature_edge` en el byte 4,
  que es su sitio en la **v1_1**. En `gpu_metrics_v1_0` lo primero tras la cabecera es
  `uint64_t system_clock_counter`, y el kernel avisa de que la v1_0 «is not naturally aligned».
  Así que temperaturas, actividad, consumo y relojes salen de los bytes del contador de tiempo.
- Escenario: una tarjeta que publique la 1.0. Cuál es **dudoso**: la Vega 20 por powerplay,
  probablemente; no se ha confirmado.
- Qué sale mal: cifras creíbles y falsas, el caso que la lección de `gpu_metrics` dice que hay
  que evitar. `grados()` divide entre 100 todo lo que pase de 200, así que la basura acaba
  pareciendo una temperatura.
- Arreglo: quitar `(1, 0)` de `VERSIONES`, que pase por `sin_interpretar` y lo diga, hasta tener
  su tabla.

**B-3. En una APU AMD, «Consumo» es el del paquete entero, con la CPU dentro.** **[código + fuente]**
- Dónde: `providers/drm.py:914-918` (`power1_average`/`power1_input` → `power_w`; `power1_cap` →
  `power_cap_w`), y `:974` (`socket_power` de `gpu_metrics`, si hwmon no lo tiene).
- Fuente: docs.kernel.org/gpu/amdgpu/thermal.html: «power1_average: average power used by the
  SoC in microWatts. **On APUs this includes the CPU.**». En `gpu_metrics_v2_1`,
  `average_socket_power` lleva el comentario «dGPU + APU power on A + A platform».
- Qué sale mal: la ficha «Consumo» de una Radeon 780M y la barra «x W de y W» de «Ahora mismo»
  (`graphics.py:788-791`) le cuelgan a la gráfica lo que gasta todo el procesador. Es el mismo
  error que la lección del `uncore` evita en Intel. En Inicio sale igual (`home.py:307`).
- Arreglo: con `integrated=True` y amdgpu, no poner `power_w` ni `power_cap_w`. Si se quiere,
  sacar `average_gfx_power` de la v2.x, que es de la gráfica, cuando haya tabla verificada.

**B-4. En una APU con `gpu_metrics` v2.1, el «Punto caliente» es la temperatura del SoC.** **[código + fuente]**
- Dónde: `gpumetrics.py:91` (`"temp_hotspot": ("H", 6), # temperature_soc`) y
  `providers/drm.py:972`, que lo rellena porque el hwmon de una APU solo trae `edge`.
- Fuente: `kgd_pp_interface.h`: `uint16_t temperature_soc; // soc temperature on APUs`.
- Qué sale mal: la ficha de sensores dice «Punto caliente: X °C», y su globo (`gpu.tip.hotspot`)
  afirma «El punto más caliente del chip… Es el que gobierna el ventilador». En una APU no es
  ninguna de las dos cosas. También sale en el detalle de la ficha de temperatura
  (`graphics.py:761-764`).
- Arreglo: un campo `soc_temp_c`, o no mapearlo.

**B-5. Con un framebuffer de respaldo, la tarjeta sale dos veces o con la identidad de otra.** **[código]**
- Dónde: `providers/drm.py:175` (`_graficas_del_bus()`: todas las tarjetas del bus, tengan o no
  driver), `:185-186` y `:217` (`pop(0)`, la primera por orden de bus).
- Escenario 1: `simpledrm` en `card0` y `nvidia` en `card1` a la vez (NVIDIA < 570 o
  `fbdev=0`; **dudoso** que sea frecuente). `card0` coge la identidad de la propia NVIDIA: sale
  una tarjeta repetida, con la nota «El kernel no tiene driver para GeForce …», que es falsa.
- Escenario 2: `nomodeset` con integrada y dedicada, y el firmware arrancando con la dedicada.
  La ficha del framebuffer dice «UHD 630» y la imagen está en la NVIDIA.
- Arreglo: elegir la candidata de `boot_vga`/`boot_display`, y descartar las que ya tienen un
  nodo `drm/` propio.

**B-6. Una Arc dedicada con i915 enseña el uso de la integrada.** **[código + fuente]**
- Dónde: `providers/drm.py:557-558`: `_pmu_de` devuelve siempre `"i915"`. El comentario dice
  «i915 solo admite una tarjeta», y no es así: desde 2019 la integrada (0000:00:02.0) se registra
  como `i915` y las demás con la ranura PCI detrás.
- Escenario: una integrada de Intel con una Arc A-series en i915, que es lo de serie para DG2
  hasta que `xe` la toma.
- Qué sale mal: el uso, los motores y el vídeo de la Arc son los de la integrada.
- Arreglo: como en `xe`, con la ranura; el nombre exacto (`i915_0000_03_00.0`) hay que mirarlo
  en `/sys/bus/event_source/devices/` de un equipo con Arc. **Dudoso**.

**B-7. Una Intel dedicada (Arc, con i915 o xe) se marca «sin sensor de temperatura».** (el código **[código]**; los atributos del kernel, **dudoso**)
- Dónde: `providers/drm.py:187-192` (`no_temperature_sensor = True` para cualquier i915/xe), y el
  aviso `INTEL_AVISOS` («driver»/«hardware» → `prov.drm.inteltemp`) de `drm.py:511-521`.
- Escenario: Arc A/B con `xe`. El hwmon de xe publica la temperatura del paquete y la de la VRAM
  con etiqueta. Que sean `temp2_input`/«pkg» y `temp3_input`/«vram» desde 6.1x es **dudoso**.
  `_sensores` solo busca `edge` y, si no está, `temp1_input`: con «pkg» se queda en `None`.
- Qué sale mal: `no_aplica` esconde la ficha de temperatura y dice al pie que la tarjeta no la
  publica, que es falso. Tampoco se calcula el consumo de `energy1_input` (i915/xe en dedicada
  no tienen `power1_input`).
- Arreglo: marcar `no_temperature_sensor` solo en la integrada (`integrated is True`), y aceptar
  `pkg` en `_etiquetadas`. Lo hace mejor quien tenga una Arc delante.

**B-8. En un híbrido con nouveau, OpenGL se le atribuye a la integrada; con NVK, desaparece.** **[código]** (las cadenas de Mesa, **dudoso**)
- Dónde: `providers/gpu_apis.py:197` (las marcas de NVIDIA no incluyen `nouveau`, `nvk` ni
  `NVxxx`), `:203` (`zink` en `_POR_SOFTWARE`) y `:231-232` (sin pistas, a la principal).
- Escenario: silux arrancado con `DRI_PRIME=1`, o un equipo donde EGL contesta con la NVIDIA;
  renderer «NV167», fabricante «nouveau». Con NVK, «zink Vulkan 1.x(NVIDIA GeForce …)».
- Qué sale mal: la ficha de la UHD lleva el OpenGL de la NVIDIA (la lección de `_es_de`, otra
  vez). Con zink, la fila de OpenGL no sale en ninguna.

##### Media

**B-9. Inicio, la imagen de compartir y la temperatura de Inicio usan `gpus[0]`.** **[código]**
- `ui/pages/home.py:284`, `:327` (`gpus.0.usage`), `:388`, `:396-398`; `ui/tarjeta.py:167`.
- En un portátil para jugar, Inicio y la imagen de compartir dicen «Intel UHD Graphics», sin
  temperatura y con la nota «no publica su temperatura», teniendo una RTX al lado. Y como
  depende de `cardN`, puede salir una u otra según el arranque (**dudoso**).
- Arreglo: una única función en el modelo o en `render` («la tarjeta que se enseña sola»):
  dedicada > `boot_display`/`boot_vga` > la primera. Así lo usan Inicio, la imagen de compartir
  y el informe (regla 1: si ya hay quien decide, no se decide al lado).

**B-10. Una gráfica sin nodo DRM no aparece, y la clase 0x0380 no se busca.** **[código]**
- `providers/drm.py:164-176`: solo se enumeran los `cardN`. Una dedicada sin driver, en
  `vfio-pci` o con nouveau en la lista negra y sin nvidia no sale, ni con una nota, salvo que
  haya un framebuffer de respaldo. `CLASES_GRAFICAS` (`drm.py:626`) no tiene 0x0380, la clase
  de algunas iGPU de AMD según el hilo de LKML.
- Arreglo: después de los `cardN`, recorrer el bus y añadir lo que no se haya visto, con la nota
  del driver.

**B-11. Con NVIDIA propietaria, la temperatura, el consumo y el reloj no llegan al árbol de Sensores.** **[código]**
- `providers/derived.py:109-126` añade uso, VR, voltajes, ventilador, reloj del SoC, reloj
  efectivo y VRAM, pero no `temp_c`, `power_w`, `power_cap_w` ni `clocks.core_hz`. En amdgpu
  vienen por hwmon; NVML no tiene hwmon.
- Qué sale mal: Sensores (lo que hace HWMonitor) no enseña la temperatura de una GeForce, y
  tampoco va al CSV de `registro.py`.

**B-12. F-M17, confirmado y ampliado.** **[código]**
- `providers/drm.py:335-339`. La condición es solo «AMD y sin "radeon" en el nombre», y corre
  en `_identidad` (`:184`), **antes** del ioctl (`:196`), así que ni siquiera puede mirar
  `_is_apu`.
- Disparos además del que hay anotado: un `pci.ids` viejo que no trae el ID de una dedicada
  reciente (RX 9060 XT en una distribución estable), y cualquier AMD de cálculo (Instinct,
  FirePro) cuyo nombre no lleve «Radeon». En un portátil APU + AMD dedicada salen las dos con
  el mismo nombre.
- Arreglo: aplicarlo después de `_preguntar_al_driver` y solo con `_is_apu is True`.

**B-13. F-M20, confirmado en cinco sitios.** **[código]**
- `gpumetrics.py:175` (`mhz`: `if v`), `:191` (`voltios`), `:226` (`link_speed`);
  `nvml.py:228` (`mhz`); `providers/derived.py:31` (`_mhz`) y `:35` (`_megas`: 0 bytes de GTT
  ocupados → `None`).
- Efecto real: en amdgpu, hwmon `freq1_input` va primero (`drm.py:772`, `:965`), así que el
  `if v` de `gpu_metrics` solo se nota cuando hwmon no trae `sclk`. En NVML, un reloj de
  memoria a 0 en reposo profundo saldría «—» en vez de «En reposo» (`graphics.py:519`).
  `_megas` es el que más se ve: la fila «GTT» del árbol desaparece cuando está a cero.

**B-14. F-M21, confirmado.** **[código]**
- `providers/drm.py:459` pone `_pmu_ok = True` y nada lo vuelve a `False`: ni el
  `return None, None` de `:444` (cliente desconectado) ni el `HelperError` de `:454`. Si el
  ayudante muere, `_avisar_de_intel` (`:515-516`) elige «hardware» (gris, «no existe») en vez de
  «root» con su botón.

**B-15. ROP de AMD: la fórmula puede valer solo para la 9070 XT.** (**dudoso**, sin confirmar)
- `amdgpu.py:101-106`: `num_rb_pipes × num_shader_engines × num_shader_arrays_per_engine`.
  Si `num_rb_pipes` ya es el total de RB (en `amdgpu_kms.c` creo que es `max_backends_per_se ×
  max_shader_engines`), la cuenta de herramientas como amdgpu_top es `rb_pipes × 4`, u `× 8` con
  RB+ (RDNA2 en adelante).
- Las dos fórmulas dan lo mismo en la 9070 XT (16 × 4 × 2 = 128 = 16 × 8) y en Polaris o Vega
  (con un array por motor). Una Navi 33 (RX 7600: 2 SE × 2 SA, 64 ROP) saldría **32** con la de
  silux si su `num_rb_pipes` es 8. Hace falta el volcado del ioctl de una Navi 22/23/33.

**B-16. El `average_socket_power` de la v2.1 va probablemente en mW.** **dudoso**
- `gpumetrics.py:217` lo pasa tal cual como vatios. La v2_4 dice «(unit: mW)» y la v2_1 no dice
  nada. En Renoir el driver convierte `CurrentSocketPower` con `/1000`, de memoria.
- Solo se usa si hwmon no da consumo (`drm.py:974-977`). Si pasa, una APU marcaría «15000 W».
  Con B-3 arreglado, deja de importar para la gráfica.

**B-17. Con un `GpuState` que revienta, ninguna tarjeta tiene datos.** (supuesto)
- `collector.py:171-202` captura por proveedor: una excepción con la tarjeta 2 se lleva el uso
  y los relojes de todas en ese muestreo, y deja una nota suelta `gpus.load`. Lo que podría
  lanzarla: `float()` en `_niveles` (`drm.py:746`) con una cadena rara, o `int(dominio, 16)` en
  `nvml._ranura` (`nvml.py:279`). No es probable, pero el `try` iría mejor por tarjeta.

**B-18. El estático no ve tarjetas nuevas.** **[código]**
- `providers/drm.py:152` (`static = True`): una eGPU o un driver que se carga con el programa
  abierto no aparecen (regla 9). `GpuState` vuelve a buscar por el `drm_node` guardado
  (`:401-404`), no por la ranura.

##### Baja

- **B-19.** `providers/gpu_apis.py:247-253`: `_vulkan_de` casa por `vendor_id:device_id`. Con dos
  tarjetas iguales, las dos se quedan con el primer dispositivo de Vulkan, memoria incluida.
  `VK_EXT_pci_bus_info` da la ranura.
- **B-20.** `providers/gpu_apis.py:209`: Vulkan da `deviceType` (integrada o dedicada) y se
  guarda en `kind` sin usarse. Sería la tercera fuente de `_es_integrada` cuando queda `None`
  (radeon antiguo, render node sin permiso, virtio).
- **B-21.** `providers/drm.py:365`: Intel decide la integrada por la ranura 00:02.0 y devuelve
  `False`, no `None`, si no casa. En una máquina virtual con la integrada pasada en otra ranura,
  sale dedicada.
- **B-22.** `providers/drm.py:926`: `_primero(vddgfx, vddnb)`. Si falta `vddgfx`, el voltaje del
  SoC sale como «Voltaje del núcleo». nouveau etiqueta `in0` como «GPU core» y no se recoge.
- **B-23.** `nvml.py:34-44` y `:268`: «relojes fijados por la aplicación» (0x2), «por la
  pantalla» (0x100) y la sincronización (0x10) cuentan como recorte, así que «Se está frenando»
  puede salir sin que haya freno.
- **B-24.** Texto en español fijo con la interfaz en inglés (F-M8, confirmado aquí):
  `nvml.py:34-44` (`MOTIVOS`), `gpumetrics.py:31-53` (`MOTIVOS`), `gpu_apis.py:83`
  («instancia …»), `render.py:472` («parado»), `model.py:1109` («Gráfica N»).
- **B-25.** `nvml.py:225-226`: si solo existe `nvmlDeviceGetPciInfo` (v1), su estructura tiene
  `busId[16]` al principio y `_Pci` lee `busId` en otro sitio. Solo pasaría con drivers de
  antes de 2017.
- **B-26.** `providers/drm.py:182`: `primary` solo sale de `boot_vga`. En ARM o en plataforma no
  existe y ninguna tarjeta es «principal». Una dedicada de clase 0x0302 nunca lo es, y está bien,
  pero el globo de la chapa no explica qué significa.

##### Descartado al revisar

- Rutas fijas `card0`, `renderD128` o `hwmon0`: **no las hay**. Se guarda el nombre del nodo
  (`drm.py:179`), el render node sale de `device/drm/renderD*` (`amdgpu.py:124-133`) y el hwmon
  se busca con un glob (`drm.py:872-876`). El `renderD128` del docstring de `amdgpu.py:8` es
  solo un ejemplo.
- `_es_integrada` sin NVIDIA ni AMD devuelve `None`, no `False`, y la página no esconde nada
  con `None` (`graphics.py:192-198`).
- `-EPERM`/`-EBUSY` de amdgpu en suspensión: `read_text` captura `OSError` (`base.py:196`) y
  `gpumetrics.raw_of` también (`gpumetrics.py:245`). No tumba el muestreo.
- Leer `status`, `edid` y `modes` de los conectores no despierta la tarjeta (es lo guardado), y
  además solo lo hace `DrmGpus`, que es estático.

---

## 3. Plan por fases

De lo más útil a lo menos. Cada fase va en su rama, un commit por fallo con
su test, y el test necesita un volcado real (sección 4). Lo que solo se
puede arreglar quitando un dato falso se puede hacer antes de tener el
volcado: el test se escribe con el árbol que da el kernel según su código y
su documentación, y se valida en cuanto llegue el volcado. Lo que añade un
dato nuevo espera al volcado.

**Fase 0. Que las herramientas puedan grabar lo que falta.** Sin esto no
llega ningún volcado útil.

- `tools/volcar_equipo.py` y `volcar_gpu.py` leen `power/runtime_status`
  y `power_state` antes que nada, y no despiertan una tarjeta dormida
  (B-1).
- Graban NVML por `sysroot.a_traves`, como los ioctl de amdgpu e i915:
  hoy NVML queda fuera.
- Buscan los archivos de `xe` en el nodo PCI, no en el DRM (I14).
- Recorren la cadena de puentes (I1) y graban
  `/sys/bus/event_source/devices/*` (I2, I9).
- Un `silux --volcar NOMBRE` desde el AppImage, para que pueda mandar un
  volcado quien no clona el repositorio. Esto es código de la aplicación:
  se propone aparte.

**Fase 1. Dejar de mentir** (fallos 1 a 12). Casi todo es quitar o
reetiquetar, no leer algo nuevo:

1. **No despertar la dedicada** (1):
   - Si `runtime_status` es `suspended`, la tarjeta se enseña «en reposo
     (D3)» y no se pregunta nada más, ni a sysfs ni a NVML.
   - Es el único arreglo que cambia el comportamiento del equipo, y el
     primero.
2. **APU de AMD** (2, 4, 12, 13):
   - Sin consumo de la gráfica (o `average_gfx_power` cuando haya tabla
     verificada).
   - El uso de video en centésimas.
   - La temperatura del SoC con su nombre.
   - La reserva de la BIOS como «reservada» y no como VRAM, sin ReBAR.
3. **`gpu_metrics` 1.0** (3): a `sin_interpretar`, que lo dice, hasta tener
   su tabla.
4. **Arc** (5, 6, 7):
   - Descartar los enlaces internos de la tarjeta, que son los dos extremos
     del mismo fabricante que la gráfica.
   - Contador por ranura en `i915`. El ayudante **toca privilegios**: va
     como propuesta con lo medido, y hasta entonces la Arc con `i915` no
     enseña uso, en vez de enseñar el de otra.
   - Temperatura `pkg` en `xe`, y la nota solo cuando de verdad no hay.
5. **El framebuffer de respaldo** (8): elegir por `boot_vga` o
   `boot_display` y descartar las tarjetas que ya tienen nodo DRM propio.
6. **nouveau** (9, 10):
   - La pista dice lo que hay según la generación y si usa GSP.
   - OpenGL se atribuye por el `nouveau` o el `NVxxx` del renderer.
7. **La principal** (11): `switcheroo-control` por D-Bus si está, si no
   `boot_vga`. Inicio y la imagen de compartir enseñan la principal, y la
   dedicada si es la que trabaja.

**Fase 2. Intel `xe` y Arc** (16, 17):

- La frecuencia real, los motivos de freno, RC6, los motores y las
  unidades con `xe`.
- El consumo de las Arc a partir de `energy1_input`, restando entre
  muestreos como ya se hace con RC6.
- El límite (`power1_max`), el voltaje, y la VRAM ocupada, visible y ReBAR
  por la consulta de `xe` o `i915`.
- El uso con `xe` pide el contador de `xe` en el ayudante: **toca
  privilegios**, propuesta aparte.

**Fase 3. APU y AMD antiguas** (14, 15, 20, 24):

- `gpu_metrics` 2.2 (reutilizando la 2.1), 2.3, 2.4 y 3.0.
- Los ROP desde el número de RB por el de ROP de cada RB, por familia.
- `radeon`: reloj y voltaje sin etiqueta, su aviso, y lo que da su ioctl
  sin permisos.
- Lo que no existe en Polaris, Fiji, Tonga, CI y SI, escondido y nombrado
  al pie (regla 5).

**Fase 4. NVIDIA** (18, 19, 21, 23):

- NVML:
  - Nota con el motivo cuando falla, sin reintentar cada segundo.
  - Los motivos como claves de idioma, y los dos de NVML 13.4.
  - `GetMemoryInfo_v2`.
  - Lo estático, leído una vez.
  - Las funciones nuevas con respaldo a las viejas.
  - Sin leer el número de serie.
- Lo que vale la pena añadir: ventilador en RPM, codificador y
  decodificador, P-state, arquitectura (los núcleos CUDA sin depender de
  `pci.ids`) y energía total.
- nouveau antes de Turing: el ventilador, el voltaje `GPU core` y el límite
  `power1_cap_max`.
- Sensores con la temperatura, el consumo y el reloj de NVIDIA.
- Antes de cualquiera de estas, medir cuánta memoria cuesta NVML dentro del
  proceso (regla 8, N15).

**Fase 5. Lo demás** (22, 25): F-M17, F-M20 y F-M21; una tarjeta sin nodo
DRM; las eGPU; las integradas de chipset de NVIDIA.

## 4. Los volcados que harían falta

### 4.1 Por orden de lo que desbloquean

Se juntan las listas de los cuatro informes (detalle en el apartado 4.3).
Los primeros desbloquean la fase 1 entera:

| # | Equipo | Driver y kernel | Para qué |
|---|---|---|---|
| 1 | **Portátil Intel + NVIDIA Ampere o posterior** (RTD3 de serie) | propietario; un kernel ≥ 6.18 y otro anterior | Fallo 1: `runtime_status` con silux cerrado y abierto. Es el más importante |
| 2 | **Ryzen 7000/9000 de escritorio con la gráfica integrada activa** | `amdgpu`, ≥ 6.6 | Fallo 2 en su peor caso: «consumo de la gráfica» siguiendo a la CPU en reposo y con carga |
| 3 | **Portátil Phoenix o Hawk Point (780M)** | `amdgpu`, uno < 6.10 (Ubuntu 22.04 HWE) y otro ≥ 6.10, reproduciendo un video | Fallos 4 y 12 |
| 4 | **Arc B580** | `xe`, ≥ 6.17, con y sin Resizable BAR | Fallos 5, 7, 16 y 17 |
| 5 | **Portátil con Arc A (A370M/A550M) e integrada** | `i915`, ≥ 6.13 | Fallo 6: el nombre del contador de la dedicada |
| 6 | **Lunar Lake** | `xe` | Fallo 16 en una integrada; memoria en el encapsulado |
| 7 | **GeForce de sobremesa Turing, Ampere o Ada** | propietario r570+ y, si puede ser, r580 (NVML 13); también con el módulo abierto | Fallos 18 y 19, y lo que vale la pena añadir |
| 8 | **Turing con nouveau, con GSP y sin él** (`nouveau.config=NvGspRm=0`) | ≥ 6.18 | Fallo 9 |
| 9 | **Renoir o Cezanne** (Ryzen 4000/5000 U o G, o una Steam Deck) | `amdgpu` | Fallo 14 |
| 10 | **Polaris** (RX 570/580) | `amdgpu`, 5.15 (Ubuntu 22.04) | Fallos 15 y 24 |
| 11 | **GCN 1.0 (HD 7770, R7 250)** con `radeon` y con `amdgpu.si_support=1` | ≤ 6.18 y ≥ 7.0 | Fallos 15 y 20 |
| 12 | **Sobremesa con integrada y dedicada activas** (IGFX en la BIOS), y el mismo con `nomodeset` | cualquiera | Fallos 8 y 11 |

Del resto (Kepler con r470, Pascal y Maxwell con nouveau, Vega 56/64,
Rembrandt, Strix Point, una APU con dedicada AMD, Kaveri y TeraScale), el
detalle está en el apartado 4.3.

### 4.2 Cómo pedírselos a la comunidad

**Qué se pide.** Un volcado de `tools/volcar_equipo.py` es lo único que
sirve de fixture: copia lo que leen los proveedores, anonimizado, y se
monta en los tests tal cual. Las capturas y las salidas de `nvidia-smi` o
`amdgpu_top` sirven de contraste, no de fixture. Ningún equipo entra en la
suite sin un volcado real detrás.

**Cómo se pide:**

1. **Una plantilla de issue «Mi gráfica en silux»** con tres partes:
   - El equipo: gráfica, driver y versión (`modinfo -F version amdgpu`,
     `cat /proc/driver/nvidia/version`), kernel, distribución y, si es un
     portátil, si tiene dos gráficas.
   - El volcado, como `.tar.gz` adjunto:
     `python3 tools/volcar_equipo.py mi-equipo` y después
     `python3 tools/comprobar_privacidad.py`. Más adelante, cuando exista
     (fase 0), `silux --volcar mi-equipo` desde el AppImage.
   - Lo de contraste que pida cada caso: `nvidia-smi -q`, `sudo cat
     /sys/kernel/debug/dri/N/amdgpu_pm_info`, una captura de Gráficos con
     `--anonimo`. Se pide en reposo y con carga.
2. **Una lista de lo que se busca**, en `docs/hardware-validado.md` y
   enlazada desde el README («Lo que más se agradece recibir»): la tabla
   4.1, con una casilla por equipo que se marca al recibirlo.
3. **Los sitios donde preguntar**, con el enlace a la plantilla:
   - Los foros y subreddits de las distribuciones donde más hay de cada
     pieza: CachyOS y Arch para las Arc y las NVIDIA recientes, Fedora para
     los Lunar Lake, Ubuntu 22.04 para los kernels viejos.
   - Las Steam Deck en su comunidad.
   - Nada de spam: una vez por sitio, diciendo qué se busca y por qué.
4. **La privacidad, dicha antes:**
   - Qué quita el volcado: el nombre, las direcciones, los números de serie
     y lo enchufado por USB.
   - Que el autor lo revisa con `tools/comprobar_privacidad.py` antes de
     subirlo al repositorio.
   - Que quien lo manda puede pedir que no se suba y solo se use para
     mirarlo.

**Antes de pedir nada**, la fase 0 tiene que estar hecha. Si no, el primer
portátil híbrido que llegue vendrá grabado con la dedicada despierta, y una
B580 sin sus frecuencias.

### 4.3 El detalle de cada informe

#### AMD
Con `tools/volcar_equipo.py`, más `gpu_metrics` en binario y, como
referencia, `sudo cat /sys/kernel/debug/dri/N/amdgpu_pm_info` (o la salida de
`amdgpu_top --dump`). Por orden de lo que desbloquean:

1. **Raphael o Granite Ridge con la iGPU activa** (Ryzen 7000/9000 de
   escritorio, amdgpu, kernel ≥ 6.6): el punto 1 en su peor caso. Una medida
   en reposo y otra con la CPU cargada, para ver que «consumo de la gráfica»
   sigue a la CPU.
2. **Phoenix o Hawk Point** (780M), dos veces: con un kernel < 6.10 (Ubuntu
   22.04 HWE 6.8) y con uno ≥ 6.10, reproduciendo un vídeo, para el punto 2.
   Sirve además para el «punto caliente» (punto 3).
3. **Renoir o Cezanne** (Ryzen 5x00U/G): la v2.2 (punto 7), consumo en W y no
   en mW, LPDDR4X o DDR4.
4. **Rembrandt** (Ryzen 6000, LPDDR5): la v2.1 en mW y qué MCLK da la SMU con
   LPDDR5 (ancho de banda, dudoso).
5. **Strix Point o Krackan** (Ryzen AI 300): la v3.0.
6. **Raven o Picasso** (Ryzen 3x00G/U): `gpu_metrics` que falla al leer, sin
   consumo y sin vddgfx.
7. **Polaris** (RX 570/580) con amdgpu y kernel 5.15 (Ubuntu 22.04 GA):
   `unknown` en el fabricante, ROP (Polaris 10 debería acertar), ausencia de
   `temp2`/`temp3` y de `gpu_metrics`. Si es posible, también una Polaris 11/12
   (RX 560/550) para el ROP.
8. **SI** (HD 7770/R7 250, Verde u Oland), dos veces: con `radeon` (kernel ≤
   6.18, puntos 8 y 9) y con `amdgpu.si_support=1 radeon.si_support=0` o un
   kernel ≥ 7.0 (pp_dpm que falla, ROP mal).
9. **CIK** (R9 290/390 Hawaii o R7 260X Bonaire) con `radeon` y con amdgpu.
10. **Vega 56/64** (HBM, sin `gpu_metrics`, sin `mem_busy_percent`).
11. **Portátil APU + dedicada AMD** con la dedicada dormida (punto 15).
12. Opcionales: Kaveri (A10-7850K) con `radeon` y con amdgpu, una TeraScale
    (HD 5000/6000) con `radeon` y una Radeon VII (v1.0).

No se ha inventado ningún dato de equipo: todo lo de arriba sale del fuente
del kernel o de su documentación, y lo que no, va marcado **dudoso**.

#### Intel
Ninguno existe hoy (`tests/fixtures/equipos/`: `i5-10400`, `i5-10400-turbo`,
`5800x3d`). Por orden de lo que desbloquean:

1. **Arc B580 o B570 con xe**, kernel ≥ 6.17 (mejor ≥ 6.19, por `used` y
   `throttle/reasons`), en una placa con PCIe 4.0. Valida I1, I3, I10, I13, I5-I9
   y el `cpu_visible_size` con y sin ReBAR en la BIOS (dos volcados).
2. **Arc A750/A770 con i915**, kernel ≥ 6.13, **con la integrada de Intel
   activa** (o un portátil con Arc A370M/A570M). Valida I2 (el más grave en
   silencio), I4, I11 y la cadena de puentes de DG2.
3. **Lunar Lake con xe** (portátil, kernel ≥ 6.12). Valida §2 entera: frecuencias
   `act` frente a `cur`, `throttle/`, `gtidle/`, topología Xe2 y si
   `energy-gpu` da algo.
4. **Meteor Lake o Arrow Lake con i915** (lo de serie). Valida el GT de medios y
   que `EU_TOTAL` y el PMU sigan igual que en CML.
5. Opcional: la misma Arc A-series con `xe.force_probe` (DG2 en xe: `in1`,
   `temp3`, dos ventiladores).

Para que sirvan, antes hay que arreglar `tools/volcar_gpu.py` (I14) o pedir a
mano, en cada equipo: `ls -R /sys/bus/pci/devices/<BDF>/tile0`,
los valores de `tile0/gt*/freq0/*`, `freq0/throttle/*`, `gtidle/*`, el hwmon
entero con sus `*_label`, `lspci -tv` y `lspci -vv -s` de cada puente hasta la
raíz (`LnkCap`/`LnkSta`), `cat /sys/bus/pci/devices/<BDF>/resource` y
`resource2_resize`, y `ls /sys/bus/event_source/devices/*/events`. Las
respuestas de los ioctl (consulta de memoria y topología) no salen de sysfs:
habría que grabarlas por el mismo camino que `sysroot.a_traves` usa con amdgpu.

#### NVIDIA
No se cita ningún equipo concreto salvo los dos que ya constan en `docs/hardware-validado.md` (GTX 1660 Ti TU116 y RTX 3050 Mobile GA107M, capturas del 26-08-2026). Sus dueños son los candidatos naturales para repetir con nouveau.

`tools/volcar_equipo.py` no graba NVML (lo dice en «sin_grabar», `tools/volcar_equipo.py:676`) y `NvidiaGpus.available()` se apaga con un volcado montado (`nvidia.py:42-43`). Antes de nada haría falta grabar la respuesta de NVML (el `NvidiaGpu` serializado y los códigos de error por función), por el mismo camino que `sysroot.a_traves` usa para los ioctl de amdgpu e i915.

| # | Equipo | Driver / kernel | Qué se quiere ver |
|---|---|---|---|
| V1 | Sobremesa GeForce Turing, Ampere o Ada | propietario **r570+** y, si puede ser, **r580 (NVML 13)**; cualquier kernel | `nvidia-smi -q` en reposo y con carga; `-d CLOCK` (si el reloj de memoria es la mitad de la tasa de datos); `-d MEMORY` (v1 frente a v2: lo reservado); `-d PERFORMANCE` (motivos de recorte) con el límite de potencia tocado; varios ventiladores y RPM; `/proc/driver/nvidia/version` y `gpus/*/information` |
| V2 | Lo mismo con el **módulo abierto** | nvidia-open r560+ | Que NVML dé lo mismo; el texto de `/proc/driver/nvidia/version` para distinguirlos |
| V3 | **Portátil Optimus** Ampere+ (RTD3 por defecto) | propietario; **kernel ≥ 6.18** y uno anterior | `cat /sys/bus/pci/devices/<bdf>/power/runtime_status` con silux cerrado y abierto; `gpus/*/power`; si `nvidia-smi` o una llamada NVML suelta la despierta. Es lo que confirma o descarta N1 |
| V4 | Kepler (GTX 6xx/7xx) | **r470** en 5.15 o 6.1 | Que las funciones de NVML 11.6+ (núcleos, bus) den `None` sin romper nada; `_v3` presente |
| V5 | Pascal con nouveau (la GTX 1050 Mobile de la lección sirve) | nouveau, 5.15 y reciente | `ls hwmon/`: se espera solo `temp1_*` y quizá `fan1_input`, sin `pwm` ni `in0` ni `power1`. Confirmar que la página no promete relojes |
| V6 | Kepler o Maxwell 1 con nouveau | nouveau | `pwm1`, `pwm1_max`, `in0_label`; `power1_*` solo si la placa tiene INA; `sudo cat /sys/kernel/debug/dri/*/pstate` |
| V7 | Turing con nouveau, **con y sin GSP** (la GTX 1660 Ti) | 6.18+ por defecto, y `nouveau.config=NvGspRm=0` | Que con GSP no hay hwmon y sin GSP vuelve `temp1`; getparam `FB_SIZE` y `VRAM_USED` |
| V8 | Ampere, Ada o Blackwell con nouveau + NVK | ≥ 6.8 (GB20x ≥ 6.16) | Sin hwmon; memoria por Vulkan y por getparam |
| V9 (opcional) | ION / 9400M / 320M (MCP79/MCP89) | nouveau | Que se marque como integrada (hoy sale dedicada) |

#### Revisión del código y equipos con dos gráficas
En todos, lo primero que se lee es `device/power/runtime_status`, `device/power_state` y
`device/power/control` de cada tarjeta, **antes** de tocar nada más; para eso hay que corregir
`tools/volcar_gpu.py` (B-1). Además: `boot_vga`, `boot_display`, `class`, la salida de
`busctl get-property net.hadess.SwitcherooControl /net/hadess/SwitcherooControl
net.hadess.SwitcherooControl GPUs`, `ls /sys/bus/event_source/devices/` y el kernel.

1. **Portátil Intel + NVIDIA propietaria con RTD3** (Turing o posterior, driver ≥ 525):
   `runtime_status` y `/proc/driver/nvidia/gpus/*/power` con silux cerrado, abierto, y abierto
   tras 30 s en Gráficos y en Inicio. Sirve para medir B-1 y la duda de NVML. Además
   `nvidia-smi -q` comparado con lo que enseña silux, y la versión del driver para lo de
   `simpledrm` (B-5).
2. **El mismo portátil con nouveau, y con NVK si la distribución lo trae por omisión**: el
   renderer de `glxinfo -B` y `eglinfo` con y sin `DRI_PRIME=1`, que es lo que necesita B-8.
3. **APU AMD sola** (Rembrandt o Phoenix): `gpu_metrics` en bruto y su versión, los
   `hwmon/*_label` y `power1_*`, con la CPU en carga y la gráfica en reposo. Confirma B-3, B-4 y
   B-16, y las unidades de la v2.x.
4. **APU AMD + AMD dedicada**, mejor una Navi 33 (RX 7600M/7600S): el ioctl `DEV_INFO`
   (`num_rb_pipes`, SE, SA) para B-15; F-M17 con y sin `pci.ids`; los dos hwmon `amdgpu` para la
   colisión de claves; `boot_vga`/`boot_display` para lo de 0x0380.
5. **Una AMD que publique `gpu_metrics` 1.0** (Radeon VII / MI50 con powerplay): sus primeros
   128 bytes para B-2. Si no hay ninguna, basta con quitar la 1.0 de la tabla.
6. **Intel integrada + Arc dedicada**, con i915 y con xe: los nombres de los PMU, el hwmon de la
   Arc (etiquetas `temp*`, `energy1_input`, `power1_*`) y el `engine/` de cada una. Es lo que
   necesitan B-6 y B-7.
7. **Sobremesa con la integrada habilitada y el monitor en la dedicada**, con la BIOS en IGFX y
   en PEG: `boot_vga`, los conectores conectados y el orden de `card0`/`card1` en dos o tres
   arranques, para B-9 y la columna de la tabla.
8. **Un equipo arrancado con `nomodeset` y dos tarjetas**: el driver de `card0`,
   `_graficas_del_bus` y el `boot_vga`, para B-5.

---

## Anexo: lo dudoso y las fuentes

### Intel
#### 7. Dudoso, en una lista

- Que ANV declare como montones `DEVICE_LOCAL` exactamente la VRAM de una Arc
  (con y sin ReBAR).
- Qué devuelve `cur_freq` de xe con el GT en C6.
- Que `I915_PARAM_EU_TOTAL` conteste bien en DG2 y en Meteor/Arrow Lake.
- Que el firmware rellene `energy-gpu` (RAPL PP1) en Meteor/Arrow/Lunar Lake;
  el kernel lo declara (`rapl.c`, `model_skl`). Panther Lake no aparece en esa
  tabla.
- Qué atributos rellena el blob de hwconfig de GuC en cada Arc (tipo de memoria,
  canales) y desde qué versión existe `DRM_I915_QUERY_HWCONFIG_BLOB`.
- Desde qué versión existen `auto_link_downgrade_*` y
  `DRM_XE_DEVICE_QUERY_UC_FW_VERSION`.
- Si `temp3_input` (VRAM) da algo con DG2 forzada a xe.
- Los IDs de los puentes internos de Battlemage (los de DG2 son 8086:4fa0/4fa1
  de subida y 8086:4fa4 de bajada, según foros; no comprobados).

#### Fuentes

- Intel, «Intel® Arc™ Graphics Cards show incorrect PCIe link speed/width»:
  https://www.intel.com/content/www/us/en/support/articles/000094587/graphics.html
- Foro openSUSE, A380 con `LnkCap 2.5GT/s x1`:
  https://forums.opensuse.org/t/pcie-3-0-lspci-vv-shows-weird-speed-for-intel-arc-gpu/173054
- Intel Community, A770 a «PCIe Gen1 x1»:
  https://community.intel.com/t5/Graphics/Intel-Arc-A770-PCIe-Speed-2-5GT-s-Width-x1/m-p/1460788
- Código y ABI del kernel en `master` y en las etiquetas citadas (K… y C… arriba).
- Mesa, `src/intel/dev/intel_hwconfig_types.h`:
  https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/src/intel/dev/intel_hwconfig_types.h

### NVIDIA
#### Lo que queda marcado como dudoso

- Si NVML (o leer `/proc/driver/nvidia/gpus/*/information`) despierta una GPU en D3cold.
- Si `power_state` se lee sin despertar.
- Qué driver trae `NVML_TEMPERATURE_GPU_MAX` y si funciona en GeForce.
- `NVML_FI_DEV_MEMORY_TEMP` en GDDR.
- El reloj de memoria de NVML como mitad de la tasa de datos.
- Cuánto de la «used» de la v1 es memoria reservada.
- La errata de `FanSpeed_v2` en la doc.
- Que `nvidia-drm` cree `cardN` también con `modeset=0`.
- Que nouveau no tenga fdinfo de motores.
- Que `open-gpu-kernel-modules` no registre hwmon.
- Las ramas exactas de NVIDIA (r560 abierto por defecto; r580 última para Maxwell, Pascal y Volta).
- Si un `nvmlInit` fallido lanza `nvidia-modprobe`.
- El coste en memoria de NVML en el proceso.

### Revisión del código y equipos con dos gráficas
#### Fuentes

- Runtime PM: https://docs.kernel.org/power/runtime_pm.html y `Documentation/ABI/testing/sysfs-devices-power` (`runtime_status`).
- `power_state` y `d3cold_allowed`: `Documentation/ABI/testing/sysfs-bus-pci` (https://raw.githubusercontent.com/torvalds/linux/master/Documentation/ABI/testing/sysfs-bus-pci).
- `boot_vga` solo en VGA, y la clase 0x0380: https://lkml.iu.edu/2606.2/11467.html, https://lkml.iu.edu/2606.2/09515.html
- `boot_display`: https://patchew.org/linux/20250717173812.3633478-1-superm1@kernel.org (serie v9, «Adjust fbcon console device detection»).
- Leer el enlace despierta la tarjeta desde 6.18: https://lkml.iu.edu/2509.3/01025.html, https://patchew.org/linux/20250924095711.v2.1.Ibb5b6ca1e2c059e04ec53140cd98a44f2684c668@changeid
- amdgpu `_if_active`: https://lists.freedesktop.org/archives/amd-gfx/2025-February/119555.html, https://lists.freedesktop.org/archives/amd-gfx/2024-August/113213.html, `drivers/gpu/drm/amd/pm/amdgpu_pm.c`.
- Consumo de las APU: https://docs.kernel.org/gpu/amdgpu/thermal.html
- Estructuras de `gpu_metrics`: https://raw.githubusercontent.com/torvalds/linux/master/drivers/gpu/drm/amd/include/kgd_pp_interface.h
- RTD3 de NVIDIA: https://download.nvidia.com/XFree86/Linux-x86_64/575.64/README/dynamicpowermanagement.html ; el informe de los 588 W: https://forums.developer.nvidia.com/t/rtx-5000-ada-laptop-gpu-reports-invalid-588-593-w-power-draw-while-runtime-d3-suspended/378866
- PMU de i915 con varias tarjetas: https://lists.freedesktop.org/archives/intel-gfx/2019-August/207366.html
- switcheroo-control: `/usr/share/doc/switcheroo-control/NEWS` (3.0) y la respuesta de su D-Bus en la oficina; https://gitlab.freedesktop.org/hadess/switcheroo-control
- vga_switcheroo: https://docs.kernel.org/gpu/vga-switcheroo.html
- `DRI_PRIME`: https://docs.mesa3d.org/envvars.html ; PRIME de NVIDIA: README de NVIDIA, capítulo «PRIME Render Offload».

Las fuentes de AMD van dentro de sus tablas (apartado 1.1), con la clave de cada documento al principio.
