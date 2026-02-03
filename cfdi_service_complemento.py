import os
import xml.etree.ElementTree as ET
from zeep import Client
from datetime import datetime
from decimal import Decimal
from lxml import etree
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from cryptography import x509
import base64



BASE_DIR = os.path.dirname(os.path.abspath(__file__))

RUTA_CER = os.path.join(BASE_DIR, "CSD_Sucursal_1_EKU9003173C9_20230517_223850.cer")
RUTA_KEY = os.path.join(BASE_DIR, "CSD_Sucursal_1_EKU9003173C9_20230517_223850.key")
PASSWORD_KEY = b"12345678a"  

RUTA_XSLT = r"xslt\cadenaoriginal_4_0.xslt"

PAC_WSDL = "https://testing.solucionfactible.com/ws/services/Timbrado?wsdl"
PAC_USER = "testing@solucionfactible.com"
PAC_PASSWORD = "timbrado.SF.16672"


#extraer valores emisor, receptor,
def parse_xml_complemento(xml_cfdi: str, forma_pago: str) -> dict:
    ns = {
        "cfdi": "http://www.sat.gob.mx/cfd/4",
        "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital"
    }

    root = ET.fromstring(xml_cfdi)

    # Extraer datos del nodo Comprobante
    comprobante = root.attrib
    emisor = root.find('cfdi:Emisor', ns).attrib
    receptor = root.find('cfdi:Receptor', ns).attrib 
    timbre = root.find('.//tfd:TimbreFiscalDigital', ns).attrib
    
    # Extraer Impuestos
    impuestos_nodo = root.find('cfdi:Impuestos', ns)
    traslados = impuestos_nodo.find('cfdi:Traslados', ns)
    traslado = traslados.find('cfdi:Traslado', ns).attrib
    
    # Extraer Concepto
    conceptos_nodo = root.find('cfdi:Conceptos', ns)
    concepto = conceptos_nodo.find('cfdi:Concepto', ns).attrib
    
    # UUID de la factura original
    uuid_factura = timbre['UUID']
    
    # Valores de la factura original - Nodo: Comprobante
    version_factura = comprobante.get('Version')
    total_factura = float(comprobante['Total'])
    subtotal_factura = float(comprobante['SubTotal'])
    serie_factura = comprobante.get('Serie', '')
    folio_factura = comprobante.get('Folio', '')
    exportacion_factura = comprobante.get('Exportacion')
    lugar_expedicion = comprobante.get('LugarExpedicion')  
    metodo_pago_original = comprobante.get('MetodoPago')
    moneda_original = comprobante.get('Moneda')
    
    # Certificado (para el complemento de pago)
    certificado = comprobante.get('Certificado')
    no_certificado = comprobante.get('NoCertificado')
    
    # Fecha actual 
    fecha_actual = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    
    # Calcular valores del pago (asumiendo pago total)
    monto_pago = total_factura
    imp_saldo_ant = total_factura
    imp_pagado = monto_pago
    imp_saldo_insoluto = imp_saldo_ant - imp_pagado
    
    # Calcular impuestos proporcionales
    base_dr = float(traslado['Base'])
    tasa_dr = traslado['TasaOCuota']
    importe_dr = float(traslado['Importe'])
    impuesto_tipo = traslado['Impuesto']
    tipo_factor = traslado['TipoFactor']
    
    # Construir el diccionario del complemento de pago
    complemento_pago_dict = {
        'Comprobante': {
            'Version': '4.0',
            'Serie': 'P',  # Puedes parametrizar esto
            'Folio': folio_factura,  # Asigna tu número de folio
            'Fecha': fecha_actual,
            'SubTotal': '0',
            'Moneda': 'XXX',  #  Siempre xxx en complementos de pago
            'Total': '0',
            'TipoDeComprobante': 'P',
            'Exportacion': exportacion_factura,
            'LugarExpedicion': lugar_expedicion
            # 'NoCertificado': no_certificado,
            # 'Certificado': certificado,
            # 'Sello': ''  # Se genera antes de enviar al PAC
        },
        
        'Emisor': {
            'Rfc': emisor.get('Rfc'),
            'Nombre': emisor.get('Nombre'),
            'RegimenFiscal': emisor.get('RegimenFiscal')
        },
        
        'Receptor': {
            'Rfc': receptor.get('Rfc'),
            'Nombre': receptor.get('Nombre'),
            'DomicilioFiscalReceptor': receptor.get('DomicilioFiscalReceptor'),
            'RegimenFiscalReceptor': receptor.get('RegimenFiscalReceptor'),
            'UsoCFDI': 'CP01'  #  Siempre CP01 para complementos de pago
        },
        
        'Conceptos': {
            'Concepto': {
                'ClaveProdServ': '84111506',  #  Siempre este código
                'Cantidad': '1',
                'ClaveUnidad': 'ACT',
                'Descripcion': 'Pago',
                'ValorUnitario': '0',  #  Siempre 0
                'Importe': '0',  #  Siempre 0
                'ObjetoImp': '01'  #  Siempre 01
            }
        },
        
        'Complemento': {
            'Pagos': {
                'Version': '2.0',
                
                'Totales': {
                    'MontoTotalPagos': f'{monto_pago:.2f}',
                    'TotalTrasladosBaseIVA16': f'{base_dr:.2f}',
                    'TotalTrasladosImpuestoIVA16': f'{importe_dr:.2f}'
                },
                
                'Pago': {
                    'FechaPago': fecha_actual,
                    'FormaDePagoP': forma_pago,  # aqui va la seleccion pasada como argumento
                    'MonedaP': moneda_original,
                    'TipoCambioP': '1',
                    'Monto': f'{monto_pago:.2f}',

                    'ImpuestosP': {
                        'TrasladosP': [
                            {
                                'BaseP': f'{base_dr:.2f}',
                                'ImpuestoP': impuesto_tipo,
                                'TipoFactorP': tipo_factor,
                                'TasaOCuotaP': f'{float(tasa_dr):.6f}',
                                'ImporteP': f'{importe_dr:.2f}'
                            }
                        ]
                    },
                    
                    'DoctoRelacionado': {
                        'IdDocumento': uuid_factura,
                        'Serie': serie_factura,
                        'Folio': folio_factura,
                        'MonedaDR': moneda_original,
                        'EquivalenciaDR': '1',
                        'NumParcialidad': '1',
                        'ImpSaldoAnt': f'{imp_saldo_ant:.2f}',
                        'ImpPagado': f'{imp_pagado:.2f}',
                        'ImpSaldoInsoluto': f'{imp_saldo_insoluto:.2f}',
                        'ObjetoImpDR': '02',
                        # 'MetodoDePagoDR': metodo_pago_original,
                        'ImpuestosDR': {
                            'TrasladosDR': [
                                {
                                    'BaseDR': f'{base_dr:.2f}',
                                    'ImpuestoDR': impuesto_tipo,
                                    'TipoFactorDR': tipo_factor,
                                    'TasaOCuotaDR': f'{float(tasa_dr):.6f}',
                                    'ImporteDR': f'{importe_dr:.2f}'
                                }
                            ]
                        }
                    }
                }
            }
        }
    }
    
    return complemento_pago_dict

def cargar_certificado(cert_path: str) -> tuple:
    with open(cert_path, 'rb') as f:
        cert_data = f.read()
    
    # Cargar certificado X509
    cert = x509.load_der_x509_certificate(cert_data, default_backend())
    
    # Obtener número de certificado (usando tu método que funciona)
    serial_hex = format(cert.serial_number, 'x')
    try:
        no_certificado = bytes.fromhex(serial_hex).decode('ascii')
    except Exception:
        no_certificado = serial_hex
    
    # Convertir certificado a base64
    certificado_base64 = base64.b64encode(cert_data).decode('ascii')
    
    return certificado_base64, no_certificado


def crear_cfdi_complemento(complemento_dict: dict, no_certificado, certificado_base64: str) -> str:
    # Crear el nodo raíz
    root = ET.Element('{http://www.sat.gob.mx/cfd/4}Comprobante')
    
    # Agregar atributos del Comprobante
    for key, value in complemento_dict['Comprobante'].items():
        root.set(key, str(value))
    
    root.set("NoCertificado", no_certificado)
    root.set("Certificado", certificado_base64)
    
    # Agregar namespaces
    root.set('{http://www.w3.org/2001/XMLSchema-instance}schemaLocation', 
             'http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd')
    
    # Agregar Emisor
    emisor = ET.SubElement(root, '{http://www.sat.gob.mx/cfd/4}Emisor')
    for key, value in complemento_dict['Emisor'].items():
        emisor.set(key, str(value))
    
    # Agregar Receptor
    receptor = ET.SubElement(root, '{http://www.sat.gob.mx/cfd/4}Receptor')
    for key, value in complemento_dict['Receptor'].items():
        receptor.set(key, str(value))
    
    # Agregar Conceptos
    conceptos = ET.SubElement(root, '{http://www.sat.gob.mx/cfd/4}Conceptos')
    concepto = ET.SubElement(conceptos, '{http://www.sat.gob.mx/cfd/4}Concepto')
    for key, value in complemento_dict['Conceptos']['Concepto'].items():
        concepto.set(key, str(value))
    
    # Agregar Complemento
    complemento = ET.SubElement(root, '{http://www.sat.gob.mx/cfd/4}Complemento')
    
    # Agregar Pagos
    pagos = ET.SubElement(complemento, '{http://www.sat.gob.mx/Pagos20}Pagos')
    pagos.set('Version', '2.0')
    pagos.set('{http://www.w3.org/2001/XMLSchema-instance}schemaLocation',
              'http://www.sat.gob.mx/Pagos20 http://www.sat.gob.mx/sitio_internet/cfd/Pagos/Pagos20.xsd')
    
    # Agregar Totales
    totales = ET.SubElement(pagos, '{http://www.sat.gob.mx/Pagos20}Totales')
    for key, value in complemento_dict['Complemento']['Pagos']['Totales'].items():
        if value is not None:
            totales.set(key, str(value))
    
    # Agregar Pago
    pago = ET.SubElement(pagos, '{http://www.sat.gob.mx/Pagos20}Pago')
    pago_data = complemento_dict['Complemento']['Pagos']['Pago']
    for key, value in pago_data.items():
        if key not in ['DoctoRelacionado', 'ImpuestosP'] and value is not None:
            pago.set(key, str(value))

    # Agregar DoctoRelacionado
    docto = ET.SubElement(pago, '{http://www.sat.gob.mx/Pagos20}DoctoRelacionado')
    docto_data = pago_data['DoctoRelacionado']
    for key, value in docto_data.items():
        if key != 'ImpuestosDR' and value is not None:
            docto.set(key, str(value))
    
    # Agregar ImpuestosDR
    impuestos_dr = ET.SubElement(docto, '{http://www.sat.gob.mx/Pagos20}ImpuestosDR')
    traslados_dr = ET.SubElement(impuestos_dr, '{http://www.sat.gob.mx/Pagos20}TrasladosDR')
    
    for traslado_data in docto_data['ImpuestosDR']['TrasladosDR']:
        traslado_dr = ET.SubElement(traslados_dr, '{http://www.sat.gob.mx/Pagos20}TrasladoDR')
        for key, value in traslado_data.items():
            traslado_dr.set(key, str(value))

    # Después de crear el nodo pago y antes de DoctoRelacionado
    if 'ImpuestosP' in pago_data:
        impuestos_p = ET.SubElement(pago, '{http://www.sat.gob.mx/Pagos20}ImpuestosP')
        
        if 'TrasladosP' in pago_data['ImpuestosP']:
            traslados_p = ET.SubElement(impuestos_p, '{http://www.sat.gob.mx/Pagos20}TrasladosP')
            
            for traslado_p_data in pago_data['ImpuestosP']['TrasladosP']:
                traslado_p = ET.SubElement(traslados_p, '{http://www.sat.gob.mx/Pagos20}TrasladoP')
                for key, value in traslado_p_data.items():
                    traslado_p.set(key, str(value))
    
    # Convertir a string
    xml_string = ET.tostring(root, encoding='unicode', method='xml')
    return xml_string


def cargar_llave_privada(key_path: str, password):
    """
    Carga la llave privada .key con su contraseña
    """
    with open(key_path, 'rb') as f:
        key_data = f.read()
    
    # Convertir password a bytes si es string
    if isinstance(password, str):
        password = password.encode('utf-8')

    # Cargar llave privada encriptada
    private_key = serialization.load_der_private_key(
        key_data,
        password=password,
        backend=default_backend()
    )
    
    return private_key

def sellar_cfdi(xml_sin_sellar: str, llave_privada,  xslt_path: str = None) -> str:
    """
    Genera la cadena original, sellarlo con la llave privada y agrega el sello al XML
    """
    # Parse del XML
    tree = etree.fromstring(xml_sin_sellar.encode('utf-8'))
    
    # Generar cadena original
    if xslt_path and os.path.exists(xslt_path):
        # Método oficial con XSLT del SAT
        xslt = etree.parse(xslt_path)
        transform = etree.XSLT(xslt)
        cadena_original = str(transform(tree))
    else:
        # Método simplificado (para desarrollo/pruebas)
        cadena_original = generar_cadena_original_simplificada(tree)
    
    # Firmar la cadena original
    sello = llave_privada.sign(
        cadena_original.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    sello_b64 = base64.b64encode(sello).decode('ascii')
    
    # Agregar el sello al XML
    tree.attrib['Sello'] = sello_b64
    
    # Convertir a string
    xml_sellado = etree.tostring(
        tree,
        encoding='UTF-8',
        xml_declaration=True,
        pretty_print=True
    ).decode('utf-8')
    
    return xml_sellado

def generar_cadena_original_simplificada(xml_element) -> str:
    """
    Genera la cadena original del CFDI (versión simplificada)
    NOTA: Para producción, usar el XSLT oficial del SAT
    """
    cadena = '||'
    
    def agregar_atributos(elemento, nivel=0):
        nonlocal cadena
        # Agregar atributos del elemento en orden alfabético
        for attr in sorted(elemento.attrib.keys()):
            if attr not in ['Sello', 'Certificado']:  # Excluir sello y certificado
                valor = elemento.attrib[attr]
                cadena += f'{valor}|'
        
        # Recursivamente procesar hijos
        for hijo in elemento:
            agregar_atributos(hijo, nivel + 1)
    
    agregar_atributos(xml_element)
    cadena += '|'
    
    return cadena

