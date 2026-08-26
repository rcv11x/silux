"""Lectura de datos que el kernel reserva a root.

Dos cosas necesitan privilegios y no hay forma de evitarlo:

* La tabla SMBIOS completa (`/sys/firmware/dmi/tables/DMI`, permisos 0400), que
  es donde están los módulos de memoria: fabricante, referencia, rangos,
  velocidad y voltaje.
* Los registros MSR del procesador (`/dev/cpu/*/msr`), de donde salen el
  voltaje real del núcleo y los límites de potencia configurados.

El programa principal nunca corre como root. Cuando hace falta uno de esos
datos lanza un ayudante mínimo a través de polkit, le habla por una tubería y
lo deja vivo mientras dure la sesión. El ayudante solo sabe hacer esas dos
lecturas: no ejecuta órdenes, no escribe nada y no acepta rutas arbitrarias.
"""
