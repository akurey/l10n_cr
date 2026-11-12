# copyright  2018 Carlos Wong, Akurey S.A.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Costa Rica - Exchange Rates',
    'summary': 'Daily exchange rates from the Banco Central de Costa Rica',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Localizations',
    'author': 'Odoo CR, Akurey S.A.',
    'website': 'https://github.com/akurey/l10n_cr',
    'license': 'AGPL-3',
    'depends': [
        'account',
    ],
    'data': [
        'security/ir.access.csv',
        'data/ir_cron_data.xml',
        'views/res_currency_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/l10n_cr_rate_load_wizard_views.xml',
    ],
    'uninstall_hook': 'uninstall_hook',
}
