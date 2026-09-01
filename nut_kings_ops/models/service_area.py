import json
import math
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class NutKingsServiceArea(models.Model):
    _name = "nutkings.service.area"
    _description = "Nut Kings Van Service Area"
    _order = "sequence, name"
    _check_company_auto = True

    name = fields.Char(required=True, index=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    description = fields.Text()
    safety_percent = fields.Float(string="Safety Allowance (%)", default=10.0)
    minimum_history_trips = fields.Integer(string="Minimum Completed Trips", default=3)
    history_window = fields.Integer(string="History Window", default=5)
    van_ids = fields.One2many("nutkings.truck", "primary_service_area_id", string="Primary Vans")
    van_count = fields.Integer(compute="_compute_counts")
    trip_count = fields.Integer(compute="_compute_counts")
    dispatch_plan_count = fields.Integer(compute="_compute_counts")

    _sql_constraints = [
        ("code_company_uniq", "unique(code, company_id)", "The service-area code must be unique per company."),
    ]

    @api.depends("van_ids")
    def _compute_counts(self):
        Trip = self.env["nutkings.trip"]
        Plan = self.env["nutkings.dispatch.plan"]
        for area in self:
            area.van_count = len(area.van_ids)
            area.trip_count = Trip.search_count([("service_area_id", "=", area.id)])
            area.dispatch_plan_count = Plan.search_count([("service_area_id", "=", area.id)])

    @api.constrains("safety_percent", "minimum_history_trips", "history_window")
    def _check_values(self):
        for area in self:
            if area.safety_percent < 0 or area.safety_percent > 100:
                raise ValidationError(_("The safety allowance must be between 0% and 100%."))
            if area.history_window < 1 or area.history_window > 24:
                raise ValidationError(_("The history window must be between 1 and 24 trips."))
            if area.minimum_history_trips < 1 or area.minimum_history_trips > area.history_window:
                raise ValidationError(_("Minimum completed trips must be between 1 and the history window."))

    def action_view_vans(self):
        self.ensure_one()
        action = self.env.ref("nut_kings_ops.action_nutkings_trucks", raise_if_not_found=False)
        if action:
            result = action.read()[0]
            result["domain"] = [("primary_service_area_id", "=", self.id)]
            return result
        return {"type": "ir.actions.act_window", "name": _("Vans"), "res_model": "nutkings.truck", "view_mode": "list,form", "domain": [("primary_service_area_id", "=", self.id)]}

    def action_view_plans(self):
        self.ensure_one()
        action = self.env.ref("nut_kings_ops.action_nutkings_dispatch_plan").read()[0]
        action["domain"] = [("service_area_id", "=", self.id)]
        return action


class NutKingsTruck(models.Model):
    _inherit = "nutkings.truck"

    primary_service_area_id = fields.Many2one(
        "nutkings.service.area",
        string="Primary Service Area",
        index=True,
        check_company=True,
    )
    service_area_notes = fields.Text(string="Service Area / Product Mix Notes")
    dispatch_plan_ids = fields.One2many("nutkings.dispatch.plan", "truck_id", string="Demand Plans")
    dispatch_plan_count = fields.Integer(compute="_compute_dispatch_plan_count")

    def _compute_dispatch_plan_count(self):
        Plan = self.env["nutkings.dispatch.plan"]
        for van in self:
            van.dispatch_plan_count = Plan.search_count([("truck_id", "=", van.id)])

    def action_create_demand_plan(self):
        self.ensure_one()
        plan = self.env["nutkings.dispatch.plan"].create({
            "truck_id": self.id,
            "service_area_id": self.primary_service_area_id.id,
        })
        plan.action_generate_suggestions()
        return {
            "type": "ir.actions.act_window",
            "name": _("Van Load Demand Plan"),
            "res_model": "nutkings.dispatch.plan",
            "res_id": plan.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_dispatch_plans(self):
        self.ensure_one()
        action = self.env.ref("nut_kings_ops.action_nutkings_dispatch_plan").read()[0]
        action["domain"] = [("truck_id", "=", self.id)]
        action["context"] = {"default_truck_id": self.id, "default_service_area_id": self.primary_service_area_id.id}
        return action


class NutKingsTrip(models.Model):
    _inherit = "nutkings.trip"

    service_area_id = fields.Many2one(
        "nutkings.service.area",
        string="Service Area",
        index=True,
        check_company=True,
    )
    dispatch_plan_id = fields.Many2one("nutkings.dispatch.plan", string="Demand / Load Plan", ondelete="set null")

    @api.onchange("truck_id")
    def _onchange_nutkings_truck_service_area(self):
        for trip in self:
            if trip.truck_id and not trip.service_area_id:
                trip.service_area_id = trip.truck_id.primary_service_area_id

    def action_generate_demand_plan(self):
        self.ensure_one()
        if not self.truck_id:
            raise UserError(_("Select a van before generating a demand plan."))
        area = self.service_area_id or self.truck_id.primary_service_area_id
        if not area:
            raise UserError(_("Select a service area or configure the van's primary service area."))
        plan = self.dispatch_plan_id
        if not plan:
            plan = self.env["nutkings.dispatch.plan"].create({
                "truck_id": self.truck_id.id,
                "service_area_id": area.id,
                "trip_id": self.id,
            })
            self.dispatch_plan_id = plan
        plan.action_generate_suggestions()
        return {
            "type": "ir.actions.act_window",
            "name": _("Van Load Demand Plan"),
            "res_model": "nutkings.dispatch.plan",
            "res_id": plan.id,
            "view_mode": "form",
            "target": "current",
        }


class NutKingsTripLine(models.Model):
    _inherit = "nutkings.trip.line"

    service_area_id = fields.Many2one(related="trip_id.service_area_id", store=True, index=True)
    demand_loaded_qty = fields.Float(string="Loaded", compute="_compute_demand_metrics")
    demand_sold_qty = fields.Float(string="Sold / Delivered", compute="_compute_demand_metrics")
    demand_returned_qty = fields.Float(string="Returned", compute="_compute_demand_metrics")
    demand_damaged_qty = fields.Float(string="Damaged", compute="_compute_demand_metrics")
    demand_ending_qty = fields.Float(string="Ending Van Stock", compute="_compute_demand_metrics")
    demand_variance_qty = fields.Float(string="Variance", compute="_compute_demand_metrics")
    demand_sell_through_percent = fields.Float(string="Sell-through %", compute="_compute_demand_metrics")
    demand_return_percent = fields.Float(string="Return %", compute="_compute_demand_metrics")
    demand_stockout = fields.Boolean(string="Stock-out", compute="_compute_demand_metrics")

    @api.model
    def _demand_number(self, record, candidates, default=0.0):
        for name in candidates:
            if name in record._fields:
                value = record[name]
                if value is not False and value is not None:
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        continue
        return float(default)

    def _compute_demand_metrics(self):
        for line in self:
            loaded = self._demand_number(line, ["loaded_qty", "quantity_loaded", "qty_loaded", "planned_qty", "quantity", "product_uom_qty"])
            sold = self._demand_number(line, ["delivered_qty", "quantity_delivered", "qty_delivered", "sold_qty", "quantity_sold"])
            returned = self._demand_number(line, ["returned_qty", "quantity_returned", "qty_returned"])
            damaged = self._demand_number(line, ["damaged_qty", "quantity_damaged", "qty_damaged"])
            ending = self._demand_number(line, ["ending_qty", "closing_qty", "remaining_qty", "van_ending_qty"], max(loaded - sold - returned - damaged, 0.0))
            variance = self._demand_number(line, ["variance_qty", "quantity_variance", "qty_variance"], loaded - sold - returned - damaged - ending)
            available = max(loaded, 0.0)
            line.demand_loaded_qty = loaded
            line.demand_sold_qty = sold
            line.demand_returned_qty = returned
            line.demand_damaged_qty = damaged
            line.demand_ending_qty = ending
            line.demand_variance_qty = variance
            line.demand_sell_through_percent = sold / available * 100.0 if available else 0.0
            line.demand_return_percent = returned / available * 100.0 if available else 0.0
            line.demand_stockout = bool(available and ending <= 0 and sold >= available - 0.00001)


class NutKingsDispatchPlan(models.Model):
    _name = "nutkings.dispatch.plan"
    _description = "Nut Kings Service-Area Van Load Plan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    truck_id = fields.Many2one("nutkings.truck", string="Van", required=True, tracking=True, check_company=True)
    service_area_id = fields.Many2one("nutkings.service.area", required=True, tracking=True, check_company=True)
    trip_id = fields.Many2one("nutkings.trip", string="Distribution Trip", ondelete="set null", check_company=True)
    state = fields.Selection([
        ("draft", "Draft"),
        ("review", "Review"),
        ("approved", "Approved for Loading"),
        ("used", "Used / Loaded"),
        ("cancelled", "Cancelled"),
    ], default="draft", required=True, tracking=True, index=True)
    generated_at = fields.Datetime(readonly=True)
    generated_by_id = fields.Many2one("res.users", readonly=True)
    history_trip_count = fields.Integer(readonly=True)
    history_window = fields.Integer(default=lambda self: self.env.company.nutkings_history_window)
    minimum_history_trips = fields.Integer(default=lambda self: self.env.company.nutkings_min_history_trips)
    safety_percent = fields.Float(default=lambda self: self.env.company.nutkings_default_safety_percent)
    insufficient_history = fields.Boolean(compute="_compute_totals")
    line_ids = fields.One2many("nutkings.dispatch.plan.line", "plan_id", string="Recommended Products", copy=True)
    suggested_total_qty = fields.Float(compute="_compute_totals")
    actual_total_qty = fields.Float(compute="_compute_totals")
    warehouse_shortage_line_count = fields.Integer(compute="_compute_totals")
    notes = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("nutkings.dispatch.plan") or _("New")
        return super().create(vals_list)

    @api.onchange("truck_id")
    def _onchange_truck_id(self):
        for plan in self:
            if plan.truck_id and not plan.service_area_id:
                plan.service_area_id = plan.truck_id.primary_service_area_id

    @api.depends("line_ids.suggested_load_qty", "line_ids.actual_load_qty", "line_ids.warehouse_shortage", "history_trip_count", "minimum_history_trips")
    def _compute_totals(self):
        for plan in self:
            plan.suggested_total_qty = sum(plan.line_ids.mapped("suggested_load_qty"))
            plan.actual_total_qty = sum(plan.line_ids.mapped("actual_load_qty"))
            plan.warehouse_shortage_line_count = len(plan.line_ids.filtered("warehouse_shortage"))
            plan.insufficient_history = plan.history_trip_count < plan.minimum_history_trips

    @api.constrains("history_window", "minimum_history_trips", "safety_percent")
    def _check_parameters(self):
        for plan in self:
            if plan.history_window < 1 or plan.history_window > 24:
                raise ValidationError(_("The history window must be between 1 and 24 trips."))
            if plan.minimum_history_trips < 1 or plan.minimum_history_trips > plan.history_window:
                raise ValidationError(_("Minimum history trips must be between 1 and the history window."))
            if plan.safety_percent < 0 or plan.safety_percent > 100:
                raise ValidationError(_("The safety allowance must be between 0% and 100%."))

    def _truck_location(self):
        self.ensure_one()
        for field_name in ("location_id", "stock_location_id", "inventory_location_id"):
            if field_name in self.truck_id._fields and self.truck_id[field_name]:
                return self.truck_id[field_name]
        return self.env["stock.location"].search([
            ("usage", "=", "internal"),
            "|", ("name", "ilike", self.truck_id.display_name), ("barcode", "ilike", "NK-"),
        ], limit=1)

    def _finished_goods_location(self):
        self.ensure_one()
        if self.company_id.nutkings_finished_goods_location_id:
            return self.company_id.nutkings_finished_goods_location_id
        location = self.env.ref("nut_kings_ops.location_finished_goods", raise_if_not_found=False)
        if location:
            return location
        return self.env["stock.location"].search([
            ("usage", "=", "internal"),
            ("company_id", "in", [False, self.company_id.id]),
            "|", ("barcode", "ilike", "NK-FG"), ("complete_name", "ilike", "Finished Goods"),
        ], limit=1)

    @api.model
    def _line_number(self, line, candidates, default=0.0):
        for name in candidates:
            if name in line._fields:
                value = line[name]
                if value is not False and value is not None:
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        continue
        return float(default)

    @api.model
    def _line_product(self, line):
        for name in ("product_id", "product_variant_id"):
            if name in line._fields and line[name]:
                return line[name]
        return self.env["product.product"]

    @api.model
    def _trip_line_field(self):
        Line = self.env["nutkings.trip.line"]
        for name in ("trip_id", "distribution_trip_id"):
            if name in Line._fields:
                return name
        return False

    def _completed_history(self):
        self.ensure_one()
        Trip = self.env["nutkings.trip"]
        domain = [("id", "!=", self.trip_id.id or 0), ("company_id", "=", self.company_id.id)]
        if "service_area_id" in Trip._fields:
            domain.append(("service_area_id", "=", self.service_area_id.id))
        trips = Trip.search(domain, order="date desc, id desc" if "date" in Trip._fields else "id desc", limit=max(self.history_window * 3, self.history_window))
        if "state" in Trip._fields:
            completed_states = {"done", "completed", "closed", "reconciled"}
            done = trips.filtered(lambda t: t.state in completed_states)
            if done:
                trips = done
        return trips[: self.history_window]

    @api.model
    def _quant_qty(self, product, location):
        if not product or not location:
            return 0.0
        quants = self.env["stock.quant"].sudo().search([
            ("product_id", "=", product.id),
            ("location_id", "child_of", location.id),
        ])
        available = 0.0
        for quant in quants:
            if "available_quantity" in quant._fields:
                available += quant.available_quantity
            else:
                available += quant.quantity - quant.reserved_quantity
        return max(available, 0.0)

    @api.model
    def calculate_suggested_quantity(self, weighted_average_sold, safety_percent, current_van_qty, warehouse_available):
        target = math.ceil(max(weighted_average_sold, 0.0) * (1.0 + max(safety_percent, 0.0) / 100.0))
        needed = max(target - max(current_van_qty, 0.0), 0.0)
        if warehouse_available is not None:
            needed = min(needed, max(warehouse_available, 0.0))
        return float(needed)

    def action_generate_suggestions(self):
        for plan in self:
            plan.env.user.nutkings_check_operation("FG_TRUCK")
            if not plan.truck_id or not plan.service_area_id:
                raise UserError(_("Select both a van and a service area."))
            history = plan._completed_history()
            plan.history_trip_count = len(history)
            plan.generated_at = fields.Datetime.now()
            plan.generated_by_id = self.env.user
            plan.line_ids.unlink()
            trip_line_field = plan._trip_line_field()
            if not trip_line_field:
                raise UserError(_("The distribution trip line relationship could not be identified."))
            weights = {trip.id: len(history) - index for index, trip in enumerate(history)}
            Line = self.env["nutkings.trip.line"]
            hist_lines = Line.search([(trip_line_field, "in", history.ids)]) if history else Line.browse()
            stats = defaultdict(lambda: {
                "weighted_sold": 0.0,
                "weight": 0.0,
                "loaded": 0.0,
                "sold": 0.0,
                "returned": 0.0,
                "stockouts": 0,
                "trips": 0,
                "last": None,
            })
            for line in hist_lines:
                product = plan._line_product(line)
                if not product:
                    continue
                trip = line[trip_line_field]
                weight = weights.get(trip.id, 1)
                loaded = plan._line_number(line, ["loaded_qty", "quantity_loaded", "qty_loaded", "planned_qty", "quantity", "product_uom_qty"])
                sold = plan._line_number(line, ["delivered_qty", "quantity_delivered", "qty_delivered", "sold_qty", "quantity_sold"])
                returned = plan._line_number(line, ["returned_qty", "quantity_returned", "qty_returned"])
                damaged = plan._line_number(line, ["damaged_qty", "quantity_damaged", "qty_damaged"])
                ending = plan._line_number(line, ["ending_qty", "closing_qty", "remaining_qty", "van_ending_qty"], max(loaded - sold - returned - damaged, 0.0))
                data = stats[product.id]
                data["weighted_sold"] += sold * weight
                data["weight"] += weight
                data["loaded"] += loaded
                data["sold"] += sold
                data["returned"] += returned
                data["trips"] += 1
                data["stockouts"] += int(bool(loaded and ending <= 0 and sold >= loaded - 0.00001))
                if data["last"] is None or weights.get(trip.id, 0) > data["last"][0]:
                    data["last"] = (weights.get(trip.id, 0), loaded, sold, returned)
            # Include active finished-goods products even when history is still being built.
            Product = self.env["product.product"]
            product_domain = [("active", "=", True), ("type", "!=", "service")]
            if "nutkings_inventory_type" in Product._fields:
                product_domain.append(("nutkings_inventory_type", "=", "finished"))
            products = Product.search(product_domain)
            product_ids = set(stats.keys()) | set(products.ids)
            truck_location = plan._truck_location()
            fg_location = plan._finished_goods_location()
            commands = []
            for product in Product.browse(sorted(product_ids)):
                data = stats[product.id]
                avg_sold = data["weighted_sold"] / data["weight"] if data["weight"] else 0.0
                current_van = plan._quant_qty(product, truck_location)
                warehouse_available = plan._quant_qty(product, fg_location)
                suggested = 0.0
                status = "insufficient"
                reason = _("Insufficient history — dispatcher to enter the quantity manually.")
                if plan.history_trip_count >= plan.minimum_history_trips and data["trips"]:
                    suggested = plan.calculate_suggested_quantity(avg_sold, plan.safety_percent, current_van, warehouse_available)
                    return_rate = data["returned"] / data["loaded"] * 100.0 if data["loaded"] else 0.0
                    stockout_rate = data["stockouts"] / data["trips"] * 100.0 if data["trips"] else 0.0
                    if stockout_rate >= 50:
                        status = "increase"
                        reason = _("Increase: this product repeatedly sold out in the service area.")
                    elif return_rate >= 35:
                        status = "reduce"
                        reason = _("Reduce: this product has a high return rate in the service area.")
                    else:
                        status = "maintain"
                        reason = _("Maintain: recent service-area demand is stable.")
                last = data["last"] or (0, 0.0, 0.0, 0.0)
                if data["trips"] or current_van or suggested:
                    commands.append((0, 0, {
                        "product_id": product.id,
                        "history_trip_count": data["trips"],
                        "current_van_qty": current_van,
                        "last_loaded_qty": last[1],
                        "last_sold_qty": last[2],
                        "last_returned_qty": last[3],
                        "weighted_average_sold": avg_sold,
                        "return_rate": data["returned"] / data["loaded"] * 100.0 if data["loaded"] else 0.0,
                        "stockout_rate": data["stockouts"] / data["trips"] * 100.0 if data["trips"] else 0.0,
                        "warehouse_available_qty": warehouse_available,
                        "suggested_load_qty": suggested,
                        "actual_load_qty": suggested,
                        "recommendation_status": status,
                        "recommendation_reason": reason,
                    }))
            plan.write({"line_ids": commands, "state": "review"})
        return True

    def action_use_suggested_quantities(self):
        for plan in self:
            for line in plan.line_ids:
                line.actual_load_qty = line.suggested_load_qty
        return True

    def action_approve(self):
        for plan in self:
            plan.env.user.nutkings_check_operation("FG_TRUCK")
            if not plan.line_ids:
                raise UserError(_("Generate or add at least one product before approving the load plan."))
            plan.state = "approved"
        return True

    def action_mark_used(self):
        self.write({"state": "used"})
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True

    def action_reset_draft(self):
        self.write({"state": "draft"})
        return True

    def workspace_payload(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
            "van": {"id": self.truck_id.id, "name": self.truck_id.display_name},
            "service_area": {"id": self.service_area_id.id, "name": self.service_area_id.display_name},
            "history_trip_count": self.history_trip_count,
            "minimum_history_trips": self.minimum_history_trips,
            "insufficient_history": self.insufficient_history,
            "suggested_total_qty": self.suggested_total_qty,
            "actual_total_qty": self.actual_total_qty,
            "lines": [line.workspace_payload() for line in self.line_ids.sorted(lambda l: (l.recommendation_status, l.product_id.display_name))],
        }


class NutKingsDispatchPlanLine(models.Model):
    _name = "nutkings.dispatch.plan.line"
    _description = "Nut Kings Van Load Demand Recommendation"
    _order = "recommendation_status, product_id"
    _check_company_auto = True

    plan_id = fields.Many2one("nutkings.dispatch.plan", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="plan_id.company_id", store=True, index=True)
    service_area_id = fields.Many2one(related="plan_id.service_area_id", store=True, index=True)
    truck_id = fields.Many2one(related="plan_id.truck_id", store=True, index=True)
    product_id = fields.Many2one("product.product", required=True, index=True, check_company=True)
    barcode = fields.Char(related="product_id.barcode", store=False)
    internal_reference = fields.Char(related="product_id.default_code", store=False)
    history_trip_count = fields.Integer(readonly=True)
    current_van_qty = fields.Float(readonly=True)
    last_loaded_qty = fields.Float(readonly=True)
    last_sold_qty = fields.Float(readonly=True)
    last_returned_qty = fields.Float(readonly=True)
    weighted_average_sold = fields.Float(string="Recent Weighted Average Sold", readonly=True)
    return_rate = fields.Float(string="Return %", readonly=True)
    stockout_rate = fields.Float(string="Stock-out Frequency %", readonly=True)
    warehouse_available_qty = fields.Float(string="FG Warehouse Available", readonly=True)
    suggested_load_qty = fields.Float(readonly=True)
    actual_load_qty = fields.Float(string="Dispatcher Load Quantity")
    recommendation_status = fields.Selection([
        ("increase", "Increase"),
        ("maintain", "Maintain"),
        ("reduce", "Reduce"),
        ("insufficient", "Insufficient History"),
    ], default="insufficient", required=True, index=True)
    recommendation_reason = fields.Char(readonly=True)
    dispatcher_note = fields.Char()
    warehouse_shortage = fields.Boolean(compute="_compute_warehouse_shortage")
    variance_from_suggestion = fields.Float(compute="_compute_warehouse_shortage")

    @api.depends("actual_load_qty", "suggested_load_qty", "warehouse_available_qty")
    def _compute_warehouse_shortage(self):
        for line in self:
            line.warehouse_shortage = line.actual_load_qty > line.warehouse_available_qty + 0.00001
            line.variance_from_suggestion = line.actual_load_qty - line.suggested_load_qty

    @api.constrains("actual_load_qty")
    def _check_actual_qty(self):
        for line in self:
            if line.actual_load_qty < 0:
                raise ValidationError(_("The dispatcher load quantity cannot be negative."))

    def workspace_payload(self):
        self.ensure_one()
        return {
            "id": self.id,
            "product_id": self.product_id.id,
            "product_name": self.product_id.display_name,
            "barcode": self.product_id.barcode or "",
            "internal_reference": self.product_id.default_code or "",
            "history_trip_count": self.history_trip_count,
            "current_van_qty": self.current_van_qty,
            "last_loaded_qty": self.last_loaded_qty,
            "last_sold_qty": self.last_sold_qty,
            "last_returned_qty": self.last_returned_qty,
            "weighted_average_sold": self.weighted_average_sold,
            "return_rate": self.return_rate,
            "stockout_rate": self.stockout_rate,
            "warehouse_available_qty": self.warehouse_available_qty,
            "suggested_load_qty": self.suggested_load_qty,
            "actual_load_qty": self.actual_load_qty,
            "recommendation_status": self.recommendation_status,
            "recommendation_reason": self.recommendation_reason,
            "warehouse_shortage": self.warehouse_shortage,
        }
