"""Lógica del sistema de biblioteca sobre biblioteca.db.

Reglas de negocio implementadas:
 1. No se presta un ejemplar que no esté 'disponible'.
 2. Un socio no puede tener dos préstamos activos del mismo libro.
 3. Máximo 3 préstamos activos por socio.
 4. Préstamo por 14 días; al vencer se marca 'vencido' sin borrar historial.
 5. Al devolver, si hay reserva pendiente, el ejemplar queda 'reservado' y se
    avisa a quien reservó (la reserva pasa a 'atendida').
 6. Un ejemplar en 'mantenimiento' o 'baja' no circula.

Uso rápido desde Python:
    from app.core import Biblioteca
    bib = Biblioteca("data/biblioteca.db")
    bib.prestar(socio_id=1, libro_id=10)
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

DIAS_PRESTAMO = 14
MAX_PRESTAMOS_ACTIVOS = 3
MAX_RESERVAS_PENDIENTES = 2


class BibliotecaError(Exception):
    """Error de negocio (no de base de datos)."""


@dataclass
class Prestamo:
    id: int
    ejemplar_id: int
    socio_id: int
    fecha_prestamo: str
    fecha_vencimiento: str
    estado: str


class Biblioteca:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        if not Path(self.db_path).exists():
            raise FileNotFoundError(f"no existe la base: {self.db_path}")
        self.con = sqlite3.connect(self.db_path)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")

    # ---------- utilidades internas ----------

    def _uno(self, sql, params=()):
        return self.con.execute(sql, params).fetchone()

    def _todos(self, sql, params=()):
        return self.con.execute(sql, params).fetchall()

    def _validar_socio(self, socio_id: int):
        row = self._uno("SELECT * FROM socios WHERE id = ?", (socio_id,))
        if not row:
            raise BibliotecaError(f"socio {socio_id} no existe")
        if not row["activo"]:
            raise BibliotecaError(f"socio {socio_id} está inactivo")
        return row

    def _validar_libro(self, libro_id: int):
        row = self._uno("SELECT * FROM libros WHERE id = ?", (libro_id,))
        if not row:
            raise BibliotecaError(f"libro {libro_id} no existe")
        return row

    # ---------- socios ----------

    def crear_socio(self, codigo: str, nombre: str, tipo="estudiante",
                    email=None, telefono=None) -> int:
        if not codigo.strip() or not nombre.strip():
            raise BibliotecaError("código y nombre son obligatorios")
        if tipo not in ("estudiante", "docente", "administrativo", "externo"):
            raise BibliotecaError(f"tipo inválido: {tipo}")
        try:
            cur = self.con.execute(
                "INSERT INTO socios (codigo,nombre,tipo,email,telefono) VALUES (?,?,?,?,?)",
                (codigo.strip(), nombre.strip(), tipo, email, telefono))
            self.con.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            raise BibliotecaError(f"ya existe un socio con código {codigo}")

    def desactivar_socio(self, socio_id: int):
        activos = self._uno(
            "SELECT COUNT(*) c FROM prestamos WHERE socio_id = ? AND estado = 'activo'",
            (socio_id,))["c"]
        if activos:
            raise BibliotecaError(f"el socio tiene {activos} préstamo(s) activo(s)")
        self.con.execute("UPDATE socios SET activo = 0 WHERE id = ?", (socio_id,))
        self.con.commit()

    def listar_socios(self, solo_activos=True):
        """Socios con su número de préstamos en curso (activos o vencidos sin devolver)."""
        sql = """SELECT s.id, s.codigo, s.nombre, s.tipo, s.email, s.activo,
                        (SELECT COUNT(*) FROM prestamos p
                          WHERE p.socio_id = s.id AND p.estado IN ('activo','vencido'))
                        AS prestamos_en_curso
                 FROM socios s"""
        if solo_activos:
            sql += " WHERE s.activo = 1"
        return self._todos(sql + " ORDER BY s.id")

    # ---------- catálogo ----------

    def buscar(self, texto="", materia=None, solo_disponibles=True, limite=20):
        sql = ["""SELECT l.id, l.titulo, l.autores, l.anio_primera_edicion AS anio,
                         l.materias,
                         SUM(CASE WHEN e.estado='disponible' THEN 1 ELSE 0 END) AS disponibles,
                         COUNT(e.id) AS ejemplares
                  FROM libros l LEFT JOIN ejemplares e ON e.libro_id = l.id"""]
        where, params = [], []
        if texto:
            where.append("(l.titulo LIKE ? OR l.autores LIKE ? OR l.isbn = ?)")
            like = f"%{texto}%"
            params += [like, like, texto]
        if materia:
            where.append("l.materias LIKE ?")
            params.append(f"%{materia}%")
        if where:
            sql.append("WHERE " + " AND ".join(where))
        sql.append("GROUP BY l.id")
        if solo_disponibles:
            sql.append("HAVING disponibles > 0")
        sql.append("ORDER BY l.titulo LIMIT ?")
        params.append(limite)
        return self._todos(" ".join(sql), params)

    def ejemplares_de(self, libro_id: int):
        return self._todos(
            "SELECT id, codigo, estado, ubicacion FROM ejemplares WHERE libro_id = ? ORDER BY id",
            (libro_id,))

    # ---------- préstamos ----------

    def prestar(self, socio_id: int, libro_id: int, dias: int = DIAS_PRESTAMO,
                hoy: date | None = None) -> Prestamo:
        self._validar_socio(socio_id)
        self._validar_libro(libro_id)
        hoy = hoy or date.today()

        activos = self._uno(
            "SELECT COUNT(*) c FROM prestamos WHERE socio_id = ? AND estado = 'activo'",
            (socio_id,))["c"]
        if activos >= MAX_PRESTAMOS_ACTIVOS:
            raise BibliotecaError(
                f"el socio ya tiene {activos} préstamos activos (máximo {MAX_PRESTAMOS_ACTIVOS})")

        repetido = self._uno(
            """SELECT COUNT(*) c FROM prestamos p
               JOIN ejemplares e ON e.id = p.ejemplar_id
               WHERE p.socio_id = ? AND p.estado = 'activo' AND e.libro_id = ?""",
            (socio_id, libro_id))["c"]
        if repetido:
            raise BibliotecaError("el socio ya tiene este libro prestado")

        ejemplar = self._uno(
            "SELECT id FROM ejemplares WHERE libro_id = ? AND estado = 'disponible' ORDER BY id LIMIT 1",
            (libro_id,))
        if not ejemplar:
            raise BibliotecaError("no hay ejemplares disponibles de este libro")

        vence = hoy + timedelta(days=dias)
        cur = self.con.execute(
            """INSERT INTO prestamos (ejemplar_id, socio_id, fecha_prestamo,
                                      fecha_vencimiento, estado)
               VALUES (?,?,?,?, 'activo')""",
            (ejemplar["id"], socio_id, hoy.isoformat(), vence.isoformat()))
        self.con.execute("UPDATE ejemplares SET estado = 'prestado' WHERE id = ?",
                         (ejemplar["id"],))
        self.con.commit()
        return Prestamo(cur.lastrowid, ejemplar["id"], socio_id,
                        hoy.isoformat(), vence.isoformat(), "activo")

    def devolver(self, prestamo_id: int, hoy: date | None = None) -> dict:
        hoy = hoy or date.today()
        p = self._uno("SELECT * FROM prestamos WHERE id = ?", (prestamo_id,))
        if not p:
            raise BibliotecaError(f"préstamo {prestamo_id} no existe")
        if p["estado"] not in ("activo", "vencido"):
            raise BibliotecaError(f"el préstamo ya está en estado '{p['estado']}'")

        self.con.execute(
            "UPDATE prestamos SET estado = 'devuelto', fecha_devolucion = ? WHERE id = ?",
            (hoy.isoformat(), prestamo_id))

        ejemplar_id = p["ejemplar_id"]
        libro_id = self._uno("SELECT libro_id FROM ejemplares WHERE id = ?",
                             (ejemplar_id,))["libro_id"]

        reserva = self._uno(
            """SELECT * FROM reservas WHERE libro_id = ? AND estado = 'pendiente'
               ORDER BY fecha_reserva LIMIT 1""", (libro_id,))
        if reserva:
            self.con.execute("UPDATE reservas SET estado = 'atendida' WHERE id = ?",
                             (reserva["id"],))
            self.con.execute("UPDATE ejemplares SET estado = 'reservado' WHERE id = ?",
                             (ejemplar_id,))
            destino = {"estado_ejemplar": "reservado", "reserva_atendida": reserva["id"]}
        else:
            self.con.execute("UPDATE ejemplares SET estado = 'disponible' WHERE id = ?",
                             (ejemplar_id,))
            destino = {"estado_ejemplar": "disponible", "reserva_atendida": None}

        self.con.commit()
        atrasado = hoy > date.fromisoformat(p["fecha_vencimiento"])
        return {"prestamo_id": prestamo_id, "atrasado": atrasado, **destino}

    def vencer_prestamos(self, hoy: date | None = None) -> int:
        hoy = (hoy or date.today()).isoformat()
        cur = self.con.execute(
            "UPDATE prestamos SET estado = 'vencido' WHERE estado = 'activo' AND fecha_vencimiento < ?",
            (hoy,))
        self.con.commit()
        return cur.rowcount

    def prestamos_de(self, socio_id: int, solo_activos=True):
        sql = "SELECT * FROM prestamos WHERE socio_id = ?"
        params = [socio_id]
        if solo_activos:
            sql += " AND estado = 'activo'"
        return self._todos(sql + " ORDER BY fecha_vencimiento", params)

    # ---------- reservas ----------

    def reservar(self, socio_id: int, libro_id: int, dias_vigencia: int = 3,
                 hoy: date | None = None) -> int:
        self._validar_socio(socio_id)
        self._validar_libro(libro_id)
        hoy = hoy or date.today()

        pendientes = self._uno(
            "SELECT COUNT(*) c FROM reservas WHERE socio_id = ? AND estado = 'pendiente'",
            (socio_id,))["c"]
        if pendientes >= MAX_RESERVAS_PENDIENTES:
            raise BibliotecaError(
                f"el socio ya tiene {pendientes} reservas pendientes "
                f"(máximo {MAX_RESERVAS_PENDIENTES})")

        ya = self._uno(
            """SELECT COUNT(*) c FROM reservas
               WHERE socio_id = ? AND libro_id = ? AND estado = 'pendiente'""",
            (socio_id, libro_id))["c"]
        if ya:
            raise BibliotecaError("el socio ya tiene una reserva pendiente de este libro")

        disponible = self._uno(
            "SELECT COUNT(*) c FROM ejemplares WHERE libro_id = ? AND estado = 'disponible'",
            (libro_id,))["c"]
        if disponible:
            raise BibliotecaError("hay ejemplares disponibles: presta directo en vez de reservar")

        cur = self.con.execute(
            """INSERT INTO reservas (libro_id, socio_id, fecha_reserva, estado, expira_en)
               VALUES (?,?,?, 'pendiente', ?)""",
            (libro_id, socio_id, datetime.now().isoformat(timespec="seconds"),
             (hoy + timedelta(days=dias_vigencia)).isoformat()))
        self.con.commit()
        return cur.lastrowid

    def vencer_reservas(self, hoy: date | None = None) -> int:
        hoy = (hoy or date.today()).isoformat()
        cur = self.con.execute(
            "UPDATE reservas SET estado = 'vencida' WHERE estado = 'pendiente' AND expira_en < ?",
            (hoy,))
        self.con.commit()
        return cur.rowcount

    # ---------- reportes ----------

    def mas_prestados(self, limite=10):
        return self._todos(
            """SELECT l.titulo, l.autores, COUNT(p.id) AS veces
               FROM prestamos p
               JOIN ejemplares e ON e.id = p.ejemplar_id
               JOIN libros l ON l.id = e.libro_id
               GROUP BY l.id ORDER BY veces DESC, l.titulo LIMIT ?""", (limite,))

    def prestamos_vencidos(self, hoy: date | None = None):
        hoy = (hoy or date.today()).isoformat()
        return self._todos(
            """SELECT p.id, s.nombre AS socio, l.titulo, p.fecha_vencimiento,
                      CAST(julianday(?) - julianday(p.fecha_vencimiento) AS INTEGER) AS dias_atraso
               FROM prestamos p
               JOIN socios s ON s.id = p.socio_id
               JOIN ejemplares e ON e.id = p.ejemplar_id
               JOIN libros l ON l.id = e.libro_id
               WHERE p.estado IN ('activo','vencido') AND p.fecha_vencimiento < ?
               ORDER BY dias_atraso DESC""", (hoy, hoy))

    def disponibilidad(self):
        return self._todos(
            """SELECT estado, COUNT(*) AS ejemplares FROM ejemplares
               GROUP BY estado ORDER BY ejemplares DESC""")

    def disponibilidad_dict(self) -> dict:
        """{'disponible': 7550, 'prestado': 2, ...} — los estados sin ejemplares valen 0."""
        estados = ("disponible", "prestado", "reservado", "mantenimiento", "baja")
        base = {e: 0 for e in estados}
        base.update({r["estado"]: r["ejemplares"] for r in self.disponibilidad()})
        return base

    def cerrar(self):
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cerrar()
