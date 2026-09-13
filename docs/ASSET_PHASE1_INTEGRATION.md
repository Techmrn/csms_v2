# Asset Phase 1 Integration

## Existing Receipt behavior

The current Receipt module is consumable-focused. Phase 1 changes the business rule so a receipt may contain either `CONSUMABLE` or `ASSET` lines.

For `CONSUMABLE` lines, retain the existing behavior:

- accepted quantity creates `RECEIPT` StockMovement IN
- rejected/pending quantity does not enter stock

For `ASSET` lines:

- no `RECEIPT` StockMovement is created
- accepted quantity must equal the number of supplied individual asset records
- one Asset record is created per accepted physical asset
- each Asset gets a unique Asset Number
- optional serial number is unique when supplied
- Asset status starts as `IN_STOCK`
- Asset current_store_id is the receipt Store
- Asset acquisition_financial_year_id is the receipt FY
- an AssetMovement `RECEIPT` is created
- a ReceiptLineAsset links the receipt line to the exact Asset

Mixed receipts are allowed: a single Receipt can contain consumable and asset lines.

## Asset input for an asset receipt line

Add to the asset receipt line request:

```text
asset_details: list[AssetReceiptInput]
```

where each entry contains:

- serial_no (optional)
- make (optional)
- model (optional)
- purchase_date (optional)
- purchase_reference (optional)
- purchase_value (optional)
- warranty_expiry_date (optional)
- technical_specifications (optional)
- remarks (optional)

Validation:

```text
asset accepted quantity > 0
asset_details count == accepted_quantity
accepted + rejected <= received
```

Asset accepted quantity should be a whole number because each accepted asset represents one physical object.

## Authorization

Use the existing authenticated `current_user.id` path. Do not reintroduce `actor_id` in any public schema.

Existing receipt permission/store-scope checks remain authoritative for receipt posting.

Asset Register endpoints require the existing authenticated-user dependency. Use `ASSET_VIEW` if that permission is already present in the final authorization layer.
