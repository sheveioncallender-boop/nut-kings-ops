# Nut Kings Ops 19.0.1.3.3 Validation

## Review outcome

This is a complete Odoo 19 module with one top-level `nut_kings_ops` directory. It combines the last complete mobile build with the Odoo 19 role correction, the reviewed service-area dispatch-planning work, and the Odoo 19 search-view correction.

The reported installation failures are corrected:

- `category_id` is used only on `res.groups.privilege`; every Nut Kings `res.groups` record uses Odoo 19's `privilege_id`.
- Search-view `group` elements do not use the obsolete `expand` or `string` attributes rejected by Odoo 19.

## Role and workflow checks

| Role | Allowed Nut Kings workflow |
| --- | --- |
| Office Receiving | Raw-material receipts |
| Raw Materials Employee | Raw-material issues |
| Finished Goods Entry | Finished-goods receipts |
| Dispatcher | Dispatch plans, van loads, deliveries, returns, and reconciliation |
| Manager / Administrator | All workflows, physical counts, variance closure, forced-demand override, reports, and configuration |

- Backend transfer menus are separated by role.
- Dispatcher data is company-scoped and optionally service-area-scoped.
- Manager and Odoo Settings administrators retain full access.
- Trip transitions are enforced as Planned → Loading → In Progress → Reconciliation → Closed.
- Only managers can approve a variance and close a trip.
- A first van-loading transfer advances a planned trip to Loading.
- Products, lots, quants, trucks, staff, customers, trips, and service areas are checked for company and workflow consistency before mobile API writes.
- Physical counts reject stale, duplicate, negative, cross-company, wrong-location, wrong-product, and wrong-lot rows.

## Static package checks completed

- Python syntax and byte-compilation: passed for 20 Python files.
- XML parsing: passed for 20 XML files.
- Official Odoo 19 RelaxNG view validation: all six search views and all seven standalone list views passed the matching Odoo 19 schemas.
- Search-view regression audit: search `group` elements contain neither obsolete `expand` nor `string` attributes.
- Deprecated view syntax audit: no legacy `tree`, `attrs`, or `states` syntax remains.
- Manifest data/assets: every referenced file exists and loads in dependency order.
- XML identifiers: 128 unique identifiers; local references resolve.
- Manifest load order: 219 XML references were scanned and every local identifier is defined before use.
- Access controls: 36 complete ACL rows with unique identifiers.
- Odoo 19 group and privilege schema audit: passed.
- PWA JavaScript syntax: passed with Node.js.
- PWA HTML/JavaScript element references and versioned asset references: passed.
- PWA cache, workspace, API, and application versions agree on `1.3.3`; unchanged bundle filenames remain stable asset paths.
- Compiled Python cache files are excluded from the release archive.
- ZIP integrity and top-level module layout are checked after packaging.

## Server acceptance test

A live Odoo server was not present in the build environment. After deploying to staging, complete this short acceptance test before production use:

1. Replace the complete add-on folder, restart/redeploy Odoo, update the Apps list, and install or upgrade **Nut Kings Ops**.
2. Assign one test user to each Nut Kings role and confirm each user sees only the intended workspace actions and backend transfer menus.
3. Create a small raw receipt and raw issue, then a finished-goods receipt; validate that each posts a native Odoo stock transfer.
4. Configure one service area, customer, truck, driver, and dispatcher; create a dispatch plan and run **Analyse Sales & Returns**.
5. Approve the plan, create the truck load, validate it, depart, record a delivery and return, reconcile, and close as a manager.
6. Confirm a dispatcher cannot close a variance trip, force unreserved demand, or apply a physical inventory count.
7. Open `/nutkings/reset`, refresh the workspace, and confirm offline capture and later synchronization on a test device.
