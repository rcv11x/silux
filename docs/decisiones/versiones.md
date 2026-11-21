# Las versiones de prueba

**Decisión.** Por debajo, la versión es siempre `x.y.z` según PEP 440: la
cuarta de prueba de la 0.4 es `0.4.0rc4` en `pyproject.toml`, en la etiqueta
de git y en `--version`. A quien mira la ventana o lee el informe se le
enseña «0.4-prueba4», y «0.4» en vez de «0.4.0»: el tercer número solo
aparece cuando no es cero.

**Por qué.** Las herramientas (pip, el actualizador, el canal de pruebas)
necesitan comparar versiones, y PEP 440 ordena `0.4.0rc4` antes de `0.4.0`.
Las personas leen «prueba4» sin saber qué es un *release candidate*.

**Descartado.** Etiquetas como `0.4-prueba4`: pip no las ordena y el
actualizador no podría saber cuál es más nueva.

**Dónde vive.** `render.version` y `silux/__init__.py`.
