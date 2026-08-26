"""cpuz — perfilador de hardware para Linux.

La regla que sostiene todo el paquete: los proveedores leen *valores*
(enteros en hercios, bytes, grados) y el modelo los guarda tal cual.
El texto que ve el usuario se produce en `cpuz.render`, nunca antes.
"""

__version__ = "0.1.0"

# El emoji del rótulo. Uno solo y en un sitio: en un programa que ya usa el
# color para señalar lo importante, más de uno compite con los datos.
EMOJI = "🔎"
