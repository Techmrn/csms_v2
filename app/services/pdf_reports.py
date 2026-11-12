"""Official Printing Department PDF report and voucher generator using WeasyPrint."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
import os
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "web" / "templates" / "pdf"
_JINJA_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

SUPPORTED_PAPER_SIZES: dict[str, tuple[str, str, str]] = {
    "a4": ("A4 portrait", "A4 Portrait", "a4_portrait"),
    "a4_portrait": ("A4 portrait", "A4 Portrait", "a4_portrait"),
    "a4_landscape": ("A4 landscape", "A4 Landscape", "a4_landscape"),
    "a3": ("A3 landscape", "A3 Landscape", "a3_landscape"),
    "a3_portrait": ("A3 portrait", "A3 Portrait", "a3_portrait"),
    "a3_landscape": ("A3 landscape", "A3 Landscape", "a3_landscape"),
}

_NUMERIC_KEYS = {
    "balance",
    "quantity",
    "quantity_in",
    "quantity_out",
    "qty",
    "in",
    "out",
    "requested",
    "requested_quantity",
    "issued",
    "issued_quantity",
    "accepted",
    "accepted_quantity",
    "weight_kg",
    "reel_weight_kg",
    "reels",
    "reel_count",
    "reams",
    "ream_count",
    "sheets",
    "sheet_count",
    "loose_sheets",
    "sheets_per_ream",
    "stock_in_kg",
    "stock_in_sheets",
    "gsm",
    "amount",
}

_DOMAIN_THEMES: dict[str, dict[str, str]] = {
    "general": {
        "subsystem_label": "General Store Management System",
        "accent_primary": "#1e40af",
        "accent_dark": "#1e3a8a",
        "accent_soft": "#eff6ff",
        "accent_border": "#bfdbfe",
    },
    "paper": {
        "subsystem_label": "Paper Warehouse Management System",
        "accent_primary": "#b45309",
        "accent_dark": "#78350f",
        "accent_soft": "#fffbeb",
        "accent_border": "#fde68a",
    },
}

_WEASYPRINT_HTML_CLS = None


def _ensure_windows_weasyprint_dlls() -> None:
    """Register GTK/Pango runtime directories on Windows when not explicitly configured."""
    if os.name != "nt":
        return
    configured = os.environ.get("WEASYPRINT_DLL_DIRECTORIES", "").strip()
    if configured:
        dirs = [d for d in configured.split(";") if d and os.path.isdir(d)]
    else:
        candidates = [
            r"C:\msys64\ucrt64\bin",
            r"C:\msys64\mingw64\bin",
            r"C:\Program Files\GTK3-Runtime Win64\bin",
            r"C:\Program Files\GIMP 3\bin",
        ]
        dirs = [d for d in candidates if os.path.isfile(os.path.join(d, "libpango-1.0-0.dll"))]
        if dirs:
            os.environ["WEASYPRINT_DLL_DIRECTORIES"] = ";".join(dirs)

    if hasattr(os, "add_dll_directory"):
        for d in dirs:
            try:
                os.add_dll_directory(d)
            except OSError:
                pass


def _get_weasyprint_html():
    global _WEASYPRINT_HTML_CLS
    if _WEASYPRINT_HTML_CLS is None:
        _ensure_windows_weasyprint_dlls()
        from weasyprint import HTML  # pylint: disable=import-outside-toplevel

        _WEASYPRINT_HTML_CLS = HTML
    return _WEASYPRINT_HTML_CLS


def _css_str(value: Any) -> str:
    """Escape text safely for use inside CSS quoted string values."""
    text = str(value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\r", " ").replace("\n", " ")
    return text.strip()


def _is_numeric_col(key: str, label: str) -> bool:
    low_key = str(key or "").strip().lower()
    low_label = str(label or "").strip().lower()
    if low_key in _NUMERIC_KEYS:
        return True
    if low_key.endswith(("_qty", "_quantity", "_kg", "_sheets", "_reams", "_count")):
        return True
    if low_label in {"balance", "qty", "quantity", "in", "out", "kg", "sheets", "reams", "gsm"}:
        return True
    return False


def _format_cell(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def normalize_paper_size(requested: str | None) -> str:
    """Normalize user-selected paper size query parameter."""
    raw = str(requested or "auto").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in SUPPORTED_PAPER_SIZES or raw == "auto":
        return raw
    return "auto"


def choose_paper_spec(
    columns: list[tuple[str, str]],
    rows: list[dict[str, Any]],
    requested: str | None = "auto",
) -> dict[str, str]:
    """Select A4 Portrait, A4 Landscape, A3 Portrait, or A3 Landscape cleanly."""
    norm = normalize_paper_size(requested)
    if norm in SUPPORTED_PAPER_SIZES:
        css_size, badge, code = SUPPORTED_PAPER_SIZES[norm]
        return {"css_size": css_size, "badge": badge, "code": code, "selection_mode": "manual"}

    col_count = max(1, len(columns))
    sample_rows = rows[:100]
    estimated_total_chars = 0
    for key, label in columns:
        max_len = len(str(label or ""))
        for row in sample_rows:
            cell_len = len(str(row.get(key, "") or ""))
            if cell_len > max_len:
                max_len = cell_len
        estimated_total_chars += min(46, max(4, max_len))

    if col_count <= 5 and estimated_total_chars <= 78:
        return {
            "css_size": "A4 portrait",
            "badge": "A4 Portrait (Auto)",
            "code": "a4_portrait",
            "selection_mode": "auto",
        }
    if col_count <= 8 and estimated_total_chars <= 135:
        return {
            "css_size": "A4 landscape",
            "badge": "A4 Landscape (Auto)",
            "code": "a4_landscape",
            "selection_mode": "auto",
        }
    return {
        "css_size": "A3 landscape",
        "badge": "A3 Landscape (Auto)",
        "code": "a3_landscape",
        "selection_mode": "auto",
    }


def _pack_meta_rows(meta_items: list[tuple[str, Any]] | None, per_row: int = 3) -> list[list[dict[str, Any]]]:
    if not meta_items:
        return []
    cleaned = [(str(k), _format_cell(v)) for k, v in meta_items if k and v not in (None, "")]
    if not cleaned:
        return []
    rows: list[list[dict[str, Any]]] = []
    for idx in range(0, len(cleaned), per_row):
        chunk = cleaned[idx : idx + per_row]
        row_cells = [{"label": k, "value": v, "colspan": 1, "width": f"{100 // len(chunk)}%"} for k, v in chunk]
        if len(chunk) < per_row and rows:
            # Stretch trailing row cleanly across grid columns
            extra = per_row - len(chunk) + 1
            row_cells[-1]["colspan"] = extra
        rows.append(row_cells)
    return rows


def _base_context(
    *,
    title: str,
    subtitle: str | None,
    paper_spec: dict[str, str],
    domain: str = "general",
    subsystem_label: str | None = None,
    ref_no: str | None = None,
    doc_date: str | None = None,
    meta_items: list[tuple[str, Any]] | None = None,
    generated_by: str | None = None,
    dense: bool = False,
) -> dict[str, Any]:
    theme = _DOMAIN_THEMES.get(domain, _DOMAIN_THEMES["general"])
    right_meta = subtitle or (f"Ref: {ref_no}" if ref_no else theme["subsystem_label"])
    return {
        "title": title,
        "subtitle": subtitle,
        "doc_title_attr": _css_str(title),
        "header_right_attr": _css_str(right_meta),
        "generated_at": datetime.now().strftime("%d %b %Y %H:%M"),
        "generated_by_attr": _css_str(generated_by),
        "paper_css_size": paper_spec["css_size"],
        "paper_badge": paper_spec["badge"],
        "subsystem_label": subsystem_label or theme["subsystem_label"],
        "accent_primary": theme["accent_primary"],
        "accent_dark": theme["accent_dark"],
        "accent_soft": theme["accent_soft"],
        "accent_border": theme["accent_border"],
        "ref_no": ref_no,
        "doc_date": doc_date,
        "meta_rows": _pack_meta_rows(meta_items),
        "table_font_size": "7.2pt" if dense else "7.8pt",
        "body_font_size": "8pt" if dense else "8.5pt",
    }


def _render_pdf(template_name: str, context: dict[str, Any]) -> BytesIO:
    template = _JINJA_ENV.get_template(template_name)
    html_str = template.render(**context)
    html_cls = _get_weasyprint_html()
    pdf_bytes = html_cls(string=html_str).write_pdf()
    buf = BytesIO(pdf_bytes)
    buf.seek(0)
    return buf


def make_register_pdf(
    title: str,
    columns: list[tuple[str, str]],
    rows: list[dict[str, Any]],
    subtitle: str | None = None,
    *,
    paper_size: str = "auto",
    domain: str = "general",
    subsystem_label: str | None = None,
    meta_items: list[tuple[str, Any]] | None = None,
    generated_by: str | None = None,
    search_term: str | None = None,
    signatures: list[dict[str, str]] | None = None,
) -> BytesIO:
    """Render any General Store or Paper Warehouse register as an official Printing Department PDF."""
    spec = choose_paper_spec(columns, rows, requested=paper_size)
    col_specs = [
        {"key": k, "label": label, "numeric": _is_numeric_col(k, label)}
        for k, label in columns
    ]
    formatted_rows = [
        [{"text": _format_cell(row.get(c["key"], "")), "numeric": c["numeric"]} for c in col_specs]
        for row in rows
    ]

    effective_meta = list(meta_items or [])
    if search_term:
        effective_meta.append(("Search Filter", search_term))
    effective_meta.append(("Total Records", str(len(rows))))

    default_sigs = signatures or [
        {"role": "Prepared By", "label": generated_by or "Storekeeper / Warehouseman"},
        {"role": "Verified By", "label": "Authorizing Officer"},
    ]

    ctx = _base_context(
        title=title,
        subtitle=subtitle,
        paper_spec=spec,
        domain=domain,
        subsystem_label=subsystem_label,
        meta_items=effective_meta,
        generated_by=generated_by,
        dense=len(columns) >= 8,
    )
    ctx.update(
        {
            "rows": rows,
            "col_specs": col_specs,
            "formatted_rows": formatted_rows,
            "search_term": search_term,
            "signatures": default_sigs,
            "sig_width": f"{100 // max(1, len(default_sigs))}%",
        }
    )
    return _render_pdf("register_pdf.html", ctx)


def make_voucher_pdf(
    title: str,
    columns: list[tuple[str, str]],
    items: list[dict[str, Any]],
    *,
    subtitle: str | None = None,
    ref_no: str | None = None,
    doc_date: str | None = None,
    meta_items: list[tuple[str, Any]] | None = None,
    totals_row: dict[str, Any] | None = None,
    notes: str | None = None,
    signatures: list[dict[str, str]] | None = None,
    paper_size: str = "auto",
    domain: str = "general",
    subsystem_label: str | None = None,
    generated_by: str | None = None,
) -> BytesIO:
    """Render an official Printing Department voucher/slip (Receipts, Indents, Opening, Outward Pass)."""
    if normalize_paper_size(paper_size) == "auto" and len(columns) <= 6:
        spec = {
            "css_size": "A4 portrait",
            "badge": "A4 Portrait (Auto)",
            "code": "a4_portrait",
            "selection_mode": "auto",
        }
    else:
        spec = choose_paper_spec(columns, items, requested=paper_size)

    col_specs = [
        {"key": k, "label": label, "numeric": _is_numeric_col(k, label)}
        for k, label in columns
    ]
    formatted_rows = [
        [{"text": _format_cell(row.get(c["key"], "")), "numeric": c["numeric"]} for c in col_specs]
        for row in items
    ]
    formatted_totals = None
    if totals_row:
        formatted_totals = [
            {"text": str(totals_row.get(c["key"], "")), "numeric": c["numeric"]}
            for c in col_specs
        ]

    sigs = signatures or [
        {"role": "Prepared By", "label": generated_by or "Storekeeper / Warehouseman"},
        {"role": "Authorized By", "label": "Head of Office / Controlling Officer"},
        {"role": "Received By", "label": "Receiving Official"},
    ]

    ctx = _base_context(
        title=title,
        subtitle=subtitle,
        paper_spec=spec,
        domain=domain,
        subsystem_label=subsystem_label,
        ref_no=ref_no,
        doc_date=doc_date,
        meta_items=meta_items,
        generated_by=generated_by,
        dense=len(columns) >= 8,
    )
    ctx.update(
        {
            "items": items,
            "col_specs": col_specs,
            "formatted_rows": formatted_rows,
            "totals_row": formatted_totals,
            "notes": notes,
            "signatures": sigs,
            "sig_width": f"{100 // max(1, len(sigs))}%",
        }
    )
    return _render_pdf("voucher_pdf.html", ctx)


def make_transfer_gate_pass_pdf(
    info: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    paper_size: str = "auto",
    domain: str = "general",
    generated_by: str | None = None,
) -> BytesIO:
    """Generate an official Printing Department Store/Warehouse Transfer Gate Pass PDF."""
    is_paper = domain == "paper" or any("paper_qty_display" in it for it in items)
    norm_size = normalize_paper_size(paper_size)
    if norm_size == "auto":
        spec = {
            "css_size": "A4 portrait",
            "badge": "A4 Portrait (Auto)",
            "code": "a4_portrait",
            "selection_mode": "auto",
        }
    else:
        css_size, badge, code = SUPPORTED_PAPER_SIZES[norm_size]
        spec = {"css_size": css_size, "badge": badge, "code": code, "selection_mode": "manual"}

    total_qty = Decimal("0")
    has_numeric_total = False
    for it in items:
        try:
            total_qty += Decimal(str(it.get("quantity", "0") or "0"))
            has_numeric_total = True
        except (InvalidOperation, ValueError):
            pass

    meta_items = [
        ("Gate Pass / Transfer No", info.get("transfer_no")),
        ("Transfer Date", info.get("transfer_date")),
        ("Requisition Ref", info.get("requisition_no") or "—"),
        ("Requisition Date", info.get("requisition_date") or "—"),
        ("Status", info.get("status") or "DISPATCHED"),
        ("Vehicle / Transport", info.get("vehicle_no") or "Not recorded"),
    ]

    subsystem = (
        "Paper Warehouse Inter-Press Transfer Gate Pass"
        if is_paper
        else "Inter-Office Stock Transfer Gate Pass"
    )
    title = "Paper Transfer Gate Pass" if is_paper else "Stock Transfer Gate Pass"
    subtitle = f"{info.get('source_store') or 'Central Store'} → {info.get('destination_store') or 'Branch Store'}"

    ctx = _base_context(
        title=title,
        subtitle=subtitle,
        paper_spec=spec,
        domain="paper" if is_paper else domain,
        subsystem_label=subsystem,
        ref_no=str(info.get("transfer_no") or ""),
        doc_date=str(info.get("transfer_date") or ""),
        meta_items=meta_items,
        generated_by=generated_by or info.get("dispatched_by_name"),
        dense=False,
    )
    ctx.update(
        {
            "info": info,
            "items": items,
            "is_paper": is_paper,
            "total_qty_display": f"{total_qty:.3f}" if has_numeric_total else "",
            "sig_width": "33.3%",
        }
    )
    return _render_pdf("gate_pass_pdf.html", ctx)
