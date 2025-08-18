
from odoo import models, fields


class IssuerEx(models.Model):
    _name = "issuer.ex"

    active = fields.Boolean(default=True)
    code = fields.Char()
    name = fields.Char()
