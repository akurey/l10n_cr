import importlib.util
import os

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import convert_file

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'migrations', '19.0.1.6.0', 'pre-migrate.py')
TAX_MODELS = ('account.tax', 'account.tax.group')


def migration():
    spec = importlib.util.spec_from_file_location('cr_electronic_invoice_pre_migrate_19_0_1_6_0', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install')
class TestTaxNoupdate(TransactionCase):
    """A module update leaves the taxes alone: point_of_sale refuses to change a tax used in an open
    session, and an accountant's changes to a tax are kept."""

    def _xmlids(self):
        return self.env['ir.model.data'].search([('module', '=', 'cr_electronic_invoice'),
                                                 ('model', 'in', TAX_MODELS)])

    def test_taxes_and_groups_are_noupdate(self):
        xmlids = self._xmlids()
        self.assertTrue(xmlids)
        self.assertTrue(all(xmlids.mapped('noupdate')))

    def test_migration_flags_existing_taxes(self):
        tax = self.env.ref('cr_electronic_invoice.iva_tax_13')
        self.env.cr.execute("""UPDATE ir_model_data SET noupdate = false
                                WHERE module = 'cr_electronic_invoice' AND model IN %s""", (TAX_MODELS,))
        self.env.cr.execute("""UPDATE ir_model_data SET noupdate = false
                                WHERE module = 'base' AND name = 'cr'""")
        migration().migrate(self.env.cr, '19.0.1.5.0')
        self.env.invalidate_all()
        self.assertTrue(all(self._xmlids().mapped('noupdate')))
        base_cr = self.env['ir.model.data'].search([('module', '=', 'base'), ('name', '=', 'cr')])
        self.assertFalse(base_cr.noupdate, "other modules' records are not touched")
        self.assertTrue(tax.exists())

    def test_update_does_not_write_the_taxes(self):
        tax = self.env.ref('cr_electronic_invoice.iva_tax_13')
        group = self.env.ref('cr_electronic_invoice.tax_group_IVA13')
        # Fields point_of_sale protects while an open session uses the tax.
        tax.write({'amount': 12.0, 'name': 'IVA changed by the accountant'})
        group.name = 'Changed group'
        convert_file(self.env, 'cr_electronic_invoice', 'data/account_tax_data.xml', {}, mode='update')
        self.assertEqual((tax.amount, tax.name, group.name), (12.0, 'IVA changed by the accountant', 'Changed group'))
