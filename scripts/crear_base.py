"""Crea data/biblioteca.db desde data/schema.sql y data/libros.json (sin internet).

La base no se sube al repositorio (guardaría datos de socios), así que quien
clona el proyecto la genera con este script. El resultado es el mismo catálogo
que arma el scraper: mismos libros, mismos ejemplares y mismos códigos.

Ejecutar desde la raíz del proyecto:
    python3 scripts/crear_base.py            # crea data/biblioteca.db
    python3 scripts/crear_base.py --forzar   # la borra y la vuelve a crear
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def crear(db: Path) -> tuple[int, int]:
    libros = json.loads((DATA / "libros.json").read_text(encoding="utf-8"))
    con = sqlite3.connect(db)
    con.executescript((DATA / "schema.sql").read_text(encoding="utf-8"))
    rnd = random.Random(7)  # misma semilla que scrapers/openlibrary.py
    for b in libros:
        cur = con.execute(
            """INSERT INTO libros (ol_key,titulo,subtitulo,autores,anio_primera_edicion,editorial,
                                   isbn,idioma,materias,paginas,portada_url,ediciones)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (b["ol_key"], b["titulo"], b["subtitulo"], b["autores"], b["anio_primera_edicion"],
             b["editorial"], b["isbn"], b["idioma"], b["materias"], b["paginas"],
             b["portada_url"], b["ediciones"]))
        libro_id = cur.lastrowid
        for n in range(1, rnd.choice([1, 1, 2, 3]) + 1):
            con.execute(
                "INSERT INTO ejemplares (libro_id,codigo,estado,ubicacion) VALUES (?,?,?,?)",
                (libro_id, f"LIB-{libro_id:05d}-{n}", "disponible",
                 f"Estante {chr(65 + libro_id % 6)}-{n}"))
    con.commit()
    n_libros = con.execute("SELECT COUNT(*) FROM libros").fetchone()[0]
    n_ej = con.execute("SELECT COUNT(*) FROM ejemplares").fetchone()[0]
    con.close()
    return n_libros, n_ej


def main() -> None:
    ap = argparse.ArgumentParser(description="Crea la base SQLite desde libros.json")
    ap.add_argument("--db", default=str(DATA / "biblioteca.db"))
    ap.add_argument("--forzar", action="store_true", help="reemplazar la base si ya existe")
    args = ap.parse_args()
    db = Path(args.db)
    if db.exists():
        if not args.forzar:
            sys.exit(f"Ya existe {db}. Usa --forzar para borrarla y crearla de nuevo.")
        db.unlink()
    n_libros, n_ej = crear(db)
    print(f"Base creada: {db}  (libros={n_libros}, ejemplares={n_ej})")


if __name__ == "__main__":
    main()
