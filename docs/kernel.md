# Qué versión del kernel hace falta para cada dato

silux admite **Linux 5.15 o posterior**, y se recomienda un LTS reciente o una
distribución rolling. Esta página dice, para cada dato que lee silux y que no
existe en todos los kernels, desde qué versión de mainline existe y de dónde
sale esa cifra.

Cuando un dato falta porque el kernel es anterior —y solo por eso—, la página lo dice así
—«Tu kernel (5.15) no publica esto; existe desde Linux 6.10»—, distinto de
«este equipo no lo tiene», porque el arreglo es actualizar el kernel y no
cambiar de hardware. Las versiones de las filas con clave están también en
`silux/kernel.py` (`DESDE`), y `tests/test_kernel.py` comprueba que las dos
tablas dicen lo mismo.

## Cómo se averiguó

Investigado el 18 de noviembre de 2026 mirando el código fuente en cada
etiqueta de mainline (v5.4, v5.5 a v5.15 cuando hizo falta, y v5.15 a v7.3):
la versión es la primera etiqueta en la que aparece el patrón, con la anterior
sin él. Cada commit citado se comprobó con la comparación de etiquetas de
GitHub (está en la etiqueta N y no en la N-1). Las retroportaciones a 5.15.y
salen de buscar en el árbol estable entre v5.15 y v5.15.225. Lo anterior a
5.15 se marca «≤ 5.15», con una fuente que lo muestra en 5.15, sin rastrear la
versión exacta: está en todos los kernels que silux admite.

Enlaces: **T** es
`https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=`
y **S**, el mismo en el árbol `stable`.

Hoy se atribuye al kernel en dos sitios: el techo del silicio en AMD (sin
amd-pstate, que es de 5.17, la página CPU no lo tiene) y el SPD de la DDR5
(sin `spd5118`, de 6.11). En los demás, que el dato falte no basta para
culpar al kernel: o sale por otro camino, o depende también del hardware, y
la tabla lo dice en cada fila.

## La tabla

| Dato | Lo usa | Desde | Clave | Fuente | Notas |
|---|---|---|---|---|---|
| cpufreq `cpuinfo_avg_freq` | la frecuencia de cada hilo | 6.15 | `cpufreq.cpuinfo_avg_freq` | T`fbb4a4759b541d09ebb8e391d5fa7f9a5a0cad61` | Opcional: solo si la arquitectura sabe medir la media. Sin él, silux lee `scaling_cur_freq`. |
| driver `amd_pstate` | el techo del silicio en AMD (CPPC) | 5.17 | `amd_pstate` | T`ec437d71db77a181227bf6d0ac9d4a80e58ecf0f` | Sin él, en AMD el techo no se publica: la nota lo atribuye al kernel si es anterior. |
| `amd_pstate_max_freq`, `amd_pstate_highest_perf` | el techo del silicio en AMD | 5.17 | (con `amd_pstate`) | T`ec4e3326a95507ea96fbad21b9472f5ba25500a7` · T`3ad7fde16a04aa70df8a59cba99e225ef9adf42f` | |
| modo activo EPP de amd-pstate | el driver de la página CPU | 6.3 (`amd_pstate_epp`); 6.5 (`amd-pstate-epp`) | `amd_pstate.epp` | T`ffa5096a7c338641f70fb06d4778e8cf400181a8` · renombrado: T`f4aad639302a07454dcb23b408dcadf8a9efb031` | En 6.3 y 6.4 `scaling_driver` dice `amd_pstate_epp`, con guion bajo. silux no compara ese nombre. |
| `energy_performance_preference` (amd-pstate) | la preferencia de energía | 6.3 | (con `amd_pstate.epp`) | T`ffa5096a7c338641f70fb06d4778e8cf400181a8` | Solo en modo activo. En `intel_pstate` es ≤ 5.15. |
| `amd_pstate_prefcore_ranking` | el ranking de núcleos | 6.9 | `amd_pstate.prefcore_ranking` | T`e571a5e2068ef57945fcd5d0fb950f8f96da6dc8` | |
| `acpi_cppc/highest_perf` | el ranking por CPPC | ≤ 5.15 | | [cppc_acpi.c en v5.15](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/acpi/cppc_acpi.c?h=v5.15) | |
| vulnerabilidades `meltdown`, `spectre_v1`, `spectre_v2`, `spec_store_bypass`, `l1tf`, `mds`, `tsx_async_abort`, `itlb_multihit`, `srbds` | Sistema | ≤ 5.15 | | [ABI en v5.15](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/Documentation/ABI/testing/sysfs-devices-system-cpu?h=v5.15) | |
| vulnerabilidad `mmio_stale_data` | Sistema | 5.19 | | T`8d50cdf8b8341770bc6367bce40c0c1bb0e1d5b3` | Retroportado a 5.15.48 (S`531eb5fe3171f11cece79c7aac28bb5a085fb3fa`). |
| vulnerabilidad `retbleed` | Sistema | 5.19 | | T`6b80b59b3555706508008f1f127b5412c89c7fd8` | Retroportado a 5.15.57 (S`82e92fe936dbefda25ed030abe91ae76576cd6da`). |
| vulnerabilidad `gather_data_sampling` | Sistema | 6.5 | | T`8974eb588283b7d44a7c91fa09fcbaf380339f3a` | Retroportado a 5.15.125 (S`348a89e2018428c3e55a87cdd9ae3cbd6cc8248a`). |
| vulnerabilidad `spec_rstack_overflow` | Sistema | 6.5 | | T`fb3bd914b3ec28f5fb697ac55c4846ac2d542855` | Retroportado a 5.15.125 (S`b35087763a44d1eb45857f799579a351332be505`). |
| vulnerabilidad `reg_file_data_sampling` | Sistema | 6.9 | | T`8076fcde016c9c0e0660543e67bff86cb48a7c9c` | Retroportado a 5.15.154 (S`2fb08b672eb78c4930413cf529734792456ae15f`). |
| vulnerabilidad `ghostwrite` | Sistema | 6.14 | | T`4bf97069239bcfca9840936313c7ac35a6e04488` | De RISC-V; en x86 el archivo existe con la respuesta por defecto. No está en 5.15.y (comprobado hasta 5.15.225). |
| vulnerabilidad `indirect_target_selection` | Sistema | 6.15 | | T`f4818881c47fd91fcb6d62373c57c7844e3de1c0` | Retroportado a 5.15.184 (S`e30bcefa93a6493239130556b2f9db38a1d6e761`). |
| vulnerabilidad `old_microcode` | Sistema | 6.16 | | T`4e2c719782a84702db7fc2dc07ced796f308fec7` | No está en 5.15.y (comprobado hasta 5.15.225). Otras series estables, sin mirar. |
| vulnerabilidad `tsa` | Sistema | 6.16 | | T`d8010d4ba43e9f790925375a7de100604a5e2dba` | Retroportado a 5.15.187 (S`f2b75f1368af22bb290f128e29bc64b619a9d54d`). |
| vulnerabilidad `vmscape` | Sistema | 6.17 | | T`556c1ad666ad90c50ec8fccb930dd5046cfbecfb` | Retroportado a 5.15.193 (S`2f4f2f8f860cb4c3336a7435ebe8dcfded0c9c6e`). |
| hwmon `drivetemp` | la temperatura de los discos SATA | 5.6 (≤ 5.15) | | T`5b46903d8bf372e563bf2150d46b87fff197a109` | |
| hwmon de `nvme` | la temperatura de los NVMe | 5.5 (≤ 5.15) | | T`400b6a7b13a3fd71cff087139ce45dd1e5fff444` | |
| `gigabyte_wmi` | sensores de placas Gigabyte | 5.13 (≤ 5.15) | | T`572931972cb56f7b5d7b55fde959d62cd2fbdb11` | Vive en `drivers/platform/x86/`. |
| `spd5118` | el SPD de los módulos DDR5 | 6.11 | `spd5118` | T`09262e9814ca0851c937cab1f26df4ab207885a1` · nvmem: T`25dff444c6cb122eed08e328ddc9698f3b3d2ca9` · [KernelNewbies 6.11](https://kernelnewbies.org/Linux_6.11) | Sin él no hay SPD de DDR5 en ninguna placa. Con módulos DDR5 sin SPD y un kernel anterior, Memoria lo atribuye al kernel y no a la placa. |
| `ee1004` | el SPD de los módulos DDR4 | ≤ 5.15 | | [ee1004.c en v5.15](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/misc/eeprom/ee1004.c?h=v5.15) | Es una EEPROM, no hwmon. En 6.8 crea el sensor térmico del módulo (T`393bd1000f8192fcf5fa4abc1e79c0919c123e9b`); en 6.11 pasa a nvmem conservando el archivo (T`79d0df36b54179ac2192e56ad7fdb29c952f35e2`); en 7.3 se muda a `drivers/nvmem/` (T`cf09b7a05618bea99468b67fe80202efba1b48ad`). |
| amdgpu `gpu_metrics` | la telemetría de AMD | 5.10 (≤ 5.15) | | T`25c933b1c4fcfaa65ed735e9782fdb2622f7b7e8` | El formato cambia con la versión de la tabla, no con la del kernel. |
| amdgpu `mem_info_vram_vendor` | el fabricante de la VRAM | 5.5 (≤ 5.15) | | T`ad02e08e05781c3dabe7853f39cffb69169e96b2` | |
| amdgpu `unique_id` | el identificador de la gráfica | 5.3 (≤ 5.15) | | T`fb2dbfd2427e82ae63742f667cda19f1af6b77c2` | |
| amdgpu `vcn_busy_percent` | el uso del motor de video | 6.10 | `amdgpu.vcn_busy_percent` | T`d1b2703cc28769d4bb61d7750a9a74acc916cebe` | **No se atribuye al kernel**: el mismo dato sale también de `gpu_metrics` (5.10), y las AMD sin VCN (Polaris) no lo tienen en ningún kernel. |
| amdgpu hwmon `power1_input` | el consumo de la gráfica | 6.6 | `amdgpu.power1_input` | T`bb9f7b6826257390a847abb39c719dca0de41a18` | `power1_average` es ≤ 5.15 y silux lee los dos. Desde 6.6 puede haber uno, el otro o los dos (T`15419813f2ef8b810bf2e11f5b2269acf776cb44`). |
| i915 por GT: `gt/gt0/rps_*_freq_mhz`, `gt/gt0/rc6_residency_ms` | relojes y reposo de la gráfica Intel | 5.19 | `i915.gt` | directorio: T`b770bcfae9ad816cd9efce6b0fff4dab47084578` · RPS: T`56a709cf77468e3a422b0ce3d58f8c2257bac2f1` · RC6: T`80cf8af17af042cd4b287716aca917422053f873` | Antes están en el nivel de la tarjeta (`gt_*_freq_mhz`, `power/rc6_residency_ms`), y silux los lee de ahí. Los nombres se forman con una macro: un grep literal no los ve hasta 6.1. |
| i915 `gt/gt0/throttle_reason_*` | «Estado» de la gráfica Intel | 5.19 | `i915.throttle_reason` | T`fa68bff7cf27d83e0ca83c6388d6bc2ddc599905` | **No se atribuye al kernel**: depende también de la generación. El i5-10400 (Comet Lake) no lo tiene ni con 7.3. |
| i915 `engine/<motor>/capabilities` | «Sabe hacer» de cada motor | 5.7 (≤ 5.15) | | T`4ec76dbeb62b5f897641af502b8309808e4e2d82` | |
| driver `xe` | gráficas Intel recientes | 6.8 | `xe` | T`dd08ebf6c3525a7ea2186e636df064ea47281987` · [KernelNewbies 6.8](https://kernelnewbies.org/Linux_6.8) | |
| xe `tile0/gt0/freq0/` (`rp0_freq`, `rpe_freq`, `rpn_freq`) | relojes del silicio con xe | 6.8 | (con `xe`) | T`bef52b5c7a1904fc6e1bdda4a0e6dc460f562856` | |
| powercap `intel-rapl` en AMD | el consumo del procesador en AMD | 5.11 (≤ 5.15) | | Zen y Zen 2: T`43756a298928c9a4e8201baaeb205c0c103728af` · Zen 3 y 4: T`8a9d881f22d7a0e06a46a326d0880fb45a06d3b5` | Zen 5 (familia 1Ah), sin mirar. |
| `energy_uj` solo para root (PLATYPUS, CVE-2020-8694) | el consumo sin permisos | 5.10 (≤ 5.15) | | T`949dd0104c496fa7c14991a23c03c62e44637e71` | Algunas distribuciones lo abren otra vez con reglas propias. |
| PMU `cpu_core` y `cpu_atom` (híbridos de Intel) | los tipos de núcleo | 5.13 (≤ 5.15) | | T`f83d2f91d2590318e083d05bd7b1beda2489050e` | |
| TPM `tpm_version_major` | Placa base | 5.6 (≤ 5.15) | | T`7084eddf6be94e73f8298c1a28078b91536f2975` | |
| PMU `uncore_imc_free_running` | el tráfico de la memoria | Tiger Lake 5.7, Alder Lake 5.17, Ice Lake de servidor 5.7, Snow Ridge ≤ 5.4 | | TGL: T`fdb64822443ec9fb8c3a74b598a74790ae8d2e22` · ADL: T`5a4487f9ef5ef2fdb3215cadf0a9c3e5e8678634` · ICX: T`2b3b76b5ec67568da4bb475d3ce8a92ef494b5de` | Ice Lake de cliente y Rocket Lake siguen con `uncore_imc`, no con este: el comentario de `privileged/helper.py` que dice «de Ice Lake en adelante» es falso, aunque la expresión acepta los dos nombres. No se ha tocado porque cambiar el ayudante obliga a reinstalarlo. Un Alder Lake con 5.15 o 5.16 no lo tiene. |

## Lo que no se ha confirmado

- La versión exacta de lo anterior a 5.15 (`acpi_cppc/highest_perf`, el EPP de
  `intel_pstate`, `ee1004` y las nueve vulnerabilidades antiguas): todo estaba
  ya en 5.4 salvo `srbds`, que entró entre 5.4 y 5.10.
- `old_microcode` y `ghostwrite` en series estables distintas de 5.15.y.
- Desde qué versión `amd_pstate` es el driver por defecto en cada familia de
  Zen.
- RAPL en Zen 5 (familia 1Ah).
