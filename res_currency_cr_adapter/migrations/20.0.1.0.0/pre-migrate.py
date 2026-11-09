# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


def migrate(cr, version):
    _rename_cron(cr)
    _rename_buying_rate(cr)


def _rename_cron(cr):
    """Rename the exchange rate cron to Odoo's naming.

    The cron data file is noupdate, so a new id or name in it would only
    reach new installs: an existing database would get a second cron, or
    lose its schedule. Renaming the existing record's ids keeps the same
    cron, with its schedule, and the new name replaces the old one.
    """
    cr.execute("""
        UPDATE ir_model_data
           SET name = 'ir_cron_currency_rate_update' || substr(name, length('currency_crc_rate_cron') + 1)
         WHERE module = 'res_currency_cr_adapter'
           AND name IN ('currency_crc_rate_cron', 'currency_crc_rate_cron_ir_actions_server')
     RETURNING res_id, model
    """)
    cron_ids = [res_id for res_id, model in cr.fetchall() if model == 'ir.cron']
    if not cron_ids:
        return
    # Only the English name is set: the translations of the new name are
    # loaded from the module's .po files after the upgrade
    cr.execute("""
        UPDATE ir_act_server
           SET name = jsonb_build_object('en_US', 'Costa Rica: Update currency rates')
          FROM ir_cron
         WHERE ir_cron.ir_actions_server_id = ir_act_server.id
           AND ir_cron.id IN %s
    """, [tuple(cron_ids)])
    cr.execute("""
        UPDATE ir_cron
           SET cron_name = 'Costa Rica: Update currency rates'
         WHERE id IN %s
    """, [tuple(cron_ids)])


def _rename_buying_rate(cr):
    """Rename the rate_2 field to buying_rate, keeping its data.

    Without this the upgrade would create an empty buying_rate column and
    leave the loaded buying rates in the old one. The field's id is renamed
    too, or the upgrade would delete the field as one the module no longer
    has.
    """
    cr.execute("""
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'res_currency_rate'
           AND column_name = 'rate_2'
    """)
    if not cr.fetchone():
        return
    cr.execute("ALTER TABLE res_currency_rate RENAME COLUMN rate_2 TO buying_rate")
    cr.execute("""
        UPDATE ir_model_fields
           SET name = 'buying_rate'
         WHERE model = 'res.currency.rate'
           AND name = 'rate_2'
    """)
    cr.execute("""
        UPDATE ir_model_data
           SET name = 'field_res_currency_rate__buying_rate'
         WHERE module = 'res_currency_cr_adapter'
           AND name = 'field_res_currency_rate__rate_2'
    """)
