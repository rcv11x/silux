# La lógica nunca decide sobre un texto traducido

**Decisión.** Se compara, agrupa y guarda con códigos, claves o valores en
bruto: el código de SMBIOS (`0x0B` es una fila de chips), `Note.key`,
`Segment.key`, `Sensor.device_key`. La traducción va al final, al pintar, y
ninguna fecha se guarda ya escrita.

**Datos.** La memoria soldada se reconocía por «Fila de chips», en español:
con la interfaz en inglés dejaba de reconocerse. El árbol de Sensores
guardaba sus ramas plegadas por el nombre traducido del aparato, y al cambiar
de idioma se perdían.

**Descartado.** Traducir también lo que se compara: el texto de una
traducción cambia sin que nadie toque la lógica.

**Dónde vive.** `tests/test_language_independence.py` carga cada volcado en
español y en inglés y comprueba que el modelo sale igual salvo sus textos;
`tests/test_interface_language.py` comprueba que cada página se ve solo en el
idioma elegido.
