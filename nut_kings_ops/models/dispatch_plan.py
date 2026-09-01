from collections import defaultdict

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_round


class NutKingsDispatchPlan(models.Model):
    _name = 'nutkings.dispatch.plan'
    _description = 'Nut Kings Dispatch Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'planned_departure desc, id desc'

    name = fields.Char(default='New', readonly=True, copy=False, index=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company,
        required=True, index=True,
    )
    service_area_id = fields.Many2one(
        'nutkings.service.area', required=True, tracking=True, index=True,
        domain="[('company_id', '=', company_id)]",
    )
    truck_id = fields.Many2one(
        'nutkings.truck', required=True, tracking=True, index=True,
        domain="[('company_id', '=', company_id)]",
    )
    driver_id = fields.Many2one('nutkings.staff', domain=[('role', '=', 'driver')], tracking=True)
    team_ids = fields.Many2many(
        'nutkings.staff', 'nk_dispatch_plan_staff_rel',
        'plan_id', 'staff_id', string='Distribution Team',
    )
    planned_departure = fields.Datetime(default=fields.Datetime.now, required=True, tracking=True)
    history_trip_count = fields.Integer(
        string='Trips to Analyse', default=6, required=True,
        help='Number of the most recent closed trips in this service area used for product rotation.',
    )
    safety_stock_percent = fields.Float(
        string='Sales Buffer %', default=10.0, required=True,
        help='Additional quantity above average sales. Returns are shown separately so the dispatcher can reduce or pause weak products.',
    )
    analysed_trip_count = fields.Integer(readonly=True, copy=False)
    line_ids = fields.One2many('nutkings.dispatch.plan.line', 'plan_id', string='Product Rotation')
    trip_id = fields.Many2one('nutkings.trip', readonly=True, copy=False, ondelete='set null')
    loading_picking_id = fields.Many2one('stock.picking', readonly=True, copy=False, ondelete='set null')
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('ready', 'Approved'),
            ('loading', 'Loading'),
            ('done', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft', required=True, tracking=True, index=True,
    )
    notes = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get('name', 'New') == 'New':
                values['name'] = self.env['ir.sequence'].next_by_code('nutkings.dispatch.plan') or 'New'
        return super().create(vals_list)

    @api.constrains('history_trip_count', 'safety_stock_percent')
    def _check_analysis_settings(self):
        for plan in self:
            if plan.history_trip_count < 1 or plan.history_trip_count > 100:
                raise ValidationError(_('Trips to Analyse must be between 1 and 100.'))
            if plan.safety_stock_percent < 0 or plan.safety_stock_percent > 100:
                raise ValidationError(_('Sales Buffer must be between 0% and 100%.'))

    @api.constrains('company_id', 'truck_id', 'service_area_id', 'driver_id', 'team_ids')
    def _check_truck_service_area(self):
        for plan in self:
            if plan.service_area_id.company_id != plan.company_id or plan.truck_id.company_id != plan.company_id:
                raise ValidationError(_('The service area and truck must belong to the dispatch-plan company.'))
            if plan.driver_id and plan.driver_id.company_id != plan.company_id:
                raise ValidationError(_('The driver must belong to the dispatch-plan company.'))
            if any(member.company_id != plan.company_id for member in plan.team_ids):
                raise ValidationError(_('Every distribution-team member must belong to the dispatch-plan company.'))
            assigned = plan.truck_id.service_area_ids
            if assigned and plan.service_area_id not in assigned:
                raise ValidationError(_(
                    '%(truck)s is not assigned to the %(area)s service area.',
                    truck=plan.truck_id.display_name,
                    area=plan.service_area_id.display_name,
                ))

    def _history_trips(self):
        self.ensure_one()
        return self.env['nutkings.trip'].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'),
            '|',
            ('service_area_id', '=', self.service_area_id.id),
            '&',
            ('service_area_id', '=', False),
            ('route_name', '=ilike', self.service_area_id.name),
        ], order='actual_return desc, planned_departure desc, id desc', limit=self.history_trip_count)

    @staticmethod
    def _rotation_action(average_loaded, average_sold, average_returned, sell_through):
        if not average_loaded and not average_sold and not average_returned:
            return 'manual'
        if not average_sold and average_returned:
            return 'pause'
        if sell_through >= 85.0:
            return 'increase'
        if sell_through >= 60.0:
            return 'maintain'
        if sell_through >= 30.0:
            return 'reduce'
        return 'pause'

    def action_generate_rotation(self):
        Product = self.env['product.product']
        for plan in self:
            if plan.state != 'draft':
                raise UserError(_('Return the dispatch plan to Draft before recalculating product rotation.'))
            trips = plan._history_trips()
            trip_count = len(trips)
            totals = defaultdict(lambda: {'loaded': 0.0, 'sold': 0.0, 'returned': 0.0})
            for line in trips.mapped('line_ids'):
                row = totals[line.product_id.id]
                row['loaded'] += line.qty_loaded
                row['sold'] += line.qty_delivered
                row['returned'] += line.qty_returned

            products = Product.search([
                ('active', '=', True),
                ('company_id', 'in', (False, plan.company_id.id)),
                ('product_tmpl_id.nk_enabled', '=', True),
                ('nk_inventory_type', '=', 'finished_good'),
            ], order='name, default_code')
            commands = [Command.clear()]
            divisor = trip_count or 1
            for product in products:
                row = totals[product.id]
                average_loaded = row['loaded'] / divisor
                average_sold = row['sold'] / divisor
                average_returned = row['returned'] / divisor
                sell_through = (row['sold'] / row['loaded'] * 100.0) if row['loaded'] else 0.0
                action = plan._rotation_action(
                    average_loaded, average_sold, average_returned, sell_through,
                )
                recommended = average_sold * (1.0 + plan.safety_stock_percent / 100.0)
                if action == 'pause':
                    recommended = 0.0
                recommended = float_round(
                    max(0.0, recommended),
                    precision_rounding=product.uom_id.rounding,
                    rounding_method='UP',
                )
                commands.append(Command.create({
                    'product_id': product.id,
                    'history_loaded_qty': row['loaded'],
                    'history_sold_qty': row['sold'],
                    'history_returned_qty': row['returned'],
                    'average_loaded_qty': average_loaded,
                    'average_sold_qty': average_sold,
                    'average_returned_qty': average_returned,
                    'sell_through_percent': sell_through,
                    'rotation_action': action,
                    'recommended_qty': recommended,
                    'planned_qty': recommended,
                    'selected': bool(trip_count and recommended > 0.0),
                }))
            plan.write({'line_ids': commands, 'analysed_trip_count': trip_count})
        return True

    def action_approve(self):
        for plan in self:
            if plan.state != 'draft':
                raise UserError(_('Only a Draft dispatch plan can be approved.'))
            usable = plan.line_ids.filtered(
                lambda line: line.selected and float_compare(
                    line.planned_qty, 0.0,
                    precision_rounding=line.product_uom_id.rounding,
                ) > 0
            )
            if not usable:
                raise UserError(_('Select at least one product with a positive planned quantity.'))
            plan.state = 'ready'
        return True

    def _create_trip(self):
        self.ensure_one()
        if self.trip_id:
            return self.trip_id
        customer_ids = self.service_area_id.customer_ids.filtered(
            lambda partner: partner.active and partner.nk_is_available_customer()
        ).ids
        trip = self.env['nutkings.trip'].create({
            'truck_id': self.truck_id.id,
            'driver_id': self.driver_id.id or self.truck_id.default_driver_id.id or False,
            'team_ids': [Command.set(self.team_ids.ids or self.truck_id.default_team_ids.ids)],
            'customer_ids': [Command.set(customer_ids)],
            'route_name': self.service_area_id.name,
            'service_area_id': self.service_area_id.id,
            'dispatch_plan_id': self.id,
            'planned_departure': self.planned_departure,
            'notes': self.notes,
            'company_id': self.company_id.id,
        })
        self.trip_id = trip
        return trip

    def action_create_loading(self):
        for plan in self:
            if plan.state != 'ready':
                raise UserError(_('Approve the dispatch plan before creating the truck load.'))
            if plan.loading_picking_id:
                raise UserError(_('A truck-loading transfer already exists for this dispatch plan.'))
            plan.truck_id._ensure_stock_location()
            trip = plan._create_trip()
            setup = self.env['stock.picking.type'].nk_ensure_company_setup(plan.company_id)[plan.company_id.id]
            picking_type = setup['picking_types']['finished_to_truck']
            source = setup['locations']['fg_stock']
            destination = plan.truck_id.stock_location_id
            moves = []
            for line in plan.line_ids.filtered(lambda item: item.selected and item.planned_qty > 0):
                moves.append(Command.create({
                    'name': line.product_id.display_name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.planned_qty,
                    'product_uom': line.product_uom_id.id,
                    'location_id': source.id,
                    'location_dest_id': destination.id,
                }))
            if not moves:
                raise UserError(_('The dispatch plan has no selected quantities to load.'))
            picking = self.env['stock.picking'].create({
                'picking_type_id': picking_type.id,
                'location_id': source.id,
                'location_dest_id': destination.id,
                'scheduled_date': plan.planned_departure,
                'origin': plan.name,
                'move_ids': moves,
                'nk_is_operation': True,
                'nk_operation_kind': 'finished_to_truck',
                'nk_truck_id': plan.truck_id.id,
                'nk_trip_id': trip.id,
                'nk_reference': plan.name,
                'company_id': plan.company_id.id,
            })
            picking.action_confirm()
            picking.action_assign()
            if trip.state == 'planned':
                trip.action_start_loading()
            plan.write({'loading_picking_id': picking.id, 'state': 'loading'})
        return self.action_view_loading()

    def action_view_trip(self):
        self.ensure_one()
        if not self.trip_id:
            raise UserError(_('No distribution trip has been created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': self.trip_id.display_name,
            'res_model': 'nutkings.trip',
            'view_mode': 'form',
            'res_id': self.trip_id.id,
        }

    def action_view_loading(self):
        self.ensure_one()
        if not self.loading_picking_id:
            raise UserError(_('No truck-loading transfer has been created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': self.loading_picking_id.display_name,
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.loading_picking_id.id,
        }

    def action_cancel(self):
        for plan in self:
            if plan.state in ('done', 'cancelled'):
                raise UserError(_('A completed or cancelled dispatch plan cannot be cancelled again.'))
            if plan.loading_picking_id.state == 'done' or (plan.trip_id and plan.trip_id.state == 'done'):
                raise UserError(_('A completed load or trip cannot be cancelled from the dispatch plan.'))
            if plan.loading_picking_id and plan.loading_picking_id.state != 'cancel':
                plan.loading_picking_id.action_cancel()
            if plan.trip_id and plan.trip_id.state != 'cancelled':
                plan.trip_id.action_cancel()
            plan.state = 'cancelled'
        return True

    def action_reset_draft(self):
        for plan in self:
            if plan.state not in ('ready', 'cancelled'):
                raise UserError(_('Only an approved or cancelled dispatch plan can return to Draft.'))
            if plan.loading_picking_id:
                raise UserError(_('A dispatch plan with a truck-loading transfer cannot return to Draft.'))
            plan.state = 'draft'
        return True


class NutKingsDispatchPlanLine(models.Model):
    _name = 'nutkings.dispatch.plan.line'
    _description = 'Nut Kings Dispatch Plan Product Rotation'
    _order = 'selected desc, rotation_action, product_id'

    plan_id = fields.Many2one('nutkings.dispatch.plan', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='plan_id.company_id', store=True, index=True)
    product_id = fields.Many2one(
        'product.product', required=True,
        domain=[('nk_inventory_type', '=', 'finished_good')], index=True,
    )
    product_uom_id = fields.Many2one(related='product_id.uom_id', readonly=True)
    selected = fields.Boolean(default=True)
    history_loaded_qty = fields.Float(readonly=True)
    history_sold_qty = fields.Float(string='Historical Sales', readonly=True)
    history_returned_qty = fields.Float(readonly=True)
    average_loaded_qty = fields.Float(readonly=True)
    average_sold_qty = fields.Float(string='Average Sales', readonly=True)
    average_returned_qty = fields.Float(readonly=True)
    sell_through_percent = fields.Float(string='Sell-through %', readonly=True)
    rotation_action = fields.Selection(
        [
            ('increase', 'Increase'),
            ('maintain', 'Maintain'),
            ('reduce', 'Reduce'),
            ('pause', 'Pause'),
            ('manual', 'No History / Manual'),
        ],
        default='manual', readonly=True,
    )
    recommended_qty = fields.Float(readonly=True)
    planned_qty = fields.Float(required=True)
    notes = fields.Char()

    _product_plan_unique = models.Constraint(
        'unique(plan_id, product_id)',
        'Each product can appear only once on a dispatch plan.',
    )

    @api.constrains('planned_qty')
    def _check_planned_qty(self):
        for line in self:
            if line.planned_qty < 0:
                raise ValidationError(_('Planned quantity cannot be negative.'))
