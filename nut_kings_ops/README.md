# Nut Kings Ops 19.0.1.3.2 — Odoo 19 Community

Complete consolidated package for the Nut Kings inventory and distribution system.

## Principles
- One visible Odoo app: **Nut Kings Ops**.
- Standard Odoo backend remains open; no redirect or worker lock-down code.
- Raw Materials and Finished Goods are independent inventories.
- Rapid Scan creates native `stock.picking` and `stock.move` records.
- Odoo remains authoritative for reservations, forecast, move history, detailed operations, validation, returns and physical inventory.
- The `/nutkings/` PWA caches the operational shell and stores pending actions in IndexedDB.
- Service-area product rotation changes which finished products are selected and how many are loaded based on historical sales and returns for that area. It is not an expiry/FIFO feature.

## Operational roles

| Role | Workspace capability |
| --- | --- |
| Office Receiving | Receive Raw Materials |
| Raw Materials Employee | Issue Raw Materials |
| Finished Goods Entry | Receive Finished Goods |
| Dispatcher | Dispatch plans, truck loads, customer deliveries, truck returns, and trip reconciliation |
| Manager / Administrator | All operations, physical inventory, reports, configuration, and corrections |

Odoo 19 roles use `res.groups.privilege` and `privilege_id`. A manager implies all four operational roles plus Odoo Stock Manager.
Backend transfer menus are separated by role, and only managers can close a reconciled trip, approve a variance, force unreserved demand, or apply a physical inventory count.

## Dispatch planning and product rotation

1. Configure service areas and assign customers, trucks, and optional dispatcher users.
2. Create a Dispatch Plan for a service area and truck.
3. Run **Analyse Sales & Returns**.
4. Review average loaded, sold, and returned quantities; sell-through; rotation guidance; and the editable suggested load.
5. Approve the plan and create the native Odoo truck-loading transfer.

The recommendation starts with average sales plus the configured sales buffer. Products with poor sales and returns are reduced or paused, while the dispatcher can edit the final selection and quantity before approval.

## Deployment

Replace the complete `nut_kings_ops` folder in the connected Git repository, redeploy/restart Odoo, update the Apps list, and click **Upgrade**. Do not uninstall a working earlier version. After upgrading, open `/nutkings/reset`, clear the saved workspace, return to `/nutkings/`, and synchronize.

For a fresh staging test, install on Odoo 19 Community, assign the Manager / Administrator role, create products, trucks, and service areas, open `/nutkings/`, synchronize, then test a small receipt through Draft → Mark as Todo → Validate.


## Mobile camera scanning
Rapid Scan and Physical Inventory can use the phone/tablet camera as an additional barcode input. Android/Chromium uses the browser multi-format detector when available; a bundled offline EAN-13/EAN-8/UPC-A fallback keeps core retail barcode capture available without sending camera images to the server. Hardware scanners and manual entry remain unchanged.
