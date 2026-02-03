import os
from decimal import Decimal
import xml.etree.ElementTree as ET
from zeep import Client
from zeep.transports import Transport
from requests import Session

from lxml import etree
from datetime import datetime
from decimal import Decimal
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from cryptography import x509
import pytz

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

RUTA_CER = os.path.join(BASE_DIR, "CSD_Sucursal_1_EKU9003173C9_20230517_223850.cer")
RUTA_KEY = os.path.join(BASE_DIR, "CSD_Sucursal_1_EKU9003173C9_20230517_223850.key")
PASSWORD_KEY = b"12345678a"  

RUTA_XSLT = r"xslt\cadenaoriginal_4_0.xslt"

PAC_WSDL = "https://testing.solucionfactible.com/ws/services/Timbrado?wsdl"
PAC_USER = "testing@solucionfactible.com"
PAC_PASSWORD = "timbrado.SF.16672"

def extraer_uuid_cfdi(xml_cfdi: str) -> str:
    ns = {
        "cfdi": "http://www.sat.gob.mx/cfd/4",
        "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital"
    }
    root = ET.fromstring(xml_cfdi)
    timbre = root.find(".//tfd:TimbreFiscalDigital", ns)
    return timbre.attrib.get("UUID") if timbre is not None else None

def parse_filemaker_xml(xml_str: str) -> dict:
    ns = {"fm": "http://www.filemaker.com/fmpdsoresult"}
    root = ET.fromstring(xml_str)
    rows = root.findall("fm:ROW", ns)
    if not rows:
        raise Exception("No se encontraron ROW en XML FileMaker")
    
    def get(row, tag):
        el = row.find(f"fm:{tag}/fm:DATA", ns)
        return el.text.strip() if el is not None and el.text else ""
    
    def getSinData(row, tag):
        el = row.find(f"fm:{tag}", ns)
        return el.text.strip() if el is not None and el.text else ""
    
    # Tomamos datos generales del primer ROW (comunes a todos los conceptos)
    first = rows[0]
    
    # Procesar todos los conceptos (uno por cada ROW)
    conceptos = []
    for row in rows:
        concepto = {
            "clave_prod_serv": getSinData(row, "ClaveProdServ"),
            "cantidad": Decimal(getSinData(row, "cantidad") or "0"),
            "clave_unidad": getSinData(row, "Clave_unidad"),
            "unidad": getSinData(row, "unidad"),
            "descripcion": getSinData(row, "ConceptoItem"),
            "valor_unitario": Decimal(getSinData(row, "Monto") or "0"),
            "importe": Decimal(getSinData(row, "Importe") or "0"),
            "descuento": Decimal(getSinData(row, "DescuentoItem") or "0"),
            "tasa_iva": Decimal(getSinData(row, "tasa_IVA_porcentaje") or "0"),
            "monto_item_iva": Decimal(getSinData(row, "monto_item_IVA") or "0")
        }
        conceptos.append(concepto)
    
    factura = {
        "emisor": {
            "rfc": get(first, "Emisor_RFC"),
            "nombre": get(first, "Emisor_Nombre"),
            "regimen": get(first, "Emisor_c_RegimenFiscal"),
            "cp": get(first, "Emisor_codigo_postal")
        },
        "receptor": {
            "rfc": get(first, "Receptor_RFC"),
            "nombre": get(first, "Receptor_Nombre_Cliente_opc"),
            "regimen": get(first, "Receptor_regimen"),
            "uso_cfdi": get(first, "Receptor_UsoCFDI"),
            "cp": get(first, "Receptor_CP_opc")
        },
        "conceptos": conceptos,  # Lista de conceptos
        "serie": get(first, "serie"),
        "folio": get(first, "folio"),
        "metodo_pago": get(first, "Metodo_de_pago"),
        "forma_pago": get(first, "Forma_de_pago"),
        "subtotal": Decimal(get(first, "Subtotal") or "0"),
        "iva": Decimal(get(first, "Iva") or "0"),
        "total": Decimal(get(first, "Total") or "0"),
    }
    return factura

def crear_cfdi_desde_contexto(contexto: dict, certificado_path: str, key_path: str, password: str, xslt_path: str = None) -> str:
    uuid_origen = contexto.get("uuid_origen")
    factura = contexto.get("factura")
    
    if not uuid_origen or not factura:
        raise ValueError("Contexto debe contener 'uuid_origen' y 'factura'")
    
    # Cargar certificado y llave privada
    certificado_base64, no_certificado = cargar_certificado(certificado_path)
    llave_privada = cargar_llave_privada(key_path, password)
    
    # Crear el XML del CFDI
    xml_sin_sellar = generar_xml_cfdi(factura, uuid_origen, no_certificado, certificado_base64)
    print(f"xml_sinSellar: {xml_sin_sellar}")
    
    # Sellar el CFDI
    xml_sellado = sellar_cfdi(xml_sin_sellar, llave_privada,certificado_base64, xslt_path)
    
    return xml_sellado


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


def generar_xml_cfdi(factura: dict, uuid_origen: str, no_certificado, certificado_base64: str) -> str:
    """
    Genera el XML del CFDI 4.0 sin el sello (para luego sellarlo)
    """
    # Namespaces CFDI 4.0
    nsmap = {
        'cfdi': 'http://www.sat.gob.mx/cfd/4',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
    }
    
    # Fecha y hora actual en formato ISO 8601 (Zona horaria de México)
    tz_mx = pytz.timezone('America/Mexico_City')
    fecha_cfdi = datetime.now(tz_mx).strftime('%Y-%m-%dT%H:%M:%S')
    
    # Crear elemento raíz Comprobante
    comprobante = etree.Element(
        '{http://www.sat.gob.mx/cfd/4}Comprobante',
        nsmap=nsmap
    )
    
    # Atributos del Comprobante
    comprobante.set('Version', '4.0')
    comprobante.set('Serie', factura.get('serie', ''))
    comprobante.set('Folio', factura.get('folio', ''))
    comprobante.set('Fecha', fecha_cfdi)
    comprobante.set('Sello', '')  # Se llenará después del sellado

    # FormaPago: Si MetodoPago es PPD, FormaPago debe ser "99" (Por Definir)
    metodo_pago = factura.get('metodo_pago', '')
    forma_pago = factura.get('forma_pago', '')
    if metodo_pago == 'PPD':
        forma_pago = '99'  # Por Definir (obligatorio para PPD en CFDI 4.0)

    comprobante.set('FormaPago', forma_pago)
    comprobante.set('NoCertificado', no_certificado)
    comprobante.set('Certificado', certificado_base64)
    comprobante.set('SubTotal', f"{factura['subtotal']:.2f}")
    comprobante.set('Moneda', 'MXN')
    comprobante.set('TipoCambio', '1')
    comprobante.set('Total', f"{factura['total']:.2f}")
    comprobante.set('TipoDeComprobante', 'I')  # Ingreso
    comprobante.set('Exportacion', '01')  # No aplica
    comprobante.set('MetodoPago', factura.get('metodo_pago', ''))
    comprobante.set('LugarExpedicion', factura['emisor']['cp'])
    
    # Si hay descuento total
    if factura.get('descuento_total', Decimal('0')) > 0:
        comprobante.set('Descuento', f"{factura['descuento_total']:.2f}")
    
    # CfdiRelacionados - Relación con el anticipo original
    cfdi_relacionados = etree.SubElement(comprobante, '{http://www.sat.gob.mx/cfd/4}CfdiRelacionados')
    cfdi_relacionados.set('TipoRelacion', '07')  # Aplicación de anticipo
    
    cfdi_relacionado = etree.SubElement(cfdi_relacionados, '{http://www.sat.gob.mx/cfd/4}CfdiRelacionado')
    cfdi_relacionado.set('UUID', uuid_origen)
    
    # Emisor
    emisor = etree.SubElement(comprobante, '{http://www.sat.gob.mx/cfd/4}Emisor')
    emisor.set('Rfc', factura['emisor']['rfc'])
    emisor.set('Nombre', factura['emisor']['nombre'])
    emisor.set('RegimenFiscal', factura['emisor']['regimen'])
    
    # Receptor
    receptor = etree.SubElement(comprobante, '{http://www.sat.gob.mx/cfd/4}Receptor')
    receptor.set('Rfc', factura['receptor']['rfc'])
    receptor.set('Nombre', factura['receptor']['nombre'])
    receptor.set('DomicilioFiscalReceptor', factura['receptor']['cp'])
    receptor.set('RegimenFiscalReceptor', factura['receptor']['regimen'])
    receptor.set('UsoCFDI', factura['receptor']['uso_cfdi'])
    
    # Conceptos
    conceptos_elem = etree.SubElement(comprobante, '{http://www.sat.gob.mx/cfd/4}Conceptos')
    
    for concepto in factura['conceptos']:
        concepto_elem = etree.SubElement(conceptos_elem, '{http://www.sat.gob.mx/cfd/4}Concepto')
        concepto_elem.set('ClaveProdServ', concepto['clave_prod_serv'])
        concepto_elem.set('Cantidad', f"{concepto['cantidad']:.0f}")
        concepto_elem.set('ClaveUnidad', concepto['clave_unidad'])
        concepto_elem.set('Unidad', concepto['unidad'])
        concepto_elem.set('Descripcion', concepto['descripcion'])
        concepto_elem.set('ValorUnitario', f"{concepto['valor_unitario']:.2f}")
        concepto_elem.set('Importe', f"{concepto['importe']:.2f}")
        concepto_elem.set('ObjetoImp', '02')  # Sí objeto de impuestos
        
        if concepto.get('descuento', Decimal('0')) > 0:
            concepto_elem.set('Descuento', f"{concepto['descuento']:.2f}")
        
        # Impuestos del concepto
        impuestos_concepto = etree.SubElement(concepto_elem, '{http://www.sat.gob.mx/cfd/4}Impuestos')
        traslados = etree.SubElement(impuestos_concepto, '{http://www.sat.gob.mx/cfd/4}Traslados')
        
        # Calcular base (importe - descuento)
        base = concepto['importe'] - concepto.get('descuento', Decimal('0'))
        
        traslado = etree.SubElement(traslados, '{http://www.sat.gob.mx/cfd/4}Traslado')
        traslado.set('Base', f"{base:.2f}")
        traslado.set('Impuesto', '002')  # IVA
        traslado.set('TipoFactor', 'Tasa')
        traslado.set('TasaOCuota', f"{concepto['tasa_iva']:.6f}")
        traslado.set('Importe', f"{concepto['monto_item_iva']:.2f}")
    
    # Impuestos totales
    impuestos = etree.SubElement(comprobante, '{http://www.sat.gob.mx/cfd/4}Impuestos')
    impuestos.set('TotalImpuestosTrasladados', f"{factura['iva']:.2f}")
    
    traslados_totales = etree.SubElement(impuestos, '{http://www.sat.gob.mx/cfd/4}Traslados')
    traslado_total = etree.SubElement(traslados_totales, '{http://www.sat.gob.mx/cfd/4}Traslado')
    traslado_total.set('Base', f"{factura['subtotal']:.2f}")
    traslado_total.set('Impuesto', '002')
    traslado_total.set('TipoFactor', 'Tasa')
    
    # Obtener tasa IVA del primer concepto (asumiendo que todos tienen la misma)
    tasa_iva = factura['conceptos'][0]['tasa_iva'] if factura['conceptos'] else Decimal('0.16')
    traslado_total.set('TasaOCuota', f"{tasa_iva:.6f}")
    traslado_total.set('Importe', f"{factura['iva']:.2f}")
    
    # Convertir a string XML
    xml_str = etree.tostring(
        comprobante,
        pretty_print=True,
        xml_declaration=True,
        encoding='UTF-8'
    ).decode('utf-8')
    
    return xml_str


def sellar_cfdi(xml_sin_sellar: str, llave_privada, certificado_base64: str, xslt_path: str = None) -> str:
    """
    Genera la cadena original, sellarlo con la llave privada y agrega el sello al XML
    """
    # Parse del XML
    tree = etree.fromstring(xml_sin_sellar.encode('utf-8'))
    
    # Agregar certificado
    tree.attrib['Certificado'] = certificado_base64
    
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

def generar_cadena_original(xml_element) -> str:
    """
    Genera la cadena original del CFDI usando el XSLT del SAT para CFDI 4.0
    Esta es una versión simplificada. En producción deberías usar el XSLT oficial del SAT.
    """
    # Crear cadena original concatenando atributos en orden
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


def firmar_cadena(cadena: str, llave_privada) -> str:
    # Firmar con SHA256 y RSA
    firma = llave_privada.sign(
        cadena.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    
    # Convertir a base64
    firma_base64 = base64.b64encode(firma).decode('utf-8')
    
    return firma_base64


def timbrar_con_pac(xml_bytes: bytes) -> dict:
    """
    Envía un CFDI al PAC (Solución Factible) para timbrar.
    Recibe el XML sellado (bytes) y regresa dict con uuid y xml_timbrado (base64).
    """
    try:
        client = Client(PAC_WSDL)
        xml_b64 = base64.b64encode(xml_bytes).decode()
        
        result = client.service.timbrar(PAC_USER, PAC_PASSWORD, xml_b64, False)
        
        # print(f"RESPUESTA DEL PAC - Status: {result.status}")
        
        if result.status != 200:
            mensaje = getattr(result, 'mensaje', 'Error desconocido en el timbrado')
            # print(f"ERROR DEL PAC: {mensaje}")
            return None, mensaje
        
        # DEBUG: Verificar qué contiene result
        # print(f"DEBUG - Atributos de result: {dir(result)}")
        # print(f"DEBUG - Tiene resultados: {hasattr(result, 'resultados')}")
        
        # Verificar que resultados existe y tiene elementos
        if not hasattr(result, 'resultados') or not result.resultados or len(result.resultados) == 0:
            # print("DEBUG - No hay resultados en la respuesta del PAC")
            return None, "No se recibieron resultados del PAC"
        
        # print(f"DEBUG - Número de resultados: {len(result.resultados)}")
        primer_resultado = result.resultados[0]
        # print(f"DEBUG - Atributos del primer resultado: {dir(primer_resultado)}")
        
        cfdi = primer_resultado.cfdiTimbrado
        # print(f"DEBUG - cfdiTimbrado es None: {cfdi is None}")
        # if cfdi:
            # print(f"DEBUG - Tipo de cfdi: {type(cfdi)}")
            # print(f"DEBUG - Longitud de cfdi: {len(cfdi) if hasattr(cfdi, '__len__') else 'N/A'}")
        
        # Verificar que cfdi no sea None
        if cfdi is None:
            if hasattr(primer_resultado, 'mensaje'):
                # print(f"DEBUG - Mensaje del resultado: {primer_resultado.mensaje}")
                return None, f"El PAC retornó vacío: {primer_resultado.mensaje}"
            return None, "El PAC retornó un CFDI vacío"
        
        # El PAC devuelve el XML directamente como bytes, no en base64
        if isinstance(cfdi, bytes):
            cfdi_bytes = cfdi
        elif isinstance(cfdi, str):
            # Si es string, verificar si empieza con <?xml (no está en base64)
            if cfdi.strip().startswith('<?xml'):
                cfdi_bytes = cfdi.encode('utf-8')
            else:
                # Si no empieza con <?xml, asumir que está en base64
                try:
                    cfdi_bytes = base64.b64decode(cfdi)
                except Exception as decode_error:
                    cfdi_bytes = cfdi.encode('utf-8')
        else:
            cfdi_bytes = str(cfdi).encode('utf-8')
        
        # print(" TIMBRADO EXITOSO")
        return cfdi_bytes
    
    except Exception as e:
        # print(f" ERROR AL CONECTAR CON EL PAC: {str(e)}")
        return None, f"Error al conectar con el PAC: {str(e)}"
        
    except Exception as e:
        error_msg = f"Error al timbrar: {str(e)}"
        print(f" {error_msg}")
        import traceback
        traceback.print_exc()
        return {'error': error_msg}

def generar_xml_timbrado(xml_timbrado: bytes):
    try:
        # Preparar respuesta
        respuesta = {
            "xml": xml_timbrado.decode('utf-8'),
            "success": True
        }
        
        return respuesta
        
    except Exception as e:
        return {
            "error": f"Error procesando archivos: {str(e)}",
            "success": False
        }