# Segmentación A05

La segmentación usa RFM interpretable: recencia, frecuencia e importe monetario. Las variables se escalan en cada población de ajuste; el ID nunca entra como señal. Clientes sin historial quedan explícitamente en `sin_historial` y no se fuerzan a un cluster.

La implementación usa centroides deterministas con semilla implícita por orden estable de cliente y devuelve versión, segmento y centroide para que Ventas pueda revisar perfiles sin perder correspondencia entre cierres.
