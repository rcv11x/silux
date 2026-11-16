# Propuesta: permisos e Inicio

Solo propuesta: nada de esto está escrito en la aplicación. Las maquetas están
hechas montando la ventana de verdad, con la foto de un i5-10400 sin permisos,
y cambiándole las piezas en memoria antes de capturarla; por eso salen con la
tipografía y las medidas reales.

## Lo que se propone

### 1. Un aviso arriba en Inicio

Sale solo si falta algo **que el ayudante sabe leer** en este equipo, y la lista
la dan las notas reales (`Need.ROOT`) de la foto, no un texto fijo: en un
equipo con todo leído no sale, y en uno sin SMART no promete la salud de los
discos.

- Título: «Faltan N datos que este equipo sí tiene».
- Una línea por cosa que falta, con un candado delante.
- Tres botones: **Dar permisos** (el principal), **Ahora no** y **Qué hace
  esto**, y un aspa para cerrarlo.
- «Ahora no» lo esconde hasta el próximo arranque. El aspa lo esconde para
  siempre: se guarda en `settings.json` (`aviso_permisos_cerrado`), y el enlace
  de la barra de estado sigue ahí.
- Desaparece solo cuando ya no falta nada, y vuelve a salir si algo vuelve a
  faltar después de haberlo tenido (un ayudante que se cae, F-M21), aunque se
  hubiera cerrado: eso es otro aviso.
- En compacto, la lista va en una sola línea con los nombres cortos.

Para la lista hace falta un dato que hoy las notas no traen: **qué falta**, en
pocas palabras, además de **por qué**. Se propone un campo corto en `Note`
—`que: str`— que escribe el mismo proveedor que pone la nota, y que se traduce
como lo demás que el proveedor inventa. Sin él habría que deducirlo de la ruta
de la nota, que es la lección de «volver a deducir por el nombre lo que el
proveedor ya había resuelto».

### 2. «Qué hace esto»

Un diálogo de cuatro párrafos:

- qué lee el ayudante —la tabla de memoria del firmware, el diagnóstico de los
  discos, el voltaje y los contadores de energía del procesador, y los
  contadores de la gráfica y de la memoria— y que **solo lee**;
- **esta vez**: vive mientras silux está abierto;
- **para siempre**: se instala en `/usr/local/libexec/silux` con su regla de
  polkit, se pide la contraseña una vez por sesión y se quita desde Ajustes;
- que la contraseña la pide **polkit**, en su ventana, y silux no la ve.

Con los tres botones: «Dar permisos esta vez», «Para siempre…» y «Cerrar».

### 3. Un candado donde falta un dato por permisos

Hoy un dato que falta por permisos y uno que no se pudo leer salen igual, con
«—». Se propone un **cuarto estado** junto a los tres que ya hay (dato, «—» no
lo sé, escondido y nombrado al pie porque no existe): **candado**, con tooltip
que dice qué lo guarda y que al pulsarlo se piden los permisos. En las fichas
grandes, el candado a tamaño de cifra y «con permisos» en la línea de detalle,
sin unidad.

Para pintarlo, la página necesita saber que **ese** campo falta por permisos:
se propone que la nota diga su ruta con el nombre del campo (`cpu.voltage_v`
ya lo hace; `gpus.0` habría que partirla en `gpus.0.usage` y
`gpus.0.power`), y una función en `render` que, dada la foto y una ruta,
conteste si va candado.

### 4. Barra de estado para quien usa el programa

- Fuera la lista de proveedores (`cppc, cpuid, dmi…`): es jerga, se corta en
  compacto y su sitio es el informe, que ya la lleva.
- Queda «Se actualiza cada 1 s · espacio para congelar» y, si falta algo, un
  enlace: «Faltan N datos · dar permisos».
- Margen a la izquierda: hoy el texto empieza pegado al borde.
- La insignia «N datos sin leer» de la cabecera de Inicio sobra: repetía el
  aviso y el enlace.

### 5. Inicio con la ventana grande

- **El hueco de abajo** se llena con tres tarjetas más: temperaturas (lo más
  caliente ahora, y «no tiene sensor» donde no lo hay), red (la interfaz
  principal, su enlace y su tráfico) y placa (modelo, BIOS, UEFI y TPM). Las
  tres llevan a su sección al pulsarlas, como las demás.
- **El botón de copiar imagen** pasa a la fila de las insignias, a la derecha,
  en vez de ocupar una fila para él solo.
- **La barra de memoria** lleva su leyenda: cada insignia de debajo, con el
  color de su tramo.
- **La tarjeta de la gráfica** dice algo más que los MHz: integrada o no,
  unidades, la memoria que usa y «de 1.10 GHz»; el uso y el consumo con su
  candado si faltan permisos.

## Lo que respeta y lo que hay que vigilar

- **Regla 5**: el aviso de Inicio **no sustituye** a los de cada página. Cada
  página sigue enseñando sus notas, con el botón dentro del aviso (la lección
  de «explicar que hace falta un permiso sin poner el botón al lado»); Inicio
  los junta y el candado señala el sitio exacto.
- **Solo se cuenta lo que se puede resolver** (la lección del botón que no
  sabía arreglar RAPL): el número del aviso y del enlace sale de las notas que
  el ayudante sabe leer en este equipo.
- **Ámbar** para lo que tiene arreglo, como hoy; lo que no lo tiene sigue en
  gris y no entra en la lista.
- **El aviso sigue al estado** (la lección de la tabla estática que seguía
  pidiendo permisos después de darlos): se recalcula en cada muestreo.
- **Nada de mandar a bajar `perf_event_paranoid`**: el texto habla del
  ayudante y de polkit, no de cerrojos del sistema.
- **Regla 4**: el diálogo de polkit sigue abriéndose fuera del hilo de la
  interfaz; esto es justo F-M4, y conviene arreglarlo antes de hacer el botón
  más visible.
- **Privilegios**: lo que se propone no cambia qué lee el ayudante ni cómo se
  instala; solo cómo se pide. Cualquier cambio en eso iría como propuesta
  aparte.

## Maquetas

En la carpeta de imágenes del equipo donde se hicieron, `silux-test/permisos/`,
en oscuro a 1440×880 y en compacto a 900×680, con el guion que las genera al
lado:

| Archivo | Qué enseña |
|---|---|
| `00-inicio-hoy` | Inicio como está hoy, para comparar |
| `01-inicio-sin-permisos` | el aviso, Inicio reordenado y la barra nueva |
| `02-que-hace-esto` | el diálogo |
| `03-inicio-aviso-cerrado` | el aviso cerrado: queda el enlace de abajo |
| `04-inicio-con-permisos` | sin aviso ni enlace |
| `05-cpu-candado` | el candado en el voltaje, con su tooltip |
| `06-graficos-candado` | el candado en las fichas de uso y consumo, junto al «—» de la temperatura, que no existe |
| `07-memoria-candado` | el candado en la velocidad y el banco de cada módulo |
