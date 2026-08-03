# Database bootstrap & seeds

## First boot (empty Postgres volume)

Files in `postgres/init/` are mounted into `/docker-entrypoint-initdb.d/`.
Postgres runs them **only once**, when the volume is created.

Use for extensions, roles, or a full `.sql` dump.

```bash
docker compose down -v   # destroys volume — careful
docker compose up -d
```

## Everyday seeds (JSON / CSV / SQL)

Drop files into `seed/`:

| File | Effect |
|------|--------|
| `something.json` | Writes book rows **directly** (`ON CONFLICT DO NOTHING`) — **no network** |
| `something.csv` | Same offline insert as UI Import — **no network** |
| `something.sql` | Runs SQL statements |

Ignored: `*.example.json`, `*.example.sql`, `*.example.csv`

On API startup, each file is applied if it is new or its contents changed (tracked in `schema_seeds`).

To fill missing bibliographic fields from catalogs later, use **Completar online** in the UI
(`POST /api/enrich/preview` → confirm → `POST /api/enrich/apply`).

```bash
cp seed/books.example.json seed/books.json
# o: cp seed/books.example.csv seed/books.csv
docker compose restart alejandrisbn
```

### Shared optional fields

`location`, `notes`, `genre`, `favourite`, `legal_deposit` (alias `deposito_legal`), `source`.

Use `n/a` (or blank) when a field does not apply — stored as empty.

### JSON

Shape: array of books, or `{ "books": [ ... ] }`.

- With ISBN: `isbn` + `title` (rest optional)
- Without ISBN: omit `isbn` or set `"isbn": "n/a"` + `title` (+ usually `legal_deposit`)

No network calls — values go straight into the DB. Missing ISBN → auto `LOCAL-…` id.

### CSV

Header row required. Each row needs a usable `isbn` **or** a `title`.

```csv
isbn,title,authors,legal_deposit,location,favourite
9780143127550,Some title,Some author,n/a,A1,false
n/a,Persecución y asesinato de Jean-Paul Marat,,B. 7528-1969,A1,true
```

Rows that fail to parse are skipped; the file is still marked applied. Edit the CSV and restart to re-run.
