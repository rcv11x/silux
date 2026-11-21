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

**Dónde vive.** `silux/score.py` y `silux/db/scores.json`, que van siempre en
el mismo commit que `score.VERSION`. El detalle, en
[benchmark.md](../benchmark.md).
