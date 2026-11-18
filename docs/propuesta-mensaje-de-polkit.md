# Propuesta: que la ventana de la contraseña diga qué pide silux, en su idioma

18 de noviembre de 2026. **Toca el ayudante y su regla de polkit: solo
propuesta, sin aplicar.** La revisa el autor.

## Qué ve hoy el usuario

| Caso | Orden | Acción de polkit | Lo que sale en la ventana |
|---|---|---|---|
| «Dar permisos esta vez» | `pkexec /usr/bin/python3 -c ARRANQUE silux-helper.py FUENTE` (`client.en_linea`) | la genérica, `org.freedesktop.policykit.exec` | «Authentication is needed to run `/usr/bin/python3 -c import linecache…` as the super user» (lo vio el autor, en inglés, con `LANG=es_ES.UTF-8`) |
| «Para siempre», al instalar | `pkexec python3 -c … instalar.py …` | la genérica | lo mismo |
| Con el ayudante ya instalado | `pkexec /usr/local/libexec/silux/silux-helper` | la de silux, `org.silux.helper` (`instalar.PLANTILLA`), que pkexec encuentra por la anotación `org.freedesktop.policykit.exec.path` | «Se necesita autorización para leer los módulos de memoria y el diagnóstico de los discos» (con `xml:lang="en"` para el inglés) |

Así que el texto solo es nuestro cuando el ayudante ya está instalado. Los
dos primeros casos, que son la primera impresión, enseñan la orden de un
intérprete con código dentro. Para quien no sabe lo que es, eso parece justo
lo que no hay que autorizar.

## Por qué no se puede cambiar en «esta vez»

- **pkexec elige la acción por la ruta del programa.** Busca una cuya
  anotación `exec.path` sea esa ruta; si no hay, usa la genérica, cuyo
  mensaje es fijo y lleva la orden (pkexec.c, `find_action_for_path` y el
  detalle `polkit.message`). Quien llama no puede pasar un texto propio.
- **Una acción con nuestro texto tiene que estar en
  `/usr/share/polkit-1/actions`**, que es de root. Antes de la primera
  contraseña no se puede poner nada ahí.
- **Apuntar `exec.path` a `/usr/bin/python3` no vale.** La autorización
  quedaría colgada del intérprete y serviría para cualquier script del
  equipo: es lo que `_orden()` ya evita a propósito.
- **Lanzar un archivo y no `python3 -c` tampoco vale.** Desde el AppImage, el
  montaje FUSE no deja leer a root (sin `allow_other`) y va con `nosuid`. Y
  una copia en la carpeta del usuario es sustituible entre que se escribe y
  root la ejecuta: es el agujero que se cerró al pasar a `en_linea`.
- **Usar `run0` o `systemd-run` en vez de pkexec no lo arregla.** Su acción,
  `org.freedesktop.systemd1.manage-units`, dice «gestionar servicios del
  sistema», que asusta más.

**Dudoso, a comprobar en la oficina:** el mensaje genérico de pkexec 127
salió en inglés con el escritorio en español. O el polkit de Fedora no trae
traducida esa frase, o el agente de KDE no le pasa el idioma. Se comprueba
con `pkexec true` desde una terminal en español: si sale en inglés, no es
cosa de silux.

## Lo que se propone

### 1. «Para siempre»: nuestro texto, en cada idioma (cambio pequeño)

La regla ya existe. Se cambia su texto por el que pide el autor, con una
línea por idioma de la interfaz, y se añade al instalar:

```xml
<message>Silux quiere leer datos del hardware que solo puede ver el administrador (memoria, discos, consumo). Solo lee, no cambia nada.</message>
<message xml:lang="en">Silux wants to read hardware data that only the administrator can see (memory, disks, power). It only reads; it changes nothing.</message>
```

- polkitd elige el `<message>` según el idioma de la sesión que pide
  (`xml:lang`). Si no hay de ese idioma, usa el que no lleva `xml:lang`.
- Que la frase salga de `es.json` y `en.json` al escribir la regla, para
  no tener dos sitios con el mismo texto.
- **Cambiar el texto cambia la regla**, así que `al_dia()` la dará por vieja
  y el botón «actualizar el ayudante» saldrá a quien lo tenga instalado.
  Está bien: es como debe enterarse.

### 2. «Esta vez»: decirlo antes, ya que la ventana no se puede cambiar

- En «Qué pasa al dar permisos», encima del botón, una línea: «La ventana
  del sistema que se abre ahora no la escribe silux: dirá que se va a
  ejecutar `python3` como administrador. Es el ayudante de silux, que solo
  lee. Con "Para siempre", esa ventana lo dice con estas palabras.»
- Y que «Para siempre» se presente como la forma clara.

Esto no toca el ayudante: es texto de la interfaz. Se puede hacer cuando el
autor dé el visto bueno al punto 1.

### 3. Instalar: que la primera ventana también sea la nuestra (más grande)

La primera contraseña de «Para siempre» es la del instalador, y sale con el
texto genérico. Para que también sea la nuestra haría falta que el
instalador estuviera ya en una ruta de root con su regla, y eso solo lo
puede dejar un paquete de la distribución (RPM, deb, AUR). **Propuesta: no
para el AppImage.** Para cuando haya paquetes, su regla y su ayudante van
dentro del paquete y nunca se pasa por `python3 -c`.

## Resumen para decidir

| Punto | Toca privilegios | Tamaño | Recomendación |
|---|---|---|---|
| 1. Texto de la regla, por idioma | sí (la regla instalada) | pequeño | sí, en la 0.4.1 |
| 2. Aviso antes de la ventana | no | muy pequeño | sí, junto al 1 |
| 3. Instalador con regla propia | sí | solo con paquetes | más adelante |
