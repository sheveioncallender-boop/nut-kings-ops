# Nut Kings Ops — Odoo 19 Community

Clean consolidated rebuild of the Nut Kings inventory and distribution system.

## Principles
- One visible Odoo app: **Nut Kings Ops**.
- Standard Odoo backend remains open; no redirect or worker lock-down code.
- Raw Materials and Finished Goods are independent inventories.
- Rapid Scan creates native `stock.picking` and `stock.move` records.
- Odoo remains authoritative for reservations, forecast, move history, detailed operations, validation, returns and physical inventory.
- The `/nutkings/` PWA caches the operational shell and stores pending actions in IndexedDB.

## First staging test
Install on a fresh Odoo 19 Community database, create products and trucks, open `/nutkings/`, synchronize, then test a small receipt through Draft → Mark as Todo → Validate.


## Mobile camera scanning
Rapid Scan and Physical Inventory can use the phone/tablet camera as an additional barcode input. Android/Chromium uses the browser multi-format detector when available; a bundled offline EAN-13/EAN-8/UPC-A fallback keeps core retail barcode capture available without sending camera images to the server. Hardware scanners and manual entry remain unchanged.
