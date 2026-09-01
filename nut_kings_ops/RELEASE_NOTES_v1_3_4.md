# Nut Kings Ops 19.0.1.3.4

This is the complete installable module, not a hotfix overlay.

## Corrected

- Updated the login-branding QWeb inheritance for Odoo 19: the login form is now targeted by its stable `role="form"` attribute instead of looking for `oe_login_form` in a normal `class` attribute when Odoo defines it through `t-attf-class`.
- Removed the redundant inline login stylesheet link; the same scoped stylesheet is already loaded by `web.assets_frontend`.
- Updated the service-area search view for Odoo 19 by removing the obsolete `expand` and `string` attributes from its search-view `group` element.
- Replaced the invalid Odoo 18-style `category_id` on `res.groups` with Odoo 19 privileges and `privilege_id`.
- Added every file referenced by the manifest, eliminating the incomplete-overlay packaging problem.
- Replaced hard-coded full-manager API permissions with the five Nut Kings operational roles.
- Replaced unrestricted `base.group_user` model access with role-specific ACLs and company record rules.
- Added assigned service-area filtering for dispatchers while leaving an empty assignment as all areas.
- Corrected offline trip synchronization so the entered route is retained.
- Enforced trip workflow order and manager-only variance approval/closure at both API and model layers.
- Restricted forced-demand stock overrides to managers and separated backend transfer menus by operational role.
- Added company/service-area validation for mobile contacts, trip teams, customers, trucks, and dispatch plans.
- Preserved the reinstall-safe stock-location barcode recovery, mobile camera scanner, persistent scan sound, native Odoo stock moves, offline queue, dashboard, reports, and synchronization.

## Added

- Service areas for customers, trucks, users, and trips.
- Dispatch plans with editable product rotation based on service-area sales and returns.
- Native draft/reserved truck-loading transfers created from approved plans.
- Branded Nut Kings login treatment.
- Updated application and PWA cache version to `1.3.4` so browsers load the corrected release after installation or upgrade.
