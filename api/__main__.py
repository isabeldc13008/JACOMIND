"""Línea de comandos de B.

    python -m api demo                      # migra y carga datos ficticios de demostración
    python -m api servir [--practica]       # API + app en http://127.0.0.1:8000/app/
    python -m api publicar RUTA             # directorio C2 o agenda.json C1
    python -m api cierre --corte 2026-10-31 --datos ../Green_Services_Recursos_de_Prueba
    python -m api sombra RUTA               # importa una publicación EN SOMBRA (inactividad o próxima compra; sin agenda)
    python -m api monitoreo recalcular      # salud, distribución y revisión de lo ya publicado (idempotente)
    python -m api monitoreo resultados --datos salida/a01   # desempeño con resultados maduros (M1–M5) y avisos
    python -m api monitoreo estado          # estado por modelo (sin información, pendiente, no comparable, ...)
    python -m api respaldo [--salida F]     # copia consistente + manifiesto
    python -m api restaurar RESPALDO --db DESTINO
    python -m api exportar-eventos [--salida F]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .config import cargar_env


def main(argv=None) -> int:
    cargar_env()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from .base import DIR_VAR, BaseDatos, ErrorApi, RAIZ

    p = argparse.ArgumentParser(prog="python -m api", description="JACOMIND · aplicación y operación")
    p.add_argument("--db", default=os.environ.get("JACOMIND_DB", str(DIR_VAR / "jacomind.sqlite3")))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrar")
    d = sub.add_parser("demo"); d.add_argument("--sin-cierre", action="store_true")
    s = sub.add_parser("servir")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--puerto", type=int, default=8000)
    s.add_argument("--practica", action="store_true", help="expone /salida/agenda.json para el modo práctica local")
    s.add_argument("--sin-login-demo", action="store_true", help="desactiva el inicio de sesión con identidades ficticias")
    pb = sub.add_parser("publicar"); pb.add_argument("ruta"); pb.add_argument("--actor", default="ops1")
    sb = sub.add_parser("sombra", help="importa una publicación en sombra de inactividad_60d (no cambia la agenda)")
    sb.add_argument("ruta"); sb.add_argument("--actor", default="ops1")
    mo = sub.add_parser("monitoreo", help="monitoreo de modelos: recalcular observaciones, incorporar resultados maduros o ver el estado")
    mo.add_argument("accion", choices=["recalcular", "resultados", "estado"])
    mo.add_argument("--datos", default=None, help="resultados: revisión A01 aceptada (con su cobertura declarada)")
    mo.add_argument("--modelo", default=None, help="limitar a un modelo")
    mo.add_argument("--observado-hasta", default=None, help="resultados: cobertura explícita (AAAA-MM-DD) si el lote no la declara")
    c = sub.add_parser("cierre")
    c.add_argument("--corte", required=True); c.add_argument("--datos"); c.add_argument("--desde")
    c.add_argument("--reintentos", type=int, default=2); c.add_argument("--actor", default="programador")
    r = sub.add_parser("respaldo"); r.add_argument("--salida")
    rs = sub.add_parser("restaurar"); rs.add_argument("respaldo"); rs.add_argument("--destino", required=True)
    e = sub.add_parser("exportar-eventos"); e.add_argument("--salida")
    g = sub.add_parser("generar-desde-a", help="construye C2/C1 con las funciones de pipeline/ (carril A)")
    g.add_argument("--datos", required=True); g.add_argument("--corte", required=True); g.add_argument("--salida", required=True)
    a = p.parse_args(argv)

    db = BaseDatos(a.db)
    imprimir = lambda x: print(json.dumps(x, ensure_ascii=False, indent=2, default=str))  # noqa: E731
    try:
        if a.cmd == "migrar":
            from .demo import solo_permisos
            solo_permisos(db); imprimir({"esquema": db.version_esquema()})
        elif a.cmd == "demo":
            from .demo import preparar
            imprimir(preparar(db, publicar_muestra=not a.sin_cierre))
        elif a.cmd == "servir":
            from .demo import solo_permisos
            from .servidor import Aplicacion, crear_servidor
            solo_permisos(db)
            srv = crear_servidor(Aplicacion(db, practica=a.practica, login_demo=not a.sin_login_demo), a.host, a.puerto)
            print(f"JACOMIND en http://{a.host}:{a.puerto}/app/  (base: {a.db}; Ctrl+C para salir)")
            try:
                srv.serve_forever()
            except KeyboardInterrupt:
                pass
        elif a.cmd == "publicar":
            from .demo import solo_permisos
            from .publicacion import publicar_ruta
            solo_permisos(db); imprimir(publicar_ruta(db, a.ruta, a.actor))
        elif a.cmd == "monitoreo":
            from .demo import solo_permisos
            from . import monitoreo as MON
            from . import monitoreo_modelos as MM
            solo_permisos(db); db.migrar()
            if a.accion == "recalcular":
                imprimir(MM.recalcular(db))
            elif a.accion == "resultados":
                if not a.datos:
                    raise SystemExit("monitoreo resultados necesita --datos (revisión A01 aceptada)")
                from modelos.datos import cargar_datos
                imprimir(MM.resultados(db, cargar_datos(a.datos, observado_hasta=a.observado_hasta), a.modelo))
            else:
                with db.conexion() as con:
                    filas = {m: [dict(r) for r in con.execute("SELECT * FROM monitoreo_observaciones WHERE modelo_id = ?", (m,))] for m in MON.MODELOS}
                    imprimir({m: {"estado": MON.estado_modelo(o, MON.avisos(con, m)), "observaciones": len(o),
                                  "avisos_activos": sum(1 for x in MON.avisos(con, m) if x.get("estado") != "resuelto")}
                              for m, o in filas.items() if not a.modelo or m == a.modelo})
        elif a.cmd == "sombra":
            from pathlib import Path as _P
            from .demo import solo_permisos
            from .prevencion import importar_sombra
            man = json.loads((_P(a.ruta) / "manifiesto.json").read_text(encoding="utf-8"))  # el modelo lo dice la publicación verificada
            solo_permisos(db); db.migrar()
            if man.get("modelo_id") == "venta_cruzada":
                from .venta_cruzada import importar_sombra as importar_vc
                imprimir(importar_vc(db, a.ruta, a.actor))
            elif man.get("modelo_id") == "anomalias":
                from .anomalias import importar_sombra as importar_an
                imprimir(importar_an(db, a.ruta, a.actor))
            elif man.get("modelo_id") == "demanda":
                from .demanda import importar_sombra as importar_dm
                imprimir(importar_dm(db, a.ruta, a.actor))
            else:
                imprimir(importar_sombra(db, a.ruta, a.actor, modelo_id=man.get("modelo_id", "inactividad_60d")))
        elif a.cmd == "cierre":
            from .demo import solo_permisos
            from .operacion import ejecutar_cierre
            solo_permisos(db)
            res = ejecutar_cierre(db, a.actor, a.corte, datos=a.datos, desde=a.desde, reintentos=a.reintentos)
            imprimir(res)
            return 0 if res["estado"] == "publicado" else 1
        elif a.cmd == "respaldo":
            from .operacion import respaldar
            imprimir(respaldar(db, a.salida))
        elif a.cmd == "restaurar":
            from .operacion import restaurar
            imprimir(restaurar(a.respaldo, a.destino))
        elif a.cmd == "generar-desde-a":
            from .integracion_a import generar
            m = generar(a.datos, a.corte, a.salida)
            imprimir({"cierre_id": m["cierre_id"], "tablas": {k: v["filas"] for k, v in m["tablas"].items()}, "calidad": m["calidad"].get("notas")})
        elif a.cmd == "exportar-eventos":
            from .tareas import exportar_eventos
            with db.conexion() as con:
                datos = exportar_eventos(con)
            if a.salida:
                with open(a.salida, "w", encoding="utf-8") as f:
                    json.dump(datos, f, ensure_ascii=False, indent=2)
            else:
                imprimir(datos)
    except ErrorApi as e:
        imprimir(e.como_dict())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
