"""Línea de comandos de B.

    python -m api demo                      # migra y carga datos ficticios de demostración
    python -m api servir [--practica]       # API + app en http://127.0.0.1:8000/app/
    python -m api publicar RUTA             # directorio C2 o agenda.json C1
    python -m api cierre --corte 2026-10-31 --datos ../Green_Services_Recursos_de_Prueba
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
    from .base import BaseDatos, ErrorApi, RAIZ

    p = argparse.ArgumentParser(prog="python -m api", description="JACOMIND · aplicación y operación")
    p.add_argument("--db", default=os.environ.get("JACOMIND_DB", str(RAIZ / "var" / "jacomind.sqlite3")))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrar")
    d = sub.add_parser("demo"); d.add_argument("--sin-cierre", action="store_true")
    s = sub.add_parser("servir")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--puerto", type=int, default=8000)
    s.add_argument("--practica", action="store_true", help="expone /salida/agenda.json para el modo práctica local")
    s.add_argument("--sin-login-demo", action="store_true", help="desactiva el inicio de sesión con identidades ficticias")
    pb = sub.add_parser("publicar"); pb.add_argument("ruta"); pb.add_argument("--actor", default="ops1")
    c = sub.add_parser("cierre")
    c.add_argument("--corte", required=True); c.add_argument("--datos"); c.add_argument("--desde")
    c.add_argument("--reintentos", type=int, default=2); c.add_argument("--actor", default="programador")
    r = sub.add_parser("respaldo"); r.add_argument("--salida")
    rs = sub.add_parser("restaurar"); rs.add_argument("respaldo"); rs.add_argument("--destino", required=True)
    e = sub.add_parser("exportar-eventos"); e.add_argument("--salida")
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
