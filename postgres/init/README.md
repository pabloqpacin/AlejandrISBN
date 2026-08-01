# Postgres first-boot scripts

Anything here is mounted to `/docker-entrypoint-initdb.d/` and runs **only when the data volume is empty**.

Add `.sql` or `.sh` files for one-shot setup (extensions, dumps, etc.).

Day-to-day book imports belong in `../seed/` (JSON/SQL applied by the API).
