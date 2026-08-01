# AlejandrISBN

Inventario lean de biblioteca: guarda libros por ISBN y completa título, autor, año, género y más desde catálogos públicos (Open Library + Google Books).

## Stack

- **API:** FastAPI
- **DB:** SQLite (`data/alejandrisbn.db`)
- **Frontend:** HTML / CSS / JS servido por la misma app

## Arranque

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Abre http://localhost:8000

Docs interactivas: http://localhost:8000/docs

## API

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/books?q=` | Listar / buscar (título, autor, ISBN, género, editorial, notas) |
| `GET` | `/api/books/{isbn}` | Detalle |
| `POST` | `/api/books` | Añadir por ISBN → lookup online + guardar |
| `PATCH` | `/api/books/{isbn}` | Actualizar campos |
| `DELETE` | `/api/books/{isbn}` | Eliminar |
| `GET` | `/api/lookup/{isbn}` | Preview de metadatos sin guardar |

### Ejemplo POST

```bash
curl -X POST http://localhost:8000/api/books \
  -H 'Content-Type: application/json' \
  -d '{"isbn":"9780143127550","notes":"Estantería A1"}'
```

## Columnas

`isbn`, `title`, `authors`, `publication_year`, `genre`, `publisher`, `cover_url`, `description`, `notes`, `source`, `created_at`, `updated_at`
