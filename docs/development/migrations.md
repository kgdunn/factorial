# Database Migrations

Migrations are managed with [Alembic](https://alembic.sqlalchemy.org) and run from the `backend/` directory.

## Apply Migrations

```bash
make migrate
```

## Create a New Migration

After modifying SQLAlchemy models in `backend/src/app/models/`:

```bash
cd backend && uv run alembic revision --autogenerate -m "description of change"
```

Then apply:

```bash
make migrate
```

## Notes

- All SQLAlchemy models inherit from `app.db.base.Base`
- PostgreSQL for structured/relational data (experiments, users, results)
- Neo4j for knowledge graph (entity relationships, domain ontology) — not managed by Alembic
