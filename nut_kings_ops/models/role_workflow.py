from odoo import SUPERUSER_ID, api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


OPERATION_GROUPS = {
    "RM_RECEIPT": "nut_kings_ops.group_nutkings_office_receiving",
    "RM_ISSUE": "nut_kings_ops.group_nutkings_raw_material_issue",
    "FG_RECEIPT": "nut_kings_ops.group_nutkings_finished_goods_entry",
    "FG_TRUCK": "nut_kings_ops.group_nutkings_dispatcher",
    "TRUCK_DELIVERY": "nut_kings_ops.group_nutkings_dispatcher",
    "TRUCK_RETURN": "nut_kings_ops.group_nutkings_dispatcher",
}

ROLE_LABELS = {
    "office_receiving": _("Office Receiving"),
    "raw_material_issue": _("Raw Materials Employee"),
    "finished_goods_entry": _("Finished Goods Entry"),
    "dispatcher": _("Dispatcher"),
    "manager": _("Manager / Administrator"),
}


class ResCompany(models.Model):
    _inherit = "res.company"

    nutkings_role_enforcement_enabled = fields.Boolean(
        string="Enforce Nut Kings Operational Roles",
        default=False,
        help="Assign user roles first, then enable this option. Settings administrators always retain full access.",
    )
    nutkings_require_service_area_on_dispatch = fields.Boolean(
        string="Require Service Area for Van Dispatch",
        default=True,
    )
    nutkings_history_window = fields.Integer(
        string="Demand History Window (Trips)",
        default=5,
    )
    nutkings_min_history_trips = fields.Integer(
        string="Minimum Trips for Suggestions",
        default=3,
    )
    nutkings_default_safety_percent = fields.Float(
        string="Default Demand Safety Allowance (%)",
        default=10.0,
    )
    nutkings_finished_goods_location_id = fields.Many2one(
        "stock.location",
        string="Finished Goods Warehouse Location",
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [False, id])]",
    )

    @api.constrains("nutkings_history_window", "nutkings_min_history_trips", "nutkings_default_safety_percent")
    def _check_nutkings_demand_settings(self):
        for company in self:
            if company.nutkings_history_window < 1 or company.nutkings_history_window > 24:
                raise ValidationError(_("The demand history window must be between 1 and 24 trips."))
            if company.nutkings_min_history_trips < 1 or company.nutkings_min_history_trips > company.nutkings_history_window:
                raise ValidationError(_("Minimum history trips must be between 1 and the history window."))
            if company.nutkings_default_safety_percent < 0 or company.nutkings_default_safety_percent > 100:
                raise ValidationError(_("The safety allowance must be between 0% and 100%."))


class ResUsers(models.Model):
    _inherit = "res.users"

    nutkings_role_office_receiving = fields.Boolean(
        string="Office Receiving",
        compute="_compute_nutkings_role_flags",
        inverse="_inverse_nutkings_role_office_receiving",
    )
    nutkings_role_raw_material_issue = fields.Boolean(
        string="Raw Materials Employee",
        compute="_compute_nutkings_role_flags",
        inverse="_inverse_nutkings_role_raw_material_issue",
    )
    nutkings_role_finished_goods_entry = fields.Boolean(
        string="Finished Goods Entry",
        compute="_compute_nutkings_role_flags",
        inverse="_inverse_nutkings_role_finished_goods_entry",
    )
    nutkings_role_dispatcher = fields.Boolean(
        string="Dispatcher",
        compute="_compute_nutkings_role_flags",
        inverse="_inverse_nutkings_role_dispatcher",
    )
    nutkings_role_manager = fields.Boolean(
        string="Nut Kings Manager / Administrator",
        compute="_compute_nutkings_role_flags",
        inverse="_inverse_nutkings_role_manager",
    )
    nutkings_role_summary = fields.Char(
        string="Nut Kings Roles",
        compute="_compute_nutkings_role_flags",
    )

    def _nutkings_groups_field(self):
        return "groups_id" if "groups_id" in self._fields else "group_ids"

    def _nutkings_has_target_group(self, xmlid):
        self.ensure_one()
        group = self.env.ref(xmlid, raise_if_not_found=False)
        if not group:
            return False
        return group in self[self._nutkings_groups_field()]

    @api.depends("write_date")
    def _compute_nutkings_role_flags(self):
        refs = {
            "nutkings_role_office_receiving": "nut_kings_ops.group_nutkings_office_receiving",
            "nutkings_role_raw_material_issue": "nut_kings_ops.group_nutkings_raw_material_issue",
            "nutkings_role_finished_goods_entry": "nut_kings_ops.group_nutkings_finished_goods_entry",
            "nutkings_role_dispatcher": "nut_kings_ops.group_nutkings_dispatcher",
            "nutkings_role_manager": "nut_kings_ops.group_nutkings_manager",
        }
        for user in self:
            labels = []
            for field_name, xmlid in refs.items():
                enabled = user._nutkings_has_target_group(xmlid)
                user[field_name] = enabled
                if enabled:
                    labels.append(dict(ROLE_LABELS).get(field_name.replace("nutkings_role_", ""), field_name))
            user.nutkings_role_summary = ", ".join(str(label) for label in labels) or _("No operational role assigned")

    def _set_nutkings_group(self, xmlid, enabled):
        group = self.env.ref(xmlid)
        group_field = self._nutkings_groups_field()
        for user in self:
            user.write({group_field: [(4 if enabled else 3, group.id)]})

    def _inverse_nutkings_role_office_receiving(self):
        for user in self:
            user._set_nutkings_group("nut_kings_ops.group_nutkings_office_receiving", user.nutkings_role_office_receiving)

    def _inverse_nutkings_role_raw_material_issue(self):
        for user in self:
            user._set_nutkings_group("nut_kings_ops.group_nutkings_raw_material_issue", user.nutkings_role_raw_material_issue)

    def _inverse_nutkings_role_finished_goods_entry(self):
        for user in self:
            user._set_nutkings_group("nut_kings_ops.group_nutkings_finished_goods_entry", user.nutkings_role_finished_goods_entry)

    def _inverse_nutkings_role_dispatcher(self):
        for user in self:
            user._set_nutkings_group("nut_kings_ops.group_nutkings_dispatcher", user.nutkings_role_dispatcher)

    def _inverse_nutkings_role_manager(self):
        for user in self:
            user._set_nutkings_group("nut_kings_ops.group_nutkings_manager", user.nutkings_role_manager)

    def nutkings_role_codes(self):
        self.ensure_one()
        roles = []
        mapping = [
            ("manager", "nut_kings_ops.group_nutkings_manager"),
            ("office_receiving", "nut_kings_ops.group_nutkings_office_receiving"),
            ("raw_material_issue", "nut_kings_ops.group_nutkings_raw_material_issue"),
            ("finished_goods_entry", "nut_kings_ops.group_nutkings_finished_goods_entry"),
            ("dispatcher", "nut_kings_ops.group_nutkings_dispatcher"),
        ]
        for code, xmlid in mapping:
            if self._nutkings_has_target_group(xmlid):
                roles.append(code)
        return roles

    def nutkings_is_manager(self):
        self.ensure_one()
        return self.id == SUPERUSER_ID or self.has_group("base.group_system") or self._nutkings_has_target_group("nut_kings_ops.group_nutkings_manager")

    def nutkings_can_operation(self, operation_code):
        self.ensure_one()
        code = (operation_code or "").upper()
        if self.nutkings_is_manager() or not self.company_id.nutkings_role_enforcement_enabled:
            return True
        group_xmlid = OPERATION_GROUPS.get(code)
        return bool(group_xmlid and self._nutkings_has_target_group(group_xmlid))

    def nutkings_check_operation(self, operation_code):
        self.ensure_one()
        if not self.nutkings_can_operation(operation_code):
            raise AccessError(_("Your Nut Kings Ops login is not authorized for this operation."))
        return True


class StockPicking(models.Model):
    _inherit = "stock.picking"

    nutkings_service_area_id = fields.Many2one(
        "nutkings.service.area",
        string="Service Area",
        index=True,
        check_company=True,
    )
    nutkings_van_id = fields.Many2one(
        "nutkings.truck",
        string="Van",
        index=True,
        check_company=True,
    )
    nutkings_dispatch_plan_id = fields.Many2one(
        "nutkings.dispatch.plan",
        string="Dispatch Plan",
        index=True,
        ondelete="set null",
    )

    @api.model
    def _nutkings_operation_code_from_picking_type(self, picking_type):
        if not picking_type:
            return False
        text = " ".join(filter(None, [picking_type.name, getattr(picking_type, "sequence_code", False), getattr(picking_type, "barcode", False)])).upper()
        source = getattr(picking_type, "default_location_src_id", False)
        dest = getattr(picking_type, "default_location_dest_id", False)
        loc_text = " ".join(filter(None, [
            getattr(source, "complete_name", False), getattr(source, "barcode", False),
            getattr(dest, "complete_name", False), getattr(dest, "barcode", False),
        ])).upper()
        combined = text + " " + loc_text
        if "RAW" in combined and ("RECEIPT" in combined or "RECEIVE" in combined):
            return "RM_RECEIPT"
        if "RAW" in combined and ("ISSUE" in combined or "CONSUM" in combined):
            return "RM_ISSUE"
        if "FINISHED" in combined and ("RECEIPT" in combined or "RECEIVE" in combined or "ENTRY" in combined):
            return "FG_RECEIPT"
        if ("TRUCK" in combined or "VAN" in combined) and ("LOAD" in combined or "DISPATCH" in combined):
            return "FG_TRUCK"
        if ("TRUCK" in combined or "VAN" in combined) and ("RETURN" in combined):
            return "TRUCK_RETURN"
        if ("TRUCK" in combined or "VAN" in combined) and ("DELIVERY" in combined or "CUSTOMER" in combined):
            return "TRUCK_DELIVERY"
        return False

    @api.model
    def _nutkings_operation_code_from_vals(self, vals):
        for key in ("nutkings_operation_code", "operation_code", "operation_type_code", "nutking_operation_type"):
            value = vals.get(key)
            if value:
                return str(value).upper()
        picking_type_id = vals.get("picking_type_id")
        if picking_type_id:
            return self._nutkings_operation_code_from_picking_type(self.env["stock.picking.type"].browse(picking_type_id))
        return False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            code = self._nutkings_operation_code_from_vals(vals)
            if code:
                self.env.user.nutkings_check_operation(code)
                if code in ("FG_TRUCK", "TRUCK_DELIVERY", "TRUCK_RETURN") and self.env.company.nutkings_role_enforcement_enabled:
                    if self.env.company.nutkings_require_service_area_on_dispatch and not vals.get("nutkings_service_area_id"):
                        raise ValidationError(_("Select a service area before confirming this van operation."))
        return super().create(vals_list)

    def button_validate(self):
        for picking in self:
            code = self._nutkings_operation_code_from_picking_type(picking.picking_type_id)
            if code:
                self.env.user.nutkings_check_operation(code)
                if code in ("FG_TRUCK", "TRUCK_DELIVERY", "TRUCK_RETURN") and self.env.company.nutkings_role_enforcement_enabled:
                    if self.env.company.nutkings_require_service_area_on_dispatch and not picking.nutkings_service_area_id:
                        raise ValidationError(_("Select a service area before validating this van operation."))
        return super().button_validate()
