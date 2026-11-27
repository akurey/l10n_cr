"""Stop module updates from rewriting the Costa Rican taxes and tax groups.

data/account_tax_data.xml is now ``noupdate``, but ir.model.data keeps the flag the records were
first loaded with, so the existing records are flagged here, before the data files load. Otherwise
every update writes the taxes again, and point_of_sale refuses to change a tax (amount, type, group...)
used by an order line of an open session: the update fails until every session is closed. It also
keeps the changes an accountant makes to a tax.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_model_data
           SET noupdate = true
         WHERE module = 'cr_electronic_invoice'
           AND model IN ('account.tax', 'account.tax.group')
           AND noupdate IS NOT TRUE
    """)
