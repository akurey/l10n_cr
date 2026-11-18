# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tools.sql import column_exists, create_column, rename_column


def migrate(cr, version):
    _rename_cron(cr)
    _reschedule_cron(cr)
    _rename_buying_rate(cr)
    _shift_rate_dates(cr)
    _enable_update(cr)
    _move_token(cr)


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
           SET name = jsonb_build_object('en_US', 'Costa Rica: Update BCCR exchange rates'),
               code = 'model._cron_l10n_cr_update_rates()',
               model_id = (SELECT id FROM ir_model WHERE model = 'res.company')
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



def _reschedule_cron(cr):
    """Run the exchange rate cron every hour, on the hour, from the next one.

    Its data file is noupdate, so an upgrade keeps the daily schedule of
    Odoo 19, and the record is marked noupdate as on a new install.
    """
    cr.execute("""
        UPDATE ir_cron
           SET interval_number = 1,
               interval_type = 'hours',
               nextcall = date_trunc('hour', now() AT TIME ZONE 'UTC') + interval '1 hour'
         WHERE id IN (SELECT res_id FROM ir_model_data
                       WHERE module = 'res_currency_cr_adapter'
                         AND name = 'ir_cron_currency_rate_update')
    """)
    cr.execute("""
        UPDATE ir_model_data
           SET noupdate = true
         WHERE module = 'res_currency_cr_adapter'
           AND name IN ('ir_cron_currency_rate_update', 'ir_cron_currency_rate_update_ir_actions_server')
    """)

def _rename_buying_rate(cr):
    """Rename the rate_2 field to l10n_cr_buying_rate, keeping its data.

    Without this the upgrade would create an empty l10n_cr_buying_rate column and
    leave the loaded buying rates in the old one. The field's id is renamed
    too, or the upgrade would delete the field as one the module no longer
    has.
    """
    if not column_exists(cr, 'res_currency_rate', 'rate_2'):
        return
    rename_column(cr, 'res_currency_rate', 'rate_2', 'l10n_cr_buying_rate')
    cr.execute("""
        UPDATE ir_model_fields
           SET name = 'l10n_cr_buying_rate'
         WHERE model = 'res.currency.rate'
           AND name = 'rate_2'
    """)
    cr.execute("""
        UPDATE ir_model_data
           SET name = 'field_res_currency_rate__l10n_cr_buying_rate'
         WHERE module = 'res_currency_cr_adapter'
           AND name = 'field_res_currency_rate__rate_2'
    """)


def _shift_rate_dates(cr):
    """Move the Costa Rica rates to the day before the one they apply to.

    Odoo 19 applied a rate from its own date and Odoo 20 from the next day
    (odoo/odoo@cba671d), so the module now stores each rate the day before.
    Rates left on their Odoo 19 dates would apply a day late.
    """
    cr.execute("""
        SELECT DISTINCT rate.id, rate.name
          FROM res_currency_rate rate
          JOIN res_currency currency ON currency.id = rate.currency_id
          JOIN res_company company ON company.parent_id IS NULL
                                  AND (rate.company_id = company.id OR rate.company_id IS NULL)
          JOIN res_currency company_currency ON company_currency.id = company.currency_id
          JOIN res_country country ON country.id = company.account_fiscal_country_id
         WHERE country.code = 'CR'
           AND (company_currency.name, currency.name) IN (('CRC', 'USD'), ('USD', 'CRC'))
         ORDER BY rate.name
    """)
    # Oldest first, so each rate moves to a day the previous one already left
    for rate_id, __ in cr.fetchall():
        cr.execute("UPDATE res_currency_rate SET name = name - 1 WHERE id = %s", [rate_id])


def _enable_update(cr):
    """Switch the update on for the companies that loaded their rates automatically in Odoo 19.

    The column is created here, as the switch is new and its field doesn't
    exist yet. Odoo 19's Hacienda source is now the BCCR, which asks for a
    token in Settings if none was set.
    """
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = 'exchange_source'")
    source = cr.fetchone()
    if not source or source[0] not in ('bccr', 'hacienda'):
        return
    if not column_exists(cr, 'res_company', 'l10n_cr_bccr_rates_enabled'):
        create_column(cr, 'res_company', 'l10n_cr_bccr_rates_enabled', 'bool')
    cr.execute("""
        UPDATE res_company company
           SET l10n_cr_bccr_rates_enabled = true
          FROM res_currency currency, res_country country
         WHERE company.parent_id IS NULL
           AND currency.id = company.currency_id
           AND country.id = company.account_fiscal_country_id
           AND country.code = 'CR'
           AND currency.name IN ('CRC', 'USD')
    """)


def _move_token(cr):
    """Keep the BCCR token under the module's key, and drop the Odoo 19 settings it no longer uses."""
    cr.execute("""
        UPDATE ir_config_parameter
           SET key = 'res_currency_cr_adapter.bccr_token'
         WHERE key = 'bccr_token'
           AND NOT EXISTS (SELECT 1 FROM ir_config_parameter WHERE key = 'res_currency_cr_adapter.bccr_token')
    """)
    cr.execute("""
        DELETE FROM ir_config_parameter
         WHERE key IN ('bccr_token', 'bccr_username', 'bccr_email', 'exchange_source')
    """)
