#!/usr/bin/env python3
"""CLI del sistema de biblioteca.

Ejemplos:
    python3 -m app.cli buscar "cien años de soledad"
    python3 -m app.cli socio-nuevo DEMO-001 "Ana Torres" --tipo estudiante
    python3 -m app.cli prestar 1 42
    python3 -m app.cli devolver 1
    python3 -m app.cli reservar 1 42
    python3 -m app.cli reportes
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import Biblioteca, BibliotecaError  # noqa: E402

DB = Path(__file__).resolve().parent.parent / "data" / "biblioteca.db"


def tabla(rows, headers):
    if not rows:
        print("  (sin resultados)")
        return
    data = [[str(r[h]) if not isinstance(r, dict) else str(r.get(h)) for h in headers] for r in rows]
    anchos = [max(len(h), *(len(fila[i]) for fila in data)) for i, h in enumerate(headers)]
    print("  " + "  ".join(h.ljust(a) for h, a in zip(headers, anchos)))
    print("  " + "  ".join("-" * a for a in anchos))
    for fila in data:
        print("  " + "  ".join(c.ljust(a) for c, a in zip(fila, anchos)))


def main():
    ap = argparse.ArgumentParser(description="Sistema de biblioteca (CLI)")
    ap.add_argument("--db", default=str(DB))
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("buscar", help="buscar en el catálogo")
    b.add_argument("texto", nargs="?", default="")
    b.add_argument("--materia")
    b.add_argument("--todos", action="store_true", help="incluir libros sin ejemplares disponibles")
    b.add_argument("--limite", type=int, default=10)

    s = sub.add_parser("socio-nuevo", help="crear socio")
    s.add_argument("codigo")
    s.add_argument("nombre")
    s.add_argument("--tipo", default="estudiante")
    s.add_argument("--email")

    p = sub.add_parser("prestar", help="prestar un libro a un socio")
    p.add_argument("socio_id", type=int)
    p.add_argument("libro_id", type=int)
    p.add_argument("--dias", type=int, default=14)

    d = sub.add_parser("devolver", help="devolver un préstamo")
    d.add_argument("prestamo_id", type=int)

    r = sub.add_parser("reservar", help="reservar un libro sin ejemplares disponibles")
    r.add_argument("socio_id", type=int)
    r.add_argument("libro_id", type=int)

    sub.add_parser("reportes", help="más prestados, vencidos y disponibilidad")
    sub.add_parser("vencer", help="marcar préstamos y reservas vencidos")

    args = ap.parse_args()
    if not Path(args.db).exists():
        sys.exit(f"no existe la base {args.db}; corre primero scrapers/openlibrary.py")

    try:
        with Biblioteca(args.db) as bib:
            if args.cmd == "buscar":
                rows = bib.buscar(args.texto, args.materia,
                                  solo_disponibles=not args.todos, limite=args.limite)
                tabla([dict(r) for r in rows], ["id", "titulo", "autores", "anio", "disponibles"])
            elif args.cmd == "socio-nuevo":
                sid = bib.crear_socio(args.codigo, args.nombre, args.tipo, args.email)
                print(f"socio creado: id={sid} codigo={args.codigo}")
            elif args.cmd == "prestar":
                pr = bib.prestar(args.socio_id, args.libro_id, dias=args.dias)
                print(f"préstamo {pr.id}: ejemplar {pr.ejemplar_id}, vence {pr.fecha_vencimiento}")
            elif args.cmd == "devolver":
                res = bib.devolver(args.prestamo_id)
                print(f"devuelto: ejemplar queda {res['estado_ejemplar']}"
                      + (f", reserva {res['reserva_atendida']} atendida" if res["reserva_atendida"] else "")
                      + ("  ¡ATRASADO!" if res["atrasado"] else ""))
            elif args.cmd == "reservar":
                rid = bib.reservar(args.socio_id, args.libro_id)
                print(f"reserva creada: id={rid}")
            elif args.cmd == "reportes":
                print("\nDisponibilidad:")
                tabla([{"estado": k, "ejemplares": v} for k, v in bib.disponibilidad_dict().items()],
                      ["estado", "ejemplares"])
                print("\nMás prestados:")
                tabla([dict(r) for r in bib.mas_prestados(5)], ["titulo", "autores", "veces"])
                print("\nVencidos:")
                tabla([dict(r) for r in bib.prestamos_vencidos()], ["id", "socio", "titulo", "dias_atraso"])
            elif args.cmd == "vencer":
                print(f"préstamos marcados vencidos: {bib.vencer_prestamos()}")
                print(f"reservas marcadas vencidas: {bib.vencer_reservas()}")
    except BibliotecaError as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
