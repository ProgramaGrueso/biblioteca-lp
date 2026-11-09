"""Capa web mínima del sistema de biblioteca (estándar, sin dependencias externas).

Ejecutar:
    python3 -m app.web --port 8080
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core import Biblioteca, BibliotecaError  # noqa: E402

DB_DEFAULT = ROOT / "data" / "biblioteca.db"


class BibliotecaWebHandler(BaseHTTPRequestHandler):
    @property
    def db_path(self) -> str:
        return getattr(self.server, "db_path", str(DB_DEFAULT))

    def _responder_html(self, status: int, cuerpo: str):
        doc = f"""<!DOCTYPE html>
<html lang=\"es\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>Sistema de Biblioteca</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; margin: 2rem auto; max-width: 900px; padding: 0 1rem; color: #222; background: #fafafa; }}
        header, nav {{ margin-bottom: 1.5rem; }}
        nav a {{ margin-right: 1rem; color: #0066cc; text-decoration: none; font-weight: bold; }}
        nav a:hover {{ text-decoration: underline; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        th, td {{ padding: 0.6rem 0.8rem; text-align: left; border-bottom: 1px solid #e0e0e0; }}
        th {{ background: #f0f4f8; font-size: 0.9rem; }}
        .badge {{ display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }}
        .badge-disponible {{ background: #d4edda; color: #155724; }}
        .badge-prestado {{ background: #fff3cd; color: #856404; }}
        .badge-reservado {{ background: #cce5ff; color: #004085; }}
        .card {{ background: #fff; padding: 1.5rem; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 1.5rem; }}
        .form-inline {{ display: flex; gap: 0.5rem; margin-top: 0.5rem; }}
        input, select, button {{ padding: 0.5rem; font-size: 0.95rem; border: 1px solid #ccc; border-radius: 4px; }}
        button {{ background: #0066cc; color: white; border: none; cursor: pointer; }}
        button:hover {{ background: #0052a3; }}
        .error {{ background: #f8d7da; color: #721c24; padding: 1rem; border-radius: 4px; margin-bottom: 1rem; }}
        .exito {{ background: #d4edda; color: #155724; padding: 1rem; border-radius: 4px; margin-bottom: 1rem; }}
    </style>
</head>
<body>
    <header>
        <h1>📚 Sistema de Biblioteca</h1>
        <nav>
            <a href=\"/\">Buscar Catálogo</a>
            <a href=\"/socios\">Socios</a>
            <a href=\"/devolver\">Devoluciones</a>
            <a href=\"/reportes\">Reportes</a>
        </nav>
    </header>
    <main>
        {cuerpo}
    </main>
</body>
</html>"""
        data = doc.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _responder_json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _leer_post(self) -> tuple[dict, bool]:
        ct = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        is_json = "application/json" in ct or "application/json" in self.headers.get("Accept", "")
        if "application/json" in ct:
            try:
                return (json.loads(body) if body else {}), True
            except Exception:
                return {}, True
        else:
            parsed = parse_qs(body)
            data = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
            return data, is_json

    def do_GET(self):
        u = urlparse(self.path)
        params = parse_qs(u.query)

        with Biblioteca(self.db_path) as bib:
            if u.path in ("/", "/buscar"):
                q = params.get("q", [""])[0].strip()
                materia = params.get("materia", [""])[0].strip() or None
                todos = params.get("todos", ["0"])[0] == "1"
                rows = bib.buscar(q, materia=materia, solo_disponibles=not todos, limite=25)

                cuerpo = f"""
                <div class=\"card\">
                    <h2>Buscar en el Catálogo</h2>
                    <form action=\"/buscar\" method=\"GET\">
                        <div class=\"form-inline\">
                            <input type=\"text\" name=\"q\" placeholder=\"Título, autor o ISBN...\" value=\"{html.escape(q)}\" style=\"flex: 2;\">
                            <input type=\"text\" name=\"materia\" placeholder=\"Materia (opcional)\" value=\"{html.escape(materia or '')}\" style=\"flex: 1;\">
                            <label style=\"display: flex; align-items: center; gap: 0.3rem; font-size: 0.85rem;\">
                                <input type=\"checkbox\" name=\"todos\" value=\"1\" {'checked' if todos else ''}> Incluir agotados
                            </label>
                            <button type=\"submit\">Buscar</button>
                        </div>
                    </form>
                </div>
                """
                if not rows:
                    cuerpo += "<p>No se encontraron libros con los criterios indicados.</p>"
                else:
                    cuerpo += f"""
                    <h3>Resultados ({len(rows)})</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Título</th>
                                <th>Autores</th>
                                <th>Año</th>
                                <th>Disponibles</th>
                                <th>Acción</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
                    for r in rows:
                        cuerpo += f"""
                            <tr>
                                <td>{r['id']}</td>
                                <td><strong><a href=\"/libro?id={r['id']}\">{html.escape(r['titulo'] or '')}</a></strong></td>
                                <td>{html.escape(r['autores'] or 'Desconocido')}</td>
                                <td>{r['anio'] or '-'}</td>
                                <td><span class=\"badge {'badge-disponible' if r['disponibles'] > 0 else 'badge-prestado'}\">{r['disponibles']} / {r['ejemplares']}</span></td>
                                <td><a href=\"/libro?id={r['id']}\">Ver ficha →</a></td>
                            </tr>
                        """
                    cuerpo += "</tbody></table>"
                self._responder_html(200, cuerpo)

            elif u.path == "/libro":
                lid_str = params.get("id", [""])[0]
                if not lid_str.isdigit():
                    self._responder_html(400, "<div class=\"error\">ID de libro inválido</div>")
                    return
                lid = int(lid_str)
                libro = bib._uno("SELECT * FROM libros WHERE id = ?", (lid,))
                if not libro:
                    self._responder_html(404, "<div class=\"error\">Libro no encontrado</div>")
                    return
                ejemplares = bib.ejemplares_de(lid)
                msg = params.get("msg", [""])[0]
                err = params.get("err", [""])[0]

                cuerpo = ""
                if msg:
                    cuerpo += f"<div class=\"exito\">{html.escape(msg)}</div>"
                if err:
                    cuerpo += f"<div class=\"error\">{html.escape(err)}</div>"

                cuerpo += f"""
                <div class=\"card\">
                    <h2>Ficha de Libro: {html.escape(libro['titulo'])}</h2>
                    <p><strong>Autores:</strong> {html.escape(libro['autores'] or '-')}</p>
                    <p><strong>Editorial:</strong> {html.escape(libro['editorial'] or '-')} | <strong>Año:</strong> {libro['anio_primera_edicion'] or '-'} | <strong>ISBN:</strong> {html.escape(libro['isbn'] or '-')}</p>
                    <p><strong>Materias:</strong> {html.escape(libro['materias'] or '-')}</p>
                </div>

                <div class=\"card\">
                    <h3>Ejemplares Físicos ({len(ejemplares)})</h3>
                    <table>
                        <thead>
                            <tr><th>ID</th><th>Código</th><th>Estado</th><th>Ubicación</th></tr>
                        </thead>
                        <tbody>
                """
                disponibles = 0
                for ej in ejemplares:
                    if ej['estado'] == 'disponible':
                        disponibles += 1
                    cuerpo += f"""
                        <tr>
                            <td>{ej['id']}</td>
                            <td><code>{html.escape(ej['codigo'])}</code></td>
                            <td><span class=\"badge badge-{ej['estado']}\">{ej['estado']}</span></td>
                            <td>{html.escape(ej['ubicacion'] or '-')}</td>
                        </tr>
                    """
                cuerpo += "</tbody></table></div>"

                cuerpo += f"""
                <div style=\"display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;\">
                    <div class=\"card\">
                        <h3>Prestar este libro</h3>
                        <form action=\"/prestar\" method=\"POST\">
                            <input type=\"hidden\" name=\"libro_id\" value=\"{lid}\">
                            <label>ID Socio:<br><input type=\"number\" name=\"socio_id\" required style=\"width: 100%; margin-top: 0.3rem;\"></label><br><br>
                            <button type=\"submit\" style=\"width: 100%;\" {'disabled' if disponibles == 0 else ''}>
                                {'Realizar Préstamo' if disponibles > 0 else 'Sin ejemplares disponibles'}
                            </button>
                        </form>
                    </div>
                    <div class=\"card\">
                        <h3>Reservar este libro</h3>
                        <form action=\"/reservar\" method=\"POST\">
                            <input type=\"hidden\" name=\"libro_id\" value=\"{lid}\">
                            <label>ID Socio:<br><input type=\"number\" name=\"socio_id\" required style=\"width: 100%; margin-top: 0.3rem;\"></label><br><br>
                            <button type=\"submit\" style=\"width: 100%; background: #28a745;\" {'disabled' if disponibles > 0 else ''}>
                                {'Reservar (solo si está agotado)' if disponibles == 0 else 'Hay ejemplares disponibles'}
                            </button>
                        </form>
                    </div>
                </div>
                """
                self._responder_html(200, cuerpo)

            elif u.path == "/devolver":
                msg = params.get("msg", [""])[0]
                err = params.get("err", [""])[0]
                cuerpo = ""
                if msg:
                    cuerpo += f"<div class=\"exito\">{html.escape(msg)}</div>"
                if err:
                    cuerpo += f"<div class=\"error\">{html.escape(err)}</div>"
                cuerpo += """
                <div class=\"card\">
                    <h2>Devolución de Préstamo</h2>
                    <form action=\"/devolver\" method=\"POST\">
                        <label>ID del Préstamo:<br>
                            <input type=\"number\" name=\"prestamo_id\" required placeholder=\"Ej. 1\" style=\"width: 200px; margin-top: 0.5rem;\">
                        </label><br><br>
                        <button type=\"submit\">Procesar Devolución</button>
                    </form>
                </div>
                """
                self._responder_html(200, cuerpo)

            elif u.path == "/reportes":
                disp = bib.disponibilidad_dict()
                mas = bib.mas_prestados(5)
                venc = bib.prestamos_vencidos()
                cuerpo = """
                <div class=\"card\">
                    <h2>Estado de la Colección</h2>
                    <p>""" + " | ".join(f"<strong>{k.capitalize()}:</strong> {v}" for k, v in disp.items()) + f"""</p>
                </div>
                <div class=\"card\">
                    <h3>Más Prestados</h3>
                    <table>
                        <thead><tr><th>Título</th><th>Autores</th><th>Préstamos</th></tr></thead>
                        <tbody>
                """
                for m in mas:
                    cuerpo += f"<tr><td>{html.escape(m['titulo'])}</td><td>{html.escape(m['autores'] or '-')}</td><td>{m['veces']}</td></tr>"
                cuerpo += f"""
                        </tbody>
                    </table>
                </div>
                <div class=\"card\">
                    <h3>Préstamos Vencidos ({len(venc)})</h3>
                    <table>
                        <thead><tr><th>ID</th><th>Socio</th><th>Título</th><th>Días de Atraso</th></tr></thead>
                        <tbody>
                """
                for v in venc:
                    cuerpo += f"<tr><td>{v['id']}</td><td>{html.escape(v['socio'])}</td><td>{html.escape(v['titulo'])}</td><td>{v['dias_atraso']}</td></tr>"
                cuerpo += "</tbody></table></div>"
                self._responder_html(200, cuerpo)
            elif u.path == "/socios":
                msg = params.get("msg", [""])[0]
                err = params.get("err", [""])[0]
                socios = bib.listar_socios()
                cuerpo = ""
                if msg:
                    cuerpo += f"<div class=\"exito\">{html.escape(msg)}</div>"
                if err:
                    cuerpo += f"<div class=\"error\">{html.escape(err)}</div>"
                tipos = "".join(f"<option value=\"{t}\">{t.capitalize()}</option>"
                                for t in ("estudiante", "docente", "administrativo", "externo"))
                cuerpo += f"""
                <div class=\"card\">
                    <h2>Nuevo Socio</h2>
                    <form method=\"POST\" action=\"/socios\">
                        <label>Código:<br><input type=\"text\" name=\"codigo\" required placeholder=\"Ej. U-2026-001\"></label><br><br>
                        <label>Nombre:<br><input type=\"text\" name=\"nombre\" required style=\"width: 100%;\"></label><br><br>
                        <label>Tipo:<br><select name=\"tipo\">{tipos}</select></label><br><br>
                        <label>Email (opcional):<br><input type=\"email\" name=\"email\"></label><br><br>
                        <button type=\"submit\">Registrar Socio</button>
                    </form>
                </div>
                <div class=\"card\">
                    <h2>Socios Activos ({len(socios)})</h2>
                    <table>
                        <thead><tr><th>ID</th><th>Código</th><th>Nombre</th><th>Tipo</th><th>Préstamos en curso</th></tr></thead>
                        <tbody>
                """
                for s in socios:
                    cuerpo += (f"<tr><td>{s['id']}</td><td>{html.escape(s['codigo'])}</td>"
                               f"<td>{html.escape(s['nombre'])}</td><td>{s['tipo']}</td>"
                               f"<td>{s['prestamos_en_curso']}</td></tr>")
                cuerpo += "</tbody></table></div>"
                self._responder_html(200, cuerpo)
            else:
                self._responder_html(404, "<div class=\"error\">Ruta no encontrada</div>")

    def do_POST(self):
        u = urlparse(self.path)
        data, is_json = self._leer_post()

        with Biblioteca(self.db_path) as bib:
            try:
                if u.path in ("/prestar", "/api/prestar"):
                    socio_id = int(data.get("socio_id", 0))
                    libro_id = int(data.get("libro_id", 0))
                    p = bib.prestar(socio_id, libro_id)
                    if is_json or u.path.startswith("/api/"):
                        self._responder_json(200, {
                            "ok": True,
                            "prestamo": {
                                "id": p.id,
                                "ejemplar_id": p.ejemplar_id,
                                "socio_id": p.socio_id,
                                "fecha_prestamo": p.fecha_prestamo,
                                "fecha_vencimiento": p.fecha_vencimiento,
                                "estado": p.estado
                            }
                        })
                    else:
                        msg = f"Préstamo #{p.id} registrado con éxito (Ejemplar #{p.ejemplar_id}, vence {p.fecha_vencimiento})"
                        self.send_response(303)
                        self.send_header("Location", f"/libro?id={libro_id}&msg={parse_qs_quote(msg)}")
                        self.end_headers()

                elif u.path in ("/devolver", "/api/devolver"):
                    prestamo_id = int(data.get("prestamo_id", 0))
                    res = bib.devolver(prestamo_id)
                    if is_json or u.path.startswith("/api/"):
                        self._responder_json(200, {"ok": True, "resultado": res})
                    else:
                        msg = f"Préstamo #{prestamo_id} devuelto. Ejemplar queda en estado '{res['estado_ejemplar']}'"
                        if res.get("atrasado"):
                            msg += " (¡ATRASADO!)"
                        self.send_response(303)
                        self.send_header("Location", f"/devolver?msg={parse_qs_quote(msg)}")
                        self.end_headers()

                elif u.path in ("/reservar", "/api/reservar"):
                    socio_id = int(data.get("socio_id", 0))
                    libro_id = int(data.get("libro_id", 0))
                    rid = bib.reservar(socio_id, libro_id)
                    if is_json or u.path.startswith("/api/"):
                        self._responder_json(200, {"ok": True, "reserva_id": rid})
                    else:
                        msg = f"Reserva #{rid} registrada con éxito"
                        self.send_response(303)
                        self.send_header("Location", f"/libro?id={libro_id}&msg={parse_qs_quote(msg)}")
                        self.end_headers()
                elif u.path in ("/socios", "/api/socios"):
                    sid = bib.crear_socio(
                        str(data.get("codigo", "")), str(data.get("nombre", "")),
                        tipo=data.get("tipo") or "estudiante",
                        email=data.get("email") or None)
                    if is_json or u.path.startswith("/api/"):
                        self._responder_json(200, {"ok": True, "socio_id": sid})
                    else:
                        msg = f"Socio #{sid} registrado: {data.get('nombre')}"
                        self.send_response(303)
                        self.send_header("Location", f"/socios?msg={parse_qs_quote(msg)}")
                        self.end_headers()
                else:
                    if is_json or u.path.startswith("/api/"):
                        self._responder_json(404, {"ok": False, "error": "ruta no encontrada"})
                    else:
                        self._responder_html(404, "<div class=\"error\">Ruta no encontrada</div>")

            except (BibliotecaError, ValueError) as exc:
                if is_json or u.path.startswith("/api/"):
                    self._responder_json(400, {"ok": False, "error": str(exc)})
                else:
                    lid = data.get("libro_id")
                    if lid and u.path == "/prestar":
                        self.send_response(303)
                        self.send_header("Location", f"/libro?id={lid}&err={parse_qs_quote(str(exc))}")
                        self.end_headers()
                    elif u.path == "/devolver":
                        self.send_response(303)
                        self.send_header("Location", f"/devolver?err={parse_qs_quote(str(exc))}")
                        self.end_headers()
                    elif u.path == "/socios":
                        self.send_response(303)
                        self.send_header("Location", f"/socios?err={parse_qs_quote(str(exc))}")
                        self.end_headers()
                    else:
                        self._responder_html(400, f"<div class=\"error\">{html.escape(str(exc))}</div>")


def parse_qs_quote(texto: str) -> str:
    from urllib.parse import quote_plus
    return quote_plus(texto)


class BibliotecaServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, db_path: str):
        super().__init__(server_address, RequestHandlerClass)
        self.db_path = db_path


def crear_servidor(host: str = "127.0.0.1", port: int = 8080, db_path: str = str(DB_DEFAULT)) -> BibliotecaServer:
    return BibliotecaServer((host, port), BibliotecaWebHandler, db_path=db_path)


def main():
    parser = argparse.ArgumentParser(description="Servidor web del sistema de biblioteca")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default=str(DB_DEFAULT))
    args = parser.parse_args()

    servidor = crear_servidor(host=args.host, port=args.port, db_path=args.db)
    print(f"Servidor de biblioteca web escuchando en http://{args.host}:{args.port} (DB: {args.db})")
    print("Presiona Ctrl+C para detener.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo servidor...")
    finally:
        servidor.server_close()
        print("Servidor apagado.")


if __name__ == "__main__":
    main()
