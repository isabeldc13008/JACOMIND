# Ficha de operaciones A02

`pipeline.operaciones` consume las tablas del paquete sintético o la carpeta `01_Datos` publicada por A01 y mantiene ventas y compras como hechos separados.

```python
from datetime import date
from pathlib import Path
from pipeline.operaciones import calcular_cierre

resultado = calcular_cierre(Path("C:/ruta/Green_Services_Recursos_de_Prueba"), date(2026, 10, 31))
print(resultado.sales.total_cop)
```

Las operaciones anuladas no suman ingreso ni conteo confirmado. Las ventas USD requieren TRM de la fecha; una tasa ausente se registra en `missing_rates`. Los importes se calculan por operación y se redondean a dos decimales antes de agregar para reproducir la referencia publicada del paquete. La representación monetaria final permanece en `Decimal`.

Las ventas y compras exponen operaciones originales, conteos, total COP y agregados por mes, familia, moneda y proveedor. Las compras no se combinan con ventas. Las anomalías comparan cada valor con la historia previa de su familia y moneda mediante mediana y MAD; con historia insuficiente no alertan.
