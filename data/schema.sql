
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
