# CSMS V2 UI / Workflow Update

This build includes:

- Administration success/error alerts and duplicate-entry conflict handling.
- Explicit Back/Cancel navigation on admin and transaction forms.
- Contextual field-help text on workflow forms and multi-role/store checkbox assignment in User Administration.
- Online Indent create, approval and issue workflow.
- Requisition create, branch approval, central approval, and dispatch workflow UI.
- Transfer receipt workflow UI.
- Central Store destination Office/Section selection for manual and online indents.
- Petty Purchase no longer requires a user-entered indent for immediate issue. The user selects an immediate-issue destination Office/Section and the system creates the internal issue document during posting.
- New migration 0014 adds petty-purchase immediate-issue destination fields.
- Seed grants INDENT_APPROVE to the Deputy Superintendent, Stock & Stores.

The existing database must be upgraded with `alembic upgrade head` after installing this build.
