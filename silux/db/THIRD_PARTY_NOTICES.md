# Avisos de terceros

Silux es software libre bajo la GPL-3.0 o posterior; el texto completo está
en `LICENSE`. La tabla con que identifica los procesadores,
`silux/db/cpu_ids.json`, se generó con los datos de cuatro proyectos y de AMD,
y la de las unidades de los contadores de los discos,
`silux/db/smart_units.json`, con los de smartmontools. Sus avisos van aquí
tal como piden sus licencias, en el repositorio, en el paquete de pip y
dentro de cada AppImage.

## libcpuid

<https://github.com/anrieff/libcpuid>, y su fork
<https://github.com/rcv11x/libcpuid>, que es de donde se genera ahora.

De sus tablas de reconocimiento (`libcpuid/recog_intel.c`,
`libcpuid/recog_amd.c` y `libcpuid/recog_arm.c`) salen los nombres en clave,
los nodos de fabricación y los patrones de nombre comercial de los
procesadores x86, y los nombres de los núcleos ARM. `silux/db/__init__.py`
reescribe en Python su forma de emparejarlos: los mismos pesos y el mismo
lenguaje de patrones. De sus volcados de prueba (`tests/`) sale
`tests/fixtures/referencias_cpu.json`, con el que se comprueba la tabla.

```
Copyright 2008  Veselin Georgiev,
anrieffNOSPAM @ mgail_DOT.com (convert to gmail)

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

1. Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## Linux

<https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git>

De `arch/x86/include/asm/intel-family.h`, en la etiqueta que dice
`silux/db/cpu_ids.json` (`sources.linux`), salen la familia y el modelo de
cada microarquitectura de Intel y su nombre: la tabla los mira cuando la de
libcpuid no reconoce un procesador. Se toman los números y los nombres, que
son datos, no código. El archivo es del kernel Linux, bajo la GPL-2.0.

## amd.com

<https://www.amd.com/en/products/specifications/processors.html>

De la tabla de especificaciones de AMD salen el nombre en clave, el
encapsulado y el nodo de cada modelo que lista (`amd_models` en
`silux/db/cpu_ids.json`), con la página de cada uno como fuente. Son datos
de AMD, no código: la tabla los usa cuando libcpuid no reconoce un
procesador o no sabe su nodo o su encapsulado.

## cpuid

<https://etallen.com/cpuid.html>

De las tablas de microarquitectura de `cpuid.c` (`decode_uarch_intel` y
`decode_uarch_amd`), en la versión que dice `sources.cpuid` de
`silux/db/cpu_ids.json`, sale el nodo de fabricación por familia y modelo
(`cpuid_nodes`): la tabla lo usa cuando ninguna otra fuente da el nodo de un
procesador. Se toman los datos, no el código.

```
cpuid dumps CPUID information for each CPU.
Copyright 2003,2004,2005,2006,2010,2011,2012,2013,2014,2015,2016,2017,2018,
2020,2021,2022,2023,2024,2025,2026 by Todd Allen.

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.
```

## CPU-X

<https://github.com/TheTumultuousUnicornOfDarkness/CPU-X>

De su tabla de encapsulados (`src/core/databases.h`) sale el encapsulado de
cada procesador.

```
Copyright © 2014-2025 The Tumultuous Unicorn Of Darkness

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
```

Es la misma licencia que la de Silux, cuyo texto completo está en `LICENSE`.

## smartmontools

<https://github.com/smartmontools/smartmontools>

De su base de datos de discos (`drivedb/drivedb.h`), en el commit que dice
`silux/db/smart_units.json` (`sources.smartmontools`), salen los patrones del
modelo de cada disco y la unidad en que cuentan lo escrito y lo leído
(atributos 241, 242, 246 y 247): la que dice el nombre que smartmontools le
da a cada uno. Se toman los datos, no el código.

```
drivedb.h - smartmontools drive database file

Copyright (C) 2003-11 Philip Williams, Bruce Allen
Copyright (C) 2008-26 Christian Franke

SPDX-License-Identifier: GPL-2.0-or-later
```
