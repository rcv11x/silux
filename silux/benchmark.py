"""Una prueba de rendimiento que dice en qué condiciones se hizo.

La cifra de un benchmark no vale nada por sí sola. El mismo procesador da
resultados muy distintos según el gobernador de energía, según lo caliente que
esté, según si otro programa le está robando la mitad de los núcleos. Quien
compara su número con el de internet y no cuadra se queda sin saber por qué.

Silux ya sabe leer todo eso mientras trabaja, así que aquí la prueba no
devuelve un número: devuelve un número **y las condiciones en las que salió**.
Si el gobernador estaba en ahorro, lo dice. Si la CPU bajó de frecuencia a
mitad de prueba, lo dice. Si había carga de fondo, avisa de que el resultado no
es comparable. Eso es lo que convierte una cifra en un diagnóstico.

Sobre las cargas: son de la biblioteca estándar, y no por comodidad. Compilar
un núcleo en C daría lo mismo (se probó: la misma estabilidad), pero dentro de
un AppImage no hay compilador, y una prueba que solo funciona desde el código
fuente no le sirve a quien descarga el programa. `zlib`, `bz2` y `hashlib`
tienen su bucle en C igualmente, ya compilado, y liberan el intérprete mientras
trabajan, así que reparten de verdad entre núcleos.

`SHA-512` y no `SHA-256` a propósito: la instrucción `sha_ni` acelera la
segunda y no la primera, así que con SHA-256 un procesador que la tenga saldría
inflado y dejaría de poder compararse con uno que no. Vale para las dos cargas
que usan hash, la del resumen y la de derivación de clave: en esta última el
efecto sería incluso mayor, porque son miles de rondas encadenadas.
"""

from __future__ import annotations

import bz2
import functools
import hashlib
import os
import pathlib
import threading
import time
import zlib
from dataclasses import dataclass, field
from typing import Callable, Optional

SYS_CPU = "/sys/devices/system/cpu"

# 4 MB con entropía media: ni tan repetido que la compresión sea trivial ni tan
# aleatorio que no haya nada que comprimir.
BLOQUE = bytes(range(256)) * 16384
# Un trozo del anterior: la compresión pesada es tan lenta que con los 4 MB
# enteros cada operación tardaría más que la medida entera.
MEDIO = BLOQUE[:65536]

# Cuánto dura cada medida. Por debajo de tres segundos el resultado depende de
# si al turbo le dio tiempo a subir; por encima de diez, la prueba entera se
# hace larga sin cambiar la cifra.
SEGUNDOS = 5.0
SEGUNDOS_RAPIDO = 2.0
# Los extremos de lo que se puede pedir. Por debajo de uno la cifra depende de
# si al turbo le dio tiempo a subir; por encima de sesenta, la prueba se hace
# eterna para medir lo mismo que a los treinta.
MINIMO_SEGUNDOS = 1.0
# Media hora por medida. Con seis medidas eso son tres horas de prueba, que es
# más de lo que nadie necesita, pero quien quiera dejar el equipo cociéndose
# toda la tarde para ver si aguanta tiene derecho a pedirlo.
MAXIMO_SEGUNDOS = 1800.0

# A partir de aquí, la carga de fondo estropea la medida.
CARGA_ACEPTABLE = 10.0
# Y a partir de aquí, la frecuencia cayó lo bastante como para decirlo.
CAIDA_NOTABLE = 0.90


@dataclass(frozen=True, slots=True)
class Carga:
    """Una de las cosas que se le pide hacer al procesador."""

    key: str
    name: str
    explanation: str
    work: Callable[[], object]


# El bloque tiene que no caber en la caché, y cuánto es eso depende del
# procesador: un 5800X3D lleva 96 MB de L3 y se traga entero un bloque de 64,
# así que ahí la prueba mediría la caché y no la memoria. Se dimensiona al
# doble de la L3 que haya, con un suelo para las CPU pequeñas y un techo para
# no pedir media RAM prestada.
BLOQUE_MINIMO_MB = 64
BLOQUE_MAXIMO_MB = 192
_grande: Optional[bytes] = None


def _tamano_del_bloque() -> int:
    """En megas: el doble de la caché de último nivel, entre 64 y 192."""
    mayor = 0
    for indice in range(5):
        crudo = _leer(f"{SYS_CPU}/cpu0/cache/index{indice}/size")
        if not crudo:
            continue
        try:
            valor = int(crudo.rstrip("KMG"))
        except ValueError:
            continue
        if crudo.endswith("M"):
            valor *= 1024
        elif crudo.endswith("G"):
            valor *= 1024 * 1024
        mayor = max(mayor, valor // 1024)          # a megas
    return max(BLOQUE_MINIMO_MB, min(BLOQUE_MAXIMO_MB, mayor * 2 or BLOQUE_MINIMO_MB))


def _bloque_grande() -> bytes:
    global _grande
    if _grande is None:
        megas = _tamano_del_bloque()
        _grande = BLOQUE * (megas * 1024 * 1024 // len(BLOQUE))
    return _grande


def _soltar_el_bloque() -> None:
    """Devuelve los megas del bloque al terminar la prueba.

    Son hasta 192 MB, y el programa entero se mueve en 130: dejarlos vivos
    después de medir dispararía el consumo el resto de la sesión por una
    prueba que dura medio minuto.
    """
    global _grande
    _grande = None


CARGAS: tuple[Carga, ...] = (
    Carga("compresion", "Compresión",
          "Comprimir es enteros y acceso a memoria, que es lo que hace el "
          "equipo al instalar un juego o abrir un proyecto grande.",
          lambda: zlib.compress(BLOQUE, 9)),
    Carga("hash", "Resumen criptográfico",
          "Enteros puros y sin instrucciones especializadas: mide el núcleo, "
          "no una aceleración concreta.",
          lambda: hashlib.sha512(BLOQUE).digest()),
    # bzip2 y no LZMA, y no es indiferente: ver `POR QUÉ NO LZMA` más abajo.
    Carga("compresion_dura", "Compresión pesada",
          "Lo mismo pero apretando de verdad: bzip2 ordena el bloque entero "
          "antes de comprimirlo, así que hace mucho más trabajo por byte y "
          "separa a un núcleo rápido de uno que solo tiene muchos hermanos.",
          lambda: bz2.compress(MEDIO, 9)),
    Carga("derivacion", "Derivación de clave",
          "Miles de rondas encadenadas sin poder adelantar trabajo: es lo que "
          "hace un gestor de contraseñas al abrirse, y no lo acelera ninguna "
          "instrucción especial.",
          lambda: hashlib.pbkdf2_hmac("sha512", b"silux", b"benchmark", 12_000)),
    Carga("memoria", "Memoria",
          "Recorre de una vez el doble de lo que cabe en la caché de este "
          "procesador. Aquí no gana el que va más rápido sino el "
          "que trae los datos antes, y por eso escala mucho peor con los "
          "hilos: el camino hasta la memoria es uno y se comparte.",
          lambda: zlib.crc32(_bloque_grande())),
)

# POR QUÉ NO LZMA. La compresión pesada fue `lzma.compress(MEDIO, preset=0)`
# hasta que se midió de qué venía la dispersión de la puntuación multihilo.
# LZMA alterna entre dos velocidades —25 800 y 32 500 operaciones por segundo
# en un 5800X3D, un 26 % de diferencia— según le llueva o no una tormenta de
# fallos de página: 280 000 por segundo contra ninguno, de los búferes que
# pide en cada llamada. El estado se decide por proceso, tarda entre cero y
# más de veinticinco segundos en asentarse, y a veces no se asienta; dentro de
# una misma medida es plano, así que alargarla no lo promedia, lo hereda. Con
# eso, la puntuación entera dispersaba un 4,7 % entre repeticiones del mismo
# equipo, y quitando esta carga, un 0,3 %: era ella sola.
#
# Se probó a domarla y no se pudo. Rodar más no basta porque a veces no se
# calma nunca. `mallopt` con el umbral de `mmap` fijo lo empeora —a 256 KB
# baja a 4 787 op/s— porque fijarlo apaga el ajuste dinámico de glibc, que es
# justo lo que llevaba al estado bueno. Bajar el diccionario lo hunde a un
# tercio y subirlo a 1 MB, a un octavo. Y no es el asignador y ya: con
# `preset=1` los fallos casi desaparecen y sigue dispersando un 18 %, o sea
# que LZMA tiene además otra fuente de inestabilidad que no se aisló.
#
# bzip2 no tiene ninguna de las dos: dispersa un 2,1 % en vez de un 20,6 % y
# reparte igual de bien (×9.9 con dieciséis hilos, contra ×10.9). Es más lenta
# en operaciones por segundo, y da igual: lo que se compara es contra el
# patrón, no contra otra carga.

# No hay carga de coma flotante, y no es un olvido. Todo lo que la haría en
# Python sin dependencias —sumar, multiplicar listas— tiene el bucle en C pero
# manejando objetos del intérprete, así que no suelta el GIL: medido aquí,
# escala ×1.0 con dieciséis hilos. Una prueba multihilo que no reparte no mide
# el procesador, mide el candado.


@dataclass(frozen=True, slots=True)
class Medida:
    """El resultado de una carga con un número de hilos."""

    load: str
    threads: int
    operations: int
    seconds: float

    @property
    def per_second(self) -> float:
        return self.operations / self.seconds if self.seconds else 0.0


@dataclass(frozen=True, slots=True)
class Conditions:
    """En qué estado estaba la máquina mientras se medía."""

    # Lo que ocupaba otro programa mientras se medía, no antes de empezar. Son
    # dos preguntas distintas y la segunda es la que importa: una prueba de
    # quince segundos por carga dura dos minutos y medio, y `background_load`
    # se tomaba en tres décimas antes del primer paso. Con eso, alguien que
    # abriera el navegador a mitad salía con «0 % de carga de fondo» y una
    # cifra baja sin explicación.
    background_peak: Optional[float] = None
    frequency_avg_hz: Optional[int] = None
    frequency_peak_hz: Optional[int] = None
    frequency_end_hz: Optional[int] = None
    temperature_start_c: Optional[float] = None
    temperature_peak_c: Optional[float] = None
    governor: Optional[str] = None
    energy_preference: Optional[str] = None
    background_load: Optional[float] = None

    @property
    def throttled(self) -> bool:
        """Si la frecuencia cayó de forma apreciable durante la prueba."""
        if not (self.frequency_peak_hz and self.frequency_end_hz):
            return False
        return self.frequency_end_hz < self.frequency_peak_hz * CAIDA_NOTABLE


@dataclass(frozen=True, slots=True)
class Result:
    """Las medidas y el contexto que dice si valen."""

    measures: tuple[Medida, ...] = ()
    conditions: Conditions = field(default_factory=Conditions)
    warnings: tuple[str, ...] = ()

    def find(self, load: str, threads: int) -> Optional[Medida]:
        return next((m for m in self.measures
                     if m.load == load and m.threads == threads), None)

    def scaling(self, load: str, threads: int) -> Optional[float]:
        """Cuánto multiplica el rendimiento al usar todos los hilos."""
        uno = self.find(load, 1)
        muchos = self.find(load, threads)
        if not (uno and muchos and uno.per_second):
            return None
        return round(muchos.per_second / uno.per_second, 1)


def run(quick: bool = False, on_progress: Optional[Callable[[str, float], None]] = None,
        stop: Optional[threading.Event] = None,
        seconds: Optional[float] = None) -> Result:
    """Ejecuta la prueba entera. Bloquea: llámese desde un hilo aparte.

    `on_progress` recibe qué se está midiendo y cuánto se lleva, de 0 a 1.
    `stop` permite cancelar entre medidas.
    `seconds` fija cuánto dura cada medida; sin él manda `quick`.

    Alargar la prueba no cambia la cifra, cambia en qué condiciones se toma:
    a los cinco segundos el turbo ya subió y el disipador aún no se ha
    calentado, mientras que a los treinta se mide con el equipo asentado, que
    es lo que de verdad va a pasar mientras se juega o se compila.
    """
    duracion = (max(MINIMO_SEGUNDOS, min(MAXIMO_SEGUNDOS, float(seconds)))
                if seconds else (SEGUNDOS_RAPIDO if quick else SEGUNDOS))
    hilos = os.cpu_count() or 1
    vigilante = _Vigilante()

    fondo = _carga_de_fondo()
    temperatura_inicial = _temperatura()

    pasos = [(carga, n) for carga in CARGAS for n in (1, hilos)]
    medidas: list[Medida] = []
    vigilante.empezar()
    try:
        for indice, (carga, n) in enumerate(pasos):
            if stop is not None and stop.is_set():
                break
            if on_progress:
                etiqueta = f"{carga.name}, {n} {'hilo' if n == 1 else 'hilos'}"
                on_progress(etiqueta, indice / len(pasos))
            medidas.append(_medir(carga, n, duracion))
    finally:
        vigilante.parar()
        _soltar_el_bloque()

    if on_progress:
        on_progress("listo", 1.0)

    condiciones = Conditions(
        frequency_avg_hz=vigilante.media(),
        frequency_peak_hz=vigilante.pico(),
        frequency_end_hz=vigilante.final(),
        temperature_start_c=temperatura_inicial,
        temperature_peak_c=vigilante.temperatura_pico(),
        governor=_leer(f"{SYS_CPU}/cpu0/cpufreq/scaling_governor"),
        energy_preference=_leer(f"{SYS_CPU}/cpu0/cpufreq/energy_performance_preference"),
        background_load=fondo,
        background_peak=vigilante.ajeno_pico(),
    )
    return Result(tuple(medidas), condiciones, _avisos(condiciones))


# -- ejecución ---------------------------------------------------------------

# Unas vueltas que no se cuentan, antes de cada medida. La primera vez que una
# carga corre en un proceso da una cifra distinta de todas las siguientes, y lo
# que se paga ahí no es del procesador sino del asignador, que sirve con `mmap`
# los búferes holgados hasta que glibc sube su umbral por su cuenta.
#
# Con la compresión pesada de entonces —LZMA— la diferencia era del 65 %:
# 1 780 operaciones por segundo la primera vez y 2 950 a partir de la segunda.
# Con bzip2 es del 2,7 % a un hilo (151,7 la primera y 156,0 después), porque
# no pide en cada llamada un búfer que cruce el umbral. Sigue mereciendo la
# pena: cuesta unas centésimas y quita un sesgo que caía siempre en la misma
# cifra, la de un hilo, por medirse antes que las demás.
#
# Con unas ochenta vueltas ya está en régimen; se dejan ciento veinte de
# margen. Lo que el rodaje no arregla es la inestabilidad de LZMA que la sacó
# de aquí: esa no se calma en ningún número de vueltas.
VUELTAS_EN_VACIO = 120

# Tope por si la carga es lentísima en un equipo modesto: más vale medir con
# el arranque a medio pagar que dejar la prueba colgada un minuto por carga.
TOPE_EN_VACIO_S = 2.0


def _rodar_en_vacio(carga: "Carga", hilos: int) -> None:
    """Deja la carga en régimen para que la medida no pague su arranque.

    Como el orden es un hilo primero y todos después, ese arranque lo pagaba
    siempre la medida de un hilo: la escala entre uno y todos salía en catorce
    veces con un procesador de ocho núcleos.
    """
    # Se cuentan vueltas y no segundos. Lo que hay que dejar atrás es el
    # arranque de la carga, que son unas ochenta llamadas, y eso no dura lo
    # mismo en un Ryzen que en un portátil de hace diez años: medio segundo
    # aquí son cientos de vueltas y allí puede que ninguna.
    fin = time.perf_counter() + TOPE_EN_VACIO_S

    def bucle() -> None:
        trabajo = carga.work
        for _vuelta in range(VUELTAS_EN_VACIO):
            if time.perf_counter() > fin:
                break
            trabajo()

    obreros = [threading.Thread(target=bucle, daemon=True)
               for _ in range(hilos)]
    for obrero in obreros:
        obrero.start()
    for obrero in obreros:
        obrero.join(timeout=TOPE_EN_VACIO_S + 5)


def _medir(carga: Carga, hilos: int, duracion: float) -> Medida:
    """Cuenta cuántas veces cabe la carga en el tiempo dado.

    Se mide por tiempo y no por trabajo fijo porque una cantidad que en un
    Ryzen tarda un segundo, en un portátil de hace diez años tarda treinta.
    """
    _rodar_en_vacio(carga, hilos)
    parar = threading.Event()
    cuenta = [0] * hilos

    def bucle(indice: int) -> None:
        vueltas = 0
        trabajo = carga.work
        while not parar.is_set():
            trabajo()
            vueltas += 1
        cuenta[indice] = vueltas

    obreros = [threading.Thread(target=bucle, args=(i,), daemon=True)
               for i in range(hilos)]
    inicio = time.perf_counter()
    for obrero in obreros:
        obrero.start()
    time.sleep(duracion)
    parar.set()
    for obrero in obreros:
        obrero.join(timeout=10)
    transcurrido = time.perf_counter() - inicio

    return Medida(load=carga.key, threads=hilos,
                  operations=sum(cuenta), seconds=transcurrido)


# Aquí vivían `_fijar_afinidad` y `_nucleo_preferido`, que ataban el hilo de
# la medida de un núcleo al que el firmware señala como mejor. La idea era
# quitar ruido —un hilo que salta de núcleo tira la caché— y hacía justo lo
# contrario: medida contra medida, atarlo cuesta un 40 % en la compresión
# pesada y un 11 % en la derivación de clave, y la dispersión entre
# repeticiones sale igual o peor que dejándolo suelto.
#
# Y como la afinidad solo se fijaba al medir con un hilo, esa penalización
# caía siempre en la misma cifra. La prueba entera daba 1 771 operaciones por
# segundo a un hilo y 24 842 a dieciséis: una escala de catorce veces en un
# procesador de ocho núcleos, que no es posible. Sin atar nada sale 3 004 y
# 24 099, ocho veces, que es lo que dan las otras cuatro cargas.
#
# Si algún día vuelve a hacer falta, que sea con una medición delante: la
# dispersión sin atar, en este equipo y con el gobernador en «performance»,
# fue del 1,3 % al 3,3 % según la carga.


# -- contexto ----------------------------------------------------------------

class _Vigilante:
    """Sigue la frecuencia y la temperatura mientras se mide."""

    def __init__(self) -> None:
        self._frecuencias: list[int] = []
        self._temperaturas: list[float] = []
        self._ajeno: list[float] = []
        self._cpu_antes = _jiffies()
        self._parar = threading.Event()
        self._hilo: Optional[threading.Thread] = None

    def empezar(self) -> None:
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()

    def parar(self) -> None:
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=2)

    def _bucle(self) -> None:
        while not self._parar.is_set():
            # Solo cuenta la frecuencia más alta del momento: la media de todos
            # los núcleos, con la mitad dormidos, no dice a qué fue el trabajo.
            picos = [_entero(f"{SYS_CPU}/cpu{i}/cpufreq/scaling_cur_freq")
                     for i in range(os.cpu_count() or 1)]
            validos = [p for p in picos if p]
            if validos:
                self._frecuencias.append(max(validos) * 1000)
            if (grados := _temperatura()) is not None:
                self._temperaturas.append(grados)
            if (robado := self._cuanto_roban()) is not None:
                self._ajeno.append(robado)
            self._parar.wait(0.25)

    def _cuanto_roban(self) -> Optional[float]:
        """Qué parte de la máquina se lleva otro programa, ahora mismo.

        No vale mirar `/proc/stat` a secas mientras la prueba corre: la prueba
        ocupa el equipo entero y todo saldría al cien por cien. Lo que se busca
        es la resta, lo ocupado menos lo que consume este mismo proceso, que es
        justo lo que le está quitando sitio a la medida.
        """
        ahora = _jiffies()
        anterior, self._cpu_antes = self._cpu_antes, ahora
        if ahora is None or anterior is None:
            return None
        total, inactivo, propio = ahora
        total_antes, inactivo_antes, propio_antes = anterior
        transcurrido = total - total_antes
        if transcurrido <= 0:
            return None
        ocupado = transcurrido - (inactivo - inactivo_antes)
        ajeno = ocupado - (propio - propio_antes)
        # Puede salir negativo por unas centésimas: los dos ficheros no se leen
        # en el mismo instante. Cero es la respuesta, no un error.
        return max(0.0, ajeno / transcurrido * 100)

    def media(self) -> Optional[int]:
        return int(sum(self._frecuencias) / len(self._frecuencias)) if self._frecuencias else None

    def pico(self) -> Optional[int]:
        return max(self._frecuencias) if self._frecuencias else None

    def final(self) -> Optional[int]:
        """La media del último tramo, para ver si acabó más baja que empezó."""
        if len(self._frecuencias) < 8:
            return self._frecuencias[-1] if self._frecuencias else None
        cola = self._frecuencias[-len(self._frecuencias) // 4:]
        return int(sum(cola) / len(cola))

    def temperatura_pico(self) -> Optional[float]:
        return max(self._temperaturas) if self._temperaturas else None

    def ajeno_pico(self) -> Optional[float]:
        """Lo más que llegó a robarle otro programa durante la prueba.

        El pico y no la media: lo que estropea una medida es que algo se
        despierte a mitad, y promediado entre dos minutos y medio eso se diluye
        hasta parecer nada.
        """
        return round(max(self._ajeno), 1) if self._ajeno else None


def _avisos(condiciones: Conditions) -> tuple[str, ...]:
    """Lo que hay que saber antes de comparar esta cifra con otra."""
    avisos = []
    if condiciones.background_load and condiciones.background_load > CARGA_ACEPTABLE:
        avisos.append(
            f"Había un {condiciones.background_load:.0f} % de carga de fondo al "
            "empezar. El resultado no es comparable con el de una máquina en "
            "reposo."
        )
    # Lo de arriba mira cómo estaba el equipo antes de empezar; esto, lo que
    # pasó mientras se medía. Son preguntas distintas y la segunda es la que
    # estropea una prueba: quien la lanza y se va a hacer otra cosa, o quien
    # tiene una actualización en marcha sin saberlo, salía con «0 % de carga de
    # fondo» y una cifra baja que no tenía explicación en ninguna parte.
    if (condiciones.background_peak
            and condiciones.background_peak > CARGA_ACEPTABLE):
        avisos.append(
            f"Otro programa llegó a llevarse el "
            f"{condiciones.background_peak:.0f} % de la máquina mientras se "
            "medía. La cifra sale más baja de lo que da este equipo en reposo."
        )
    if condiciones.governor and condiciones.governor not in ("performance",):
        avisos.append(
            f"El gobernador de energía estaba en «{condiciones.governor}». "
            "En «performance» la cifra sería más alta."
        )
    if condiciones.throttled:
        pico = condiciones.frequency_peak_hz or 0
        final = condiciones.frequency_end_hz or 0
        avisos.append(
            f"La frecuencia bajó de {pico / 1e9:.2f} a {final / 1e9:.2f} GHz "
            "durante la prueba: el procesador no pudo sostener su máximo."
        )
    return tuple(avisos)


def _jiffies() -> Optional[tuple[int, int, int]]:
    """Del sistema: totales e inactivos; y lo que lleva gastado este proceso.

    Los tres a la vez y del mismo instante, porque lo que se busca es la resta
    entre ellos.
    """
    try:
        with open("/proc/stat", encoding="utf-8") as fichero:
            numeros = [int(x) for x in fichero.readline().split()[1:8]]
        with open(f"/proc/{os.getpid()}/stat", encoding="utf-8") as fichero:
            campos = fichero.read().rsplit(")", 1)[1].split()
        # utime + stime, que es lo que este proceso ha consumido de CPU.
        propio = int(campos[11]) + int(campos[12])
    except (OSError, ValueError, IndexError):
        return None
    if len(numeros) < 5:
        return None
    return sum(numeros), numeros[3] + numeros[4], propio


def _carga_de_fondo() -> Optional[float]:
    """Qué porcentaje de la máquina está ocupado antes de empezar."""
    def instantanea() -> Optional[tuple[int, int]]:
        try:
            with open("/proc/stat", encoding="utf-8") as fichero:
                campos = fichero.readline().split()
        except OSError:
            return None
        if len(campos) < 5:
            return None
        numeros = [int(c) for c in campos[1:8] if c.isdigit()]
        return sum(numeros), numeros[3]        # total, inactivo

    antes = instantanea()
    if antes is None:
        return None
    time.sleep(0.3)
    despues = instantanea()
    if despues is None or despues[0] == antes[0]:
        return None
    ocupado = (despues[0] - antes[0]) - (despues[1] - antes[1])
    return round(ocupado / (despues[0] - antes[0]) * 100, 1)


def _temperatura() -> Optional[float]:
    """La del procesador, del primer chip que la publique."""
    for indice in range(16):
        nombre = _leer(f"/sys/class/hwmon/hwmon{indice}/name")
        if nombre in ("k10temp", "coretemp", "zenpower", "cpu_thermal"):
            milesimas = _entero(f"/sys/class/hwmon/hwmon{indice}/temp1_input")
            if milesimas:
                return round(milesimas / 1000, 1)
    return None


def _leer(ruta: str) -> Optional[str]:
    try:
        return pathlib.Path(ruta).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _entero(ruta: str) -> Optional[int]:
    crudo = _leer(ruta)
    try:
        return int(crudo) if crudo else None
    except ValueError:
        return None
