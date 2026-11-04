

{
    'name': 'Códigos País para Facturación electrónica Costa Rica',
    'version': '20.0.1.0.0',
    'author': 'Odoo CR',
    'license': 'AGPL-3',
    'website': 'https://github.com/odoocr',
    'category': 'Account',
    'description': '''Códigos País para Facturación electrónica Costa Rica.''',
    'depends': [
        'base',
        'account',
        'product'
    ],
    'data': [
        'data/res_country_data.xml',
        'data/res.country.county.csv',
        'data/res.country.district.csv',
        'data/res.country.neighborhood.csv',
        'security/ir.access.csv',
        'views/country_codes_views.xml',
        'views/res_company_views.xml',
        'views/res_partner_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'l10n_cr_country_codes/static/src/scss/address.scss',
        ],
    },
    # "pre_init_hook": "pre_init_hook",
    'installable': True,
}
