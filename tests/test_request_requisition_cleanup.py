from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_return_create_permission_catalogued():
    text = (ROOT / "app/security/permissions.py").read_text()
    assert '"STOCK_RETURN_CREATE"' in text
    assert '"SECTION_USER": ["INDENT_VIEW", "INDENT_CREATE", "STOCK_RETURN_VIEW", "STOCK_RETURN_CREATE"]' in text

def test_requisition_review_keeps_requested_read_only():
    text = (ROOT / "app/web/templates/requisition_detail.html").read_text()
    assert "Requested" in text
    assert "Approved" in text
    assert "Requested quantity is read-only" in text

def test_my_activity_route_exists():
    text = (ROOT / "app/web/routes.py").read_text()
    assert '@router.get("/app/my-activity"' in text
    assert '("My Activity", "/app/my-activity", None)' in text

def test_api_get_endpoints_are_scoped():
    for rel, fragment in [
        ("app/api/routes/indents.py", 'require_store_visibility(current_user.id, indent.store_id)'),
        ("app/api/routes/requisitions.py", 'require_store_visibility(current_user.id, requisition.requesting_store_id)'),
        ("app/api/routes/transfers.py", 'User is not authorized to access this transfer'),
    ]:
        text = (ROOT / rel).read_text()
        assert fragment in text
