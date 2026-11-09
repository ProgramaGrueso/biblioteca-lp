"""Carga datos de demostración: socios, historial de préstamos, préstamos activos,
préstamos vencidos y una reserva pendiente. Así los reportes no salen vacíos.

Usa la misma lógica de app/core.py (las reglas de negocio se respetan), pero con
fechas pasadas para simular uso real de las últimas semanas.

Ejecutar desde la raíz del proyecto:
    python3 scripts/datos_demo.py              # usa data/biblioteca.db (hace respaldo antes)
    python3 scripts/datos_demo.py --db otra.db

Si ya hay socios DEMO-*, no hace nada (es seguro correrlo dos veces).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core import Biblioteca  # noqa: E402

SOCIOS = [
    ("DEMO-01", "Ana Torres Quispe", "estudiante", "ana.torres@demo.pe"),
    ("DEMO-02", "Luis Mendoza Ríos", "estudiante", "luis.mendoza@demo.pe"),
    ("DEMO-03", "Carla Huamán Soto", "estudiante", None),
    ("DEMO-04", "Jorge Salazar Paredes", "docente", "jsalazar@demo.pe"),
    ("DEMO-05", "Rosa Flores Chávez", "estudiante", None),
    ("DEMO-06", "Diego Ramírez Vega", "estudiante", "diego.rv@demo.pe"),
    ("DEMO-07", "Lucía Castillo Rojas", "docente", "lcastillo@demo.pe"),
    ("DEMO-08", "Miguel Ángel Pérez", "administrativo", None),
    ("DEMO-09", "Valeria Gutiérrez León", "estudiante", "vale.gl@demo.pe"),
    ("DEMO-10", "Carlos Núñez Ibarra", "externo", None),
]

# Títulos del catálogo real que usamos en la demo (se buscan por título exacto).
FICCIONES = "Ficciones"
CIUDAD = "La ciudad y los perros"
PARAMO = "Pedro Páramo"
PRINCIPITO = "El principito"
VEINTE = "Veinte poemas de amor y una canción desesperada"
CRONICA = "Crónica de una infamia"
QUIJOTE = "Mujeres del Quijote"


def libro_id(bib: Biblioteca, titulo: str) -> int:
    row = bib._uno("SELECT id FROM libros WHERE titulo = ? ORDER BY id LIMIT 1", (titulo,))
    if not row:
        raise SystemExit(f"no encontré en el catálogo: {titulo!r}")
    return row["id"]


def cargar(db: Path) -> None:
    hoy = date.today()
    with Biblioteca(db) as bib:
        if bib._uno("SELECT 1 FROM socios WHERE codigo LIKE 'DEMO-%'"):
            print("Ya hay socios DEMO-* en la base: no cargo nada otra vez.")
            return

        ids = [bib.crear_socio(c, n, t, email=e) for c, n, t, e in SOCIOS]
        s = dict(zip(range(1, 11), ids))  # s[1] = id real del socio DEMO-01
        lib = {t: libro_id(bib, t) for t in (FICCIONES, CIUDAD, PARAMO, PRINCIPITO,
                                             VEINTE, CRONICA, QUIJOTE)}

        # 1) Historial: préstamos ya devueltos (alimentan "Más prestados").
        historial = [
            (FICCIONES, [1, 2, 3, 9]),
            (CIUDAD, [4, 5, 6]),
            (PARAMO, [7, 9, 10]),
            (PRINCIPITO, [2, 8]),
            (VEINTE, [3, 6]),
        ]
        devueltos = 0
        for titulo, socios in historial:
            for i, n in enumerate(socios):
                inicio = hoy - timedelta(days=70 - i * 12)
                p = bib.prestar(s[n], lib[titulo], hoy=inicio)
                bib.devolver(p.id, hoy=inicio + timedelta(days=9))
                devueltos += 1

        # 2) Préstamos vencidos: salieron hace 25 días (vencían a los 14).
        hace_25 = hoy - timedelta(days=25)
        bib.prestar(s[3], lib[CRONICA], hoy=hace_25)
        bib.prestar(s[5], lib[QUIJOTE], hoy=hace_25)
        vencidos = bib.vencer_prestamos(hoy)

        # 3) Préstamos activos en plazo (salieron hace 3 días).
        hace_3 = hoy - timedelta(days=3)
        activos = [(1, FICCIONES), (2, CIUDAD), (4, PARAMO), (6, PRINCIPITO), (7, VEINTE)]
        for n, titulo in activos:
            bib.prestar(s[n], lib[titulo], hoy=hace_3)

        # 4) Reserva: "Pedro Páramo" tiene un solo ejemplar y está prestado.
        #    Al devolverlo en la demo, el ejemplar pasa a 'reservado' para DEMO-08.
        bib.reservar(s[8], lib[PARAMO], dias_vigencia=7)

        print(f"Socios creados: {len(ids)} (ids {ids[0]}–{ids[-1]})")
        print(f"Préstamos devueltos (historial): {devueltos}")
        print(f"Préstamos vencidos: {vencidos}")
        print(f"Préstamos activos: {len(activos)}")
        print(f"Reserva pendiente: '{PARAMO}' para {SOCIOS[7][1]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Carga datos de demostración")
    ap.add_argument("--db", default=str(ROOT / "data" / "biblioteca.db"))
    ap.add_argument("--sin-respaldo", action="store_true",
                    help="no copiar la base antes de modificarla")
    args = ap.parse_args()
    db = Path(args.db)
    if not args.sin_respaldo:
        respaldo = db.with_name(f"{db.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(db, respaldo)
        print(f"Respaldo: {respaldo}")
    cargar(db)


if __name__ == "__main__":
    main()
