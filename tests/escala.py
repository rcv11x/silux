"""La escala del benchmark, para los tests que la necesitan.

Cuando `score.referencias()` sale vacía, estos tests no tienen nada que
evaluar, y antes se saltaban. Con eso, subir `score.VERSION` sin regenerar
`db/scores.json` dejaba la suite en verde con diez tests sin ejecutar: ya pasó
con la v5, y un test que vigilaba que una prueba incompleta no puntúa pasaba
porque no puntuaba ninguna. Una escala que no carga es un fallo, no un motivo
para saltar.
"""

NO_CARGA = ("score.referencias() está vacía: score.VERSION no coincide con la "
            "version_formula de silux/db/scores.json, o el archivo falta. Los "
            "dos van en el mismo commit; desparejados no puntúa nada.")


def tabla_de_la_escala(caso) -> dict:
    """La tabla vigente, o el test falla diciendo por qué no la hay."""
    from silux import score

    tabla = score.references()
    if not tabla:
        caso.fail(NO_CARGA)
    return tabla
