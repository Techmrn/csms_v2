"""Exact unit arithmetic and display formatting for Paper Warehouse commodities.

Sheet/Ream paper (form_type == 'SHEET') is stored and calculated strictly as
exact integer total_sheets, formatted as Reams + Loose Sheets using
item.sheets_per_ream (default 500).

Reel paper (form_type == 'REEL') is stored and calculated strictly in
kilograms (weight_kg, Numeric(18, 3)).
"""
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException


def to_total_sheets(reams: int, sheets: int, sheets_per_ream: int = 500) -> int:
    if sheets_per_ream <= 0:
        raise HTTPException(422, "sheets_per_ream must be positive")
    if reams < 0 or sheets < 0:
        raise HTTPException(422, "Reams and sheets cannot be negative")
    return int(reams) * int(sheets_per_ream) + int(sheets)


def from_total_sheets(total_sheets: int, sheets_per_ream: int = 500) -> tuple[int, int]:
    spr = int(sheets_per_ream) if sheets_per_ream and sheets_per_ream > 0 else 500
    total = int(total_sheets or 0)
    if total < 0:
        sign = -1
        reams, loose = divmod(abs(total), spr)
        return sign * reams, sign * loose
    return divmod(total, spr)


def decimal_reams_to_sheets(reams_decimal: Decimal | None, sheets_per_ream: int = 500) -> int:
    if not reams_decimal:
        return 0
    spr = Decimal(sheets_per_ream if sheets_per_ream > 0 else 500)
    return int((Decimal(str(reams_decimal)) * spr).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def sheets_to_decimal_reams(total_sheets: int, sheets_per_ream: int = 500) -> Decimal:
    spr = Decimal(sheets_per_ream if sheets_per_ream > 0 else 500)
    return (Decimal(int(total_sheets or 0)) / spr).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def calc_sheet_weight_kg(
    total_sheets: int, sheets_per_ream: int, weight_per_ream_kg: Decimal | None
) -> Decimal:
    if not total_sheets or not weight_per_ream_kg:
        return Decimal("0.000")
    spr = Decimal(sheets_per_ream if sheets_per_ream > 0 else 500)
    wt = (Decimal(int(total_sheets)) / spr) * Decimal(str(weight_per_ream_kg))
    return wt.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def format_sheet_qty(total_sheets: int, sheets_per_ream: int = 500) -> str:
    total = int(total_sheets or 0)
    if total == 0:
        return "0 Sheets"
    reams, loose = from_total_sheets(total, sheets_per_ream)
    parts = []
    if reams:
        parts.append(f"{reams} {'Ream' if abs(reams) == 1 else 'Reams'}")
    if loose:
        parts.append(f"{loose} {'Sheet' if abs(loose) == 1 else 'Sheets'}")
    return " ".join(parts) if parts else "0 Sheets"


def format_reel_qty(weight_kg: Decimal | float | None) -> str:
    wt = Decimal(str(weight_kg or 0)).quantize(Decimal("0.001"))
    return f"{wt:,.3f} kg"


def format_paper_balance(form_type: str, total_sheets: int, weight_kg: Decimal, sheets_per_ream: int = 500) -> str:
    if form_type == "REEL":
        return format_reel_qty(weight_kg)
    return format_sheet_qty(total_sheets, sheets_per_ream)

