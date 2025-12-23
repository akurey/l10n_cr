
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

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not args:
            args = []
        domain = args + ["|", "|", ("name", operator, name), ("code", operator, name), ("ciiu3", operator, name)]
        activities = self.search_fetch(domain, ['display_name'], limit=limit)
        return [(a.id, a.display_name) for a in activities]

    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.code} - {record.ciiu3}] {record.name}"