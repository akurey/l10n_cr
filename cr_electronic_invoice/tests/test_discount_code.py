from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models.account_move import DEFAULT_DISCOUNT_CODE


@tagged('post_install', '-at_install')
class TestDiscountCode(TransactionCase):
    """A discount line without a code is sent as "Descuento Comercial" (07). It used to be sent as
    01 "Descuento por regalía", which Hacienda only accepts for a 100% discount (-518)."""

    def test_default_is_commercial_discount(self):
        self.assertEqual(DEFAULT_DISCOUNT_CODE, '07')
        default = self.env['discount.code'].search([('code', '=', DEFAULT_DISCOUNT_CODE)])
        self.assertEqual(default.name, 'Descuento Comercial')
