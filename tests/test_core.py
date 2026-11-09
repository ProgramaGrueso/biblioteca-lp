"""Pruebas de la lógica de biblioteca (unittest, sin dependencias externas).

Ejecutar:  python3 -m unittest discover -s tests -v
"""
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core import Biblioteca, BibliotecaError, MAX_PRESTAMOS_ACTIVOS  # noqa: E402


def base_limpia(bib):
    """Deja la copia solo con catálogo: sin socios ni movimientos (la base real puede
    tener datos de demostración)."""
    bib.con.executescript("""
        DELETE FROM reservas; DELETE FROM prestamos; DELETE FROM socios;
        UPDATE ejemplares SET estado = 'disponible';
    """)
    bib.con.commit()

DB_FUENTE = ROOT / "data" / "biblioteca.db"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = Path(self.tmp) / "test.db"
        shutil.copy(DB_FUENTE, self.db)
        self.bib = Biblioteca(self.db)
        base_limpia(self.bib)
        self.socio = self.bib.crear_socio("S-001", "Ana Torres")
        # libro con un solo ejemplar, para forzar escenarios
        row = self.bib._uno(
            """SELECT l.id FROM libros l JOIN ejemplares e ON e.libro_id = l.id
               GROUP BY l.id HAVING COUNT(e.id) = 1 LIMIT 1""")
        self.libro_unico = row["id"]

    def tearDown(self):
        self.bib.cerrar()
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestPrestamos(Base):
    def test_prestamo_feliz(self):
        antes = self.bib.disponibilidad_dict()["disponible"]
        p = self.bib.prestar(self.socio, self.libro_unico)
        self.assertEqual(p.estado, "activo")
        self.assertEqual(p.fecha_vencimiento,
                         (date.today() + timedelta(days=14)).isoformat())
        self.assertEqual(self.bib.disponibilidad_dict()["disponible"], antes - 1)
        self.assertEqual(self.bib.disponibilidad_dict()["prestado"], 1)

    def test_no_presta_sin_disponibles(self):
        self.bib.prestar(self.socio, self.libro_unico)
        otro = self.bib.crear_socio("S-002", "Luis Paz")
        with self.assertRaises(BibliotecaError) as ctx:
            self.bib.prestar(otro, self.libro_unico)
        self.assertIn("no hay ejemplares", str(ctx.exception))

    def test_no_repite_libro(self):
        libro = self.bib._uno(
            """SELECT l.id FROM libros l JOIN ejemplares e ON e.libro_id=l.id
               GROUP BY l.id HAVING COUNT(e.id) >= 2 LIMIT 1""")["id"]
        self.bib.prestar(self.socio, libro)
        with self.assertRaises(BibliotecaError) as ctx:
            self.bib.prestar(self.socio, libro)
        self.assertIn("ya tiene este libro", str(ctx.exception))

    def test_maximo_prestamos(self):
        libros = self.bib._todos(
            """SELECT l.id FROM libros l JOIN ejemplares e ON e.libro_id=l.id
               GROUP BY l.id HAVING COUNT(e.id) >= 1 LIMIT ?""",
            (MAX_PRESTAMOS_ACTIVOS + 1,))
        for r in libros[:MAX_PRESTAMOS_ACTIVOS]:
            self.bib.prestar(self.socio, r["id"])
        with self.assertRaises(BibliotecaError) as ctx:
            self.bib.prestar(self.socio, libros[MAX_PRESTAMOS_ACTIVOS]["id"])
        self.assertIn("máximo", str(ctx.exception))

    def test_socio_inactivo_no_presta(self):
        self.bib.desactivar_socio(self.socio)
        with self.assertRaises(BibliotecaError):
            self.bib.prestar(self.socio, self.libro_unico)


class TestDevoluciones(Base):
    def test_devuelve_prestamo_vencido(self):
        hace_30 = date.today() - timedelta(days=30)
        p = self.bib.prestar(self.socio, self.libro_unico, hoy=hace_30)
        self.assertEqual(self.bib.vencer_prestamos(), 1)
        res = self.bib.devolver(p.id)
        self.assertTrue(res["atrasado"])
        self.assertEqual(res["estado_ejemplar"], "disponible")

    def test_socio_sin_codigo_falla(self):
        with self.assertRaises(BibliotecaError):
            self.bib.crear_socio("  ", "Sin Código")

    def test_devolucion_libera_ejemplar(self):
        p = self.bib.prestar(self.socio, self.libro_unico)
        r = self.bib.devolver(p.id)
        self.assertEqual(r["estado_ejemplar"], "disponible")
        self.assertFalse(r["atrasado"])
        self.assertEqual(self.bib.disponibilidad_dict()["prestado"], 0)

    def test_devolucion_marca_atraso(self):
        p = self.bib.prestar(self.socio, self.libro_unico)
        r = self.bib.devolver(p.id, hoy=date.today() + timedelta(days=20))
        self.assertTrue(r["atrasado"])

    def test_devolver_dos_veces_falla(self):
        p = self.bib.prestar(self.socio, self.libro_unico)
        self.bib.devolver(p.id)
        with self.assertRaises(BibliotecaError):
            self.bib.devolver(p.id)

    def test_devolucion_atiende_reserva(self):
        self.bib.prestar(self.socio, self.libro_unico)
        reservante = self.bib.crear_socio("S-003", "Rosa Vega")
        reserva_id = self.bib.reservar(reservante, self.libro_unico)
        p = self.bib._uno(
            "SELECT * FROM prestamos WHERE socio_id=? AND estado='activo'", (self.socio,))
        r = self.bib.devolver(p["id"])
        self.assertEqual(r["estado_ejemplar"], "reservado")
        self.assertEqual(r["reserva_atendida"], reserva_id)

    def test_vencer_prestamos(self):
        self.bib.prestar(self.socio, self.libro_unico,
                         hoy=date.today() - timedelta(days=30))
        n = self.bib.vencer_prestamos()
        self.assertGreaterEqual(n, 1)
        self.assertEqual(self.bib.disponibilidad_dict()["prestado"], 1)  # sigue fuera


class TestReservas(Base):
    def test_reserva_cuando_no_hay_disponibles(self):
        self.bib.prestar(self.socio, self.libro_unico)
        otro = self.bib.crear_socio("S-004", "Eva Ruiz")
        rid = self.bib.reservar(otro, self.libro_unico)
        self.assertIsInstance(rid, int)

    def test_reserva_rechazada_si_hay_disponibles(self):
        libro = self.bib._uno(
            """SELECT l.id FROM libros l JOIN ejemplares e ON e.libro_id=l.id
               WHERE e.estado='disponible' GROUP BY l.id HAVING COUNT(e.id) >= 1 LIMIT 1""")["id"]
        with self.assertRaises(BibliotecaError) as ctx:
            self.bib.reservar(self.socio, libro)
        self.assertIn("presta directo", str(ctx.exception))

    def test_reserva_duplicada_falla(self):
        self.bib.prestar(self.socio, self.libro_unico)
        otro = self.bib.crear_socio("S-005", "Iván Soto")
        self.bib.reservar(otro, self.libro_unico)
        with self.assertRaises(BibliotecaError) as ctx:
            self.bib.reservar(otro, self.libro_unico)
        self.assertIn("ya tiene una reserva", str(ctx.exception))


class TestReportes(Base):
    def test_reportes_corren(self):
        self.bib.prestar(self.socio, self.libro_unico)
        self.assertIsInstance(self.bib.mas_prestados(), list)
        self.assertIsInstance(self.bib.prestamos_vencidos(), list)
        disp = self.bib.disponibilidad_dict()
        self.assertIn("disponible", disp)
        self.assertGreater(disp["disponible"], 0)


if __name__ == "__main__":
    unittest.main()
