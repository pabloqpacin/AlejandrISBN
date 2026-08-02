# AlejandrISBN

Inventario lean de biblioteca: guarda libros por ISBN y completa título, autor, año, género y más desde catálogos públicos (Open Library + Google Books).

**Licencia:** MIT · **Self-host:** [guía Windows (usuarios no técnicos)](docs/SELFHOSTING.md) · **Release/CI:** [docs/RELEASE.md](docs/RELEASE.md)

## Stack

- **API:** FastAPI + Uvicorn
- **DB:** PostgreSQL 16 (volumen Docker `alejandrisbn_pgdata`)
- **Frontend:** HTML / CSS / JS vanilla, servido por la misma API (`/` y `/static`)

## Arranque rápido (Docker)

### Windows (recomendado si no programas)

1. Instala [Docker Desktop](https://www.docker.com/products/docker-desktop/) y [Git](https://git-scm.com/download/win)
2. Clona el repo y entra en la carpeta
3. Doble clic en `start.bat`

Detalle paso a paso: **[docs/SELFHOSTING.md](docs/SELFHOSTING.md)**

### Cualquier SO (terminal)

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
