# Guía para ejecutar el sistema de biblioteca en tu computadora

Todo está hecho en Python, solo con la librería estándar: **no hay que instalar
librerías con `pip`**. Necesitas Python y una copia del proyecto.

## 1. Requisitos

| Qué | Versión | Para qué |
|-----|---------|----------|
| Python | 3.10 o más nuevo | Ejecutar el sistema |
| Navegador | Chrome, Edge, Firefox… | Ver la interfaz web |
| Git (opcional) | cualquiera | Descargar el proyecto con `git clone` |

No hace falta internet para usarlo: el catálogo de 4 371 libros ya viene en `data/libros.json`.

## 2. Instalar Python (solo si no lo tienes)

Abre una terminal y escribe:

- **Windows** (PowerShell o "Símbolo del sistema"): `py --version`
- **Mac / Linux**: `python3 --version`

Si responde `Python 3.10` o un número mayor, ya está. Si no:

- **Windows**: descárgalo de <https://www.python.org/downloads/> e instálalo.
  En la primera pantalla del instalador **marca la casilla "Add python.exe to PATH"**.
  Cierra y vuelve a abrir la terminal después de instalar.
- **Mac**: descárgalo de la misma página e instálalo.
- **Linux**: casi siempre ya viene instalado.

> En esta guía, donde dice `python`, usa **`py`** en Windows y **`python3`** en Mac/Linux.

## 3. Descargar el proyecto

**Opción A, sin Git:** en la página del repositorio pulsa **Code → Download ZIP**,
descomprime el archivo y entra en la carpeta `biblioteca-lp-main`.

**Opción B, con Git:**

```bash
git clone https://github.com/ProgramaGrueso/biblioteca-lp.git
cd biblioteca-lp
```

Abre la terminal **dentro de la carpeta del proyecto**. En Windows, entra en la carpeta
desde el Explorador, escribe `powershell` en la barra de dirección y pulsa Enter.

## 4. Crear la base de datos (solo la primera vez)

La base de datos no se sube al repositorio, así que se crea a partir del catálogo:

```bash
python scripts/crear_base.py
python scripts/datos_demo.py
```

El primer comando crea `data/biblioteca.db` con los libros y sus ejemplares. El segundo
agrega 10 socios de prueba, préstamos (algunos vencidos) y una reserva, para que los
reportes no salgan vacíos.

## 5. Abrir la aplicación web

```bash
python -m app.web --port 8080
```

Abre en el navegador: **<http://127.0.0.1:8080>**

Para apagar el servidor, vuelve a la terminal y pulsa **Ctrl + C**.

### Qué probar

1. **Reportes**: los libros más prestados y los 2 préstamos vencidos.
2. **Socios**: registra un socio nuevo y anota su ID.
3. **Buscar catálogo**: busca un libro (por ejemplo "Borges"), entra a su ficha y préstalo
   con el ID del socio.
4. **Devoluciones**: devuelve el préstamo **19** (*Pedro Páramo*). Como hay una reserva
   pendiente, el ejemplar queda "reservado" para quien lo reservó.
5. Devuelve el préstamo **15**, que está vencido: el sistema avisa que está atrasado.

## 6. Correr las pruebas automáticas

```bash
python -m unittest discover -s tests
```

Debe terminar con `OK` (25 pruebas). Las pruebas trabajan sobre una copia de la base,
así que no modifican tus datos.

## 7. Usarlo desde la terminal (opcional)

```bash
python -m app.cli buscar "biología" --limite 5
python -m app.cli reportes
python -m app.cli --help
```

## Problemas frecuentes

| Mensaje | Solución |
|---------|----------|
| `'python' no se reconoce…` | En Windows usa `py`. Si tampoco funciona, reinstala Python marcando "Add python.exe to PATH". |
| `No module named app` | No estás dentro de la carpeta del proyecto. Entra con `cd` a la carpeta que tiene `README.md`. |
| `no existe la base: …biblioteca.db` | Te faltó el paso 4. |
| `Ya existe data/biblioteca.db` | Ya la creaste antes. Para empezar de cero: `python scripts/crear_base.py --forzar` y luego `python scripts/datos_demo.py`. |
| `Address already in use` / puerto ocupado | Ya hay un servidor abierto. Ciérralo con Ctrl + C o usa otro puerto: `--port 8090`. |
