# CSMS V2

Clean rebuild of the Central Store Management System based on the approved V2 business architecture.

## Current foundation

- FastAPI
- SQLAlchemy 2.x async ORM
- asyncpg
- PostgreSQL
- Alembic
- Pydantic 2.x
- Store-based stock ownership architecture
- Directorate + Central Store
- Branch Offices + Branch Stores
- Central Press as Branch Office
- Financial Year
- Category: CONSUMABLE / ASSET
- Unit
- Item Master
- InventoryPolicy foundation
- Roles and permissions foundation
- Async database health endpoint
- Working Office/Store/Master endpoints

## Windows setup without Docker

```cmd
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e .
copy .env.example .env
```

Create PostgreSQL database `csms_v2`, then ensure `.env` contains a correct `DATABASE_URL`.

Run migration:

```cmd
alembic upgrade head
```

Seed baseline data:

```cmd
python scripts\seed.py
```

Run:

```cmd
uvicorn app.main:app --reload
```

Open:

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/api/health
- http://127.0.0.1:8000/api/health/db

## Architecture

```text
FastAPI router
    -> schema validation
    -> service
    -> repository
    -> AsyncSession
    -> PostgreSQL
```

Stock mutation must eventually pass through the posting layer. Routers must never write StockMovement directly.
