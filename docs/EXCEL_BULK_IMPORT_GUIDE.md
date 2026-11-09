# Excel Bulk Import Guide — Categories, Units & Items

This guide covers populating the three master tables (`categories`, `units`, `items`)
from Excel files using a one-time import script.

---

## How the System Works (Quick Reference)

| Table | Model | Key constraints |
|---|---|---|
| `categories` | `app/models/category.py` | `code` unique; `type` must be `CONSUMABLE` or `ASSET` only |
| `units` | `app/models/unit.py` | `code` unique |
| `items` | `app/models/item.py` | `code` unique; `name+category_id` unique; FK to both `categories` and `units` |

Rules enforced by `MasterAdminService` (and the DB itself):

- `category.type` → only `CONSUMABLE` or `ASSET` (never `MATERIAL`)
- `category.code`, `unit.code`, and `item.code` are **immutable after creation**
- `item.name` must be unique **within the same category**
- Items reference categories/units by **code** in Excel; the script resolves to integer IDs

---

## Excel File Formats

### 1 — `categories.xlsx`

> Only two valid types exist: `CONSUMABLE` and `ASSET`.

| Column | Type | Required | Rules |
|---|---|---|---|
| `code` | Text | ✅ | Max 30 chars. Unique. Immutable after first import. |
| `name` | Text | ✅ | Max 100 chars. |
| `type` | Text | ✅ | Must be exactly `CONSUMABLE` or `ASSET` (case-insensitive; stored uppercase). |
| `description` | Text | ❌ | Optional free text. |
| `is_active` | TRUE/FALSE | ❌ | Defaults to `TRUE` if omitted. |

**Example rows:**

| code | name | type | description | is_active |
|---|---|---|---|---|
| CONSUMABLE | Consumable | CONSUMABLE | Day-to-day consumable items | TRUE |
| ASSET | Asset | ASSET | Capital assets and equipment | TRUE |

---

### 2 — `units.xlsx`

| Column | Type | Required | Rules |
|---|---|---|---|
| `code` | Text | ✅ | Max 30 chars. Unique. Immutable after first import. |
| `name` | Text | ✅ | Max 100 chars. |
| `symbol` | Text | ❌ | Max 20 chars. E.g. `kg`, `L`, `Nos`. |
| `decimal_allowed` | TRUE/FALSE | ❌ | `TRUE` for weight/volume/length; `FALSE` for countable items. Defaults `FALSE`. |
| `is_active` | TRUE/FALSE | ❌ | Defaults to `TRUE` if omitted. |

**Example rows:**

| code | name | symbol | decimal_allowed | is_active |
|---|---|---|---|---|
| NOS | Numbers | Nos | FALSE | TRUE |
| KG | Kilogram | kg | TRUE | TRUE |
| LTR | Litre | L | TRUE | TRUE |
| REAM | Ream | ream | FALSE | TRUE |
| BOX | Box | box | FALSE | TRUE |
| METER | Meter | m | TRUE | TRUE |
| PKT | Packet | pkt | FALSE | TRUE |
| PRS | Pairs | prs | FALSE | TRUE |
| SET | Set | set | FALSE | TRUE |
| ROLL | Roll | roll | FALSE | TRUE |

---

### 3 — `items.xlsx`

> **`category_code` and `unit_code`** must match `code` values already in the database
> (or imported earlier in the same run). The script resolves these to the integer
> foreign-key IDs (`category_id`, `unit_id`) before inserting — **do not put IDs in the Excel**.

| Column | Type | Required | Rules |
|---|---|---|---|
| `code` | Text | ✅ | Max 50 chars. Unique across all items. Immutable after first import. |
| `name` | Text | ✅ | Max 255 chars. Must be unique within the same category. |
| `category_code` | Text | ✅ | Must match `code` in `categories` table. |
| `unit_code` | Text | ✅ | Must match `code` in `units` table. |
| `specification` | Text | ❌ | Optional technical specification. |
| `remarks` | Text | ❌ | Optional remarks. |
| `is_active` | TRUE/FALSE | ❌ | Defaults to `TRUE` if omitted. |

**Example rows:**

| code | name | category_code | unit_code | specification | remarks | is_active |
|---|---|---|---|---|---|---|
| CON-PEN-01 | Ball Point Pen (Blue) | CONSUMABLE | BOX | Reynolds 045 | | TRUE |
| CON-PAP-A4 | A4 Printing Paper | CONSUMABLE | REAM | 75 GSM, 500 sheets | | TRUE |
| CON-INK-001 | Printer Ink Cartridge | CONSUMABLE | NOS | HP 803 Black | | TRUE |
| AST-CMP-001 | Desktop Computer | ASSET | NOS | Core i5, 8GB RAM | | TRUE |
| AST-PRN-001 | Laser Printer | ASSET | NOS | HP LaserJet M107w | | TRUE |

---

## Import Order

```
1. categories.xlsx  ──►  2. units.xlsx  ──►  3. items.xlsx
```

Items have foreign keys to both categories and units, so categories and units **must be
imported (and flushed) before** items are inserted.

---

## Import Script

Create `scripts/import_master_excel.py`:

```python
"""
One-time bulk import of Categories, Units, and Items from Excel files.

Usage:
    python scripts/import_master_excel.py

Place the three Excel files in a data/ directory at the project root before running:
    data/categories.xlsx
    data/units.xlsx
    data/items.xlsx

Requires: pip install openpyxl
"""
import asyncio
import sys

import openpyxl
from sqlalchemy import select

from app.db.session import AsyncSessionLocal, engine
from app.models import Category, Item, Unit


def _load_sheet(path: str):
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    return headers, ws


async def import_categories(session, path: str) -> int:
    headers, ws = _load_sheet(path)
    inserted = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        data = {k: v for k, v in zip(headers, row) if k is not None}
        code = str(data.get("code") or "").strip()
        if not code:
            continue
        type_ = str(data.get("type") or "").strip().upper()
        if type_ not in {"CONSUMABLE", "ASSET"}:
            print(f"  SKIP category '{code}': type must be CONSUMABLE or ASSET, got '{type_}'")
            continue
        data["type"] = type_
        existing = await session.scalar(select(Category).where(Category.code == code))
        if existing is not None:
            print(f"  SKIP category '{code}': already exists")
            continue
        is_active = data.get("is_active")
        if is_active is None:
            data["is_active"] = True
        session.add(Category(**data))
        inserted += 1
    return inserted


async def import_units(session, path: str) -> int:
    headers, ws = _load_sheet(path)
    inserted = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        data = {k: v for k, v in zip(headers, row) if k is not None}
        code = str(data.get("code") or "").strip()
        if not code:
            continue
        existing = await session.scalar(select(Unit).where(Unit.code == code))
        if existing is not None:
            print(f"  SKIP unit '{code}': already exists")
            continue
        if data.get("decimal_allowed") is None:
            data["decimal_allowed"] = False
        if data.get("is_active") is None:
            data["is_active"] = True
        session.add(Unit(**data))
        inserted += 1
    return inserted


async def import_items(session, path: str) -> int:
    # Resolve codes → integer FK IDs from the live database
    cat_map  = {c.code: c.id for c in (await session.scalars(select(Category))).all()}
    unit_map = {u.code: u.id for u in (await session.scalars(select(Unit))).all()}

    headers, ws = _load_sheet(path)
    inserted = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        data = {k: v for k, v in zip(headers, row) if k is not None}
        code = str(data.get("code") or "").strip()
        if not code:
            continue

        # Resolve category_code → category_id
        cat_code = str(data.pop("category_code") or "").strip()
        unit_code = str(data.pop("unit_code") or "").strip()
        category_id = cat_map.get(cat_code)
        unit_id = unit_map.get(unit_code)

        if category_id is None:
            print(f"  SKIP item '{code}': category code '{cat_code}' not found")
            continue
        if unit_id is None:
            print(f"  SKIP item '{code}': unit code '{unit_code}' not found")
            continue

        existing = await session.scalar(select(Item).where(Item.code == code))
        if existing is not None:
            print(f"  SKIP item '{code}': already exists")
            continue

        if data.get("is_active") is None:
            data["is_active"] = True

        session.add(Item(
            **data,
            category_id=category_id,
            unit_id=unit_id,
            is_temporary=False,
        ))
        inserted += 1
    return inserted


async def main():
    cat_path  = "data/categories.xlsx"
    unit_path = "data/units.xlsx"
    item_path = "data/items.xlsx"

    async with AsyncSessionLocal() as session:
        print("Importing categories...")
        n = await import_categories(session, cat_path)
        await session.flush()
        print(f"  → {n} categories inserted")

        print("Importing units...")
        n = await import_units(session, unit_path)
        await session.flush()
        print(f"  → {n} units inserted")

        print("Importing items...")
        n = await import_items(session, item_path)
        print(f"  → {n} items inserted")

        await session.commit()
        print("Import complete.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Pre-requisites & Run Instructions

> **Run migrations and seed first.**
> `python scripts/seed.py` must have been executed before this import —
> it sets up roles, financial year, offices, and stores.

```powershell
# 1. Install openpyxl (one-time admin utility — not a runtime dependency)
.\venv\Scripts\Activate.ps1
pip install openpyxl

# 2. Place Excel files in the data/ directory
mkdir data
# copy categories.xlsx, units.xlsx, items.xlsx into data\

# 3. Run from project root
cd f:\project\central_store_V2
python scripts/import_master_excel.py
```

---

## Key Business Rules Checklist

| Rule | How handled in script |
|---|---|
| `category.type` only `CONSUMABLE` or `ASSET` | Validated; row skipped with message if invalid |
| Duplicate `code` → skip, never update | Codes are immutable; existing rows are always skipped |
| `item.name` unique within category | DB constraint `uq_items_name_category` catches duplicates at commit |
| `is_temporary=False` on all imported items | Set explicitly on every `Item()` constructor call |
| Categories and units flushed before items | `await session.flush()` called after each group |
| Entire run is one transaction | Single `session.commit()` at the end; any error rolls back all |
| Excel uses human-readable codes for FKs | `category_code`/`unit_code` resolved to integer IDs via lookup maps |

