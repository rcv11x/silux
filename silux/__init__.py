"""silux — perfilador de hardware para Linux.

Copyright (C) 2026 rcv11x

Este programa es software libre: puede redistribuirlo y modificarlo bajo los
términos de la Licencia Pública General de GNU, versión 3 o posterior, tal y
como la publica la Free Software Foundation. Se distribuye con la esperanza de
que resulte útil, pero SIN NINGUNA GARANTÍA. El texto completo está en el
fichero LICENSE.

La licencia es la GPL porque la base de datos de identificación incluye la
tabla de encapsulados que hereda de CPU-X, que es GPL-3.0.

La regla que sostiene todo el paquete: los proveedores leen *valores*
(enteros en hercios, bytes, grados) y el modelo los guarda tal cual.
El texto que ve el usuario se produce en `silux.render`, nunca antes.
"""

__version__ = "0.1.0"

# El emoji del rótulo. Uno solo y en un sitio: en un programa que ya usa el
# color para señalar lo importante, más de uno compite con los datos.
EMOJI = "🔎"
