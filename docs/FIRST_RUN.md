# CSMS V2 — First Run on Windows (No Docker)

## 1. Create virtual environment

```cmd
python -m venv venv
venv\Scripts\activate
```

## 2. Install project

```cmd
python -m pip install --upgrade pip
pip install -e .
```

## 3. Configure PostgreSQL

Create a database named:

`csms_v2`

Copy `.env.example` to `.env` and set the PostgreSQL connection string.

Example:

```text
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/csms_v2
```

## 4. Run migrations

```cmd
alembic upgrade head
```

## 5. Seed baseline master/security data

```cmd
python scripts\seed.py
```

## 6. Run application

```cmd
uvicorn app.main:app --reload
```

Open:

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/api/health
- http://127.0.0.1:8000/api/health/db
