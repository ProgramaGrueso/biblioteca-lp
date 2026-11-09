"""Pruebas de la capa web de biblioteca (unittest, http.server, sin dependencias externas).

Ejecutar:  python3 -m unittest tests/test_web.py -v
"""
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core import Biblioteca  # noqa: E402
from app.web import crear_servidor  # noqa: E402
from test_core import base_limpia  # noqa: E402

DB_FUENTE = ROOT / "data" / "biblioteca.db"


class TestWebBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.db = Path(cls.tmp) / "test_web.db"
        shutil.copy(DB_FUENTE, cls.db)
        
        # Crear socio de prueba en la copia de prueba
        with Biblioteca(cls.db) as bib:
            base_limpia(bib)
            cls.socio_id = bib.crear_socio("W-001", "Carlos Web", "estudiante")
            cls.socio2_id = bib.crear_socio("W-002", "Elena Web", "estudiante")
            # Libro con un solo ejemplar para probar préstamo y reserva
            row = bib._uno("""SELECT l.id FROM libros l JOIN ejemplares e ON e.libro_id = l.id
                               GROUP BY l.id HAVING COUNT(e.id) = 1 LIMIT 1""")
            cls.libro_unico = row["id"]

        cls.server = crear_servidor(host="127.0.0.1", port=0, db_path=str(cls.db))
        cls.port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _get(self, path):
        req = urllib.request.Request(f"{self.base_url}{path}")
        with urllib.request.urlopen(req) as resp:
            return resp.getcode(), resp.read().decode("utf-8")

    def _post_form(self, path, data):
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}{path}", data=encoded,
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.getcode(), resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def _post_json(self, path, data):
        encoded = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}{path}", data=encoded,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.getcode(), json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))


class TestWebEndpoints(TestWebBase):
    def test_01_buscar_home(self):
        code, html = self._get("/")
        self.assertEqual(code, 200)
        self.assertIn("Biblioteca", html)
        self.assertIn("Buscar", html)

    def test_02_buscar_con_filtro(self):
        code, html = self._get("/buscar?q=quijote")
        self.assertEqual(code, 200)
        self.assertIn("Quijote", html)

    def test_03_ficha_libro(self):
        code, html = self._get(f"/libro?id={self.libro_unico}")
        self.assertEqual(code, 200)
        self.assertIn("Ficha de Libro", html)
        self.assertIn("Ejemplares", html)

    def test_04_prestar_y_devolver_flujo_completo(self):
        # 1. Prestar vía POST form
        code, resp = self._post_json("/api/prestar", {"socio_id": self.socio_id, "libro_id": self.libro_unico})
        self.assertEqual(code, 200)
        self.assertTrue(resp.get("ok"))
        prestamo_id = resp["prestamo"]["id"]
        self.assertIsNotNone(prestamo_id)

        # Verificar en base de datos directamente
        with Biblioteca(self.db) as bib:
            p = bib._uno("SELECT * FROM prestamos WHERE id = ?", (prestamo_id,))
            self.assertEqual(p["estado"], "activo")
            self.assertEqual(p["socio_id"], self.socio_id)

        # 2. Intentar reservar cuando ya está prestado (socio2)
        code_res, resp_res = self._post_json("/api/reservar", {"socio_id": self.socio2_id, "libro_id": self.libro_unico})
        self.assertEqual(code_res, 200)
        self.assertTrue(resp_res.get("ok"))
        reserva_id = resp_res["reserva_id"]

        # Verificar reserva en DB
        with Biblioteca(self.db) as bib:
            r = bib._uno("SELECT * FROM reservas WHERE id = ?", (reserva_id,))
            self.assertEqual(r["estado"], "pendiente")

        # 3. Devolver vía POST
        code_dev, resp_dev = self._post_json("/api/devolver", {"prestamo_id": prestamo_id})
        self.assertEqual(code_dev, 200)
        self.assertTrue(resp_dev.get("ok"))
        # Al devolver, el ejemplar pasa a 'reservado' porque había reserva pendiente
        self.assertEqual(resp_dev["resultado"]["estado_ejemplar"], "reservado")
        self.assertEqual(resp_dev["resultado"]["reserva_atendida"], reserva_id)

        # Verificar en DB que el préstamo quedó como devuelto
        with Biblioteca(self.db) as bib:
            p_final = bib._uno("SELECT * FROM prestamos WHERE id = ?", (prestamo_id,))
            self.assertEqual(p_final["estado"], "devuelto")
            r_final = bib._uno("SELECT * FROM reservas WHERE id = ?", (reserva_id,))
            self.assertEqual(r_final["estado"], "atendida")

    def test_05_error_validacion_http(self):
        code, resp = self._post_json("/api/prestar", {"socio_id": 99999, "libro_id": self.libro_unico})
        self.assertEqual(code, 400)
        self.assertFalse(resp.get("ok"))
        self.assertIn("error", resp)

    def test_05b_reportes_sin_llaves_sueltas(self):
        code, html = self._get("/reportes")
        self.assertEqual(code, 200)
        self.assertIn("Préstamos Vencidos (", html)
        self.assertNotIn("{len(", html)

    def test_06_pagina_socios(self):
        code, html = self._get("/socios")
        self.assertEqual(code, 200)
        self.assertIn("Nuevo Socio", html)
        self.assertIn("Carlos Web", html)

    def test_07_registrar_socio_formulario(self):
        code, html = self._post_form("/socios", {"codigo": "W-100", "nombre": "Marta Form",
                                                 "tipo": "docente"})
        self.assertEqual(code, 200)  # sigue el 303 hacia /socios
        self.assertIn("Marta Form", html)
        self.assertIn("registrado", html)

    def test_08_socio_duplicado_muestra_error(self):
        code, html = self._post_form("/socios", {"codigo": "W-001", "nombre": "Repetido"})
        self.assertEqual(code, 200)
        self.assertIn("ya existe", html)


if __name__ == '__main__':
    unittest.main()
