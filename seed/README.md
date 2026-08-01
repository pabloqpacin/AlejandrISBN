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
| `something.json` | Writes book rows **directly** to the DB (`ON CONFLICT DO NOTHING`) |
| `something.csv` | **Online ISBN lookup** for each row, then insert (optional overrides) |
| `something.sql` | Runs SQL statements |

Ignored: `*.example.json`, `*.example.sql`, `*.example.csv`

On API startup, each file is applied if it is new or its contents changed (tracked in `schema_seeds`).

```bash
# Full metadata already known → JSON
cp seed/books.example.json seed/books.json

# Only ISBNs (and maybe location/notes) → CSV looks up catalogs online
cp seed/books.example.csv seed/books.csv

docker compose restart alejandrisbn
```

### JSON

Shape: array of books, or `{ "books": [ ... ] }`.

Required: `isbn`, `title`.  
Optional: `authors`, `publication_year`, `genre`, `publisher`, `cover_url`, `description`, `location`, `notes`, `favourite`, `source`.

No network calls — values go straight into Postgres.

### CSV

Header row required. Only `isbn` is required — the API looks up the rest online.

```csv
isbn
9780143127550
9788490000000
```

You may include a `title` column as a provisional label; **the online lookup always overwrites it** (same for authors, year, publisher, cover, description).

Optional columns that *do* stick after lookup: `location`, `notes`, `genre`, `favourite`, `source`.

```csv
isbn,title,location,notes
9780143127550,borrador cualquiera,A1,Donación
```

For each row the API:

1. Skips if the ISBN is already in the inventory
2. Looks up metadata online (same catalogs as the UI)
3. Applies library-field overrides from the CSV (`location`, `notes`, …)
4. Inserts the book with the catalog title

Rows that fail lookup are logged and skipped; the file is still marked applied. Edit the CSV (change contents) and restart to re-run.
