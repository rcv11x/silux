# La puntuación usa dos cargas de cinco

**Decisión** (escala v6, septiembre de 2026). Puntúan el resumen
criptográfico y la compresión pesada. Las otras tres se miden y se enseñan
con un asterisco y con la biblioteca que las midió al lado, porque delatan
qué hay debajo.

**Datos.** Un i5-10400, el mismo día, midiendo la verificación con la zlib de
cada distribución: 14,9 GB/s con la zlib-ng de Fedora, 3,9 con la de Debian,
2,0 con la de Arch y 1,5 con la de Ubuntu 22.04 (la del AppImage). Un ×9,7
que no es del procesador. El resumen criptográfico dio 190,05 · 190,13 ·
190,17 op/s en tres distribuciones y dos versiones mayores de OpenSSL; la
compresión pesada se mueve un 3 %.

**Descartado.** Registrar qué zlib midió y corregir con un factor: `libz.so.1`
elige su ruta mirando el CPUID, así que el factor dependería también del
procesador.

**Descartado también.** Acercar las tres cargas de fuera usando lo que trae
CPython: su sha512 interno da 55 op/s en Python 3.14 y 109 en 3.10 (cambió
la implementación y hasta el nombre del módulo), el doble de dispersión que
OpenSSL. Y `pbkdf2_hmac` no tiene versión interna: sin OpenSSL desaparece de
`hashlib`, así que esa carga no se puede desatar del sistema.

**Las versiones anteriores.**

- **v4**: la compresión pesada pasó de LZMA a bzip2. LZMA saltaba entre dos
  velocidades separadas un 26 % y metía ella sola un 4,7 % de dispersión en
  la puntuación de un equipo consigo mismo; dos piezas que se llevaran menos
  que eso salían indistinguibles.
- **v5**: la carga que recorre un bloque grande dejó de contar operaciones y
  pasó a bytes por segundo. El bloque se dimensiona con la caché de cada
  equipo (de 64 a 192 MB), así que una «operación» no era lo mismo en dos
  máquinas: con el mismo ancho de banda, un procesador con poca caché sacaba
  un 42,8 % más. En bytes por segundo queda un 1 % residual, por debajo del
  ruido de la medida (1,3 %). La carga pasó a llamarse «verificación». La v5
  no llegó a publicarse: la v6 se vio antes de fusionarla.

**Dónde vive.** `silux/score.py` y `silux/db/scores.json`, que van siempre en
el mismo commit que `score.VERSION`. El detalle, en
[benchmark.md](../benchmark.md).
