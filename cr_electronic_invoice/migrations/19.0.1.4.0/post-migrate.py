"""Restore the days of payment terms migrated from 16.0 whose nb_days ended up at 0.

Odoo 17 replaced account.payment.term.line.days with nb_days. nb_days is a stored compute that
reads itself (``line.nb_days = line.nb_days``), so a mass recompute leaves it at 0: on a
production copy every credit term ("8 días", "30 días", "45 Días"...) had nb_days = 0 while the
16.0 column ``days`` still held 8, 30, 45. Invoices then fall due on their invoice date, and a
credit sale (condición 02) is sent with PlazoCredito 0, which Hacienda rejects (-58).

Only "days after the invoice date" lines are restored: for the end-of-month options of 16.0,
``days`` meant something else.
"""
import logging

_logger = logging.getLogger(__name__)


def _columns(cr):
    cr.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name = 'account_payment_term_line'""")
    return {row[0] for row in cr.fetchall()}


def migrate(cr, version):
    columns = _columns(cr)
    if 'days' not in columns or 'nb_days' not in columns:
        return  # not a database migrated from 16.0
    option_filter = "AND (option IS NULL OR option = 'day_after_invoice_date')" if 'option' in columns else ''
    cr.execute(f"""
        UPDATE account_payment_term_line
           SET nb_days = days
         WHERE COALESCE(nb_days, 0) = 0
           AND COALESCE(days, 0) > 0
           AND delay_type = 'days_after'
           {option_filter}
     RETURNING id, payment_id, days
    """)
    rows = cr.fetchall()
    for line_id, term_id, days in rows:
        _logger.info("Payment term %s, line %s: nb_days restored to %s from the 16.0 column", term_id, line_id, days)
    _logger.info("Payment term lines restored: %s", len(rows))
