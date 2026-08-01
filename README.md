# AlejandrISBN

Inventario lean de biblioteca: guarda libros por ISBN y completa título, autor, año, género y más desde catálogos públicos (Open Library + Google Books).

## Stack

- **API:** FastAPI
- **DB:** PostgreSQL 16 (volumen Docker `alejandrisbn_pgdata`)
- **Frontend:** HTML / CSS / JS servido por la misma app

## Arranque (Docker)

```bash
cp .env.example .env   # opcional; cambia POSTGRES_PASSWORD
docker compose up --build -d
```

Abre http://localhost:8000

Los datos viven en el volumen nombrado `alejandrisbn_pgdata` (no se borran con `docker compose down`).

```bash
docker compose down          # para contenedores, conserva el volumen
docker compose down -v       # ¡borra también Postgres!
```

## Arranque (local)

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
| `POST` | `/api/books` | Añadir por ISBN → lookup online + guardar |
| `PATCH` | `/api/books/{isbn}` | Actualizar campos |
| `DELETE` | `/api/books/{isbn}` | Eliminar |
| `GET` | `/api/lookup/{isbn}` | Preview sin guardar |

### Ejemplo POST

```bash
curl -X POST http://localhost:8000/api/books \
  -H 'Content-Type: application/json' \
  -d '{"isbn":"9780143127550","notes":"Estantería A1"}'
```

## Columnas

`isbn`, `title`, `authors`, `publication_year`, `genre`, `publisher`, `cover_url`, `description`, `location`, `notes`, `source`, `created_at`, `updated_at`
