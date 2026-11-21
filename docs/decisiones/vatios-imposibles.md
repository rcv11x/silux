# Un vatio imposible se descarta y el informe lo cuenta

**Decisión.** Un vatio negativo o por encima de lo que la pieza puede dar no
entra en la gráfica, ni en el máximo, ni en la media. El techo es el PL4 que
declara RAPL (`peak_power`); sin él, el doble de su límite más alto, y sin
ningún límite, 1000 W. El informe dice cuántos se descartaron y con qué
números.

**Por qué.** Es la red, detrás de la ventana válida
([ventana-de-los-ritmos.md](ventana-de-los-ritmos.md)): si algo se cuela por
otro camino, no estropea el máximo de la sesión, y el informe deja ver que
pasó para encontrar la causa.

**Descartado.** Un techo fijo para todos (un portátil de 15 W y un sobremesa
de 250 W no comparten ninguno útil) y descartar en silencio.

**Dónde vive.** `rapl.package_ceiling_w`, `rapl.Discarded` y
`report.power.discarded`.
