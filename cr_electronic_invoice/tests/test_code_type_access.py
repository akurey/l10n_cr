from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestCodeTypeAccess(TransactionCase):
    """A product's "Tipo de Código" is read whenever a product is opened or
    created (its default). Sales users and administrators who don't invoice
    used to get "No puede acceder a los registros 'code.type.product'"."""

    def _product_manager(self, login, groups):
        return new_test_user(self.env, login=login, groups=f'product.group_product_manager,{groups}')

    def test_salesman_creates_and_reads_products(self):
        user = self._product_manager('test_code_type_sales', 'sales_team.group_sale_salesman')
        product = self.env['product.template'].with_user(user).create({'name': 'TEST Servicio'})
        self.assertTrue(product.code_type_id.with_user(user).display_name)

    def test_administrator_reads_code_types(self):
        user = new_test_user(self.env, login='test_code_type_admin', groups='base.group_system')
        self.assertTrue(self.env['code.type.product'].with_user(user).search([]))

    def test_other_product_users_open_and_create_products(self):
        # A product manager outside sales, invoicing and administration (e.g.
        # inventory or purchase) doesn't see the field, gets its default, and
        # can still open and create products.
        user = self._product_manager('test_code_type_stock', 'base.group_user')
        Product = self.env['product.template'].with_user(user)
        arch = etree.fromstring(Product.get_view(view_type='form')['arch'])
        self.assertFalse(arch.xpath("//field[@name='code_type_id']"))
        product = Product.create({'name': 'TEST Bien'})
        self.assertEqual(product.sudo().code_type_id.code, '04')

    def test_other_users_still_cannot(self):
        user = new_test_user(self.env, login='test_code_type_employee', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['code.type.product'].with_user(user).search([])
