# Me&You Backend

## Local PostgreSQL

From the repository root, start PostgreSQL with `docker compose up -d postgres`. The service exposes port 5432 and stores data in the named `me_you_postgres_data` volume. Copy `.env.example` to `.env` and adjust local settings as needed; the example contains placeholders only.

## Tests

Run the backend suite from any directory with:

```sh
./backend/scripts/test.sh
```

Arguments are forwarded to pytest, for example `./backend/scripts/test.sh -m postgres -q`. Set `PYTHON` to select a Python interpreter; by default the script uses the workspace pytest interpreter when available and otherwise uses `python`.

## Migrations

Set `ME_YOU_DATABASE_URL` to a `postgresql+asyncpg://` URL, then run Alembic from this directory, for example `alembic upgrade head`.