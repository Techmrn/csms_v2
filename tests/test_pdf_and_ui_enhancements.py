from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import re
import uuid
import zlib

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.financial_year import FinancialYear
from app.models.role import Role
from app.models.section import Section
from app.models.store import Store
from app.models.user import User
from app.paper_store.models.indent_issue import PaperIndent
from app.paper_store.models.item import PaperItem
from app.paper_store.models.stock import PaperOpeningStock
from app.paper_store.models.receipt import PaperReceipt
from app.paper_store.models.transfer import PaperTransfer
from app.paper_store.schemas.opening import PaperOpeningStockCreate, PaperOpeningStockLineCreate
from app.paper_store.schemas.receipt import PaperReceiptCreate, PaperReceiptLineCreate
from app.paper_store.services.opening import PaperOpeningService
from app.paper_store.services.receipt import PaperReceiptService
from app.security.auth import create_access_token
from app.services.pdf_reports import (
    _JINJA_ENV,
    choose_paper_spec,
    make_register_pdf,
    make_transfer_gate_pass_pdf,
    make_voucher_pdf,
    normalize_paper_size,
)


ROOT = Path(__file__).resolve().parents[1]


def _extract_mediabox_pts(pdf_bytes: bytes) -> tuple[float, float]:
    chunks = [pdf_bytes]
    for raw_stream in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, re.DOTALL):
        try:
            chunks.append(zlib.decompress(raw_stream))
        except zlib.error:
            pass
    for chunk in chunks:
        match = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([0-9.]+)\s+([0-9.]+)\s*\]", chunk)
        if match is not None:
            return float(match.group(1)), float(match.group(2))
    raise AssertionError("PDF missing /MediaBox coordinates")


def test_pdf_auto_and_manual_paper_sizing_and_printing_department_header():
    narrow_cols = [("code", "Code"), ("name", "Item"), ("unit", "Unit"), ("balance", "Balance")]
    narrow_rows = [{"code": "P-01", "name": "A4 Bond", "unit": "REAM", "balance": "10.000"}]

    medium_cols = [(f"col{i}", f"Header {i}") for i in range(7)]
    medium_rows = [{f"col{i}": "Sample value" for i in range(7)}]

    wide_cols = [(f"w{i}", f"Wide Column {i}") for i in range(10)]
    wide_rows = [{f"w{i}": "Long paper description with GSM & sheet info" for i in range(10)}]

    assert normalize_paper_size("A3-Landscape") == "a3_landscape"
    assert normalize_paper_size("unknown_val") == "auto"

    assert choose_paper_spec(narrow_cols, narrow_rows, "auto")["code"] == "a4_portrait"
    assert choose_paper_spec(medium_cols, medium_rows, "auto")["code"] == "a4_landscape"
    assert choose_paper_spec(wide_cols, wide_rows, "auto")["code"] == "a3_landscape"
    assert choose_paper_spec(narrow_cols, narrow_rows, "a3_landscape")["code"] == "a3_landscape"
    assert choose_paper_spec(wide_cols, wide_rows, "a4_portrait")["code"] == "a4_portrait"

    pdf_a4p = make_register_pdf(
        'Test & <Safe> "Title"',
        narrow_cols,
        [{"code": "I<&>1", "name": "Paper <75> & Bond", "unit": "REAM", "balance": "5.000"}],
        "Central Store | FY 2025-26",
        paper_size="auto",
        generated_by="Tester",
    ).getvalue()
    assert pdf_a4p.startswith(b"%PDF")
    w_p, h_p = _extract_mediabox_pts(pdf_a4p)
    assert 590 <= w_p <= 600 and 838 <= h_p <= 846  # A4 Portrait

    pdf_a3l = make_register_pdf(
        "Paper Wide Register",
        wide_cols,
        wide_rows,
        "Central Press Warehouse | FY 2025-26",
        paper_size="auto",
        domain="paper",
    ).getvalue()
    assert pdf_a3l.startswith(b"%PDF")
    w_a3, h_a3 = _extract_mediabox_pts(pdf_a3l)
    assert 1185 <= w_a3 <= 1195 and 838 <= h_a3 <= 846  # A3 Landscape

    # Verify rendered template carries "Printing Department" header, running footer & autoescaping
    rendered_html = _JINJA_ENV.get_template("register_pdf.html").render(
        title='Title & <Script>',
        subtitle="Store | FY",
        doc_title_attr="Title",
        header_right_attr="Store",
        generated_at="12 Nov 2026 09:00",
        generated_by_attr="Storekeeper",
        paper_css_size="A4 portrait",
        paper_badge="A4 Portrait (Auto)",
        subsystem_label="General Store Management System",
        accent_primary="#1e40af",
        accent_dark="#1e3a8a",
        accent_soft="#eff6ff",
        accent_border="#bfdbfe",
        meta_rows=[],
        rows=[{"code": "<x>"}],
        col_specs=[{"key": "code", "label": "Code", "numeric": False}],
        formatted_rows=[[{"text": "<x>", "numeric": False}]],
        search_term=None,
        signatures=[],
        sig_width="50%",
    )
    assert "Printing Department" in rendered_html
    assert "counter(page)" in rendered_html and "counter(pages)" in rendered_html
    assert "&lt;Script&gt;" in rendered_html
    assert "&lt;x&gt;" in rendered_html

    # Voucher PDF + Paper Transfer Gate Pass PDF
    voucher = make_voucher_pdf(
        "Outward Pass",
        [("item", "Item"), ("quantity", "Quantity")],
        [{"item": "Ink & <Toner>", "quantity": "3.000"}],
        ref_no="ISS-100",
        doc_date="2026-04-01",
        paper_size="a4_landscape",
    ).getvalue()
    assert voucher.startswith(b"%PDF")
    wv, hv = _extract_mediabox_pts(voucher)
    assert 838 <= wv <= 846 and 590 <= hv <= 600  # A4 Landscape

    gp_paper = make_transfer_gate_pass_pdf(
        {
            "transfer_no": "PTP-10",
            "transfer_date": "2026-04-01",
            "source_store": "Central Press Paper Warehouse",
            "destination_store": "Branch Press Warehouse",
            "destination_office": "Branch Press",
            "fy_name": "2025-26",
            "status": "DISPATCHED",
        },
        [
            {
                "item_code": "MAP-70",
                "item_name": "Maplitho 70 GSM",
                "unit_code": "SHEET",
                "paper_qty_display": "4 Reams + 100 Sheets",
                "quantity": "2100 SH",
                "remarks": "Sealed bundles",
            }
        ],
        domain="paper",
    ).getvalue()
    assert gp_paper.startswith(b"%PDF")


def test_css_print_isolation_and_nav_differentiation():
    css = (ROOT / "app/web/static/css/csms.css").read_text(encoding="utf-8")
    for token in (
        "--ok:",
        "--brand:",
        "--warn:",
        "--border-color:",
        "--bg-card:",
        "--text-muted:",
        ".badge.ok",
        ".badge.warn",
        ".badge.info",
        ".badge.danger",
        ".button.sm",
        ".button.secondary",
        ".button.danger",
        ".kpi-grid.cols-3",
        ".ctx-field",
        ".page-actions",
        ".nav-group--paper",
        ".nav-group--general",
        ".nav-group--admin",
        "@media print",
        ".print-only-masthead",
    ):
        assert token in css, f"Missing CSS token/class: {token}"

    base_html = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
    for icon_key in ("'activity'", "'receipt'", "'indent'", "'online'", "'req'", "'return'", "'asset'", "'petty'", "'register'", "'paper'", "'store'", "'org'"):
        assert icon_key in base_html, f"Missing differentiated SVG icon key {icon_key} in base.html"
    assert "Printing Department" in base_html


@pytest.mark.asyncio
async def test_pdf_web_endpoints_rbac_and_dashboards(client):
    async with AsyncSessionLocal() as session:
        user_stmt = select(User).options(selectinload(User.roles).selectinload(Role.permissions))
        whman = await session.scalar(user_stmt.where(User.username == "dev_cp_whman"))
        press_sk = await session.scalar(user_stmt.where(User.username == "dev_press_sk"))
        general_sk = await session.scalar(user_stmt.where(User.username == "dev_general_sk"))
        deputy = await session.scalar(user_stmt.where(User.username == "dev_deputy"))
        admin = await session.scalar(user_stmt.where(User.username == "dev_admin"))

        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        cp_wh = await session.scalar(
            select(Store).where(Store.store_type == "PAPER_WAREHOUSE", Store.is_active.is_(True)).limit(1)
        )
        assert whman and press_sk and general_sk and deputy and admin and fy and cp_wh

        # Ensure at least one opening & one receipt exist for cp_wh so voucher PDF routes are tested on real DB rows
        opening = await session.scalar(select(PaperOpeningStock).where(PaperOpeningStock.store_id == cp_wh.id).limit(1))
        receipt = await session.scalar(select(PaperReceipt).where(PaperReceipt.store_id == cp_wh.id).limit(1))
        if not opening or not receipt:
            p_item = await session.scalar(select(PaperItem).where(PaperItem.form_type == "SHEET", PaperItem.is_active.is_(True)).limit(1))
            if p_item:
                if not opening:
                    opening = await PaperOpeningService(session).create_and_post(
                        PaperOpeningStockCreate(
                            opening_date=date.today(),
                            store_id=cp_wh.id,
                            financial_year_id=fy.id,
                            opening_type="INITIAL",
                            remarks="PDF test opening",
                            lines=[PaperOpeningStockLineCreate(paper_item_id=p_item.id, reams=1, sheets=0)],
                        ),
                        actor_id=whman.id,
                    )
                if not receipt:
                    receipt = await PaperReceiptService(session).create_and_post(
                        PaperReceiptCreate(
                            receipt_date=date.today(),
                            store_id=cp_wh.id,
                            financial_year_id=fy.id,
                            challan_no=f"CH-{uuid.uuid4().hex[:6]}",
                            lines=[
                                PaperReceiptLineCreate(
                                    paper_item_id=p_item.id,
                                    challan_reams=2,
                                    challan_sheets=0,
                                    received_reams=2,
                                    received_sheets=0,
                                    accepted_reams=2,
                                    accepted_sheets=0,
                                    weight_kg=Decimal("10.000"),
                                )
                            ],
                        ),
                        actor_id=whman.id,
                    )
                await session.commit()

        p_indent = await session.scalar(select(PaperIndent).limit(1))
        p_xfer = await session.scalar(select(PaperTransfer).limit(1))

        wh_tok = create_access_token(whman)
        sk_tok = create_access_token(press_sk)
        gen_tok = create_access_token(general_sk)
        dep_tok = create_access_token(deputy)
        adm_tok = create_access_token(admin)

        wh_id = cp_wh.id
        fy_id = fy.id
        opening_id = opening.id if opening else None
        receipt_id = receipt.id if receipt else None
        p_indent_id = p_indent.id if p_indent else None
        p_xfer_id = p_xfer.id if p_xfer else None

    # 1. General Store PDFs with paper_size work cleanly
    for path in (
        "/app/registers/issues.pdf?paper_size=a3_landscape",
        "/app/registers/distribution.pdf?paper_size=auto",
        "/app/registers/transactions.pdf?paper_size=a4_landscape",
        "/app/registers/computers.pdf?paper_size=auto",
        "/app/registers/e-waste.pdf?paper_size=a4_portrait",
    ):
        res = await client.get(path, cookies={"csms_access_token": gen_tok})
        assert res.status_code == 200, f"Failed {path}: {res.status_code}"
        assert res.headers["content-type"] == "application/pdf"
        assert res.content.startswith(b"%PDF")

    # 2. Paper Warehouse Register PDFs work for Warehouseman & 403 for General Storekeeper
    for kind in ("stock", "receipts", "issues", "transfers", "opening", "ledger"):
        ok_resp = await client.get(
            f"/app/paper/registers/{kind}.pdf?store_id={wh_id}&financial_year_id={fy_id}&paper_size=a3_landscape",
            cookies={"csms_access_token": wh_tok},
        )
        assert ok_resp.status_code == 200, f"Paper {kind}.pdf failed: {ok_resp.status_code}"
        assert ok_resp.content.startswith(b"%PDF")
        w, _ = _extract_mediabox_pts(ok_resp.content)
        assert 1185 <= w <= 1195  # Requested A3 Landscape honored

        deny_resp = await client.get(
            f"/app/paper/registers/{kind}.pdf?store_id={wh_id}&financial_year_id={fy_id}",
            cookies={"csms_access_token": sk_tok},
        )
        assert deny_resp.status_code == 403

    # 3. Paper Warehouse Voucher & Gate Pass PDFs
    if opening_id:
        r_op = await client.get(f"/app/paper/opening-stock/{opening_id}.pdf", cookies={"csms_access_token": wh_tok})
        assert r_op.status_code == 200 and r_op.content.startswith(b"%PDF")
        assert (await client.get(f"/app/paper/opening-stock/{opening_id}.pdf", cookies={"csms_access_token": sk_tok})).status_code == 403
    if receipt_id:
        r_rc = await client.get(f"/app/paper/receipts/{receipt_id}.pdf", cookies={"csms_access_token": wh_tok})
        assert r_rc.status_code == 200 and r_rc.content.startswith(b"%PDF")
        assert (await client.get(f"/app/paper/receipts/{receipt_id}.pdf", cookies={"csms_access_token": sk_tok})).status_code == 403
    if p_indent_id:
        r_in = await client.get(f"/app/paper/indents/{p_indent_id}.pdf", cookies={"csms_access_token": wh_tok})
        assert r_in.status_code == 200 and r_in.content.startswith(b"%PDF")
    if p_xfer_id:
        r_xf = await client.get(f"/app/paper/transfers/{p_xfer_id}/gate-pass.pdf", cookies={"csms_access_token": wh_tok})
        assert r_xf.status_code == 200 and r_xf.content.startswith(b"%PDF")

    # 4. Dashboards: focused action workbenches (no full ledger dump on /app)
    wh_dash = (await client.get("/app", cookies={"csms_access_token": wh_tok})).text
    assert "PENDING ACTION QUEUE" in wh_dash
    assert "Full Paper Stock Ledger" in wh_dash
    assert "FY Stock Ledger" not in wh_dash

    sk_dash = (await client.get("/app", cookies={"csms_access_token": gen_tok})).text
    assert "STORE OPERATIONS QUEUE" in sk_dash
    assert "Current General Store Balances" not in sk_dash

    dep_dash = (await client.get("/app", cookies={"csms_access_token": dep_tok})).text
    assert "Executive Approvals Hub" in dep_dash

    adm_redirect = await client.get("/app", cookies={"csms_access_token": adm_tok})
    assert adm_redirect.status_code == 303
    adm_dash_resp = await client.get("/app/admin", cookies={"csms_access_token": adm_tok})
    assert adm_dash_resp.status_code == 200
    adm_dash = adm_dash_resp.text
    assert "Paper Warehouses" in adm_dash
    assert "Paper Catalog" in adm_dash
