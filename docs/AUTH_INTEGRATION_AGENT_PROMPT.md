Test the current CSMS V2 after authentication integration.
Use AGENTS.md and docs/AUTH_INTEGRATION_TEST_PLAN.md.
Use existing PostgreSQL database.
Run migrations and seed scripts.
Login through /api/auth/token and use Authorization: Bearer tokens for application endpoints.
Update existing test clients to send tokens, but preserve all previous business assertions.
Deliberately send a mismatched actor_id and verify HTTP 403.
Run all previous test suites: manual indent/issue, receipt/return, requisition/transfer, petty purchase, stock control.
Do not weaken authorization or business rules.
Report PASS/FAIL with exact traceback/file/line for failures.
