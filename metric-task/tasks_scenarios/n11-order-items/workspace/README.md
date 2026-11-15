# orderdesk-db

Schema and seed data for the order desk. Production is PostgreSQL; local development and CI replay the same
migrations on SQLite with `migrate.py`.

```sh
python3 migrate.py --check            # replay all migrations on a scratch database
python3 migrate.py --db dev.db        # create or upgrade a local database
python3 migrate.py --db dev.db --status
```

## Writing a migration

- Add the next number: `migrations/NNNN_short_name.sql`. Numbers are contiguous; `--check` fails on a gap.
- Never edit an applied migration. `migrate.py` records a checksum and refuses a changed file.
- A file runs as one transaction with `PRAGMA foreign_keys = ON`. Do not write BEGIN/COMMIT yourself.
- SQLite cannot drop a column that an index or a foreign key uses. Rebuild the table instead; 0011 shows the
  pattern: a `-- migrate: foreign_keys=off` line (enforcement cannot be switched inside the transaction), create
  the new table, copy, drop, rename, recreate indexes. `migrate.py` runs the foreign key check before commit.
- Seed data lives in the migration that creates the table, or in a later `*_seed.sql` file.

## Roles

PostgreSQL roles are declared in the migrations and checked locally:

```sql
CREATE ROLE <name> LOGIN PASSWORD '<password>' GRANT SELECT (col, ...) ON <table>, UPDATE (col) ON <table>;
ALTER ROLE <name> GRANT SELECT (col, ...) ON <table>;
ALTER ROLE <name> REVOKE SELECT (col, ...) ON <table>;
DROP ROLE <name>;
```

After every migration each granted column must exist. When a column moves to another table, move its grants in
the same migration so that the role keeps the access it had.

## Open work

- ORD-412: line items still live on `orders` (first line in `sku`/`quantity`/`unit_price_cents`, further lines
  as a JSON array in `extra_items`, see 0008). Split them into an `order_items` table.
