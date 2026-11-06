#!/usr/bin/env python3
"""Scraper de catálogo de biblioteca desde Open Library (API pública).

Salida (en ./data):
  libros.json  – registros crudos normalizados
  libros.csv   – mismo contenido, plano
  biblioteca.db – SQLite con esquema de sistema de biblioteca (libros, ejemplares,
                  socios, prestamos, reservas) y los libros cargados + ejemplares.

Uso:  python3 scrapers/openlibrary.py [--target 2000]
"""
import argparse
import csv
import json
import random
import sqlite3
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "biblioteca-utp/1.0 (trabajo academico; contacto: juang)"

SUBJECTS = [
    "novela", "poesía", "cuento", "teatro", "ensayo",
    "historia", "filosofía", "psicología", "sociología", "antropología",
    "ciencia", "física", "química", "biología", "matemáticas",
    "medicina", "odontología", "enfermería", "salud pública",
    "derecho", "economía", "administración", "contabilidad", "educación",
    "ingeniería", "informática", "tecnología", "arte", "música", "arquitectura",
]

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS libros (
    id INTEGER PRIMARY KEY,
    ol_key TEXT UNIQUE,
    titulo TEXT NOT NULL,
    subtitulo TEXT,
    autores TEXT,
    anio_primera_edicion INTEGER,
    editorial TEXT,
    isbn TEXT,
    idioma TEXT,
    materias TEXT,
    paginas INTEGER,
    portada_url TEXT,
    ediciones INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ejemplares (
    id INTEGER PRIMARY KEY,
    libro_id INTEGER NOT NULL REFERENCES libros(id),
    codigo TEXT UNIQUE NOT NULL,
    estado TEXT NOT NULL DEFAULT 'disponible'
        CHECK (estado IN ('disponible','prestado','reservado','mantenimiento','baja')),
    ubicacion TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS socios (
    id INTEGER PRIMARY KEY,
    codigo TEXT UNIQUE NOT NULL,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'estudiante'
        CHECK (tipo IN ('estudiante','docente','administrativo','externo')),
    email TEXT,
    telefono TEXT,
    activo INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prestamos (
    id INTEGER PRIMARY KEY,
    ejemplar_id INTEGER NOT NULL REFERENCES ejemplares(id),
    socio_id INTEGER NOT NULL REFERENCES socios(id),
    fecha_prestamo TEXT NOT NULL,
    fecha_vencimiento TEXT NOT NULL,
    fecha_devolucion TEXT,
    estado TEXT NOT NULL DEFAULT 'activo'
        CHECK (estado IN ('activo','devuelto','vencido','cancelado')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reservas (
    id INTEGER PRIMARY KEY,
    libro_id INTEGER NOT NULL REFERENCES libros(id),
    socio_id INTEGER NOT NULL REFERENCES socios(id),
    fecha_reserva TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente','atendida','vencida','cancelada')),
    expira_en TEXT
);

CREATE INDEX IF NOT EXISTS idx_prestamos_estado ON prestamos(estado);
CREATE INDEX IF NOT EXISTS idx_ejemplares_libro ON ejemplares(libro_id);
CREATE INDEX IF NOT EXISTS idx_libros_titulo ON libros(titulo);
"""


def get_json(url, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as exc:
            if attempt == tries - 1:
                print(f"  ! fallo {url[:80]}: {exc}", flush=True)
                return None
            time.sleep(2 * (attempt + 1))


def normalize(doc):
    isbn = ""
    for cand in doc.get("isbn", []) or []:
        if len(cand) in (10, 13):
            isbn = cand
            break
    publishers = doc.get("publisher") or []
    subjects = doc.get("subject") or []
    return {
        "ol_key": doc.get("key"),
        "titulo": (doc.get("title") or "").strip(),
        "subtitulo": (doc.get("subtitle") or "").strip() or None,
        "autores": "; ".join(doc.get("author_name") or [])[:300] or None,
        "anio_primera_edicion": doc.get("first_publish_year"),
        "editorial": (publishers[0][:150] if publishers else None),
        "isbn": isbn or None,
        "idioma": "; ".join(doc.get("language") or [])[:60] or None,
        "materias": "; ".join(subjects[:6])[:300] or None,
        "paginas": doc.get("number_of_pages_median"),
        "portada_url": (f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-M.jpg"
                        if doc.get("cover_i") else None),
        "ediciones": doc.get("edition_count"),
    }


def scrape(target, per_subject=None):
    seen, out = set(), []
    for subject in SUBJECTS:
        if per_subject is None and len(out) >= target:
            break
        got_here = 0
        page = 1
        while page <= 8:
            if per_subject is None and len(out) >= target:
                break
            if per_subject is not None and got_here >= per_subject:
                break
            q = urllib.parse.quote(f'subject:"{subject}"')
            url = (f"https://openlibrary.org/search.json?q={q}"
                   f"&language=spa&fields=key,title,subtitle,author_name,first_publish_year,"
                   f"publisher,isbn,language,subject,number_of_pages_median,cover_i,edition_count"
                   f"&limit=100&page={page}")
            payload = get_json(url)
            if not payload or not payload.get("docs"):
                break
            added = 0
            for doc in payload["docs"]:
                rec = normalize(doc)
                if not rec["titulo"] or not rec["ol_key"] or rec["ol_key"] in seen:
                    continue
                seen.add(rec["ol_key"])
                rec["materia_busqueda"] = subject
                out.append(rec)
                added += 1
                got_here += 1
            print(f"  {subject:14s} p{page}: +{added:3d} (total {len(out)})", flush=True)
            if added == 0:
                break
            page += 1
            time.sleep(0.4)
    return out


def write_outputs(books):
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "libros.json").write_text(json.dumps(books, ensure_ascii=False, indent=1))
    cols = list(books[0].keys())
    with (DATA / "libros.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(books)

    db = DATA / "biblioteca.db"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    rnd = random.Random(7)
    for i, b in enumerate(books, start=1):
        cur = con.execute(
            """INSERT INTO libros (ol_key,titulo,subtitulo,autores,anio_primera_edicion,editorial,
                                    isbn,idioma,materias,paginas,portada_url,ediciones)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (b["ol_key"], b["titulo"], b["subtitulo"], b["autores"], b["anio_primera_edicion"],
             b["editorial"], b["isbn"], b["idioma"], b["materias"], b["paginas"],
             b["portada_url"], b["ediciones"]),
        )
        libro_id = cur.lastrowid
        for n in range(1, rnd.choice([1, 1, 2, 3]) + 1):
            con.execute(
                "INSERT INTO ejemplares (libro_id,codigo,estado,ubicacion) VALUES (?,?,?,?)",
                (libro_id, f"LIB-{libro_id:05d}-{n}", "disponible",
                 f"Estante {chr(65 + libro_id % 6)}-{n}"),
            )
    con.commit()
    cur = con.execute("SELECT COUNT(*) FROM libros")
    n_libros = cur.fetchone()[0]
    cur = con.execute("SELECT COUNT(*) FROM ejemplares")
    n_ej = cur.fetchone()[0]
    con.close()
    (DATA / "schema.sql").write_text(SCHEMA)
    return n_libros, n_ej


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=2000)
    ap.add_argument("--per-subject", type=int, default=None,
                    help="tope de libros por materia (reparte mejor el catálogo)")
    args = ap.parse_args()
    print(f"Scrapeando {'%d por materia' % args.per_subject if args.per_subject else args.target} "
          f"libros en español de Open Library...", flush=True)
    books = scrape(args.target, args.per_subject)
    print(f"Total scrapeado: {len(books)}", flush=True)
    n_libros, n_ej = write_outputs(books)
    print(f"OK  libros={n_libros}  ejemplares={n_ej}  -> {DATA}", flush=True)


if __name__ == "__main__":
    main()
