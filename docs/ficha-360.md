# Ficha 360 A03

`pipeline.ficha` genera una fila por cliente y cierre, preservando clientes sin ventas y manteniendo coberturas en una colección separada para no multiplicar importes.

Incluye recencia, frecuencia, valor monetario COP, primera/última compra, intervalos entre días distintos, productos históricos, etiquetas `frecuente`, `frio`, `nuevo` y `sin_compras`, además de coberturas vigentes, próximas y vencidas.

Una cobertura próxima se cuenta también como vigente cuando su fecha fin aún no llegó. La frontera de frío es inclusiva: 90 días sin compra marca `frio`. La frecuencia cuenta operaciones confirmadas; anuladas y compras a proveedores no alteran la ficha de clientes.
