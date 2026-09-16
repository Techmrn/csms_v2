from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_menu_rbac_alignment():
    text=(ROOT/"app/web/routes.py").read_text()
    assert '("Receipts", "/app/receipts", "STOCK_RECEIPT_VIEW")' in text
    assert '("Returns", "/app/returns", "STOCK_RETURN_VIEW")' in text
    assert '("Manual Indents", "/app/indents", "INDENT_PROCESS")' in text

def test_api_hardening():
    assert 'MASTER_DATA_MANAGE' in (ROOT/"app/api/routes/masters.py").read_text()
    assert 'ORGANIZATION_MANAGE' in (ROOT/"app/api/routes/offices.py").read_text()
    assert 'ORGANIZATION_MANAGE' in (ROOT/"app/api/routes/stores.py").read_text()
    stock=(ROOT/"app/api/routes/stock.py").read_text()
    assert 'STOCK_VIEW' in stock and 'REGISTER_VIEW' in stock and stock.count('require_store_visibility') >= 2

def test_sod_hardening():
    assert 'purchase.created_by == actor_id' in (ROOT/"app/services/petty_purchase.py").read_text()
    assert 'purchase.verified_by == actor_id' in (ROOT/"app/services/petty_purchase.py").read_text()
    assert 'discrepancy.reported_by == actor_id' in (ROOT/"app/services/transfer.py").read_text()
    assert 'indent.created_by == actor_id' in (ROOT/"app/services/indent.py").read_text()

def test_no_obsolete_role_reference():
    assert '"SUPERINTENDENT"' not in (ROOT/"app/services/authorization.py").read_text()
    assert '"SUPERINTENDENT"' not in (ROOT/"app/services/asset.py").read_text()
