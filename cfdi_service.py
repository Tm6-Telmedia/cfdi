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
import pytz

'''
para produccion cambiar PAC_WSDL, PAC_USER  y PAC_PASSWORD
'''

# Configuración del PAC modo test
PAC_WSDL = "https://testing.solucionfactible.com/ws/services/Timbrado?wsdl"
PAC_USER = "testing@solucionfactible.com"
PAC_PASSWORD = "timbrado.SF.16672"

# PAC_WSDL_CANCELAR = "https://testing.solucionfactible.com/ws/services/Cancelacion?wsdl"



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

def timbrar_con_pac(xml_bytes: bytes):
    """
    Envía un CFDI al PAC (Solución Factible) para timbrar.
    Recibe el XML sellado (bytes).
    Retorna:
        (cfdi_bytes, None) si es exitoso
        (None, mensaje_error) si falla
    """
    try:
        client = Client(PAC_WSDL)
        xml_b64 = base64.b64encode(xml_bytes).decode()

        result = client.service.timbrar(PAC_USER, PAC_PASSWORD, xml_b64, False)

        print(f"RESPUESTA DEL PAC - Status: {result.status}")

        #  ERROR GENERAL DEL PAC
        if result.status != 200:
            mensaje = getattr(result, 'mensaje', 'Error desconocido en el timbrado')
            print(f"ERROR DEL PAC: {mensaje}")
            return {"cfdi": None, "cadena_original": "", "error": mensaje}

        #  Validar que existan resultados
        if not hasattr(result, 'resultados') or not result.resultados:
            print(" No se recibieron resultados del PAC")
            return {"cfdi": None, "cadena_original": "", "error": "No se recibieron resultados del PAC"}

        primer_resultado = result.resultados[0]
        print(" primer_resultado:", primer_resultado)
        # print(" cfdiTimbrado:", getattr(primer_resultado, 'cfdiTimbrado', 'NO EXISTE'))
        # print(" mensaje:", getattr(primer_resultado, 'mensaje', 'NO EXISTE'))

        if hasattr(primer_resultado, 'mensaje') and primer_resultado.mensaje:
            if not getattr(primer_resultado, 'cfdiTimbrado', None):
                print(" PAC retornó vacío:", primer_resultado.mensaje)
                return {"cfdi": None, "cadena_original": "", "error": f"El PAC retornó vacío: {primer_resultado.mensaje}"}

        cfdi = primer_resultado.cfdiTimbrado
        # print(" cfdi obtenido:", cfdi)

        if not cfdi:
            print(" CFDI vacío")
            return None, "El PAC retornó un CFDI vacío"

        #  Convertir a bytes correctamente
        if isinstance(cfdi, bytes):
            cfdi_bytes = cfdi

        elif isinstance(cfdi, str):
            if cfdi.strip().startswith('<?xml'):
                cfdi_bytes = cfdi.encode('utf-8')
            else:
                try:
                    cfdi_bytes = base64.b64decode(cfdi)
                except Exception:
                    return {"cfdi": None, "cadena_original": "", "error": "No se pudo decodificar el CFDI retornado por el PAC"}

        else:
            cfdi_bytes = str(cfdi).encode('utf-8')

        print("TIMBRADO EXITOSO")
        return {
            "mensaje_pac": primer_resultado.mensaje,
            "status_pac" : result.status,
            "cfdi": cfdi_bytes,
            "cadena_original": getattr(primer_resultado, 'cadenaOriginal', ''),
            "qr_base64": base64.b64encode(primer_resultado.qrCode).decode('utf-8') if getattr(primer_resultado, 'qrCode', None) else "",
            "error": None
        }

    except Exception as e:
        error_msg = f"Error al conectar con el PAC: {str(e)}"
        print(error_msg)
        return {"cfdi": None, "cadena_original": "", "error": error_msg}

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

"""
las funciones de abajo son propias del proceso timbrado pero a su vez son 
funciones exclusivas de aplicacion DE ANTICIPO
"""

def generar_xml_cfdi(factura: dict, uuids_relacionados: list, no_certificado, certificado_base64: str) -> str:
    nsmap = {
        'cfdi': 'http://www.sat.gob.mx/cfd/4',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
    }

    tz_mx = pytz.timezone('America/Mexico_City')
    fecha_cfdi = datetime.now(tz_mx).strftime('%Y-%m-%dT%H:%M:%S')

    comprobante = etree.Element('{http://www.sat.gob.mx/cfd/4}Comprobante', nsmap=nsmap)

    comprobante.set('Version', '4.0')
    comprobante.set('Serie', factura.get('serie', ''))
    comprobante.set('Folio', factura.get('folio', ''))
    comprobante.set('Fecha', fecha_cfdi)
    comprobante.set('Sello', '')

    metodo_pago = factura.get('metodo_pago', '')
    forma_pago = factura.get('forma_pago', '')
    if metodo_pago == 'PPD':
        forma_pago = '99'

    comprobante.set('FormaPago', forma_pago)
    comprobante.set('NoCertificado', no_certificado)
    comprobante.set('Certificado', certificado_base64)
    comprobante.set('SubTotal', f"{factura['subtotal']:.2f}")
    comprobante.set('Moneda', 'MXN')
    comprobante.set('TipoCambio', '1')
    comprobante.set('Total', f"{factura['total']:.2f}")
    comprobante.set('TipoDeComprobante', 'I')
    comprobante.set('Exportacion', '01')
    comprobante.set('MetodoPago', metodo_pago)
    comprobante.set('LugarExpedicion', factura['emisor']['cp'])

    if factura.get('descuento_total', Decimal('0')) > 0:
        comprobante.set('Descuento', f"{factura['descuento_total']:.2f}")

    # CfdiRelacionados — solo si vienen UUIDs
    if uuids_relacionados:
        cfdi_relacionados = etree.SubElement(comprobante, '{http://www.sat.gob.mx/cfd/4}CfdiRelacionados')
        cfdi_relacionados.set('TipoRelacion', '07')
        for uuid in uuids_relacionados:
            cfdi_relacionado = etree.SubElement(cfdi_relacionados, '{http://www.sat.gob.mx/cfd/4}CfdiRelacionado')
            cfdi_relacionado.set('UUID', uuid)

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
        concepto_elem.set('ObjetoImp', '02')

        if concepto.get('descuento', Decimal('0')) > 0:
            concepto_elem.set('Descuento', f"{concepto['descuento']:.2f}")

        impuestos_concepto = etree.SubElement(concepto_elem, '{http://www.sat.gob.mx/cfd/4}Impuestos')
        traslados = etree.SubElement(impuestos_concepto, '{http://www.sat.gob.mx/cfd/4}Traslados')

        base = concepto['importe'] - concepto.get('descuento', Decimal('0'))

        traslado = etree.SubElement(traslados, '{http://www.sat.gob.mx/cfd/4}Traslado')
        traslado.set('Base', f"{base:.2f}")
        traslado.set('Impuesto', '002')
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

    tasa_iva = factura['conceptos'][0]['tasa_iva'] if factura['conceptos'] else Decimal('0.16')
    traslado_total.set('TasaOCuota', f"{tasa_iva:.6f}")
    traslado_total.set('Importe', f"{factura['iva']:.2f}")

    xml_str = etree.tostring(
        comprobante,
        pretty_print=True,
        xml_declaration=True,
        encoding='UTF-8'
    ).decode('utf-8')

    return xml_str


def sellar_cfdi(xml_sin_sellar: str, llave_privada, certificado_base64: str, xslt_path: str = None) -> dict:
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
        # print(cadena_original)
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
    
    return {
        "xml_sellado":xml_sellado,
        "cad_original_cfdi": cadena_original
    }


"""
las funciones de abajo son propias del proceso timbrado pero a su vez son 
funciones exclusivas de COMPLEMENTO DE PAGO
"""

def sellar_cfdi_complemento(xml_sin_sellar: str, llave_privada,  xslt_path: str = None) -> str:
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
        # print("*******************************************************")
        # print(cadena_original)
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


# la funcion de abajo se utiliza para ambos cfdi para poder sellar
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


#cancelacion de CFDI
def cancelar_cfdi_con_pac(uuid: str, motivo: str, rfc_emisor: str, email: str, uuid_sustituto: str = "", csd_cer: bytes = None, csd_key: bytes = None, csd_password: str = None) -> tuple:
    """
    Cancela un CFDI con el PAC Solución Factible.
    
    Args:
        uuid: UUID del CFDI a cancelar
        motivo: Motivo de cancelación (01, 02, 03, 04)
        rfc_emisor: RFC del emisor del CFDI
        email: Correo electrónico del emisor
        uuid_sustituto: UUID del CFDI sustituto (solo requerido con motivo 01)
    """
    try:
        # Construir cadena de cancelación en el formato que espera SF
        uuids = f"{uuid}|{motivo}|{uuid_sustituto}"
        # client = Client(PAC_WSDL_CANCELAR)
        client = Client(PAC_WSDL)
        #cancelarAsincrono
        # result = client.service.cancelar(PAC_USER, PAC_PASSWORD, uuids, rfc_emisor,email, csd_cer,csd_key,csd_password)
        result = client.service.cancelar(PAC_USER, PAC_PASSWORD, uuids, csd_cer,csd_key,csd_password)
        
        print(f"RESPUESTA DEL PAC - Status: {result.status}")

        if result.status != 200:
            mensaje = getattr(result, 'mensaje', 'Error desconocido en la cancelación')
            print(f"ERROR DEL PAC: {mensaje}")
            return None, mensaje

        if not hasattr(result, 'resultados') or not result.resultados:
            return None, "No se recibieron resultados del PAC"

        primer_resultado = result.resultados[0]

        uuid_cancelado = getattr(primer_resultado, 'uuid', None)
        status_resultado = getattr(primer_resultado, 'status', None)
        mensaje_resultado = getattr(primer_resultado, 'mensaje', None)
        status_uuid = getattr(primer_resultado, 'statusUUID', None)

        print(f"UUID: {uuid_cancelado}")
        print(f"Status resultado: {status_resultado}")
        print(f"Mensaje resultado: {mensaje_resultado}")
        print(f"StatusUUID: {status_uuid}")

        # Validar por status del resultado, no por statusUUID
        if status_resultado != 200:
            return None, f"Error en cancelación: {mensaje_resultado}"

        return {
            "uuid": uuid_cancelado,
            "status": status_resultado,
            "mensaje": mensaje_resultado,
            "statusUUID": status_uuid
        }, None

    except Exception as e:
        error_msg = f"Error al conectar con el PAC: {str(e)}"
        print(error_msg)
        return None, error_msg
