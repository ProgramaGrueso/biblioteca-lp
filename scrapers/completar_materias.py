#!/usr/bin/env python3
"""Completa materias que fallaron por timeout y reconstruye DB/CSV sin perder lo ya scrapeado."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import openlibrary as ol  # noqa: E402

MISSING = ["salud pública", "derecho"]


def main():
    books = ol.json.loads((ol.DATA / "libros.json").read_text())
    seen = {b["ol_key"] for b in books}
    for subject in MISSING:
        got = 0
        page = 1
        while page <= 3 and got < 100:
            import urllib.parse
            q = urllib.parse.quote(f'subject:"{subject}"')
            url = (f"https://openlibrary.org/search.json?q={q}&language=spa"
                   f"&fields=key,title,subtitle,author_name,first_publish_year,publisher,isbn,"
                   f"language,subject,number_of_pages_median,cover_i,edition_count&limit=100&page={page}")
            payload = ol.get_json(url, tries=5)
            if not payload or not payload.get("docs"):
                print(f"  {subject} p{page}: sin datos", flush=True)
                break
            for doc in payload["docs"]:
                rec = ol.normalize(doc)
                if not rec["titulo"] or not rec["ol_key"] or rec["ol_key"] in seen:
                    continue
                seen.add(rec["ol_key"])
                rec["materia_busqueda"] = subject
                books.append(rec)
                got += 1
            print(f"  {subject} p{page}: +{got} (total {len(books)})", flush=True)
            page += 1
    n_libros, n_ej = ol.write_outputs(books)
    print(f"OK libros={n_libros} ejemplares={n_ej}", flush=True)


if __name__ == "__main__":
    main()
