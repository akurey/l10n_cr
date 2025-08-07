UrlHaciendaToken = {
    'api-stag': 'https://idp.comprobanteselectronicos.go.cr/auth/realms/rut-stag/protocol/openid-connect/token',
    'api-prod': 'https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/openid-connect/token',
}

UrlHaciendaRecepcion = {
    'api-stag': 'https://api-sandbox.comprobanteselectronicos.go.cr/recepcion/v1/recepcion/',
    'api-prod': 'https://api.comprobanteselectronicos.go.cr/recepcion/v1/recepcion/',
}

TipoCedula = {   # no se está usando !!
    'Fisico': 'fisico',
    'Juridico': 'juridico',
    'Dimex': 'dimex',
    'Nite': 'nite',
    'Extranjero': 'extranjero',
}

SituacionComprobante = {
    'normal': '1',
    'contingencia': '2',
    'sininternet': '3',
}

TipoDocumento = {
    'FE': '01',  # Factura Electrónica
    'ND': '02',  # Nota de Débito
    'NC': '03',  # Nota de Crédito
    'TE': '04',  # Tiquete Electrónico
    'CCE': '05',  # confirmacion comprobante electronico
    'CPCE': '06',  # confirmacion parcial comprobante electronico
    'RCE': '07',  # rechazo comprobante electronico
    'FEC': '08',  # Factura Electrónica de Compra
    'FEE': '09',  # Factura Electrónica de Exportación
}

# Xmlns used by Hacienda
XmlnsHacienda = {
    'FE': 'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica',
    'ND': 'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/notaDebitoElectronica',
    'NC': 'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/notaCreditoElectronica',
    'TE': 'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/tiqueteElectronico',
    'FEC': 'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/facturaElectronicaCompra',
    'FEE': 'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronicaExportacion'
}

schemaLocation = {
    'FE': 'https://www.hacienda.go.cr/ATV/Comprobante' +
    'Electronico/docs/esquemas/2016/v4.4/FacturaElectronica_V4.4.xsd',
    'ND': 'https://www.hacienda.go.cr/ATV/Comprobante' +
    'Electronico/docs/esquemas/2016/v4.3/NotaDebitoElectronica_V4.3.xsd',
    'NC': 'https://www.hacienda.go.cr/ATV/Comprobante' +
    'Electronico/docs/esquemas/2016/v4.3/NotaCreditoElectronica_V4.3.xsd',
    'TE': 'https://www.hacienda.go.cr/ATV/Comprobante' +
    'Electronico/docs/esquemas/2016/v4.4/TiqueteElectronico_V4.4.xsd',
    'FEC': 'https://www.hacienda.go.cr/ATV/Comprobante' +
    'Electronico/docs/esquemas/2016/v4.3/FacturaElectronicaCompra_V4.3.xsd',
    'FEE': 'https://www.hacienda.go.cr/ATV/Comprobante' +
    'Electronico/docs/esquemas/2016/v4.4/FacturaElectronicaExportacion_V4.4.xsd'
}

tagName = {
    'FE': 'FacturaElectronica',  # Factura Electrónica
    'ND': 'NotaDebitoElectronica',  # Nota de Débito
    'NC': 'NotaCreditoElectronica',  # Nota de Crédito
    'TE': 'TiqueteElectronico',  # Tiquete Electrónico
    'FEC': 'FacturaElectronicaCompra',  # Factura Electrónica de Compra
    'FEE': 'FacturaElectronicaExportacion'  # Factura Electrónica de Exportación
}

nombreInstitucion = {
    'Ministerio de Hacienda': '01',
    'Ministerio de Relaciones Exteriores y Culto': '02',
    'Ministerio de Agricultura y Ganadería': '03',
    'Ministerio de Economía, Industria y Comercio': '04',
    'Cruz Roja Costarricense': '05',
    'Benemérito Cuerpo de Bomberos de Costa Rica': '06',
    'Asociación Obras del Espíritu Santo': '07',
    'Federación Cruzada Nacional de protección al Anciano (Fecrunapa)': '08',
    'Escuela de Agricultura de la Región Húmeda (EARTH)': '09',
    'Instituto Centroamericano de Administración de Empresas (INCAE)': '10',
    'Junta de Protección Social (JPS)': '11',
    'Autoridad Reguladora de los Servicios Públicos (Aresep)': '12',
    'Otros': '99'
}
