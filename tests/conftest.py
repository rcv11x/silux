"""Lo que solo lee pytest. La suite es de `unittest` y corre igual sin esto.

Marca los tests que comparan dos medidas de rendimiento. Con la suite
repartida entre todos los hilos del equipo, lo que miden es cuánto les dejan
los demás procesos: el del tamaño del bloque, que compara el ancho de banda
con 64 y con 192 MB, falló siete veces de ocho con dieciséis procesos (5,7
contra 11,2 GB/s). No es un test que falle a ratos: es un test que necesita
el equipo para él. Se pasan aparte, cuando lo demás ha terminado:

    pytest -n auto -m "not a_solas"
    pytest -m a_solas

Van aquí por nombre, y no con un decorador en cada uno, para que los
archivos de tests no tengan que importar pytest: en el Python del suelo se
ejecutan con `unittest` y sin él.

Also puts back, before every class and every test, the font, the theme and
the language a test starts with (`tests/qt.py`): with pytest the order can't hand one test
the font of another. Under `unittest` they're set once, when Qt starts.
"""

import pytest

A_SOLAS = (
    "tests/test_benchmark.py::TestCargaDeVerificacion::"
    "test_el_tamano_del_bloque_no_cambia_lo_que_se_puntua",
    "tests/test_benchmark.py::TestCargasNuevas::test_todas_reparten_de_verdad_entre_hilos",
    "tests/test_benchmark.py::TestEjecucion::"
    "test_la_medida_de_un_hilo_no_paga_el_arranque_de_la_carga",
)


@pytest.fixture(autouse=True, scope="class")
def _default_theme_for_each_class():
    # Before the class's own setUpClass, which may apply another and keeps
    # it for all its tests.
    from silux import i18n
    from tests import qt

    qt.reset_theme()
    # And in Spanish, the original: a class that switched to English left
    # the next ones in another process reading English texts.
    if i18n.current() != "es":
        i18n.set_language("es")
    yield


@pytest.fixture(autouse=True)
def _suite_font_for_each_test():
    from tests import qt

    qt.reset_font()
    yield


def pytest_collection_modifyitems(config, items):
    vistos = set()
    for item in items:
        if item.nodeid in A_SOLAS:
            item.add_marker(pytest.mark.a_solas)
            vistos.add(item.nodeid)
    # Un test que cambia de nombre dejaría de pasar aparte sin que nadie lo
    # notara. Solo se exige con la suite entera: quien lanza un archivo
    # suelto no los ha recogido todos.
    recogidos = {item.nodeid.split("::")[0] for item in items}
    faltan = [n for n in A_SOLAS if n not in vistos and n.split("::")[0] in recogidos]
    if faltan and not config.getoption("keyword") and len(recogidos) > 1:
        raise pytest.UsageError(
            "tests/conftest.py nombra tests que ya no existen: " + ", ".join(faltan))
