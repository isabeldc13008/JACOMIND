"""Revisión de datos aceptada por A01, cobertura declarada e historial de compras (B0-01).

Entrenamiento, evaluación, puntuación y cierre leen la misma revisión publicada por
``pipeline.carga.cargar_lote``: ``<a01>/publicado``. Un lote ``fallido`` nunca se usa;
un lote ``pendiente_revision`` solo se usa con aceptación parcial explícita y, en ese
caso, se leen las filas aceptadas de ``<a01>/lote_actual`` y se registran las exclusiones.
Nunca se vuelve a leer el archivo original del paquete.

Cobertura temporal: la última venta no prueba que la ingestión esté completa. El límite
``datos_observados_hasta`` se toma, por orden, de un argumento explícito, del manifiesto
A01 (``datos_observados_hasta.ventas``) o de una declaración registrada en
``config/coberturas_declaradas.json`` cuyas huellas de origen coincidan todas con el lote. Si
nada aplica, la cobertura es desconocida y no se puntúa (``resolver_cobertura`` y
``verificar_cobertura_corte`` son la política única de CLI, comparación y cierre). En el
paquete sintético se usa la convención documentada de disponibilidad por fecha del evento.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

ESTADOS_ACEPTADOS = {"publicable", "reutilizado"}


class LoteNoAceptado(RuntimeError):
    """El lote no está aceptado por A01 o no declara su cobertura."""


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()


def preparar_lote(paquete: str | Path, salida: str | Path, configuracion: str | Path | None = None):
    """Ejecuta A01 sobre el paquete original y deja la revisión normalizada en ``salida``."""
    from pipeline.carga import cargar_lote

    return cargar_lote(Path(paquete), Path(salida), Path(configuracion) if configuracion else None)


def resolver_lote(ruta: str | Path, *, aceptar_parcial: bool = False) -> tuple[Path, dict[str, Any]]:
    """Devuelve (directorio de tablas aceptadas, manifiesto A01) o lanza ``LoteNoAceptado``."""
    ruta = Path(ruta)
    if (ruta / "manifiesto.json").is_file():
        base = ruta
    elif ruta.name in ("publicado", "lote_actual") and (ruta.parent / "manifiesto.json").is_file():
        base = ruta.parent
    elif (ruta / "01_Datos").is_dir() or (ruta / "clientes.csv").is_file():
        raise LoteNoAceptado(f"{ruta} es un paquete original sin revisión A01. Ejecuta primero "
                             "'python -m modelos.cli preparar --datos <paquete> --salida salida/a01'.")
    else:
        raise LoteNoAceptado(f"No hay manifiesto A01 en {ruta}")
    manifiesto = json.loads((base / "manifiesto.json").read_text(encoding="utf-8"))
    estado = manifiesto.get("status")
    if estado in ESTADOS_ACEPTADOS:
        tablas = base / "publicado"
        if not tablas.is_dir():
            raise LoteNoAceptado(f"El manifiesto A01 indica '{estado}' pero falta {tablas}")
        return tablas, manifiesto
    if estado == "pendiente_revision":
        if not aceptar_parcial:
            raise LoteNoAceptado(f"A01 dejó el lote en 'pendiente_revision' (revisión {manifiesto.get('revision')}); "
                                 "no sustituye al último válido. Usa la aceptación parcial explícita para continuar.")
        tablas = base / "lote_actual"
        if not tablas.is_dir():
            raise LoteNoAceptado(f"Falta {tablas} con las filas aceptadas")
        return tablas, manifiesto
    raise LoteNoAceptado(f"A01 rechazó el lote (estado '{estado}'); no se usa.")


@dataclass
class DatosAceptados:
    directorio: Path
    revision: int | None
    estado_lote: str
    aceptacion_parcial: bool
    huellas: dict[str, str]
    huella_datos: str
    huellas_origen: dict[str, str]
    exclusiones: dict[str, dict[str, int]]
    observado_hasta: date | None
    fuente_cobertura: str
    convencion_disponibilidad: str
    clientes: list[dict[str, Any]] = field(default_factory=list, repr=False)
    ventas: list[dict[str, Any]] = field(default_factory=list, repr=False)
    productos: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)
    tasas: dict[date, Decimal] = field(default_factory=dict, repr=False)

    @property
    def cobertura(self) -> "Cobertura":
        return Cobertura(self.observado_hasta, self.fuente_cobertura, self.convencion_disponibilidad)

    def descripcion(self) -> dict[str, Any]:
        """Metadatos auditables (sin filas) para ``datos.json`` y artefactos."""
        return {"directorio": str(self.directorio), "revision": self.revision, "estado_lote": self.estado_lote,
                "aceptacion_parcial": self.aceptacion_parcial, "huella_datos": self.huella_datos,
                "huellas_publicadas": self.huellas, "huellas_origen": self.huellas_origen,
                "exclusiones_a01": self.exclusiones, "datos_observados_hasta": self.observado_hasta.isoformat() if self.observado_hasta else None,
                "fuente_cobertura": self.fuente_cobertura, "convencion_disponibilidad": self.convencion_disponibilidad,
                "conteos": {"clientes": len(self.clientes), "ventas": len(self.ventas),
                            "ventas_confirmadas": sum(1 for v in self.ventas if v.get("estado") == "Confirmada"),
                            "productos": len(self.productos)}}


class CoberturaInsuficiente(LoteNoAceptado):
    """La cobertura declarada no alcanza el corte pedido o no está declarada."""


COBERTURAS_DECLARADAS = Path(__file__).resolve().parent / "config" / "coberturas_declaradas.json"


@dataclass(frozen=True)
class Cobertura:
    """Límite de datos completos (``None`` = desconocido) y su procedencia verificable."""
    observado_hasta: date | None
    fuente: str
    convencion_disponibilidad: str = "fecha_evento"

    @property
    def conocida(self) -> bool:
        return self.observado_hasta is not None

    def como_dict(self) -> dict[str, Any]:
        return {"datos_observados_hasta": self.observado_hasta.isoformat() if self.observado_hasta else None,
                "fuente": self.fuente, "convencion_disponibilidad": self.convencion_disponibilidad,
                "estado": "declarada" if self.conocida else "desconocida"}


def _fecha(valor: str | date) -> date:
    return valor if isinstance(valor, date) else date.fromisoformat(str(valor))


def resolver_cobertura(manifiesto: dict[str, Any], *, explicito: str | date | None = None,
                       declaraciones: str | Path | None = None) -> Cobertura:
    """Política única de cobertura para CLI, cierre y comparación.

    Orden: argumento explícito; ``datos_observados_hasta.ventas`` del manifiesto A01; declaración
    registrada en ``coberturas_declaradas.json`` cuyas huellas de origen coincidan TODAS con las
    del lote. Si nada aplica, la cobertura es desconocida: nunca se deduce de la última venta ni
    se hereda la fecha del paquete sintético en un lote distinto.
    """
    if explicito is not None:
        return Cobertura(_fecha(explicito), "argumento explícito (--observado-hasta)")
    declarada = (manifiesto.get("datos_observados_hasta") or {}).get("ventas")
    if declarada:
        return Cobertura(_fecha(declarada), f"manifiesto A01 revisión {manifiesto.get('revision')} (datos_observados_hasta.ventas)")
    origen = manifiesto.get("source_hashes") or {}
    ruta = Path(declaraciones or COBERTURAS_DECLARADAS)
    if origen and ruta.is_file():
        for lote in json.loads(ruta.read_text(encoding="utf-8")).get("lotes", []):
            if lote.get("huellas_origen") == origen and (lote.get("datos_observados_hasta") or {}).get("ventas"):
                return Cobertura(_fecha(lote["datos_observados_hasta"]["ventas"]),
                                 f"declaración registrada «{lote.get('nombre')}» ({ruta.name}; huellas de origen idénticas): {lote.get('fuente')}",
                                 lote.get("convencion_disponibilidad", "fecha_evento"))
    return Cobertura(None, "no declarada: el manifiesto A01 no trae datos_observados_hasta y el lote no coincide con ninguna declaración registrada")


def verificar_cobertura_corte(corte: date, cobertura: Cobertura) -> None:
    """Puntuar un corte exige datos completos hasta el corte (no los 30 días futuros, que solo evalúan)."""
    if not cobertura.conocida:
        raise CoberturaInsuficiente(
            f"No se puede puntuar ni publicar el corte {corte}: la cobertura temporal del lote es desconocida ({cobertura.fuente}). "
            "Declara datos_observados_hasta en la configuración de la carga A01 (y vuelve a cargar el lote) o indica "
            "--observado-hasta AAAA-MM-DD si consta que los datos están completos hasta esa fecha.")
    if corte > cobertura.observado_hasta:
        raise CoberturaInsuficiente(
            f"No se puede puntuar ni publicar el corte {corte}: los datos solo están completos hasta {cobertura.observado_hasta} "
            f"({cobertura.fuente}). Carga un lote que cubra hasta {corte} o usa un corte no posterior a {cobertura.observado_hasta}.")


def verificar_coherencia(ventas: list[dict[str, Any]], cobertura: Cobertura) -> None:
    """Una venta posterior a la cobertura declarada contradice la declaración."""
    if not cobertura.conocida:
        return
    tardias = [v for v in ventas if v["fecha"] > cobertura.observado_hasta]
    if tardias:
        raise LoteNoAceptado(f"{len(tardias)} ventas son posteriores a la cobertura declarada {cobertura.observado_hasta} "
                             f"({cobertura.fuente}); la declaración no es coherente con el lote. Corrige datos_observados_hasta.")


def cargar_datos(ruta: str | Path, *, aceptar_parcial: bool = False, observado_hasta: str | date | None = None,
                 cobertura_config: dict[str, Any] | None = None, exigir_cobertura: bool = True) -> DatosAceptados:
    """Carga clientes, ventas, productos y TRM de la revisión aceptada y fija la cobertura.

    ``cobertura_config`` (la sección ``cobertura`` de la configuración del modelo) ya no se usa como
    valor por defecto: se conserva el parámetro por compatibilidad. La cobertura sale de
    ``resolver_cobertura``.
    """
    from pipeline.operaciones import _load, _rates

    tablas, manifiesto = resolver_lote(ruta, aceptar_parcial=aceptar_parcial)
    cobertura = resolver_cobertura(manifiesto, explicito=observado_hasta)
    if exigir_cobertura and not cobertura.conocida:
        raise CoberturaInsuficiente(f"La cobertura temporal del lote es desconocida ({cobertura.fuente}); la última transacción no "
                                    "basta para suponerla completa. Declárala en el manifiesto A01 o con --observado-hasta.")
    huellas = {p.name: _sha(p) for p in sorted(tablas.glob("*.csv"))}
    huella = hashlib.sha256(json.dumps(huellas, sort_keys=True).encode()).hexdigest()
    exclusiones = {t: {"aisladas": int(v.get("isolated", 0)), "duplicadas": int(v.get("duplicates", 0))}
                   for t, v in (manifiesto.get("tablas") or {}).items()}
    datos = DatosAceptados(
        directorio=tablas, revision=manifiesto.get("revision"), estado_lote=manifiesto.get("status"),
        aceptacion_parcial=tablas.name == "lote_actual", huellas=huellas, huella_datos=huella,
        huellas_origen=manifiesto.get("source_hashes") or {}, exclusiones=exclusiones, observado_hasta=cobertura.observado_hasta,
        fuente_cobertura=cobertura.fuente, convencion_disponibilidad=cobertura.convencion_disponibilidad)
    datos.clientes = _load(tablas, "clientes.csv", "clientes")
    datos.ventas = _load(tablas, "ventas.csv", "ventas")
    datos.productos = {str(p["producto_id"]): p for p in _load(tablas, "productos.csv", "productos")}
    datos.tasas = _rates(tablas)
    verificar_coherencia(datos.ventas, cobertura)
    return datos
