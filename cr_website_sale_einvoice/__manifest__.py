{
    'name': 'Costa Rica eCommerce Electronic Invoice',
    'version': '19.0.1.0.0',
    'summary': 'Customers ask for an electronic invoice in their name at checkout; otherwise an electronic ticket',
    'category': 'Website/Website',
    'author': 'Akurey',
    'website': 'https://github.com/akurey/l10n_cr',
    'license': 'LGPL-3',
    'depends': ['website_sale', 'cr_electronic_invoice'],
    'data': [
        'views/einvoice_templates.xml',
        'views/sale_order_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'cr_website_sale_einvoice/static/src/scss/einvoice.scss',
        ],
    },
    'installable': True,
}
