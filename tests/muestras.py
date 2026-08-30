"""Un equipo de mentira, para los tests que necesitan encontrar algo.

Muchas pruebas de la interfaz montaban sus widgets con
`Collector().sample()`, o sea con el hardware de quien las ejecuta. En la
máquina del autor eso son noventa y nueve sensores con nombres largos y
siempre hay material; en un equipo sin `hwmon` el árbol sale vacío y entonces
fallan cosas que no tienen nada que ver con lo que se quería probar:

- filtrar por «temperatura» no encuentra nada, y el test lo llama fallo cuando
  el filtro ha acertado;
- las columnas no se reparten igual, porque sin nombres largos que medir sobra
  sitio y la curva se lo queda.

Las dos cosas pasaban en la acción de GitHub y aquí solo de vez en cuando,
según lo que publicara el equipo en ese momento, que es como se persigue un
fantasma durante una tarde.

Los tests que solo comparan el árbol consigo mismo pueden seguir leyendo la
máquina: no dependen de que haya nada. Los que exigen un resultado concreto
usan esto.
"""

from silux.model import Sensor, SensorKind

# Nombres largos a propósito: la columna de nombres tiene que medir algo
# parecido a lo que mide en un equipo de verdad, porque hay tests que
# comprueban cómo se reparte lo que sobra a partir de ella.
SENSORES = {
    "AMD Ryzen 7 5800X3D": {
        "cat.temperature": (
            Sensor(key="k10temp/1", chip="k10temp", device="AMD Ryzen 7 5800X3D",
                   label="Tctl", kind=SensorKind.TEMPERATURE, value=45.5),
            Sensor(key="k10temp/2", chip="k10temp", device="AMD Ryzen 7 5800X3D",
                   label="Tccd1", kind=SensorKind.TEMPERATURE, value=43.0),
        ),
        "cat.clock": (
            Sensor(key="cpufreq/0", chip="cpufreq", device="AMD Ryzen 7 5800X3D",
                   label="Núcleo 0", kind=SensorKind.CLOCK, value=4450.0),
            Sensor(key="cpufreq/1", chip="cpufreq", device="AMD Ryzen 7 5800X3D",
                   label="Núcleo 1", kind=SensorKind.CLOCK, value=3559.8),
        ),
        "cat.power": (
            Sensor(key="rapl/pkg", chip="rapl", device="AMD Ryzen 7 5800X3D",
                   label="Paquete", kind=SensorKind.POWER, value=53.3),
        ),
    },
    "Gigabyte X570 AORUS ELITE": {
        "cat.voltage": (
            Sensor(key="nct/in0", chip="nct6798", device="Gigabyte X570 AORUS ELITE",
                   label="Tensión del núcleo", kind=SensorKind.VOLTAGE, value=0.845),
        ),
        "cat.fan": (
            Sensor(key="nct/fan1", chip="nct6798", device="Gigabyte X570 AORUS ELITE",
                   label="Ventilador de caja", kind=SensorKind.FAN, value=912.0),
        ),
    },
}


def arbol_de_sensores() -> dict:
    """Lo que devolvería `Snapshot.sensor_tree()` en un equipo con sensores."""
    return {aparato: dict(categorias) for aparato, categorias in SENSORES.items()}


def cuantos_sensores() -> int:
    return sum(len(s) for cat in SENSORES.values() for s in cat.values())
