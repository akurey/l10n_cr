
from odoo import models, fields, api


class EconomicActivity(models.Model):
    _name = "economic.activity"
    _description = 'Economic activities listed by Ministerio de Hacienda'
    _order = "code"

    active = fields.Boolean(default=True)
    code = fields.Char()
    name = fields.Char()
    description = fields.Char()
    ciiu3 = fields.Char(string="CIIU 3")
    sale_type = fields.Selection(selection=[('goods', 'Goods'), ('services', 'Services')],
                                 default='goods',
                                 required=True)
    company_ids = fields.Many2many(
        'res.company',
        'economic_activity_company_rel',
        'activity_id',
        'company_id',
        string='Companies',
    )

    @api.model
    def _from_hacienda(self, activities):
        """The active activities of a Hacienda registry answer, created (or reactivated) when missing."""
        activity_model = self.with_context(active_test=False)
        active = [activity for activity in activities or []
                  if activity.get("estado") == "A" and activity.get("codigo")]
        records = activity_model.search([('code', 'in', [activity["codigo"] for activity in active])])
        missing = [activity for activity in active if activity["codigo"] not in records.mapped('code')]
        if missing:
            records |= activity_model.create([{
                'code': activity["codigo"],
                'name': activity.get("descripcion", ""),
                'description': activity.get("descripcion", ""),
                'sale_type': 'services' if activity.get("tipo") == "S" else 'goods',
            } for activity in missing])
        records.filtered(lambda activity: not activity.active).write({'active': True})
        # Hacienda's order: the first one is the main activity.
        order = [activity["codigo"] for activity in active]
        return records.sorted(lambda activity: order.index(activity.code))

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        if not domain:
            domain = []
        domain = domain + ["|", "|", ("name", operator, name), ("code", operator, name), ("ciiu3", operator, name)]
        activities = self.search_fetch(domain, ['display_name'], limit=limit)
        return [(a.id, a.display_name) for a in activities]

    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.code} - {record.ciiu3}] {record.name}"