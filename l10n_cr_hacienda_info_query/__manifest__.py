{
    "name": "Consultar Información de Clientes en Hacienda Costa Rica",
    "version": '19.0.1.0.0',
    "author": "Odoo Community Association (OCA), Odoo CR, Factura Sempai, FSS Solutions",
    "license": 'LGPL-3',
    "website": "https://github.com/odoocr/l10n_cr",
    "category": "API",
    "summary": """Consultar Nombre de Clientes en Hacienda Costa Rica""",
    "depends": [
        'base',
        'contacts',
        'point_of_sale',
        'base_setup',
        'web_notify'
    ],
    "data": [
        'data/res_config_settings.xml',
        'views/res_config_settings_views.xml',
    ],
    "assets": {
        'point_of_sale._assets_pos': [
            'l10n_cr_hacienda_info_query/static/src/js/actualizar_pos.js',
            'l10n_cr_hacienda_info_query/static/src/js/models.js',
        ],
        'web.assets_backend': [
            'l10n_cr_hacienda_info_query/static/src/css/actualizar_pos.css',
        ],
    },
    "installable": True,
}
