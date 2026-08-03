# AlejandrISBN

Inventario lean de biblioteca: guarda libros por ISBN y completa título, autor, año, género y más desde catálogos públicos (Open Library + Google Books).

**Licencia:** MIT · **Self-host:** [guía Windows (usuarios no técnicos)](docs/SELFHOSTING.md) · **Release/CI:** [docs/RELEASE.md](docs/RELEASE.md)

## Stack

- **API:** FastAPI + Uvicorn
- **DB:** PostgreSQL 16 (Docker) **o** SQLite (modo escritorio / PCs modestos)
- **Frontend:** HTML / CSS / JS vanilla, servido por la misma API (`/` y `/static`)

## Arranque rápido

### Windows — PCs modestos (recomendado, sin Docker)

1. Instala [Python 3.11+](https://www.python.org/downloads/) (*Add to PATH*)
2. Carpeta del repo (`git clone` o ZIP)
3. Doble clic en **`start-desktop.bat`** → http://127.0.0.1:8000

Datos en `%LOCALAPPDATA%\AlejandrISBN\alejandrisbn.db`. Guía: **[docs/SELFHOSTING.md](docs/SELFHOSTING.md)**

### Windows — Docker (≥8 GB RAM)

1. (PC nuevo) `setup-windows.bat` → Brave, Git, Docker Desktop
2. Abre Docker Desktop y doble clic en `start.bat`

### Cualquier SO (Docker)

```bash
git clone https://github.com/pabloqpacin/AlejandrISBN.git
cd AlejandrISBN
cp .env.example .env   # opcional; cambia POSTGRES_PASSWORD
docker compose up --build -d
```

Abre http://localhost:8000

Los datos viven en el volumen nombrado `alejandrisbn_pgdata` (no se borran con `docker compose down`).

```bash
docker compose down          # para contenedores, conserva el volumen
docker compose down -v       # ¡borra también Postgres!
```

En Windows también: `stop.bat` / `update.bat`.

### Escritorio local (SQLite, cualquier SO)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ALEJANDRISBN_BACKEND=sqlite   # Windows: set ALEJANDRISBN_BACKEND=sqlite
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Seeds / bootstrap DB

- **Primer arranque del volumen:** SQL en `postgres/init/` (entrypoint oficial de Postgres).
- **Día a día:** deja `*.json`, `*.csv` o `*.sql` en `seed/` → la API los aplica al arrancar (idempotente por checksum).
  - **JSON** → escribe filas directamente en la DB
  - **CSV** → lookup online por cada ISBN, luego inserta (puedes pasar `location`, `notes`, etc.)

Ver `seed/README.md`.

```bash
cp seed/books.example.json seed/books.json
# o: cp seed/books.example.csv seed/books.csv
docker compose restart alejandrisbn
```

## Arranque (local, desarrollo)

Necesitas Postgres accesible y `DATABASE_URL`:

```bash
export DATABASE_URL=postgresql://alejandrisbn:alejandrisbn@localhost:5432/alejandrisbn
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Docs: http://localhost:8000/docs

## API

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/books?q=` | Listar / buscar |
| `GET` | `/api/books/{isbn}` | Detalle |
| `POST` | `/api/books` | Añadir por ISBN (lookup) o sin ISBN (`title` obligatorio) |
| `PATCH` | `/api/books/{isbn}` | Actualizar campos |
| `DELETE` | `/api/books/{isbn}` | Eliminar |
| `GET` | `/api/export/books?format=json\|csv` | Descargar inventario (JSON seed o CSV) |
| `GET` | `/api/lookup/{isbn}` | Preview sin guardar |

### Ejemplo POST

```bash
curl -X POST http://localhost:8000/api/books \
  -H 'Content-Type: application/json' \
  -d '{"isbn":"9780143127550","notes":"Estantería A1"}'
```

## Columnas

`isbn`, `title`, `authors`, `publication_year`, `genre`, `publisher`, `cover_url`, `description`, `location`, `notes`, `legal_deposit`, `favourite`, `source`, `created_at`, `updated_at`
