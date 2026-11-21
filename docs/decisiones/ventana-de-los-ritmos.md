# Ningún ritmo sale de una ventana de menos de medio intervalo

**Decisión.** Todo lo que divide la diferencia de dos lecturas por el tiempo
(el consumo, el uso del procesador y de la gráfica, la red, los discos, el
tráfico de la memoria, los estados de reposo) pasa por
`providers/counters.py`. Si entre las dos lecturas no ha pasado al menos la
mitad del intervalo, o el contador ha ido hacia atrás, no hay dato y esa
lectura es la nueva base.

**Datos.** Un portátil con una Iris Xe que gastaba 9 W tuvo un punto de
1336648637,3 W: unos 9 J divididos entre unos 7 ns. Un valor y su marca de
tiempo tomados en momentos distintos dan ventanas así, y un contador que se
reinicia da una diferencia negativa enorme.

**Descartado.** Arreglar cada proveedor por su cuenta (era así, y cada uno
tenía su propio umbral o ninguno) y suavizar la serie, que esconde el fallo
en vez de evitarlo.

**Dónde vive.** `providers/counters.py` (`MIN_WINDOW_SHARE = 0.5`) y
`tests/test_counter_windows.py`. Las fotos de un test van separadas un
intervalo de reloj falso (`tests/interval.py`).
