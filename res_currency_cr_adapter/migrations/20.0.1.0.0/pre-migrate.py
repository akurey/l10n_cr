# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tools.sql import column_exists, rename_column


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
           SET name = CASE name
                        WHEN 'currency_crc_rate_cron' THEN 'ir_cron_currency_rate_update'
                        ELSE 'ir_cron_currency_rate_update_ir_actions_server'
                      END
         WHERE module = 'res_currency_cr_adapter'
           AND name IN ('currency_crc_rate_cron', 'currency_crc_rate_cron_ir_actions_server')
    """)
    # Only the English name is set: the translations of the new name are
    # loaded from the module's .po files after the upgrade
    cr.execute("""
        UPDATE ir_act_server action
           SET name = jsonb_build_object('en_US', 'Costa Rica: Update currency rates')
          FROM ir_model_data imd
         WHERE imd.module = 'res_currency_cr_adapter'
           AND imd.name = 'ir_cron_currency_rate_update_ir_actions_server'
           AND imd.res_id = action.id
    """)
    cr.execute("""
        UPDATE ir_cron cron
           SET cron_name = action.name->>'en_US'
          FROM ir_act_server action
         WHERE action.id = cron.ir_actions_server_id
           AND cron.id IN (SELECT res_id FROM ir_model_data
                            WHERE module = 'res_currency_cr_adapter'
                              AND name = 'ir_cron_currency_rate_update')
    """)


def _rename_buying_rate(cr):
    """Rename the rate_2 field to buying_rate, keeping its data.

    Without this the upgrade would create an empty buying_rate column and
    leave the loaded buying rates in the old one. The field's id is renamed
    too, or the upgrade would delete the field as one the module no longer
    has.
    """
    if not column_exists(cr, 'res_currency_rate', 'rate_2'):
        return
    rename_column(cr, 'res_currency_rate', 'rate_2', 'buying_rate')
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
