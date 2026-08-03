# AlejandrISBN

Inventario lean de biblioteca: guarda libros por ISBN y completa título, autor, año, género y más desde catálogos públicos (Open Library + Google Books).

**Licencia:** MIT · **Self-host:** [guía Windows (usuarios no técnicos)](docs/SELFHOSTING.md) · **Release/CI:** [docs/RELEASE.md](docs/RELEASE.md)

## Stack

- **API:** FastAPI + Uvicorn
- **DB:** PostgreSQL 16 (Docker) **o** SQLite (modo escritorio / PCs modestos)
- **Frontend:** HTML / CSS / JS vanilla, servido por la misma API (`/` y `/static`)

## Arranque rápido

### Windows — uso diario (sin Python ni Docker)

1. Descarga **`AlejandrISBN-Setup.exe`** desde [Releases](https://github.com/pabloqpacin/AlejandrISBN/releases)
2. Instálalo → icono en Escritorio; puedes borrar el Setup
3. Cierra la ventanita de la app para salir

Detalle: **[docs/SELFHOSTING.md](docs/SELFHOSTING.md)**

### Cualquier SO — Docker (Postgres)

```bash
git clone https://github.com/pabloqpacin/AlejandrISBN.git
cd AlejandrISBN
cp .env.example .env   # opcional; cambia POSTGRES_PASSWORD
docker compose up --build -d
```

Abre http://localhost:8000

En un PC Windows nuevo puedes instalar Brave + Git + Docker Desktop con `packaging/windows/setup-windows.bat` (solo prerequisitos; el arranque es `docker compose` como arriba).

Los datos viven en el volumen nombrado `alejandrisbn_pgdata` (no se borran con `docker compose down`).

```bash
docker compose down          # para contenedores, conserva el volumen
docker compose down -v       # ¡borra también Postgres!
git pull && docker compose up --build -d   # actualizar
```

### Escritorio local (SQLite, desarrollo)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ALEJANDRISBN_BACKEND=sqlite   # Windows: set ALEJANDRISBN_BACKEND=sqlite
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Bootstrap DB / importar inventario

- **Primer arranque del volumen:** SQL en `postgres/init/` (entrypoint oficial de Postgres).
- **Restaurar inventario:** en la UI, **Importar** (JSON/CSV exportado). Luego **Completar online** si quieres rellenar vacíos.

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
| `GET` | `/api/export/books?format=json\|csv` | Descargar inventario (JSON o CSV) |
| `POST` | `/api/import/books` | Importar JSON/CSV (multipart `file`, sin red) |
| `POST` | `/api/enrich/preview` | Sugerencias online para campos vacíos |
| `POST` | `/api/enrich/apply` | Aplicar campos confirmados |
| `GET` | `/api/lookup/{isbn}` | Preview sin guardar |

### Ejemplo POST

```bash
curl -X POST http://localhost:8000/api/books \
  -H 'Content-Type: application/json' \
  -d '{"isbn":"9780143127550","notes":"Estantería A1"}'
```

## Columnas

`isbn`, `title`, `authors`, `publication_year`, `genre`, `publisher`, `cover_url`, `description`, `location`, `notes`, `legal_deposit`, `favourite`, `source`, `created_at`, `updated_at`
