# Modelo de compra A04

El modelo construye fotografías mensuales por cliente elegible, usando únicamente ventas confirmadas conocidas al corte. La etiqueta es una compra posterior dentro de los 30 días siguientes; los cortes sin horizonte observable no se usan para entrenar.

Variables: `recencia_dias`, `frecuencia_30d`, `frecuencia_90d` e `historial_n`. El escalado, pesos y umbral se ajustan en marzo de 2025–abril de 2026, se seleccionan en mayo–junio y se evalúan en julio–septiembre. La regla de comparación es `frecuencia_30d > 0`.

En el paquete sintético, la prueba reproduce TP=120, TN=51, FP=177 y FN=12 con umbral 0,4. Es una prueba temporal sobre la cartera sintética y no evidencia rendimiento en clientes empresariales.
