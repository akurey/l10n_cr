import importlib.util
import os

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'migrations', '19.0.1.4.0', 'post-migrate.py')


def migration():
    spec = importlib.util.spec_from_file_location('cr_electronic_invoice_post_migrate_19_0_1_4_0', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install')
class TestPaymentTermMigration(TransactionCase):
    """19.0.1.4.0 restores nb_days from the 16.0 column ``days`` on "days after invoice" lines
    whose nb_days was reset to 0, and leaves every other line alone."""

    def _line(self, name, nb_days, days, option):
        term = self.env['account.payment.term'].create({'name': name, 'line_ids': [
            (0, 0, {'value': 'percent', 'value_amount': 100.0, 'nb_days': nb_days, 'delay_type': 'days_after'})]})
        line = term.line_ids
        self.env.cr.execute('UPDATE account_payment_term_line SET nb_days = %s, days = %s, option = %s WHERE id = %s',
                            (nb_days, days, option, line.id))
        return line

    def test_restores_days_after_lines_only(self):
        # The 16.0 columns of a migrated database (DDL is rolled back with the test).
        self.env.cr.execute('ALTER TABLE account_payment_term_line ADD COLUMN days integer, ADD COLUMN option varchar')
        broken = self._line('30 días', 0, 30, 'day_after_invoice_date')
        no_option = self._line('2/7 Neto 30', 0, 30, None)
        immediate = self._line('Pago inmediato', 0, 0, 'day_after_invoice_date')
        end_of_month = self._line('Fin de mes', 0, 10, 'after_invoice_month')
        kept = self._line('45 días', 45, 45, 'day_after_invoice_date')

        migration().migrate(self.env.cr, '19.0.1.3.0')
        self.env.invalidate_all()
        self.assertEqual((broken | no_option | immediate | end_of_month | kept).mapped('nb_days'), [30, 30, 0, 0, 45])

    def test_database_not_migrated_from_16(self):
        # A database created on 19.0 has no "days" column: nothing to do, no error.
        migration().migrate(self.env.cr, '19.0.1.3.0')
