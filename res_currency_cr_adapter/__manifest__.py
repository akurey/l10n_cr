# copyright  2018 Carlos Wong, Akurey S.A.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Costa Rica Currency Adapter',
    'version': '16.0.2.0.0',
    'category': 'Account',
    'author': "Odoo CR, Akurey S.A.",
    'website': 'https://github.com/akurey/ak-odoo',
    'license': 'AGPL-3',
    'depends': [
        'base',
        'account'
    ],
    'data': [
        'data/currency_data.xml',
        'views/res_currency_rate_view.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
