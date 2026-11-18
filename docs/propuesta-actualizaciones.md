# Propuesta: que el AppImage se actualice solo

Punto 7 del autor. Hoy, para pasar de una versión a otra, hay que entrar en
GitHub, bajar el AppImage que toca y sustituir el viejo a mano. Esta propuesta
dice qué se conecta, cuándo y a dónde, y qué no hace nunca.

## Lo que no hace nunca

- **Conectarse sin que nadie lo pida.** El ajuste «Buscar actualizaciones al
  iniciar» viene **apagado**. La comunidad del autor mira la privacidad con
  lupa, y un perfilador de hardware que llama a casa al abrirse, aunque sea
  para preguntar una versión, es justo lo que esa gente no instala. Con el
  ajuste apagado y sin pulsar «Buscar ahora», el programa no abre ni un
  socket.
- **Sustituir nada sin un clic.** Encontrar una versión nueva solo pinta un
  aviso; el archivo se cambia cuando el usuario pulsa «Actualizar».
- **Mandar datos del equipo.** La petición lleva una sola cabecera propia,
  `User-Agent: silux/0.4.0`. Ni modelo, ni distribución, ni identificador.
- **Ejecutar algo que no coincide con lo publicado.** El archivo bajado se
  compara con el SHA-256 de `SHA256SUMS` en la misma release; si no está o no
  coincide, se borra y no se toca el AppImage.

## A quién se conecta

| Paso | URL | Tope | Espera |
|---|---|---|---|
| Buscar | `https://api.github.com/repos/rcv11x/silux/releases` | 1 MB | 15 s |
| Sumas | el `SHA256SUMS` de esa release | 64 kB | 15 s |
| Bajar | el AppImage de esa release | 400 MB | 60 s sin datos |

Solo HTTPS, también en las redirecciones (GitHub manda los adjuntos a
`objects.githubusercontent.com`): una redirección a `http://` se corta. Con
`urllib` de la biblioteca estándar; ninguna dependencia nueva.

## Qué versión cuenta como nueva

- Se descartan los borradores y las *prereleases*.
- La etiqueta (`v0.5.0`) se compara como tres números con
  `silux.__version__` **completa**: `0.10.0` va después de `0.9.1`. Cómo se
  enseña la versión en pantalla («0.4» o «0.4.0») no entra aquí.
- Una etiqueta que no es `x.y.z` se ignora.

## Qué AppImage se baja

El del mismo tipo que el que corre. Se distingue por la marca de construcción
que ya escribe el empaquetador (`_build.txt`, `-compat` al final en el
compatible): no hace falta nada nuevo.

| Corre | Baja |
|---|---|
| normal | `silux-x86_64.AppImage` |
| compatible | `silux-x86_64-compat.AppImage` |

## Cómo se sustituye

1. Temporal oculto en la **misma carpeta** que `$APPIMAGE` (mismo sistema de
   archivos: el paso 4 es atómico).
2. SHA-256 calculado mientras se baja; si no coincide, fuera el temporal.
3. `fsync`, `chmod 755`.
4. `os.replace` sobre `$APPIMAGE`, y `fsync` de la carpeta.
5. Botón «Reiniciar»: lanza el `$APPIMAGE` nuevo y cierra esta ventana. El
   proceso que corre no se entera del cambio: tiene abierto el archivo viejo,
   que sigue existiendo hasta que se cierra.

**El acceso directo no cambia**: la entrada de menú apunta a la ruta de
`$APPIMAGE`, y el archivo nuevo ocupa esa misma ruta con permiso de
ejecución. `desktop.status()` sigue diciendo «al día». Lo vigila un test.

## Cuándo no se sustituye y solo se avisa

| Caso | Qué se ve |
|---|---|
| Desde el código (no hay `$APPIMAGE`) | el aviso con el enlace a la release |
| La carpeta del AppImage no se puede escribir (`/opt`, un disco de solo lectura) | lo mismo |
| La release no trae `SHA256SUMS` o no lista ese AppImage | lo mismo, y el motivo |

## Dónde se ve

- **Ajustes**, grupo «Actualizaciones»: el interruptor, con el texto de a
  quién se conecta, y «Buscar ahora» con el resultado en la misma página
  (regla 9).
- **Barra lateral, al pie, debajo de la versión**: «Hay una versión nueva:
  0.5.0» y el botón que toque («Actualizar», «Ver en GitHub», «Reiniciar»).
  Cómo se pinta la versión no se toca.

## Lo que pide fuera del programa

El CI publica `SHA256SUMS` con los dos AppImage, en la release y en el
artefacto de cada ejecución (que es de donde salen los borradores). La 0.4.0
no lo lleva: es la primera que busca, y nunca se baja a sí misma.

## Reparto

- `silux/updates.py`: la comparación, la red, la comprobación y la
  sustitución. Sin Qt; el transporte se inyecta y los tests no salen a la red.
- `silux/ui/background.py`: un hilo que ejecuta una función y devuelve lo que
  da o el error.
- La ventana guarda el estado (sobrevive a cambiar de tema) y se lo pasa a
  Ajustes y a la barra lateral.

## Cómo se prueba de punta a punta, sin publicar nada

Los tests cambian la red por una falsa, y por eso no podían ver lo que
falló la primera vez que se probó entero (18 de noviembre, en el 5800X3D):
el Python del AppImage no traía `_ssl`, ninguna URL `https://` se abría y la
ventana decía «no hay conexión con GitHub». La prueba de verdad es el
AppImage construido, con su propio Python, contra un GitHub de mentira:

```bash
uv tool install mitmproxy
python3 tools/build_appimage.py --container          # el viejo, con el actualizador
gh release download v0.4.0 --pattern 'silux-x86_64.AppImage' -D /tmp/nuevo   # u otro cualquiera
python3 tools/probar_actualizador.py dist/silux-x86_64.AppImage /tmp/nuevo/silux-x86_64.AppImage
```

`tools/actualizador/github_falso.py` (un complemento de mitmproxy) publica
el segundo como una v0.4.1: contesta la lista de releases, el SHA256SUMS y
la descarga, la pasa por una redirección a `objects.githubusercontent.com`
como GitHub, y corta con un 403 todo lo demás. El certificado de mitmproxy
se le da solo a ese proceso (`SSL_CERT_FILE`); no se instala en ningún sitio.
`tools/actualizador/conductor.py` maneja la ventana sin pantalla dentro del
AppImage: «Buscar ahora», «Actualizar» y «Reiniciar», contestando que sí.

| Caso | Qué tiene que pasar | 18 de noviembre |
|---|---|---|
| bien | el nuevo en la misma ruta, ejecutable, sin temporales; es lo que corre tras reiniciar; la entrada de menú sigue apuntando ahí | bien |
| sha-mal | «lo bajado no coincide con su suma SHA-256»; el viejo, intacto | bien |
| http | «una redirección intentó salir de HTTPS»; el viejo, intacto | bien (antes decía «no hay conexión») |
| solo-lectura | solo el enlace a la release; el viejo, intacto | bien |

Por el proxy pasan cuatro peticiones, con `User-Agent: silux/0.4.0` y nada
más: la lista, `SHA256SUMS`, la descarga y su redirección.

**Lo que falta antes de meterlo en la 0.4**, ya con el CI: rebasar la rama
sobre `oficina` (choca en el paso de la release del CI, que tocan las dos),
pasar esta prueba con el AppImage que sale del CI, y una vez a mano en una
ventana de verdad, con los botones.
