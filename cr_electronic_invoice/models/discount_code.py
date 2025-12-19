from odoo import fields, models


class DiscountCode(models.Model):
    _name = "discount.code"
    _description = "Discount Code"
    _order = "sequence, id"

    active = fields.Boolean(default=True)
    code = fields.Char()
    sequence = fields.Char()
    name = fields.Char()
