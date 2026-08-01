# Database bootstrap & seeds

## First boot (empty Postgres volume)

Files in `postgres/init/` are mounted into `/docker-entrypoint-initdb.d/`.
Postgres runs them **only once**, when the volume is created.

Use for extensions, roles, or a full `.sql` dump.

```bash
docker compose down -v   # destroys volume — careful
docker compose up -d
```

## Everyday seeds (JSON / SQL)

Drop files into `seed/`:

| File | Effect |
|------|--------|
| `something.json` | Inserts books (`ON CONFLICT DO NOTHING`) |
| `something.sql` | Runs SQL statements |

Ignored: `*.example.json`, `*.example.sql`

On API startup, each file is applied if it is new or its contents changed (tracked in `schema_seeds`).

```bash
cp seed/books.example.json seed/books.json
# edit seed/books.json
docker compose restart alejandrisbn
```

JSON shape: array of books, or `{ "books": [ ... ] }`.
Required fields: `isbn`, `title`. Optional: `authors`, `publication_year`, `genre`, `publisher`, `cover_url`, `description`, `location`, `notes`, `source`.
