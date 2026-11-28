"""Estado público de los modelos M1 a M6: todos están en uso (funcionales).

Las publicaciones de M2 a M6 conservan su formato técnico (tablas ``sombra_*``, manifiestos sellados y contrato), pero la
aplicación, la API y el asistente las presentan como modelos en uso. Sus resultados siguen siendo estimaciones,
proyecciones o alertas para apoyar decisiones de personas, no hechos confirmados.
"""

import re

EN_USO = "En uso"


def estado_resumen(estado: str | None) -> str | None:
    """Normaliza el estado de un modelo del resumen de resultados: «experimental (sombra)» pasa a «operativo»."""
    if not estado:
        return estado
    return re.sub(r"^\s*experimental(?:\s*\(sombra\)|\s+en\s+sombra)?", "operativo", estado, flags=re.I)

