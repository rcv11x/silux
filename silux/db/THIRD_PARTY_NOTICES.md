# Avisos de terceros

Silux es software libre bajo la GPL-3.0 o posterior; el texto completo está
en `LICENSE`. La tabla con que identifica los procesadores,
`silux/db/cpu_ids.json`, se generó con los datos de dos proyectos. Sus avisos
van aquí tal como piden sus licencias, en el repositorio, en el paquete de
pip y dentro de cada AppImage.

## libcpuid

<https://github.com/anrieff/libcpuid>

De sus tablas de reconocimiento (`libcpuid/recog_intel.c`,
`libcpuid/recog_amd.c` y `libcpuid/recog_arm.c`) salen los nombres en clave,
los nodos de fabricación y los patrones de nombre comercial de los
procesadores x86, y los nombres de los núcleos ARM. `silux/db/__init__.py`
reescribe en Python su forma de emparejarlos: los mismos pesos y el mismo
lenguaje de patrones.

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
