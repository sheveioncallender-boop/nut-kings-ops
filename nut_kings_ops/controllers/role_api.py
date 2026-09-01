from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError, UserError, ValidationError


class NutKingsRoleWorkflowApi(http.Controller):

    @http.route("/nutkings/api/session-profile", type="json", auth="user", methods=["POST"], csrf=False)
    def session_profile(self, **kwargs):
        user = request.env.user
        company = request.env.company
        operations = {
            code: user.nutkings_can_operation(code)
            for code in ("RM_RECEIPT", "RM_ISSUE", "FG_RECEIPT", "FG_TRUCK", "TRUCK_DELIVERY", "TRUCK_RETURN")
        }
        Area = request.env["nutkings.service.area"].sudo()
        Van = request.env["nutkings.truck"].sudo()
        areas = Area.search([("company_id", "=", company.id), ("active", "=", True)], order="sequence, name")
        vans = Van.search([("company_id", "=", company.id)] if "company_id" in Van._fields else [])
        return {
            "user": {"id": user.id, "name": user.name, "login": user.login},
            "roles": user.nutkings_role_codes(),
            "role_summary": user.nutkings_role_summary,
            "is_manager": user.nutkings_is_manager(),
            "enforcement_enabled": company.nutkings_role_enforcement_enabled,
            "operations": operations,
            "service_areas": [{
                "id": area.id,
                "name": area.name,
                "code": area.code,
                "safety_percent": area.safety_percent,
                "minimum_history_trips": area.minimum_history_trips,
                "history_window": area.history_window,
            } for area in areas],
            "vans": [{
                "id": van.id,
                "name": van.display_name,
                "primary_service_area_id": van.primary_service_area_id.id,
                "primary_service_area_name": van.primary_service_area_id.display_name if van.primary_service_area_id else "",
            } for van in vans],
        }

    @http.route("/nutkings/api/dispatch-plan/generate", type="json", auth="user", methods=["POST"], csrf=False)
    def generate_dispatch_plan(self, truck_id=None, service_area_id=None, trip_id=None, **kwargs):
        user = request.env.user
        user.nutkings_check_operation("FG_TRUCK")
        if not truck_id or not service_area_id:
            raise UserError(_("Select a van and service area."))
        values = {
            "truck_id": int(truck_id),
            "service_area_id": int(service_area_id),
        }
        if trip_id:
            values["trip_id"] = int(trip_id)
        plan = request.env["nutkings.dispatch.plan"].create(values)
        plan.action_generate_suggestions()
        return plan.workspace_payload()

    @http.route("/nutkings/api/dispatch-plan/save", type="json", auth="user", methods=["POST"], csrf=False)
    def save_dispatch_plan(self, plan_id=None, lines=None, approve=False, **kwargs):
        request.env.user.nutkings_check_operation("FG_TRUCK")
        plan = request.env["nutkings.dispatch.plan"].browse(int(plan_id or 0)).exists()
        if not plan:
            raise UserError(_("The dispatch plan could not be found."))
        if plan.company_id != request.env.company:
            raise AccessError(_("You cannot update a dispatch plan from another company."))
        line_map = {int(item.get("id")): item for item in (lines or []) if item.get("id")}
        for line in plan.line_ids:
            payload = line_map.get(line.id)
            if payload is not None:
                line.write({
                    "actual_load_qty": max(float(payload.get("actual_load_qty") or 0.0), 0.0),
                    "dispatcher_note": payload.get("dispatcher_note") or False,
                })
        if approve:
            plan.action_approve()
        return plan.workspace_payload()

    @http.route("/nutkings/api/tag-operation-area", type="json", auth="user", methods=["POST"], csrf=False)
    def tag_operation_area(self, model=None, record_id=None, service_area_id=None, truck_id=None, dispatch_plan_id=None, **kwargs):
        request.env.user.nutkings_check_operation("FG_TRUCK")
        if model not in ("stock.picking", "nutkings.trip"):
            raise UserError(_("Unsupported operation record."))
        record = request.env[model].browse(int(record_id or 0)).exists()
        if not record:
            raise UserError(_("The operation record could not be found."))
        values = {}
        if service_area_id and "nutkings_service_area_id" in record._fields:
            values["nutkings_service_area_id"] = int(service_area_id)
        elif service_area_id and "service_area_id" in record._fields:
            values["service_area_id"] = int(service_area_id)
        if truck_id and "nutkings_van_id" in record._fields:
            values["nutkings_van_id"] = int(truck_id)
        if dispatch_plan_id:
            if "nutkings_dispatch_plan_id" in record._fields:
                values["nutkings_dispatch_plan_id"] = int(dispatch_plan_id)
            elif "dispatch_plan_id" in record._fields:
                values["dispatch_plan_id"] = int(dispatch_plan_id)
        if values:
            record.write(values)
        return {"ok": True, "model": model, "id": record.id}
