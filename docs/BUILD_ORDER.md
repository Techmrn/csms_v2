# CSMS V2 Build Order

1. Foundation: FastAPI, async SQLAlchemy, PostgreSQL, Alembic, organization, security and master data.
2. Stock core: StockAccount, OpeningStock, StockMovement, current stock and Stock Register.
3. Manual Indent + Issue finalization with actual issued quantities.
4. Receipt + Return.
5. Central Store Requisition + approval chain + Transfer Out/In.
6. Petty Purchase and temporary consumable item handling.
7. Verification + Adjustment + Unserviceable.
8. Assets and asset movement.
9. Audit + WorkflowTransition + Notifications.
10. Optional inventory controls: reorder, low stock, batch, expiry, FIFO/LIFO/FEFO.
