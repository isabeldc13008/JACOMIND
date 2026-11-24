"""Experimentación, artefactos e inferencia de modelos de JACOMIND.

Los módulos ``datos``, ``variables``, ``inferencia``, ``metricas`` y ``registro``
usan solo la biblioteca estándar y los consume el cierre mensual. ``compra`` y
``cli`` entrenan; importan scikit-learn únicamente dentro de la operación de
ajuste (``requirements-modelos.txt``).
"""
