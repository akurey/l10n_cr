# copyright  2018 Carlos Wong, Akurey S.A.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Costa Rica Currency Adapter',
    'version': '20.0.1.0.0',
    'category': 'Account',
    'author': "Odoo CR, Akurey S.A.",
    'website': 'https://github.com/akurey/ak-odoo',
    'license': 'AGPL-3',
    'depends': [
        'base',
        'account'
    ],
    'data': [
        'data/ir_cron_data.xml',
        'views/res_currency_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
