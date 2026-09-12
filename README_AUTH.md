# Authentication / RBAC milestone

## Install

After activating the existing V2 virtual environment:

```cmd
pip install -e .
```

Add `JWT_SECRET_KEY` to `.env`. Generate a strong random value for real use. `CSMS_DEV_PASSWORD` is for local development only.

## Set development passwords

Command Prompt:

```cmd
set CSMS_DEV_PASSWORD=DevOnly123!
python scripts\set_dev_passwords.py
```

PowerShell:

```powershell
$env:CSMS_DEV_PASSWORD="DevOnly123!"
python scripts\set_dev_passwords.py
```

## Run

```cmd
uvicorn app.main:app --reload
```

Open `/docs`, authorize using the development username/password, then call `/api/auth/me`.

## Important

The existing transaction test endpoints still use `actor_id` for backward-compatible development testing. The next integration step is to replace that client-supplied actor with the authenticated user dependency module-by-module. Do not expose `actor_id` as a trusted production identity field.
