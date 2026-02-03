"""
DEPENDENCIAS QUE REQUIEREN INSTALACIÓN:
pip install Flask==3.0.0 flask-cors==4.0.0 lxml==5.1.0 zeep==4.2.1 cryptography==41.0.7
"""

from flask import Flask, request, jsonify, Response
from lxml import etree
import base64
from datetime import datetime
from zeep import Client
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from cryptography import x509
import os
from flask_cors import CORS
from xml.dom.minidom import parseString
from decimal import Decimal
from typing import List, Optional
import ssl
app = Flask(__name__)
CORS(app)
# Crear un contexto SSL
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certfile='tm7_combined.pem')  # Certificado + clave combinados
app = Flask(__name__)
CORS(app)
# Importar funciones necesarias de PDF.py
from PDF import (
    generar_pdf_factura, PDFGenerationError, 
    ConceptoCFDI, extraer_conceptos_filemaker
)

from cfdi_service_anticipo import (
    extraer_uuid_cfdi,
    parse_filemaker_xml,
    crear_cfdi_desde_contexto,
    timbrar_con_pac,
    generar_xml_timbrado
)

from cfdi_service_complemento import (
    parse_xml_complemento,
    crear_cfdi_complemento,
    cargar_llave_privada,
    sellar_cfdi,
    cargar_certificado
    # timbrar_con_pac
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_CER = os.path.join(BASE_DIR, "CSD_Sucursal_1_EKU9003173C9_20230517_223850.cer")
RUTA_KEY = os.path.join(BASE_DIR, "CSD_Sucursal_1_EKU9003173C9_20230517_223850.key")
PASSWORD_KEY = b"12345678a"  

RUTA_XSLT = r"xslt\cadenaoriginal_4_0.xslt"

# Constantes globales
FILEMAKER_NAMESPACE = "http://www.filemaker.com/fmpdsoresult"

def parsear_filemaker_xml(xml_filemaker: bytes):
    """
    Helper para parsear XML de FileMaker y encontrar el primer ROW
    Retorna: (tree, row) o (None, None) si hay error
    """
    try:
        tree = etree.fromstring(xml_filemaker)
        
        # Buscar el primer ROW
        row = tree.find(f".//{{{FILEMAKER_NAMESPACE}}}ROW")
        if row is None:
            row = tree.find(".//ROW")
        
        return tree, row
    except Exception as e:
        log_error("Error parseando XML de FileMaker", e)
        return None, None

def extraer_campo_filemaker(row, campo_nombre: str, fm_ns: str = FILEMAKER_NAMESPACE) -> str:
    """
    Helper para extraer un campo específico de un ROW de FileMaker
    """
    for child in row:
        tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        
        if tag_name == campo_nombre:
            data_node = child.find(f"{{{fm_ns}}}DATA") if fm_ns else child.find("DATA")
            if data_node is not None and data_node.text:
                return data_node.text.strip()
    return ""

def extraer_folio_serie_filemaker(xml_filemaker: bytes) -> tuple:
    """Extrae folio y serie del archivo FileMaker"""
    tree, row = parsear_filemaker_xml(xml_filemaker)
    if not row:
        return None, None
    serie = extraer_campo_filemaker(row, "serie") or "C"
    folio = extraer_campo_filemaker(row, "folio") or ""
    return serie, folio


def aplicar_folio_serie_xml(tree, serie=None, folio=None):
    """Aplica serie y folio al XML"""
    try:
        if serie:
            tree.set("Serie", serie)
        if folio:
            tree.set("Folio", folio)
    except Exception as e:
        print(f"Error aplicando folio/serie: {e}")

def log_debug(mensaje: str):
    """Helper para logs de debug"""
    print(f"✓ DEBUG: {mensaje}")

def log_error(mensaje: str, error: Exception = None):
    """Helper para logs de error"""
    print(f"⚠ ERROR: {mensaje}")
    if error:
        print(f"   Detalle: {error}")


# CONSTANTES GLOBALES
CFDI_NS = "http://www.sat.gob.mx/cfd/4"
PAGO_NS = "http://www.sat.gob.mx/Pagos20"
TFD_NS = "http://www.sat.gob.mx/TimbreFiscalDigital"

#eliminar
app = Flask(__name__)
CORS(app)


# CONFIGURACIÓN GENERAL modo test
RUTA_CER = r"CSD_Sucursal_1_EKU9003173C9_20230517_223850.cer"
RUTA_KEY = r"CSD_Sucursal_1_EKU9003173C9_20230517_223850.key"
RUTA_XSLT = r"xslt\cadenaoriginal_4_0.xslt"
SALIDA_DIR = r"TimbradoSalida"
PASSWORD_KEY = b"12345678a"

# Configuración del PAC modo test
usuario = "testing@solucionfactible.com"
contrasena = "timbrado.SF.16672"
wsdl_url = "https://testing.solucionfactible.com/ws/services/Timbrado?wsdl"



# FUNCIONES HELPER
def buscar_nodo_xml(xmlDom, tag_name, namespace=None):
    """Busca un nodo XML de forma segura"""
    try:
        if namespace:
            elementos = xmlDom.getElementsByTagNameNS(namespace, tag_name)
            if elementos.length > 0:
                return elementos[0]
        
        elementos = xmlDom.getElementsByTagName(tag_name)
        if elementos.length > 0:
            return elementos[0]
            
        if ":" in tag_name:
            tag_sin_prefijo = tag_name.split(":")[-1]
            elementos = xmlDom.getElementsByTagName(tag_sin_prefijo)
            if elementos.length > 0:
                return elementos[0]
        
        return None
    except Exception as e:
        print(f"ADVERTENCIA: Error buscando nodo {tag_name}: {e}")
        return None

def remover_nodo_seguro(nodo_padre, nodo_hijo, descripcion="nodo"):
    """Remueve un nodo hijo de forma segura"""
    if not nodo_padre or not nodo_hijo:
        return False
    
    try:
        if nodo_hijo.parentNode != nodo_padre or nodo_hijo not in nodo_padre.childNodes:
            return False
        
        nodo_padre.removeChild(nodo_hijo)
        return True
    except Exception as e:
        print(f"Error removiendo {descripcion}: {e}")
        return False

def log_mensaje(mensaje, tipo="INFO"):
    """Función unificada para logging"""
    prefijos = {"OK": "OK:", "ERROR": "ERROR:", "ADVERTENCIA": "ADVERTENCIA:"}
    print(f"{prefijos.get(tipo, '')} {mensaje}")

def log_error_with_traceback(error_message, exception):
    """Log errors with traceback"""
    log_mensaje(f"{error_message}: {str(exception)}", "ERROR")
    import traceback
    traceback.print_exc()

def log_timbrado_exitoso(nombre_archivo):
    """Log successful timbrado"""
    log_mensaje(f"CFDI TIMBRADO EXITOSAMENTE: {nombre_archivo}", "OK")

def log_xml_sellado():
    """Log successful XML sealing"""
    log_mensaje("XML SELLADO CORRECTAMENTE", "OK")

# Alias para compatibilidad
buscar_nodo_seguro = buscar_nodo_xml

def agregar_forma_pago_xml(tree, forma_pago, tipo_comprobante=None, metodo_pago=None, moneda="MXN", tipo_cambio="1"):
    """Agrega forma de pago y método de pago al XML"""
    try:
        comprobante = tree
        if comprobante.tag.endswith("Comprobante"):
            if tipo_comprobante == "P":
                log_mensaje(f"Forma de pago '{forma_pago}' sera aplicada en FormaDePagoP", "OK")
            else:
                comprobante.set("FormaPago", forma_pago)
                
                if metodo_pago:
                    comprobante.set("MetodoPago", metodo_pago)
        else:
            log_mensaje("No se encontro el nodo Comprobante", "ADVERTENCIA")
    except Exception as e:
        log_mensaje(f"Error agregando forma de pago: {str(e)}", "ADVERTENCIA")


def obtener_no_certificado(ruta_cer):
    with open(ruta_cer, "rb") as f:
        cert = x509.load_der_x509_certificate(f.read(), backend=default_backend())
    serial_hex = format(cert.serial_number, "x")
    try:
        serial_ascii = bytes.fromhex(serial_hex).decode("ascii")
    except Exception:
        serial_ascii = serial_hex
    return serial_ascii

def generar_sello(xml_bytes, ruta_cer, ruta_key, pwd_key):

    if isinstance(xml_bytes, str):
        xml_bytes = xml_bytes.encode('utf-8')

    tree = etree.fromstring(xml_bytes)

    # Certificado
    with open(ruta_cer, "rb") as f:
        cer_bytes = f.read()
    certificado_b64 = base64.b64encode(cer_bytes).decode("ascii")

    # Clave privada
    with open(ruta_key, "rb") as f:
        private_key = serialization.load_der_private_key(
            f.read(), password=pwd_key, backend=default_backend()
        )

    # Cadena original
    xslt = etree.parse(RUTA_XSLT)
    transform = etree.XSLT(xslt)
    cadena_original = str(transform(tree))

    # Sello
    sello = private_key.sign(
        cadena_original.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    sello_b64 = base64.b64encode(sello).decode()

    tree.attrib["Sello"] = sello_b64
    tree.attrib["Certificado"] = certificado_b64

    return etree.tostring(tree, encoding="utf-8", xml_declaration=True, pretty_print=True)

def timbrar_con_sf(xml_bytes):
    try:
        client = Client(wsdl_url)
        xml_b64 = base64.b64encode(xml_bytes).decode()
        
        result = client.service.timbrar(usuario, contrasena, xml_b64, False)
        
        print(f"RESPUESTA DEL PAC - Status: {result.status}")

        if result.status != 200:
            mensaje = getattr(result, 'mensaje', 'Error desconocido en el timbrado')
            print(f"ERROR DEL PAC: {mensaje}")
            return None, mensaje
        
        # DEBUG: Verificar qué contiene result
        print(f"DEBUG - Atributos de result: {dir(result)}")
        print(f"DEBUG - Tiene resultados: {hasattr(result, 'resultados')}")
        
        # Verificar que resultados existe y tiene elementos
        if not hasattr(result, 'resultados') or not result.resultados or len(result.resultados) == 0:
            print("DEBUG - No hay resultados en la respuesta del PAC")
            return None, "No se recibieron resultados del PAC"
        
        print(f"DEBUG - Número de resultados: {len(result.resultados)}")
        primer_resultado = result.resultados[0]
        print(f"DEBUG - Atributos del primer resultado: {dir(primer_resultado)}")
        
        cfdi = primer_resultado.cfdiTimbrado
        if cfdi:
            print(f"DEBUG - Tipo de cfdi: {type(cfdi)}")
            print(f"DEBUG - Longitud de cfdi: {len(cfdi) if hasattr(cfdi, '__len__') else 'N/A'}")
        
        # Verificar que cfdi no sea None
        if cfdi is None:
            if hasattr(primer_resultado, 'mensaje'):
                print(f"DEBUG - Mensaje del resultado: {primer_resultado.mensaje}")
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
        
        print(" TIMBRADO EXITOSO")
        return cfdi_bytes, "Timbrado exitoso"
    
    except Exception as e:
        print(f" ERROR AL CONECTAR CON EL PAC: {str(e)}")
        return None, f"Error al conectar con el PAC: {str(e)}"


def preparar_xml_base(xml_original):
    """Prepara el XML con fecha y certificado"""
    tree = etree.fromstring(xml_original)
    
    # Actualizar fecha
    tree.attrib["Fecha"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    
    # Colocar NoCertificado
    no_cert = obtener_no_certificado(RUTA_CER)
    tree.attrib["NoCertificado"] = no_cert
    
    # IMPORTANTE: Asegurar que el namespace xsi esté definido
    if "{http://www.w3.org/2001/XMLSchema-instance}" not in tree.nsmap.values():
        # Agregar namespace xsi si no existe
        tree.set("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation", 
                tree.get("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation", 
                        "http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd"))
    
    return tree

def guardar_xml(xml_bytes, tipo_comprobante):
    """Guarda el XML en el directorio de salida"""
    if not os.path.exists(SALIDA_DIR):
        os.makedirs(SALIDA_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"CFDI_{tipo_comprobante}_{timestamp}.xml"
    ruta_salida = os.path.join(SALIDA_DIR, nombre_archivo)
    
    with open(ruta_salida, "wb") as f:
        f.write(xml_bytes)
    
    return nombre_archivo

def guardar_pdf(pdf_bytes, tipo_comprobante):
    """Guarda el PDF en el directorio de salida"""
    if not os.path.exists(SALIDA_DIR):
        os.makedirs(SALIDA_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"CFDI_{tipo_comprobante}_{timestamp}.pdf"
    ruta_salida = os.path.join(SALIDA_DIR, nombre_archivo)
    
    with open(ruta_salida, "wb") as f:
        f.write(pdf_bytes)
    
    return nombre_archivo


def generar_respuesta_dual(xml_timbrado, tipo_comprobante):
   
    try:
        
        # Intentar generar PDF
        pdf_bytes = None
        nombre_pdf = None
        error_pdf = None
        
        try:
            pdf_bytes = generar_pdf_factura(xml_timbrado, tipo_comprobante)
            nombre_pdf = guardar_pdf(pdf_bytes, tipo_comprobante)
        except PDFGenerationError as e:
            error_pdf = str(e)
        except Exception as e:
            error_pdf = f"Error inesperado en PDF: {str(e)}"
        
        # Preparar respuesta
        respuesta = {
            "xml": base64.b64encode(xml_timbrado).decode(),
            "success": True
        }
        
        if pdf_bytes:
            respuesta["pdf"] = base64.b64encode(pdf_bytes).decode()
            respuesta["pdf_filename"] = nombre_pdf
        else:
            respuesta["pdf_error"] = error_pdf
        
        return respuesta
        
    except Exception as e:
        return {
            "error": f"Error procesando archivos: {str(e)}",
            "success": False
        }


def extraer_valores_documento_original(xml_bytes):
    """
    Extrae Base, Importe y otros valores del documento original para el complemento de pago
    Retorna: dict con valores necesarios para el complemento
    """
    try:
        tree = etree.fromstring(xml_bytes)
        
        # Extraer Base e Importe del nodo Traslado
        base = "0.00"
        importe = "0.00"
        
        # Buscar el nodo Traslado dentro de Impuestos
        # Puede estar en cfdi:Impuestos/cfdi:Traslados/cfdi:Traslado
        traslados = tree.findall(f".//{{{CFDI_NS}}}Traslados/{{{CFDI_NS}}}Traslado")
        
        if traslados:
            # Tomar el primer traslado encontrado
            primer_traslado = traslados[0]
            base = primer_traslado.get("Base", "0.00")
            importe = primer_traslado.get("Importe", "0.00")
        
        # Convertir a float para realizar cálculos
        base_float = float(base)
        importe_float = float(importe)
        
        # REALIZAR LOS CÁLCULOS según las fórmulas especificadas:
        # Monto = Base + Importe
        monto = base_float + importe_float
        
        # MontoTotalPagos = Monto
        monto_total_pagos = monto
        
        # ImpSaldoAnt = Base + Importe
        imp_saldo_ant = base_float + importe_float
        
        # ImpPagado = ImpSaldoAnt
        imp_pagado = imp_saldo_ant
        
        # ImpSaldoInsoluto = ImpSaldoAnt - ImpPagado
        imp_saldo_insoluto = imp_saldo_ant - imp_pagado
        
        # Verificar si tiene impuestos trasladados (si Importe > 0, entonces sí tiene)
        tiene_impuestos = importe_float > 0
        
        return {
            'base': f"{base_float:.2f}",
            'importe': f"{importe_float:.2f}",
            'monto_total': f"{monto:.2f}",
            'saldo_anterior': f"{imp_saldo_ant:.2f}",
            'importe_pagado': f"{imp_pagado:.2f}",
            'saldo_insoluto': f"{imp_saldo_insoluto:.2f}",
            'tiene_impuestos': tiene_impuestos
        }
        
    except Exception as e:
        log_error_with_traceback("Error al extraer valores del documento original", e)
        return {
            'base': '0.00',
            'importe': '0.00',
            'monto_total': '0.00',
            'saldo_anterior': '0.00',
            'importe_pagado': '0.00',
            'saldo_insoluto': '0.00',
            'tiene_impuestos': False
        }

# TRANSFORMACIONES ESPECÍFICAS - COMPLEMENTO DE PAGO
def transformar_a_complemento_pago(xmlDom, uuid_documento_original=None, forma_pago="99", valores_pago=None):
    """Transforma XML a Complemento de Pago (tipo P)"""
    
    # Buscar el nodo Comprobante (con o sin namespace)
    comprobante = buscar_nodo_seguro(xmlDom, "Comprobante", CFDI_NS)
    if not comprobante:
        comprobante = buscar_nodo_seguro(xmlDom, "cfdi:Comprobante")
    if not comprobante:
        comprobante = xmlDom.documentElement

    tipoActual = comprobante.getAttribute("TipoDeComprobante")
    
    # IMPORTANTE: Extraer la moneda original ANTES de hacer cambios
    moneda_original = comprobante.getAttribute("Moneda") or "MXN"
    
    # NUEVO: Extraer Serie y Folio del documento original
    serie_original = comprobante.getAttribute("Serie") or "A"
    folio_original = comprobante.getAttribute("Folio") or "1"

    comprobante.setAttribute("TipoDeComprobante", "P")
    
    comprobante.setAttribute("SubTotal", "0")
    comprobante.setAttribute("Total", "0")
    
    comprobante.setAttribute("Moneda", "XXX")
        
    if not comprobante.getAttribute("Exportacion"):
        comprobante.setAttribute("Exportacion", "01")
    
    atributos_a_remover = ["FormaPago", "MetodoPago", "CondicionesDePago", "TipoCambio", "Descuento"]
    for atributo in atributos_a_remover:
        if comprobante.hasAttribute(atributo):
            comprobante.removeAttribute(atributo)
    
    receptor = buscar_nodo_seguro(xmlDom, "Receptor", CFDI_NS)
    if not receptor:
        receptor = buscar_nodo_seguro(xmlDom, "cfdi:Receptor")
    if receptor:
        receptor.setAttribute("UsoCFDI", "CP01")
    
    # 3. Agregar namespace pago20
    if not comprobante.hasAttribute("xmlns:pago20"):
        comprobante.setAttribute("xmlns:pago20", PAGO_NS)
    
    # 4. Actualizar schemaLocation
    schema = comprobante.getAttribute("xsi:schemaLocation") or ""
    if PAGO_NS not in schema:
        schema += " " + PAGO_NS + " http://www.sat.gob.mx/sitio_internet/cfd/Pagos/Pagos20.xsd"
        comprobante.setAttribute("xsi:schemaLocation", schema.strip())
    
    # 5.  IMPORTANTE: Remover Impuestos y Conceptos existentes
    # Buscar y remover TODOS los nodos Impuestos
    impuestosNodes = xmlDom.getElementsByTagName("cfdi:Impuestos")
    nodosARemover = []
    for i in range(impuestosNodes.length):
        nodosARemover.append(impuestosNodes[i])
    
    for nodo in nodosARemover:
        if nodo.parentNode:
            remover_nodo_seguro(nodo.parentNode, nodo, "Nodo Impuestos")
    
    # Buscar y remover TODOS los nodos Conceptos
    conceptosNodes = xmlDom.getElementsByTagName("cfdi:Conceptos")
    nodosConceptosARemover = []
    for i in range(conceptosNodes.length):
        nodosConceptosARemover.append(conceptosNodes[i])
    
    for nodo in nodosConceptosARemover:
        if nodo.parentNode:
            remover_nodo_seguro(nodo.parentNode, nodo, "Nodo Conceptos")
    
    # Crear nodo Conceptos con concepto especial para Complemento de Pago
    conceptos = xmlDom.createElementNS(CFDI_NS, "cfdi:Conceptos")
    concepto = xmlDom.createElementNS(CFDI_NS, "cfdi:Concepto")
    concepto.setAttribute("ClaveProdServ", "84111506")
    concepto.setAttribute("Cantidad", "1")
    concepto.setAttribute("ClaveUnidad", "ACT")
    concepto.setAttribute("Descripcion", "Pago")
    concepto.setAttribute("ValorUnitario", "0")
    concepto.setAttribute("Importe", "0")
    concepto.setAttribute("ObjetoImp", "01")
    conceptos.appendChild(concepto)
    
    # Insertar Conceptos después del Receptor
    receptorNode = comprobante.getElementsByTagName("cfdi:Receptor")[0] if comprobante.getElementsByTagName("cfdi:Receptor") else None
    if receptorNode and receptorNode.nextSibling:
        comprobante.insertBefore(conceptos, receptorNode.nextSibling)
    else:
        comprobante.appendChild(conceptos)
    
    # 6. NUEVO: Usar valores extraídos y calculados del documento original
    if valores_pago is None:
        # Valores por defecto si no se proporcionan
        valores_pago = {
            'base': '0.00',
            'importe': '0.00',
            'monto_total': '0.00',
            'saldo_anterior': '0.00',
            'importe_pagado': '0.00',
            'saldo_insoluto': '0.00',
            'tiene_impuestos': False
        }
    
    uuid_documento = uuid_documento_original if uuid_documento_original else "00000000-0000-0000-0000-000000000000"
    
    # Crear o limpiar complemento
    complemento = xmlDom.getElementsByTagName("cfdi:Complemento")[0] if xmlDom.getElementsByTagName("cfdi:Complemento") else None
    if complemento:
        # Limpiar complemento existente de forma más segura
        hijos_a_remover = []
        for i in range(complemento.childNodes.length):
            hijos_a_remover.append(complemento.childNodes[i])
        
        for hijo in hijos_a_remover:
            remover_nodo_seguro(complemento, hijo, "Hijo del complemento")
    else:
        # Si no hay complemento, crearlo
        complemento = xmlDom.createElementNS(CFDI_NS, "cfdi:Complemento")
        comprobante.appendChild(complemento)
    
    # Crear nodo Pagos
    pagos = xmlDom.createElementNS(PAGO_NS, "pago20:Pagos")
    pagos.setAttribute("Version", "2.0")
    
    # Crear nodo Totales con el monto calculado correctamente
    totales = xmlDom.createElementNS(PAGO_NS, "pago20:Totales")
    totales.setAttribute("MontoTotalPagos", valores_pago['monto_total'])
    
    # NUEVO: Agregar totales de impuestos si el documento original tiene impuestos
    if valores_pago['tiene_impuestos']:
        # Usar los valores calculados de Base e Importe
        base_float = float(valores_pago['base'])
        importe_float = float(valores_pago['importe'])
        
        totales.setAttribute("TotalTrasladosBaseIVA16", valores_pago['base'])
        totales.setAttribute("TotalTrasladosImpuestoIVA16", valores_pago['importe'])
    
    pagos.appendChild(totales)
    
    # Crear nodo Pago con los valores calculados correctamente
    pago = xmlDom.createElementNS(PAGO_NS, "pago20:Pago")
    fechaActual = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    pago.setAttribute("FechaPago", fechaActual)
    pago.setAttribute("FormaDePagoP", forma_pago)
    pago.setAttribute("MonedaP", moneda_original)
    # Siempre establecer TipoCambioP como "1" (obligatorio para el SAT)
    pago.setAttribute("TipoCambioP", "1")
    pago.setAttribute("Monto", valores_pago['monto_total'])
    
    # NUEVO: Agregar impuestos al pago si corresponde
    if valores_pago['tiene_impuestos']:
        impuestos_pago = xmlDom.createElementNS(PAGO_NS, "pago20:ImpuestosP")
        traslados_p = xmlDom.createElementNS(PAGO_NS, "pago20:TrasladosP")
        traslado_p = xmlDom.createElementNS(PAGO_NS, "pago20:TrasladoP")
        
        base_float = float(valores_pago['base'])
        importe_float = float(valores_pago['importe'])
        
        traslado_p.setAttribute("BaseP", valores_pago['base'])
        traslado_p.setAttribute("ImpuestoP", "002")
        traslado_p.setAttribute("TipoFactorP", "Tasa")
        traslado_p.setAttribute("TasaOCuotaP", "0.160000")
        traslado_p.setAttribute("ImporteP", valores_pago['importe'])
        
        traslados_p.appendChild(traslado_p)
        impuestos_pago.appendChild(traslados_p)
        pago.appendChild(impuestos_pago)
    
    # Crear nodo DoctoRelacionado con valores calculados correctamente y serie/folio originales
    doctoRelacionado = xmlDom.createElementNS(PAGO_NS, "pago20:DoctoRelacionado")
    doctoRelacionado.setAttribute("IdDocumento", uuid_documento)
    doctoRelacionado.setAttribute("Serie", serie_original)
    doctoRelacionado.setAttribute("Folio", folio_original)
    doctoRelacionado.setAttribute("MonedaDR", moneda_original)
    doctoRelacionado.setAttribute("EquivalenciaDR", "1")
    doctoRelacionado.setAttribute("NumParcialidad", "1")
    doctoRelacionado.setAttribute("ImpSaldoAnt", valores_pago['saldo_anterior'])
    doctoRelacionado.setAttribute("ImpPagado", valores_pago['importe_pagado'])
    doctoRelacionado.setAttribute("ImpSaldoInsoluto", valores_pago['saldo_insoluto'])
    
    # CORREGIR: ObjetoImpDR debe ser "02" si tiene impuestos, "01" si no
    objeto_imp_dr = "02" if valores_pago['tiene_impuestos'] else "01"
    doctoRelacionado.setAttribute("ObjetoImpDR", objeto_imp_dr)
    
    # NUEVO: Agregar impuestos al documento relacionado si corresponde
    if valores_pago['tiene_impuestos']:
        impuestos_dr = xmlDom.createElementNS(PAGO_NS, "pago20:ImpuestosDR")
        traslados_dr = xmlDom.createElementNS(PAGO_NS, "pago20:TrasladosDR")
        traslado_dr = xmlDom.createElementNS(PAGO_NS, "pago20:TrasladoDR")
        
        base_float = float(valores_pago['base'])
        importe_float = float(valores_pago['importe'])
        
        traslado_dr.setAttribute("BaseDR", valores_pago['base'])
        traslado_dr.setAttribute("ImpuestoDR", "002")
        traslado_dr.setAttribute("TipoFactorDR", "Tasa")
        traslado_dr.setAttribute("TasaOCuotaDR", "0.160000")
        traslado_dr.setAttribute("ImporteDR", valores_pago['importe'])
        
        traslados_dr.appendChild(traslado_dr)
        impuestos_dr.appendChild(traslados_dr)
        doctoRelacionado.appendChild(impuestos_dr)
    
    pago.appendChild(doctoRelacionado)
    
    pagos.appendChild(pago)
    complemento.appendChild(pagos)


def procesar_complemento_pago(xml_original, forma_pago="99"):
    """Función principal para procesar complemento de pago"""
    
    # PRIMERO extraer los valores del documento original
    valores_pago = extraer_valores_documento_original(xml_original)
    
    # SEGUNDO extraer el UUID del documento original antes de cualquier transformación
    uuid_documento_original = None
    try:
        tree_original = etree.fromstring(xml_original)
        
        # Agregar forma de pago al XML original (para complemento de pago, tipo P)
        agregar_forma_pago_xml(tree_original, forma_pago, "P")
        
        # Buscar TimbreFiscalDigital de manera más robusta
        tfd = None
        
        # Método 1: Buscar por namespace completo
        tfd = tree_original.find(f".//{{{TFD_NS}}}TimbreFiscalDigital")
        
        # Método 2: Buscar cualquier elemento que termine en TimbreFiscalDigital
        if tfd is None:
            for elem in tree_original.iter():
                if elem.tag.endswith("TimbreFiscalDigital"):
                    tfd = elem
                    break
        # Método 3: Buscar por atributo UUID directamente
        if tfd is None:
            for elem in tree_original.iter():
                if elem.get("UUID"):
                    tfd = elem
                    break
        if tfd is not None:
            uuid_documento_original = tfd.get("UUID")
        else:
            # Mostrar todos los elementos para debug
            for elem in tree_original.iter():
                attrs = ", ".join([f"{k}={v}" for k, v in elem.attrib.items()])
    except Exception as e:
        log_error_with_traceback("Error al extraer UUID del documento original", e)
    
    # Preparar XML base usando el tree_original ya modificado
    xml_original_modificado = etree.tostring(tree_original, encoding="UTF-8", xml_declaration=True)
    tree = preparar_xml_base(xml_original_modificado)
    
    # Validar estructura de Complemento de Pago
    tipo_comprobante = tree.attrib.get("TipoDeComprobante", "")
    if tipo_comprobante == "P":
        pagos = tree.find(f".//{{{PAGO_NS}}}Pagos")
        if pagos is None:
            print("  XML tipo P sin nodo Pagos - se creará automáticamente durante la transformación")

    # Convertir a DOM para transformación
    xml_string = etree.tostring(tree, encoding="UTF-8", xml_declaration=True)
    dom = parseString(xml_string)
    
    # Aplicar transformación a Complemento de Pago
    transformar_a_complemento_pago(dom, uuid_documento_original, forma_pago, valores_pago)
    
    # Convertir DOM a string SIN encoding parameter
    xml_transformado_str = dom.toxml()
    
    # Agregar declaración XML UTF-8
    if not xml_transformado_str.startswith('<?xml'):
        xml_transformado_str = '<?xml version="1.0" encoding="UTF-8"?>' + xml_transformado_str
    else:
        xml_transformado_str = xml_transformado_str.replace(
            '<?xml version="1.0" ?>', 
            '<?xml version="1.0" encoding="UTF-8"?>'
        )
    
    # Convertir a bytes
    xml_transformado = xml_transformado_str.encode('utf-8')
    
    # Generar sello
    xml_sellado = generar_sello(xml_transformado, RUTA_CER, RUTA_KEY, PASSWORD_KEY)
    
    log_xml_sellado()

    # Intentar timbrar
    xml_timbrado, msg = timbrar_con_sf(xml_sellado)

    # Si el timbrado no devuelve XML válido, guardar el XML sellado
    if xml_timbrado is None or not xml_timbrado.strip().startswith(b"<"):
        nombre_archivo = guardar_xml(xml_sellado, "P")
        return xml_sellado

    # Guardar solo el XML timbrado final
    nombre_archivo = guardar_xml(xml_timbrado, "P")

    log_timbrado_exitoso(nombre_archivo)
    return xml_timbrado


# FUNCIONES DE VALIDACIÓN
def detectar_datos_faltantes(xml_bytes):
    """Detecta si el XML tiene datos faltantes o plantillas"""
    try:
        xml_dom = parseString(xml_bytes)
        faltantes = []
        
        # Campos críticos que no pueden estar vacíos
        campos_criticos = [
            "RFC", "NOMBRE", "CODIGOPOSTAL", "DOMICILIOFISCALRECEPTOR",
            "REGIMENFISCAL", "REGIMENFISCALRECEPTOR", "USOCFDI", "UUID"
        ]
        
        # Buscar todos los elementos y atributos
        todos_elementos = xml_dom.getElementsByTagName("*")
        
        for elemento in todos_elementos:
            for i in range(elemento.attributes.length):
                atributo = elemento.attributes.item(i)
                valor = atributo.value
                atributo_upper = atributo.name.upper()
                
                # Detectar plantillas {{}} O campos críticos vacíos
                es_plantilla = "{{" in valor and "}}" in valor
                es_campo_critico_vacio = (valor.strip() == "" and atributo_upper in campos_criticos)
                
                if es_plantilla or es_campo_critico_vacio:
                    faltantes.append({
                        'elemento': elemento.tagName,
                        'atributo': atributo.name,
                        'valor_actual': valor,
                        'tipo': 'plantilla' if es_plantilla else 'campo_vacio'
                    })
        
        if faltantes:
            for f in faltantes[:3]:  # Solo mostrar primeros 3
                tipo_msg = "plantilla" if f['tipo'] == 'plantilla' else "campo vacío"
                print(f"   • {f['elemento']}.{f['atributo']}: {tipo_msg}")
        
        return faltantes
        
    except Exception as e:
        print(f"ERROR en validación: {e}")
        return []

@app.route("/timbrar-complemento-pago2", methods=["POST"])
def timbrar_complemento_pago2():
    try:
        #Recibir
        xml_complemento = request.files.get("xml")
        #  Leer XMLs
        xml_cfdi_string = xml_complemento.read().decode("utf-8")
        forma_pago = request.form.get("forma_pago")

        # extraer valores del xml a un dict
        factura = parse_xml_complemento(xml_cfdi_string,forma_pago)
        llave_privada = cargar_llave_privada(RUTA_KEY, PASSWORD_KEY)

        # Cargar certificado y llave privada
        certificado_base64, no_certificado = cargar_certificado(RUTA_CER)

        xml_sin_sellar = crear_cfdi_complemento(factura, no_certificado, certificado_base64)

        xml_sellado = sellar_cfdi(xml_sin_sellar,llave_privada, RUTA_XSLT)

        #transformar xml en stringa bytes
        xml_bytes = xml_sellado.encode("utf-8")
        guardar_xml(xml_bytes, tipo_comprobante="anticipo")

        #timbrar con pac
        xml_timbrado = timbrar_con_pac(xml_bytes) #bytes solo  es cfdi - listo

        respuesta = generar_xml_timbrado(xml_timbrado)

        # print(respuesta["xml"]) importante para generar xml
        xml_base64 = base64.b64encode(respuesta["xml"].encode('utf-8')).decode('utf-8')

        # if tipo == "aplicacion":
        # Leer contenido como bytes
        # xml_anticipo_bytes = xml_anticipo.read()
        # xml_filemaker_bytes = xml_filemaker.read()
        
        xml_timbrado_str = respuesta["xml"]
        xml_timbrado_bytes = xml_timbrado_str.encode('utf-8')   


        # Generar respuesta dual (XML + PDF)
        respuesta = generar_respuesta_dual(xml_timbrado_bytes, "P")

        return jsonify({
            "success": True,
            "xml_timbrado": xml_base64,  #  está en base64 para la descarga
            "pdf": respuesta["pdf"],
            # "pdf_filename": f"CFDI_Aplicacion_Anticipo.pdf"
            "pdf_filename": respuesta["pdf_filename"]
        })

        # print(f"antes de bytes: {xml_sellado}")
        # print(f"desde complemento: {xml_timbrado}")
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ENDPOINTS ESPECÍFICOS
# @app.route("/timbrar-complemento-pago", methods=["POST"])
# def timbrar_complemento_pago():
#     try:
#         xml_file = request.files.get("xml")
#         if not xml_file:
#             return jsonify({"error": "No se recibió el archivo XML", "success": False})

#         xml_original = xml_file.read()
        
#         # VALIDAR DATOS FALTANTES
#         faltantes = detectar_datos_faltantes(xml_original)
#         if faltantes:
#             # Crear mensaje detallado de datos faltantes
#             mensaje_faltantes = "El XML tiene datos faltantes o incompletos:\n"
#             for faltante in faltantes[:5]:  # Mostrar máximo 5 para no saturar
#                 tipo_error = "plantilla sin completar" if faltante['tipo'] == 'plantilla' else "campo obligatorio vacío"
#                 mensaje_faltantes += f"- {faltante['elemento']}.{faltante['atributo']}: {tipo_error} ('{faltante['valor_actual']}')\n"
#             if len(faltantes) > 5:
#                 mensaje_faltantes += f"... y {len(faltantes) - 5} más."
            
#             return jsonify({
#                 "error": mensaje_faltantes,
#                 "success": False,
#                 "datos_faltantes": faltantes
#             })
        
#         # Obtener forma de pago del formulario
#         forma_pago = request.form.get("forma_pago", "99")  # Default: Por definir
        
#         xml_resultado = procesar_complemento_pago(xml_original, forma_pago)
        
#         # Generar respuesta dual (XML + PDF)
#         respuesta = generar_respuesta_dual(xml_resultado, "P")
        
#         return jsonify(respuesta)

#     except Exception as e:
#         log_error_with_traceback("Error en timbrado de complemento", e)
#         return jsonify({"error": str(e), "success": False})


# FUNCIONES DE VALIDACIÓN
def detectar_datos_faltantes(xml_bytes):
    """Detecta si el XML tiene datos faltantes o plantillas"""
    try:
        xml_dom = parseString(xml_bytes)
        faltantes = []
        
        # Campos críticos que no pueden estar vacíos
        campos_criticos = [
            "RFC", "NOMBRE", "CODIGOPOSTAL", "DOMICILIOFISCALRECEPTOR",
            "REGIMENFISCAL", "REGIMENFISCALRECEPTOR", "USOCFDI", "UUID"
        ]
        
        # Buscar todos los elementos y atributos
        todos_elementos = xml_dom.getElementsByTagName("*")
        
        for elemento in todos_elementos:
            for i in range(elemento.attributes.length):
                atributo = elemento.attributes.item(i)
                valor = atributo.value
                atributo_upper = atributo.name.upper()
                
                # Detectar plantillas {{}} O campos críticos vacíos
                es_plantilla = "{{" in valor and "}}" in valor
                es_campo_critico_vacio = (valor.strip() == "" and atributo_upper in campos_criticos)
                
                if es_plantilla or es_campo_critico_vacio:
                    faltantes.append({
                        'elemento': elemento.tagName,
                        'atributo': atributo.name,
                        'valor_actual': valor,
                        'tipo': 'plantilla' if es_plantilla else 'campo_vacio'
                    })
        
        if faltantes:
            for f in faltantes[:3]:  # Solo mostrar primeros 3
                tipo_msg = "plantilla" if f['tipo'] == 'plantilla' else "campo vacío"
                print(f"   • {f['elemento']}.{f['atributo']}: {tipo_msg}")
        
        return faltantes
        
    except Exception as e:
        print(f"ERROR en validación: {e}")
        return []


# Importar funciones de validación desde timbrar_cmd.py
# from timbrar_cmd import detectar_datos_faltantes  # Comentado para evitar error de import


@app.route("/timbrar-aplicacion-anticipo", methods=["POST"])
def timbrar_aplicacion_anticipo():
    try:
        #  Recibir archivos
        xml_anticipo = request.files.get("xml_archivo1")     # CFDI origen timbrado
        xml_filemaker = request.files.get("xml_archivo2")    # XML FileMaker

        if not xml_anticipo:
            return jsonify({"success": False, "error": "Falta el archivo CFDI origen"}), 400
        if not xml_filemaker:
            return jsonify({"success": False, "error": "Falta el archivo FileMaker"}), 400

        #  Leer XMLs
        xml_cfdi_string = xml_anticipo.read().decode("utf-8")
        xml_filemaker_string = xml_filemaker.read().decode("utf-8")

        #  Extraer UUID del CFDI origen
        uuid_origen = extraer_uuid_cfdi(xml_cfdi_string)
        if not uuid_origen:
            return jsonify({"success": False, "error": "No se encontró UUID en CFDI origen"}), 400
        
        #parsear XML FileMaker
        factura = parse_filemaker_xml(xml_filemaker_string)
        print(factura)

        contexto = {
            "uuid_origen": uuid_origen,
            "factura": factura
        }

        #  Crear CFDI 4.0
        xml_cfdi = crear_cfdi_desde_contexto(
            contexto=contexto,
            certificado_path=RUTA_CER,
            key_path=RUTA_KEY,
            password=PASSWORD_KEY,
            xslt_path=RUTA_XSLT
        )
        # print(xml_cfdi)

        #transformar xml en stringa bytes
        xml_bytes = xml_cfdi.encode("utf-8")
        guardar_xml(xml_bytes, tipo_comprobante="anticipo")

        #timbrar con pac
        xml_timbrado = timbrar_con_pac(xml_bytes) #bytes solo  es cfdi

        respuesta = generar_xml_timbrado(xml_timbrado)

        # print(respuesta["xml"]) importante para generar xml
        xml_base64 = base64.b64encode(respuesta["xml"].encode('utf-8')).decode('utf-8')

        # if tipo == "aplicacion":
        # Leer contenido como bytes
        xml_anticipo_bytes = xml_anticipo.read()
        xml_filemaker_bytes = xml_filemaker.read()
        
        xml_timbrado_str = respuesta["xml"]
        xml_timbrado_bytes = xml_timbrado_str.encode('utf-8')   

        pdf_bytes = generar_pdf_factura(
            xml_timbrado=xml_timbrado_bytes,
            tipo_comprobante="I",
            xml_anticipo=xml_filemaker_bytes
        )

        # Convertir PDF a base64
        guardar_pdf(pdf_bytes, tipo_comprobante="anticipo")
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        return jsonify({
            "success": True,
            "xml_timbrado": xml_base64,  #  está en base64 para la descarga
            "pdf": pdf_base64,
            "pdf_filename": f"CFDI_Aplicacion_Anticipo.pdf"
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True, ssl_context=context)