from app.security.permissions import PERMISSIONS, ROLE_PERMISSIONS


def test_role_matrix_references_known_permissions_only():
    known = {code for code, *_ in PERMISSIONS}
    for role, permissions in ROLE_PERMISSIONS.items():
        assert permissions == list(dict.fromkeys(permissions)), role
        assert set(permissions) <= known, role


def test_system_admin_is_read_only_for_business_transactions():
    perms = set(ROLE_PERMISSIONS["SYSTEM_ADMIN"])
    assert "REGISTER_VIEW" in perms
    assert "STOCK_ISSUE" not in perms
    assert "STOCK_RECEIPT" not in perms
    assert "STOCK_ADJUST_POST" not in perms
    assert "PETTY_PURCHASE_POST" not in perms


def test_controller_permissions_are_not_storekeeper_permissions():
    deputy = set(ROLE_PERMISSIONS["DEPUTY_SUPDT_STORES"])
    general = set(ROLE_PERMISSIONS["GENERAL_STOREKEEPER"])
    branch_head = set(ROLE_PERMISSIONS["BRANCH_HEAD"])
    branch_sk = set(ROLE_PERMISSIONS["BRANCH_STOREKEEPER"])

    assert "STOCK_VERIFY" in deputy
    assert "STOCK_VERIFY" in branch_head
    assert "STOCK_VERIFY" not in general
    assert "STOCK_VERIFY" not in branch_sk
    assert "STOCK_ADJUST_AUTHORIZE" in deputy
    assert "STOCK_ADJUST_AUTHORIZE" in branch_head
    assert "STOCK_ADJUST_AUTHORIZE" not in general
    assert "STOCK_ADJUST_POST" in general
    assert "STOCK_ADJUST_POST" in branch_sk


def test_branch_head_can_verify_branch_petty_purchase():
    assert "PETTY_PURCHASE_VERIFY" in ROLE_PERMISSIONS["BRANCH_HEAD"]
    assert "PETTY_PURCHASE_VERIFY" not in ROLE_PERMISSIONS["BRANCH_STOREKEEPER"]


def test_register_visibility_is_available_to_operational_roles():
    for role in (
        "DIRECTOR",
        "DEPUTY_SUPDT_STORES",
        "GENERAL_STOREKEEPER",
        "ASSISTANT_STOREKEEPER",
        "BRANCH_HEAD",
        "BRANCH_STOREKEEPER",
    ):
        assert "REGISTER_VIEW" in ROLE_PERMISSIONS[role]
    assert "REGISTER_VIEW" not in ROLE_PERMISSIONS["SECTION_USER"]


def test_navigation_permissions_are_defined_and_role_scoped():
    import ast
    from pathlib import Path

    source = Path("app/web/routes.py").read_text()
    tree = ast.parse(source)
    menu_node = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "MENU" for target in node.targets)
    )
    menu = ast.literal_eval(menu_node)
    known = {code for code, *_ in PERMISSIONS}

    for label, _href, permission in menu:
        if permission is not None:
            assert permission in known, f"Unknown menu permission for {label}: {permission}"

    expected = {
        "Online Indents": "INDENT_VIEW",
        "Manual Indents": "INDENT_PROCESS",
        "Receipts": "STOCK_RECEIPT_VIEW",
        "Returns": "STOCK_RETURN_VIEW",
    }
    actual = {label: permission for label, _href, permission in menu if label in expected}
    assert actual == expected


def test_view_routes_use_explicit_view_permissions():
    import ast
    from pathlib import Path

    source = Path("app/web/routes.py").read_text()
    assert 'await require_view_permission(session, current_user.id, "STOCK_VIEW")' in source
    assert 'await require_view_permission(session, current_user.id, "MASTER_DATA_MANAGE")' in source
    assert 'await require_view_permission(session, current_user.id, "INDENT_VIEW")' in source
    assert 'await require_view_permission(session, current_user.id, "STOCK_RECEIPT_VIEW")' in source
    assert 'await require_view_permission(session, current_user.id, "STOCK_RETURN_VIEW")' in source

    # System Admin must not receive an implicit bypass inside the view helper.
    tree = ast.parse(source)
    func_node = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "require_view_permission"
    )
    # Filter out the docstring if present
    body_statements = func_node.body
    if (
        body_statements
        and isinstance(body_statements[0], ast.Expr)
        and isinstance(body_statements[0].value, ast.Constant)
        and isinstance(body_statements[0].value.value, str)
    ):
        body_statements = body_statements[1:]

    # Assert no executable statement contains a SYSTEM_ADMIN reference or conditional bypass
    for stmt in body_statements:
        for child in ast.walk(stmt):
            if isinstance(child, ast.Constant) and child.value == "SYSTEM_ADMIN":
                raise AssertionError("require_view_permission contains hardcoded SYSTEM_ADMIN bypass")
            if isinstance(child, ast.If):
                raise AssertionError("require_view_permission must not contain conditional bypasses")

