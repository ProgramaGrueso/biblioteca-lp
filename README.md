# biblioteca — sistema de ejecución de biblioteca

Trabajo grupal del curso **Lenguaje de Programación**. El objetivo es un sistema completo
de biblioteca (préstamos, devoluciones, reservas y estados de ejemplar), en la misma línea
del sistema de citas quirúrgicas que ya trabajamos con el mismo profesor.

Estado actual: **la data**. Todavía no hay app: el catálogo real ya está scrapeado y la base
con el esquema del sistema está armada, lista para montar encima la lógica.

## Estructura

```
biblioteca/
├── scrapers/openlibrary.py   # scraper del catálogo (API pública de Open Library)
├── data/
│   ├── libros.json           # registros normalizados
│   ├── libros.csv            # mismo contenido, plano
│   ├── biblioteca.db         # SQLite: esquema + catálogo + ejemplares
│   └── schema.sql            # solo el esquema (para crear la DB desde cero)
└── README.md
```

Sin dependencias externas: solo librería estándar de Python 3 (urllib, sqlite3, csv).

## Regenerar la data

```bash
python3 scrapers/openlibrary.py --per-subject 100   # ~100 libros por materia (catálogo variado)
python3 scrapers/openlibrary.py --target 2000       # alternativa: tope global
```

El scraper pide `language=spa` y deduplica por la clave de Open Library. Tarda unos minutos
porque respeta la API (0.4 s entre páginas).

## Modelo de datos

- `libros` — título, subtítulo, autores, año de primera edición, editorial, ISBN, idioma,
  materias, páginas, portada, número de ediciones.
- `ejemplares` — copias físicas de cada libro. `codigo` único (ej. `LIB-00042-2`) y
  `estado`: `disponible | prestado | reservado | mantenimiento | baja`.
- `socios` — estudiantes, docentes, administrativos, externos; con `activo` para dar de baja
  sin borrar historial.
- `prestamos` — ejemplar + socio + fecha de préstamo y vencimiento, devolución real y estado
  (`activo | devuelto | vencido | cancelado`).
- `reservas` — por libro (no por ejemplar), con estado (`pendiente | atendida | vencida |
  cancelada`) y expiración.

## Reglas de negocio que el esquema ya soporta

1. No se presta un ejemplar que no esté `disponible`.
2. Un socio no puede tener dos préstamos activos del mismo libro.
3. Una reserva pendiente se convierte en préstamo cuando vuelve un ejemplar.
4. Los préstamos vencidos se marcan por fecha, sin borrar el registro.
5. El ejemplar en `mantenimiento` o `baja` queda fuera de circulación sin perder trazabilidad.

## Siguiente paso

Montar la capa de aplicación en Python sobre `biblioteca.db`: alta de socios, préstamo,
devolución, reserva y reportes (más prestados, vencidos, disponibilidad por materia).

## Núcleo ya implementado

- `app/core.py` — clase `Biblioteca` con la lógica: `prestar`, `devolver`, `reservar`,
  `vencer_prestamos`, `vencer_reservas`, `buscar` y reportes.
- `app/cli.py` — línea de comandos para probarlo sin interfaz:

```bash
python3 -m app.cli buscar "biología" --limite 5
python3 -m app.cli socio-nuevo DEMO-001 "Ana Torres"
python3 -m app.cli prestar 1 2040
python3 -m app.cli devolver 1
python3 -m app.cli reportes
python3 -m app.cli vencer
```

- `tests/test_core.py` — 14 pruebas de las reglas de negocio, con copia temporal de la base:

```bash
python3 -m unittest discover -s tests
```

Reglas ya cubiertas por las pruebas: no prestar sin ejemplar disponible, no repetir libro
con el mismo socio, máximo 3 préstamos activos, devolución que libera o reserva el ejemplar,
atención automática de la reserva pendiente, detección de atrasos y vencimiento masivo.

