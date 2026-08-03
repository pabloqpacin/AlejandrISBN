# AlejandrISBN

Inventario lean de biblioteca y multimedia: libros, revistas, CDs, DVDs, VHS y cassettes. Los libros/revistas pueden darse de alta por ISBN (metadatos online); el resto es alta manual.

**Licencia:** MIT · **Self-host:** [guía Windows (usuarios no técnicos)](docs/SELFHOSTING.md) · **Release/CI:** [docs/RELEASE.md](docs/RELEASE.md)

## Stack

- **API:** FastAPI + Uvicorn
- **DB:** PostgreSQL 16 (Docker) **o** SQLite (modo escritorio / PCs modestos)
- **Frontend:** HTML / CSS / JS vanilla, servido por la misma API (`/` y `/static`)

## Modelo

Cada registro es un **ítem** con `id` UUID. El campo `isbn` es opcional y único (solo libros/revistas). Al arrancar, si existe la tabla legacy `books`, se migra automáticamente a `items` (los `LOCAL-*` pasan a `isbn = null`).

Tipos (`media_type`): `book`, `magazine`, `cd`, `dvd`, `vhs`, `cassette`.

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
- **Restaurar inventario:** en la UI, **Importar** (JSON/CSV exportado). Acepta el formato nuevo `{"items":[…]}` y el legacy `{"books":[…]}`. Luego **Completar online** si quieres rellenar vacíos (solo ítems con ISBN).

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
| `GET` | `/api/stats` | Totales por tipo y por ubicación |
| `GET` | `/api/items?q=&media_type=` | Listar / buscar |
| `GET` | `/api/items/{id}` | Detalle |
| `POST` | `/api/items` | Alta (ISBN lookup solo `book`/`magazine`; resto manual) |
| `PATCH` | `/api/items/{id}` | Actualizar campos |
| `DELETE` | `/api/items/{id}` | Eliminar |
| `POST` | `/api/items/batch/delete` | Borrado masivo (`ids`) |
| `POST` | `/api/items/batch/update` | Actualización masiva (`ids` + `fields`) |
| `GET` | `/api/export/items?format=json\|csv` | Descargar inventario |
| `POST` | `/api/import/items` | Importar JSON/CSV (multipart `file`) |
| `POST` | `/api/enrich/preview` | Sugerencias online para campos vacíos (`ids`) |
| `POST` | `/api/enrich/apply` | Aplicar campos confirmados |
| `GET` | `/api/lookup/{isbn}` | Preview ISBN sin guardar |

Las rutas legacy `/api/export/books` y `/api/import/books` siguen redirigidas al flujo de ítems.

### Ejemplo POST

```bash
# Libro por ISBN
curl -X POST http://localhost:8000/api/items \
  -H 'Content-Type: application/json' \
  -d '{"media_type":"book","isbn":"9780143127550","notes":"Estantería A1"}'

# CD manual
curl -X POST http://localhost:8000/api/items \
  -H 'Content-Type: application/json' \
  -d '{"media_type":"cd","title":"Nevermind","authors":"Nirvana","location":"Caja 1"}'
```

## Columnas

`id`, `media_type`, `isbn`, `title`, `authors`, `publication_year`, `genre`, `publisher`, `room`, `furniture`, `location` (compuesto), `notes`, `legal_deposit`, `collection`, `volume`, `favourite`, `source`, `created_at`, `updated_at`
