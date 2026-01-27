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

def extraer_moneda_filemaker(xml_filemaker: bytes) -> tuple:
    """
    Extrae moneda y tipo de cambio del archivo FileMaker
    Retorna: (moneda, tipo_cambio)
    """
    tree, row = parsear_filemaker_xml(xml_filemaker)
    if not row:
        return "MXN", "1"
    
    # log_debug("Parseando FileMaker para extraer moneda...")
    
    moneda = extraer_campo_filemaker(row, "Moneda_Simbolo") or "MXN"
    tipo_cambio = extraer_campo_filemaker(row, "TipoCambio") or "1"
    
    # if moneda != "MXN":
    #     log_debug(f"Moneda encontrada: {moneda}")
    # if tipo_cambio != "1":
    #     log_debug(f"Tipo cambio encontrado: {tipo_cambio}")
    
    # log_debug(f"FileMaker - Moneda: {moneda}, Tipo de cambio: {tipo_cambio}")
    return moneda, tipo_cambio

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

def obtener_comprobante(xmlDom):
    """Obtiene el nodo Comprobante del XML DOM"""
    comprobante = buscar_nodo_xml(xmlDom, "Comprobante", CFDI_NS)
    return comprobante if comprobante else xmlDom.documentElement

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
        
        if result.status != 200:
            mensaje = getattr(result, 'mensaje', 'Error desconocido en el timbrado')
            return None, mensaje
        
        # DEBUG: Verificar qué contiene result
        # print(f"DEBUG - Atributos de result: {dir(result)}")
        # print(f"DEBUG - Tiene resultados: {hasattr(result, 'resultados')}")
        
        # Verificar que resultados existe y tiene elementos
        if not hasattr(result, 'resultados') or not result.resultados or len(result.resultados) == 0:
            print("DEBUG - No hay resultados en la respuesta del PAC")
            return None, "No se recibieron resultados del PAC"
        
        primer_resultado = result.resultados[0]
        
        cfdi = primer_resultado.cfdiTimbrado
        # if cfdi:
        #     print(f"DEBUG - Tipo de cfdi: {type(cfdi)}")
        #     print(f"DEBUG - Longitud de cfdi: {len(cfdi) if hasattr(cfdi, '__len__') else 'N/A'}")
        
        # Verificar que cfdi no sea None
        if cfdi is None:
            if hasattr(primer_resultado, 'mensaje'):
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

def contar_conceptos_xml(xml_bytes: bytes) -> int:
    """
    Cuenta el número de conceptos en un XML
    """
    try:
        tree = etree.fromstring(xml_bytes)
        conceptos = 0
        
        for elem in tree.iter():
            if elem.tag.endswith("Concepto"):
                conceptos += 1
        
        return conceptos
        
    except Exception as e:
        print(f"Error contando conceptos: {e}")
        return 0

def extraer_uuid_de_xml(xml_bytes: bytes) -> str:
    """
    Extrae el UUID del TimbreFiscalDigital de un XML
    """
    try:
        tree = etree.fromstring(xml_bytes)
        
        # Buscar TimbreFiscalDigital
        for elem in tree.iter():
            if elem.tag.endswith("TimbreFiscalDigital"):
                uuid = elem.get("UUID")
                if uuid:
                    return uuid
        
        return ""
        
    except Exception as e:
        print(f"Error extrayendo UUID: {e}")
        return ""

def insertar_uuid_en_cfdi_relacionado(xml_bytes: bytes, uuid: str) -> bytes:
    """
    Inserta el UUID en el nodo CfdiRelacionado del XML de aplicación de anticipo
    """
    try:
        tree = etree.fromstring(xml_bytes)
        
        # Buscar el nodo CfdiRelacionado
        for elem in tree.iter():
            if elem.tag.endswith("CfdiRelacionado"):
                # Insertar el UUID
                elem.set("UUID", uuid)
                break
        
        # Convertir de vuelta a bytes
        return etree.tostring(tree, encoding='utf-8', xml_declaration=True)
        
    except Exception as e:
        print(f"Error insertando UUID en CfdiRelacionado: {e}")
        return xml_bytes

def agregar_cfdi_relacionados_pre_sellado(xml_bytes: bytes, uuid_relacionado: str) -> bytes:
    """Agrega CfdiRelacionados al XML ANTES del sellado"""
    try:
        dom = parseString(xml_bytes)
        comprobante = dom.documentElement
        
        # Verificar si ya existe CfdiRelacionados
        cfdi_relacionados_existente = None
        for child in comprobante.childNodes:
            if child.nodeType == child.ELEMENT_NODE and child.tagName.endswith("CfdiRelacionados"):
                cfdi_relacionados_existente = child
                break
        
        if cfdi_relacionados_existente is not None:
            for child in cfdi_relacionados_existente.childNodes:
                if child.nodeType == child.ELEMENT_NODE and child.tagName.endswith("CfdiRelacionado"):
                    child.setAttribute("UUID", uuid_relacionado)
                    break
        else:
            # Crear nuevo nodo CfdiRelacionados
            cfdi_relacionados = dom.createElementNS(CFDI_NS, "cfdi:CfdiRelacionados")
            cfdi_relacionados.setAttribute("TipoRelacion", "07")
            
            cfdi_relacionado = dom.createElementNS(CFDI_NS, "cfdi:CfdiRelacionado")
            cfdi_relacionado.setAttribute("UUID", uuid_relacionado)
            cfdi_relacionados.appendChild(cfdi_relacionado)
            
            # Insertar antes del Emisor
            emisor_node = None
            for child in comprobante.childNodes:
                if child.nodeType == child.ELEMENT_NODE and child.tagName.endswith("Emisor"):
                    emisor_node = child
                    break
            
            if emisor_node:
                comprobante.insertBefore(cfdi_relacionados, emisor_node)
            else:
                first_child = comprobante.firstChild
                if first_child:
                    comprobante.insertBefore(cfdi_relacionados, first_child)
                else:
                    comprobante.appendChild(cfdi_relacionados)
        
        xml_result = dom.toxml(encoding="UTF-8")
        return xml_result.encode('utf-8') if isinstance(xml_result, str) else xml_result
        
    except Exception as e:
        print(f"Error agregando CfdiRelacionados pre-sellado: {e}")
        return xml_bytes

def actualizar_receptor_con_filemaker(tree, xml_filemaker_bytes):
    """Actualiza los datos del receptor del XML con los datos del FileMaker"""
    try:
        # Extraer datos del receptor del FileMaker
        from PDF import extraer_datos_receptor_filemaker
        receptor_data = extraer_datos_receptor_filemaker(xml_filemaker_bytes)
        
        if not receptor_data:
            print("No se encontraron datos del receptor en FileMaker")
            return
        
        # Buscar el nodo Receptor en el XML
        receptor = None
        for elem in tree.iter():
            if elem.tag.endswith("Receptor"):
                receptor = elem
                break
        
        if receptor is None:
            print(" No se encontró nodo Receptor en el XML")
            return
        
        # Actualizar atributos del receptor con datos del FileMaker
        if "nombre" in receptor_data:
            receptor.set("Nombre", receptor_data["nombre"])
        
        if "rfc" in receptor_data:
            receptor.set("Rfc", receptor_data["rfc"])
        
        if "domicilio" in receptor_data:
            receptor.set("DomicilioFiscalReceptor", receptor_data["domicilio"])
        
        if "uso_cfdi" in receptor_data:
            receptor.set("UsoCFDI", receptor_data["uso_cfdi"])
        
        if "regimen" in receptor_data:
            receptor.set("RegimenFiscalReceptor", receptor_data["regimen"])
        
    except Exception as e:
        print(f"⚠ Error actualizando receptor con FileMaker: {e}")
        import traceback
        traceback.print_exc()

def reemplazar_conceptos_con_filemaker(tree, conceptos_filemaker):
    try:
        # Buscar nodo Conceptos
        conceptos_node = tree.find(f".//{{{CFDI_NS}}}Conceptos")
        if conceptos_node is None:
            comprobante = tree
            conceptos_node = etree.SubElement(comprobante, f"{{{CFDI_NS}}}Conceptos")
        
        # Limpiar todos los conceptos existentes
        conceptos_node.clear()

        subtotal_total = Decimal('0')
        iva_total = Decimal('0')
        
        total_conceptos = len(conceptos_filemaker)
        # Iterar sobre TODOS los conceptos de FileMaker
        for idx, concepto_fm in enumerate(conceptos_filemaker, 1):
            
            # Crear elemento Concepto
            concepto_elem = etree.SubElement(conceptos_node, f"{{{CFDI_NS}}}Concepto")
            
            # Establecer atributos básicos
            concepto_elem.set("ClaveProdServ", concepto_fm.clave_prod_serv)
            concepto_elem.set("Cantidad", str(concepto_fm.cantidad))
            concepto_elem.set("ClaveUnidad", concepto_fm.unidad)
            concepto_elem.set("Unidad", concepto_fm.unidad)
            concepto_elem.set("Descripcion", concepto_fm.descripcion)
            
            concepto_elem.set("ValorUnitario", f"{concepto_fm.valor_unitario:.2f}")
            concepto_elem.set("Importe", f"{concepto_fm.importe:.2f}")
            concepto_elem.set("ObjetoImp", "02")
            
            # Agregar descuento si existe
            if concepto_fm.descuento > 0:
                concepto_elem.set("Descuento", f"{concepto_fm.descuento:.2f}")
            
            # Crear nodo de impuestos del concepto
            impuestos_concepto = etree.SubElement(concepto_elem, f"{{{CFDI_NS}}}Impuestos")
            traslados = etree.SubElement(impuestos_concepto, f"{{{CFDI_NS}}}Traslados")
            traslado = etree.SubElement(traslados, f"{{{CFDI_NS}}}Traslado")
            
            # Calcular base gravable e IVA
            base_gravable = concepto_fm.importe - concepto_fm.descuento
            iva_importe = base_gravable * Decimal('0.16')
            
            traslado.set("Base", f"{base_gravable:.2f}")
            traslado.set("Impuesto", "002")
            traslado.set("TipoFactor", "Tasa")
            traslado.set("TasaOCuota", "0.160000")
            traslado.set("Importe", f"{iva_importe:.2f}")
            
            # Acumular totales
            subtotal_total += concepto_fm.importe
            iva_total += iva_importe
            
        # Actualizar totales en el comprobante
        tree.set("SubTotal", f"{subtotal_total:.2f}")
        total_final = subtotal_total + iva_total
        tree.set("Total", f"{total_final:.2f}")
        
        # Actualizar o crear nodo de impuestos del comprobante
        impuestos_comprobante = tree.find(f".//{{{CFDI_NS}}}Impuestos")
        if impuestos_comprobante is None:
            # Crear nodo de impuestos si no existe
            impuestos_comprobante = etree.Element(f"{{{CFDI_NS}}}Impuestos")
            # Insertarlo antes del complemento o al final
            complemento = tree.find(f".//{{{CFDI_NS}}}Complemento")
            if complemento is not None:
                comprobante = tree
                comprobante.insert(list(comprobante).index(complemento), impuestos_comprobante)
            else:
                tree.append(impuestos_comprobante)
        
        impuestos_comprobante.set("TotalImpuestosTrasladados", f"{iva_total:.2f}")
        
        # Actualizar o crear traslado del comprobante
        traslados_comp = impuestos_comprobante.find(f".//{{{CFDI_NS}}}Traslados")
        if traslados_comp is None:
            traslados_comp = etree.SubElement(impuestos_comprobante, f"{{{CFDI_NS}}}Traslados")
        
        traslado_comp = traslados_comp.find(f".//{{{CFDI_NS}}}Traslado")
        if traslado_comp is None:
            traslado_comp = etree.SubElement(traslados_comp, f"{{{CFDI_NS}}}Traslado")
        
        traslado_comp.set("Base", f"{subtotal_total:.2f}")
        traslado_comp.set("Impuesto", "002")
        traslado_comp.set("TipoFactor", "Tasa")
        traslado_comp.set("TasaOCuota", "0.160000")
        traslado_comp.set("Importe", f"{iva_total:.2f}")
        
    except Exception as e:
        print(f" ERROR reemplazando conceptos: {e}")
        import traceback
        traceback.print_exc()


def generar_respuesta_dual_anticipo(xml_timbrado, xml_original, xml_aplicacion):
    """
    Genera respuesta dual (XML + PDF) para anticipo con dos XMLs
    xml_timbrado: XML de aplicación timbrado (resultado final)
    xml_original: XML con datos adicionales (puede ser CFDI o FileMaker)
    xml_aplicacion: XML de aplicación modificado (con UUID relacionado)
    """
    try:
        # PASO 1: Guardar el XML timbrado localmente
        nombre_xml = guardar_xml(xml_timbrado, "I")
        
        # PASO 2: Intentar generar PDF con ambos XMLs
        pdf_bytes = None
        nombre_pdf = None
        error_pdf = None
        
        try:
            # La función PDF espera:
            # - xml_timbrado: XML principal timbrado (de aplicación)
            # - xml_anticipo: XML con datos adicionales (FileMaker o CFDI original)
            pdf_bytes = generar_pdf_factura(
                xml_timbrado=xml_timbrado,     # XML de aplicación timbrado (principal)
                tipo_comprobante="I",          # Tipo Ingreso
                xml_anticipo=xml_original      # XML con datos adicionales (FileMaker)
            )
            nombre_pdf = guardar_pdf(pdf_bytes, "I")
        except PDFGenerationError as e:
            error_pdf = str(e)
        except Exception as e:
            error_pdf = f"Error inesperado en PDF de anticipo: {str(e)}"
        
        # Preparar respuesta
        respuesta = {
            "xml": base64.b64encode(xml_timbrado).decode(),
            "xml_filename": nombre_xml,  # Agregar nombre del XML
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
            "error": f"Error procesando archivos de anticipo: {str(e)}",
            "success": False
        }

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

# Eliminar imports duplicados (ya están consolidados arriba)

def asegurar_namespaces_xml(xmlDom):
    """Asegura que todos los namespaces necesarios estén definidos en el XML"""
    comprobante = obtener_comprobante(xmlDom)
    
    # Asegurar namespace xsi
    if not comprobante.hasAttribute("xmlns:xsi"):
        comprobante.setAttribute("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    
    # Asegurar namespace cfdi
    if not comprobante.hasAttribute("xmlns:cfdi"):
        comprobante.setAttribute("xmlns:cfdi", CFDI_NS)
    
    # Asegurar schemaLocation básico
    if not comprobante.hasAttribute("xsi:schemaLocation"):
        comprobante.setAttribute("xsi:schemaLocation", 
                                "http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd")

# TRANSFORMACIONES ESPECÍFICAS - APLICACIÓN DE ANTICIPO
def transformar_a_aplicacion_anticipo(xmlDom, moneda="MXN", tipo_cambio="1", conceptos_ya_reemplazados=False):
    """Transforma XML para Aplicación de Anticipo (tipo I con descuento)"""
    
    # PRIMERO: Asegurar que todos los namespaces estén definidos
    asegurar_namespaces_xml(xmlDom)
    
    # Buscar el nodo Comprobante
    comprobante = obtener_comprobante(xmlDom)
    tipoActual = comprobante.getAttribute("TipoDeComprobante")

    # Transformando a Aplicación de Anticipo
    
    subTotalCalculado = 0
    
    # Si es Complemento de Pago (tipo P), extraer del nodo Pagos o conceptos
    if tipoActual == "P":
        pagos = buscar_nodo_seguro(xmlDom, "Pagos", PAGO_NS)
        if pagos:
            totales = buscar_nodo_seguro(pagos, "Totales", PAGO_NS)
            if totales:
                # Usar la base gravable del IVA como SubTotal
                baseIVA = totales.getAttribute("TotalTrasladosBaseIVA16")
                if baseIVA:
                    subTotalCalculado = float(baseIVA)
                else:
                    # Si no hay base IVA, usar el monto total
                    montoTotal = totales.getAttribute("MontoTotalPagos")
                    if montoTotal:
                        subTotalCalculado = float(montoTotal)
        else:
            # Si no hay nodo Pagos, extraer de conceptos 
            conceptos = xmlDom.getElementsByTagName("cfdi:Conceptos")[0] if xmlDom.getElementsByTagName("cfdi:Conceptos") else None
            if conceptos:
                conceptosArray = conceptos.getElementsByTagNameNS(CFDI_NS, "Concepto")
                if conceptosArray.length == 0:
                    conceptosArray = conceptos.getElementsByTagName("cfdi:Concepto")
                
                for i in range(conceptosArray.length):
                    concepto = conceptosArray[i]
                    importe = float(concepto.getAttribute("Importe") or "0")
                    subTotalCalculado += importe
    else:
        # Para otros tipos, calcular de los conceptos
        conceptos = xmlDom.getElementsByTagName("cfdi:Conceptos")[0] if xmlDom.getElementsByTagName("cfdi:Conceptos") else None
        if conceptos:
            conceptosArray = conceptos.getElementsByTagNameNS(CFDI_NS, "Concepto")
            if conceptosArray.length == 0:
                conceptosArray = conceptos.getElementsByTagName("cfdi:Concepto")
            
            for i in range(conceptosArray.length):
                concepto = conceptosArray[i]
                importe = float(concepto.getAttribute("Importe") or "0")
                subTotalCalculado += importe
    
    # Si no se pudo extraer ningún valor, usar 0
    
    # 2. AHORA cambiar tipo a "I" (Ingreso) después de extraer los datos
    if tipoActual != "I":
        comprobante.setAttribute("TipoDeComprobante", "I")
    
    # 3. Definir monto del anticipo 
    montoAnticipo = 0.00  # Sin descuento para aplicación de anticipo
    
    # 4. Calcular el Total correcto basado en los conceptos originales
    # El Total debe ser SubTotal de conceptos + Impuestos originales
    impuestosOriginales = 0
    impuestosComprobante = xmlDom.getElementsByTagName("cfdi:Impuestos")
    for i in range(impuestosComprobante.length):
        nodo = impuestosComprobante[i]
        if nodo.parentNode.tagName == "cfdi:Comprobante":
            totalImpuestos = nodo.getAttribute("TotalImpuestosTrasladados")
            if totalImpuestos:
                impuestosOriginales = float(totalImpuestos)
            break
    
    # El Total correcto es SubTotal de conceptos + Impuestos
    montoAnticipoRecibido = subTotalCalculado + impuestosOriginales
    
    # Para aplicación de anticipo, mantenemos el mismo SubTotal y Total
    # No necesitamos recalcular, solo asegurar consistencia
    
    # 5. Establecer valores básicos en el comprobante
    # Para aplicación de anticipo, el SubTotal debe ser la suma de TODOS los conceptos
    comprobante.setAttribute("SubTotal", f"{subTotalCalculado:.2f}")
    comprobante.setAttribute("Descuento", f"{montoAnticipo:.2f}")
    
    # 2.1. Establecer Moneda y TipoCambio desde FileMaker
    # log_debug(f"Estableciendo Moneda={moneda}, TipoCambio={tipo_cambio}")
    comprobante.setAttribute("Moneda", moneda)
    if tipo_cambio != "1":  # Solo establecer TipoCambio si no es 1
        comprobante.setAttribute("TipoCambio", tipo_cambio)
    else:
        log_debug("TipoCambio es 1, no se establece atributo")
    
    # 2.2. Establecer Exportacion (obligatorio en CFDI 4.0)
    if not comprobante.getAttribute("Exportacion"):
        comprobante.setAttribute("Exportacion", "01")
    
    # 3.  IMPORTANTE: Establecer MetodoPago y FormaPago (ambos obligatorios para Ingreso)
    if not comprobante.getAttribute("MetodoPago"):
        comprobante.setAttribute("MetodoPago", "PUE")
    if not comprobante.getAttribute("FormaPago"):
        comprobante.setAttribute("FormaPago", "03")
    
    # 4. Remover namespace pago20
    if comprobante.hasAttribute("xmlns:pago20"):
        comprobante.removeAttribute("xmlns:pago20")
    
    # 5. Limpiar schemaLocation de referencias a Pagos20
    schema = comprobante.getAttribute("xsi:schemaLocation") or ""
    schema = schema.replace("http://www.sat.gob.mx/Pagos20 http://www.sat.gob.mx/sitio_internet/cfd/Pagos/Pagos20.xsd", "")
    # Asegurar que el schemaLocation básico esté presente
    if "http://www.sat.gob.mx/cfd/4" not in schema:
        schema = "http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd " + schema
    comprobante.setAttribute("xsi:schemaLocation", schema.strip())
    
    # 6. Remover nodo Complemento con Pagos y TimbreFiscalDigital (si existe)
    complemento = xmlDom.getElementsByTagName("cfdi:Complemento")[0] if xmlDom.getElementsByTagName("cfdi:Complemento") else None
    if complemento:
        # Remover Pagos si existe
        pagos = buscar_nodo_seguro(complemento, "Pagos", PAGO_NS)
        if pagos:
            remover_nodo_seguro(complemento, pagos, "Nodo Pagos")
        
        # Remover TimbreFiscalDigital si existe (para re-timbrar)
        tfd = buscar_nodo_seguro(complemento, "TimbreFiscalDigital", TFD_NS)
        if not tfd:
            # Buscar también con prefijo tfd:
            tfd = buscar_nodo_seguro(complemento, "tfd:TimbreFiscalDigital")
        if tfd:
            remover_nodo_seguro(complemento, tfd, "TimbreFiscalDigital")
        
        # Si el complemento quedó vacío, removerlo
        if complemento.childNodes.length == 0:
            remover_nodo_seguro(complemento.parentNode, complemento, "Complemento vacío")
    
    # 7. Actualizar o crear nodo Conceptos
    conceptos = xmlDom.getElementsByTagName("cfdi:Conceptos")[0] if xmlDom.getElementsByTagName("cfdi:Conceptos") else None
    if not conceptos:
        # Crear Conceptos si no existe
        conceptos = xmlDom.createElementNS(CFDI_NS, "cfdi:Conceptos")
        
        # Crear un concepto para Aplicación de Anticipo
        concepto = xmlDom.createElementNS(CFDI_NS, "cfdi:Concepto")
        concepto.setAttribute("ClaveProdServ", "84111506")  # Clave para anticipo
        concepto.setAttribute("Cantidad", "1")
        concepto.setAttribute("ClaveUnidad", "ACT")
        concepto.setAttribute("Unidad", "ACT")
        concepto.setAttribute("Descripcion", "Anticipo del bien o servicio")
        concepto.setAttribute("ValorUnitario", f"{subTotalCalculado:.2f}")
        concepto.setAttribute("Importe", f"{subTotalCalculado:.2f}")
        concepto.setAttribute("Descuento", f"{montoAnticipo:.2f}")
        concepto.setAttribute("ObjetoImp", "02")  # Sí objeto de impuestos
        
        # Crear nodo de impuestos para el concepto
        impuestosConcepto = xmlDom.createElementNS(CFDI_NS, "cfdi:Impuestos")
        traslados = xmlDom.createElementNS(CFDI_NS, "cfdi:Traslados")
        traslado = xmlDom.createElementNS(CFDI_NS, "cfdi:Traslado")
        
        # Calcular IVA 16%
        impuestoCalculado = subTotalCalculado * 0.16
        impuestoCalculado = round(impuestoCalculado, 2)
        
        traslado.setAttribute("Base", f"{subTotalCalculado:.2f}")
        traslado.setAttribute("Impuesto", "002")  # IVA
        traslado.setAttribute("TipoFactor", "Tasa")
        traslado.setAttribute("TasaOCuota", "0.16")
        traslado.setAttribute("Importe", f"{impuestoCalculado:.2f}")
        
        traslados.appendChild(traslado)
        impuestosConcepto.appendChild(traslados)
        concepto.appendChild(impuestosConcepto)
        
        conceptos.appendChild(concepto)
        
        # Insertar Conceptos antes del Complemento (si existe) o al final
        complementoExistente = xmlDom.getElementsByTagName("cfdi:Complemento")[0] if xmlDom.getElementsByTagName("cfdi:Complemento") else None
        if complementoExistente:
            comprobante.insertBefore(conceptos, complementoExistente)
        else:
            comprobante.appendChild(conceptos)
    else:
        # Si los conceptos ya existen
        conceptosArray = conceptos.getElementsByTagNameNS(CFDI_NS, "Concepto")
        if conceptosArray.length == 0:
            conceptosArray = conceptos.getElementsByTagName("cfdi:Concepto")
        
        
        # CORRECCIÓN: Si los conceptos ya fueron reemplazados con datos de FileMaker, NO modificar las descripciones
        if conceptos_ya_reemplazados:
            
            # Solo asegurar que todos los conceptos tengan ObjetoImp correcto
            for i in range(conceptosArray.length):
                concepto = conceptosArray[i]
                concepto.setAttribute("ObjetoImp", "02")  # 02 para SÍ objeto de impuestos
                
        else:
            # Si hay conceptos pero NO vienen de FileMaker, aplicar la lógica anterior
            if conceptosArray.length > 0:
                primerConcepto = conceptosArray[0]
                importeOriginal = float(primerConcepto.getAttribute("Importe") or "0")
                
                # NO cambiar el importe del concepto, solo ajustar otros atributos
                primerConcepto.setAttribute("ObjetoImp", "02")  # 02 para SÍ objeto de impuestos
                
                # Solo cambiar descripción si es necesario para anticipo
                descripcionActual = primerConcepto.getAttribute("Descripcion") or ""
                if "anticipo" not in descripcionActual.lower():
                    primerConcepto.setAttribute("Descripcion", "Anticipo del bien o servicio")
                
                
                # MANTENER impuestos del concepto existentes
                impuestosConcepto = primerConcepto.getElementsByTagName("cfdi:Impuestos")[0] if primerConcepto.getElementsByTagName("cfdi:Impuestos") else None
                if impuestosConcepto:
                    print(" Impuestos mantenidos en el concepto")
                else:
                    print(" ADVERTENCIA: No se encontraron impuestos en el concepto")
                
                # IMPORTANTE: Agregar el descuento a nivel de concepto
                primerConcepto.setAttribute("Descuento", f"{montoAnticipo:.2f}")
    
    # 8. AHORA calcular el Total final con los impuestos que quedaron
    impuestosTotal = 0
    
    # Buscar nodo de impuestos a nivel comprobante (no dentro de conceptos)
    impuestosComprobante = xmlDom.getElementsByTagName("cfdi:Impuestos")
    
    # Filtrar para obtener solo el nodo de impuestos del comprobante (no de conceptos)
    impuestosNode = None
    for i in range(impuestosComprobante.length):
        nodo = impuestosComprobante[i]
        # El nodo de impuestos del comprobante es hijo directo del comprobante
        if nodo.parentNode.tagName == "cfdi:Comprobante":
            impuestosNode = nodo
            break
    
    if impuestosNode:
        # Para aplicación de anticipo, RECALCULAR los impuestos sumando los de cada concepto
        # para evitar problemas de redondeo
        impuestosTotal = 0
        conceptosArray = xmlDom.getElementsByTagName("cfdi:Concepto")
        for i in range(conceptosArray.length):
            concepto = conceptosArray[i]
            impuestosConcepto = concepto.getElementsByTagName("cfdi:Impuestos")
            if impuestosConcepto.length > 0:
                traslados = impuestosConcepto[0].getElementsByTagName("cfdi:Traslado")
                for j in range(traslados.length):
                    traslado = traslados[j]
                    importeTraslado = float(traslado.getAttribute("Importe") or "0")
                    impuestosTotal += importeTraslado
        
        # Redondear el total de impuestos
        impuestosTotal = round(impuestosTotal, 2)
        
        # Actualizar el nodo de impuestos del comprobante con el total correcto
        impuestosNode.setAttribute("TotalImpuestosTrasladados", f"{impuestosTotal:.2f}")
        
        # Actualizar el traslado del comprobante
        trasladosComprobante = impuestosNode.getElementsByTagName("cfdi:Traslado")
        if trasladosComprobante.length > 0:
            trasladosComprobante[0].setAttribute("Importe", f"{impuestosTotal:.2f}")
            trasladosComprobante[0].setAttribute("Base", f"{subTotalCalculado:.2f}")
        
    else:
        # Si no hay impuestos, crear el nodo de impuestos para aplicación de anticipo
        impuestosNode = xmlDom.createElementNS(CFDI_NS, "cfdi:Impuestos")
        traslados = xmlDom.createElementNS(CFDI_NS, "cfdi:Traslados")
        traslado = xmlDom.createElementNS(CFDI_NS, "cfdi:Traslado")
        
        # Calcular IVA 16%
        impuestosTotal = subTotalCalculado * 0.16
        impuestosTotal = round(impuestosTotal, 2)
        
        traslado.setAttribute("Base", f"{subTotalCalculado:.2f}")
        traslado.setAttribute("Impuesto", "002")  # IVA
        traslado.setAttribute("TipoFactor", "Tasa")
        traslado.setAttribute("TasaOCuota", "0.16")
        traslado.setAttribute("Importe", f"{impuestosTotal:.2f}")
        
        traslados.appendChild(traslado)
        impuestosNode.appendChild(traslados)
        impuestosNode.setAttribute("TotalImpuestosTrasladados", f"{impuestosTotal:.2f}")
        
        # Insertar antes del Complemento o al final
        complementoExistente = xmlDom.getElementsByTagName("cfdi:Complemento")[0] if xmlDom.getElementsByTagName("cfdi:Complemento") else None
        if complementoExistente:
            comprobante.insertBefore(impuestosNode, complementoExistente)
        else:
            comprobante.appendChild(impuestosNode)
        
    
    # 9. Calcular Total final (SubTotal - Descuento + Impuestos)
    # Para aplicación de anticipo, el Total debe ser igual al monto del anticipo recibido
    totalCalculado = subTotalCalculado - montoAnticipo + impuestosTotal
    comprobante.setAttribute("Total", f"{totalCalculado:.2f}")
    
    # print(f"✓ Total final calculado: {subTotalCalculado:.2f} - {montoAnticipo:.2f} + {impuestosTotal:.2f} = {totalCalculado:.2f}")
    
    # Verificar que el Total coincida con el anticipo recibido
    if abs(totalCalculado - montoAnticipoRecibido) > 0.01:
        print(f"⚠ ADVERTENCIA: Total calculado ({totalCalculado:.2f}) no coincide con anticipo recibido ({montoAnticipoRecibido:.2f})")
    
    # 10. Solo remover impuestos si el Total es 0 Y no hay impuestos trasladados
    if totalCalculado == 0 and impuestosTotal == 0:
        impuestosComprobanteNode = xmlDom.getElementsByTagName("cfdi:Impuestos")
        if impuestosComprobanteNode.length > 0:
            nodoImpuestos = impuestosComprobanteNode[0]
            remover_nodo_seguro(comprobante, nodoImpuestos, "Nodo Impuestos del Comprobante (Total = 0 sin impuestos)")
    

def extraer_valores_documento_original(xml_bytes):
    """
    Extrae Total, IVA y otros valores del documento original para el complemento de pago
    Retorna: dict con valores necesarios para el complemento
    """
    try:
        tree = etree.fromstring(xml_bytes)
        
        # Extraer Total del documento
        total = tree.get("Total", "0.00")
        
        # Verificar si tiene impuestos trasladados
        tiene_impuestos = False
        impuestos_node = tree.find(f".//{{{CFDI_NS}}}Impuestos")
        if impuestos_node is not None:
            total_impuestos = impuestos_node.get("TotalImpuestosTrasladados")
            if total_impuestos and float(total_impuestos) > 0:
                tiene_impuestos = True
        
        # log_debug(f"Valores extraídos del documento original: Total={total}, Tiene impuestos={tiene_impuestos}")
        
        return {
            'monto_total': total,
            'saldo_anterior': total,  # En un pago total, el saldo anterior es igual al total
            'importe_pagado': total,  # Se está pagando el total
            'saldo_insoluto': '0.00',  # Después del pago, el saldo es 0
            'tiene_impuestos': tiene_impuestos
        }
        
    except Exception as e:
        return {
            'monto_total': '1000.00',
            'saldo_anterior': '1000.00',
            'importe_pagado': '1000.00',
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
    
    # 6. NUEVO: Usar valores extraídos del documento original
    if valores_pago is None:
        # Valores por defecto si no se proporcionan
        valores_pago = {
            'monto_total': '1000.00',
            'saldo_anterior': '1000.00',
            'importe_pagado': '1000.00',
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
    
    # Crear nodo Totales con el monto correcto
    totales = xmlDom.createElementNS(PAGO_NS, "pago20:Totales")
    totales.setAttribute("MontoTotalPagos", valores_pago['monto_total'])
    
    # NUEVO: Agregar totales de impuestos si el documento original tiene impuestos
    if valores_pago['tiene_impuestos']:
        # Calcular base IVA 16% (monto / 1.16)
        monto_float = float(valores_pago['monto_total'])
        base_iva_16 = monto_float / 1.16
        total_iva_16 = monto_float - base_iva_16
        
        totales.setAttribute("TotalTrasladosBaseIVA16", f"{base_iva_16:.2f}")
        totales.setAttribute("TotalTrasladosImpuestoIVA16", f"{total_iva_16:.2f}")
    
    pagos.appendChild(totales)
    
    # Crear nodo Pago con los valores correctos
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
        
        monto_float = float(valores_pago['monto_total'])
        base_iva_16 = monto_float / 1.16
        total_iva_16 = monto_float - base_iva_16
        
        traslado_p.setAttribute("BaseP", f"{base_iva_16:.2f}")
        traslado_p.setAttribute("ImpuestoP", "002")
        traslado_p.setAttribute("TipoFactorP", "Tasa")
        traslado_p.setAttribute("TasaOCuotaP", "0.160000")
        traslado_p.setAttribute("ImporteP", f"{total_iva_16:.2f}")
        
        traslados_p.appendChild(traslado_p)
        impuestos_pago.appendChild(traslados_p)
        pago.appendChild(impuestos_pago)
    
    # Crear nodo DoctoRelacionado con valores correctos y serie/folio originales
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
        
        monto_float = float(valores_pago['monto_total'])
        base_iva_16 = monto_float / 1.16
        total_iva_16 = monto_float - base_iva_16
        
        traslado_dr.setAttribute("BaseDR", f"{base_iva_16:.2f}")
        traslado_dr.setAttribute("ImpuestoDR", "002")
        traslado_dr.setAttribute("TipoFactorDR", "Tasa")
        traslado_dr.setAttribute("TasaOCuotaDR", "0.160000")
        traslado_dr.setAttribute("ImporteDR", f"{total_iva_16:.2f}")
        
        traslados_dr.appendChild(traslado_dr)
        impuestos_dr.appendChild(traslados_dr)
        doctoRelacionado.appendChild(impuestos_dr)
    
    pago.appendChild(doctoRelacionado)
    
    pagos.appendChild(pago)
    complemento.appendChild(pagos)

# PROCESADORES PRINCIPALES
def procesar_aplicacion_anticipo(xml_original, forma_pago="99", metodo_pago="PPD", uuid_relacionado=None, conceptos_filemaker=None, moneda_filemaker="MXN", tipo_cambio_filemaker="1", xml_filemaker_bytes=None):
    """Función principal para procesar aplicación de anticipo"""
    
    # Preparar XML base
    tree = preparar_xml_base(xml_original)
    
    # Agregar forma de pago y método de pago al XML (para aplicación de anticipo, tipo I)
    agregar_forma_pago_xml(tree, forma_pago, "I", metodo_pago, moneda_filemaker, tipo_cambio_filemaker)
    
    # NUEVO: Si hay conceptos de FileMaker, reemplazar los conceptos del XML
    conceptos_ya_reemplazados = False
    if conceptos_filemaker:
        reemplazar_conceptos_con_filemaker(tree, conceptos_filemaker)
        conceptos_ya_reemplazados = True  # Marcar que los conceptos ya fueron reemplazados
    
    # NUEVO: Si hay XML de FileMaker, actualizar datos del receptor
    if xml_filemaker_bytes:
        actualizar_receptor_con_filemaker(tree, xml_filemaker_bytes)
        # Extraer y aplicar folio/serie de FileMaker
        serie_fm, folio_fm = extraer_folio_serie_filemaker(xml_filemaker_bytes)
        aplicar_folio_serie_xml(tree, serie_fm, folio_fm)
    
    # Validar estructura de Ingreso/Egreso
    tipo_comprobante = tree.attrib.get("TipoDeComprobante", "")
    if tipo_comprobante in ["I", "E"]:
        conceptos = tree.find(f".//{{{CFDI_NS}}}Conceptos")
        if conceptos is None:
            raise Exception("Falta el nodo Conceptos en el comprobante de Ingreso/Egreso")

    # Convertir a DOM para transformación, preservando namespaces
    xml_string = etree.tostring(tree, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    
    # IMPORTANTE: Asegurar que el XML tenga los namespaces correctos antes de parsearlo
    xml_string_str = xml_string.decode('utf-8')
    
    # Verificar y agregar namespace xsi si no existe
    if 'xmlns:xsi=' not in xml_string_str:
        xml_string_str = xml_string_str.replace(
            'xmlns:cfdi="http://www.sat.gob.mx/cfd/4"',
            'xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        )
    
    # Verificar schemaLocation
    if 'xsi:schemaLocation=' not in xml_string_str:
        xml_string_str = xml_string_str.replace(
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd"'
        )
    
    xml_string = xml_string_str.encode('utf-8')
    dom = parseString(xml_string)
    
    # Aplicar transformación
    try:
        transformar_a_aplicacion_anticipo(dom, moneda_filemaker, tipo_cambio_filemaker, conceptos_ya_reemplazados)
    except Exception as e:
        print(f"Error en transformación: {str(e)}")
        raise

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
    
    # Agregar CfdiRelacionados ANTES del sellado
    if uuid_relacionado:
        xml_transformado = agregar_cfdi_relacionados_pre_sellado(xml_transformado, uuid_relacionado)
    
    # Generar sello
    xml_sellado = generar_sello(xml_transformado, RUTA_CER, RUTA_KEY, PASSWORD_KEY)

    
    log_xml_sellado()

    # Intentar timbrar
    xml_timbrado, msg = timbrar_con_sf(xml_sellado)
    
    if xml_timbrado:
        print(f"  Longitud: {len(xml_timbrado)}")
    print(f"  Mensaje: {msg}")

    # Si el timbrado no devuelve XML válido, retornar el XML sellado
    if xml_timbrado is None or not xml_timbrado.strip().startswith(b"<"):
        return xml_sellado
    
    # ⭐⭐⭐ TAMBIÉN AGREGAR ESTA LÍNEA AQUÍ ⭐⭐⭐
    xml_timbrado = corregir_encoding_xml(xml_timbrado)

    log_timbrado_exitoso("XML timbrado correctamente")
    return xml_timbrado
    

def corregir_encoding_xml(xml_bytes):
    """
    Corrige caracteres mal codificados en el XML final
    """
    try:
        # Convertir a string
        if isinstance(xml_bytes, bytes):
            xml_str = xml_bytes.decode('utf-8')
        else:
            xml_str = xml_bytes
        
        # Reemplazar caracteres mal codificados
        # IMPORTANTE: Usar lista de tuplas, no diccionario
        # El orden importa - los patrones más largos primero
        reemplazos = [
            ('Ã³', 'ó'),
            ('Ã±', 'ñ'),
            ('Ã­', 'í'),
            ('Ã¡', 'á'),
            ('Ã©', 'é'),
            ('Ãº', 'ú'),
            ('Ã¼', 'ü'),
            ('Ã', 'Ñ'),
            ('Ã‰', 'É'),
            ('Ã"', 'Ó'),
            ('Ãš', 'Ú'),
            ('Ã‡', 'Ç'),
            ('Ã', 'Á'),
            ('Ã', 'Í'),
        ]
        
        for malo, bueno in reemplazos:
            xml_str = xml_str.replace(malo, bueno)
        
        # Convertir de vuelta a bytes
        return xml_str.encode('utf-8')
        
    except Exception as e:
        print(f"⚠ Error corrigiendo encoding: {e}")
        return xml_bytes


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

# ENDPOINT PRINCIPAL
@app.route("/timbrar", methods=["POST"])
def timbrar():
    try:
        # Obtener tipo de transformación del formulario
        tipo_transformacion = request.form.get("tipo", "")
        
        xml_file = request.files.get("xml")
        if not xml_file:
            return Response("<error>No se recibió el archivo XML</error>", mimetype="application/xml")

        xml_original = xml_file.read()
        
        # Procesar según el tipo seleccionado
        if tipo_transformacion == "complemento":
            xml_resultado = procesar_complemento_pago(xml_original)
        elif tipo_transformacion == "anticipo":
            xml_resultado = procesar_aplicacion_anticipo(xml_original)
        else:
            return Response("<error>Tipo de transformación no especificado. Usa 'complemento' o 'anticipo'</error>", mimetype="application/xml")
        
        return Response(xml_resultado, mimetype="application/xml")

    except Exception as e:
        return Response(f"<error>{str(e)}</error>", mimetype="application/xml")

# ENDPOINTS ESPECÍFICOS
@app.route("/timbrar-complemento-pago", methods=["POST"])
def timbrar_complemento_pago():
    try:
        xml_file = request.files.get("xml")
        if not xml_file:
            return jsonify({"error": "No se recibió el archivo XML", "success": False})

        xml_original = xml_file.read()
        
        # VALIDAR DATOS FALTANTES
        faltantes = detectar_datos_faltantes(xml_original)
        if faltantes:
            # Crear mensaje detallado de datos faltantes
            mensaje_faltantes = "El XML tiene datos faltantes o incompletos:\n"
            for faltante in faltantes[:5]:  # Mostrar máximo 5 para no saturar
                tipo_error = "plantilla sin completar" if faltante['tipo'] == 'plantilla' else "campo obligatorio vacío"
                mensaje_faltantes += f"- {faltante['elemento']}.{faltante['atributo']}: {tipo_error} ('{faltante['valor_actual']}')\n"
            if len(faltantes) > 5:
                mensaje_faltantes += f"... y {len(faltantes) - 5} más."
            
            return jsonify({
                "error": mensaje_faltantes,
                "success": False,
                "datos_faltantes": faltantes
            })
        
        # Obtener forma de pago del formulario
        forma_pago = request.form.get("forma_pago", "99")  # Default: Por definir
        
        xml_resultado = procesar_complemento_pago(xml_original, forma_pago)
        
        # Generar respuesta dual (XML + PDF)
        respuesta = generar_respuesta_dual(xml_resultado, "P")
        
        return jsonify(respuesta)

    except Exception as e:
        log_error_with_traceback("Error en timbrado de complemento", e)
        return jsonify({"error": str(e), "success": False})

@app.route("/timbrar-aplicacion-anticipo", methods=["POST"])
def timbrar_aplicacion_anticipo():
    try:
        # Verificar si se enviaron dos XMLs (nuevo formato)
        xml_archivo1 = request.files.get("xml_archivo1")  # Primer archivo subido
        xml_archivo2 = request.files.get("xml_archivo2")  # Segundo archivo subido
        
        # VALIDAR DATOS FALTANTES en ambos XMLs si existen
        if xml_archivo1:
            xml1_bytes = xml_archivo1.read()
            xml_archivo1.seek(0)  # Resetear para uso posterior
            faltantes1 = detectar_datos_faltantes(xml1_bytes)
            if faltantes1:
                mensaje_faltantes = f"El primer XML tiene datos faltantes:\n"
                for faltante in faltantes1[:3]:
                    mensaje_faltantes += f"- {faltante['elemento']}.{faltante['atributo']}: {faltante['valor_actual']}\n"
                return jsonify({
                    "error": mensaje_faltantes,
                    "success": False,
                    "datos_faltantes": faltantes1
                })
        
        if xml_archivo2:
            xml2_bytes = xml_archivo2.read()
            xml_archivo2.seek(0)  # Resetear para uso posterior
            faltantes2 = detectar_datos_faltantes(xml2_bytes)
            if faltantes2:
                mensaje_faltantes = f"El segundo XML tiene datos faltantes:\n"
                for faltante in faltantes2[:3]:
                    mensaje_faltantes += f"- {faltante['elemento']}.{faltante['atributo']}: {faltante['valor_actual']}\n"
                return jsonify({
                    "error": mensaje_faltantes,
                    "success": False,
                    "datos_faltantes": faltantes2
                })
        
        if xml_archivo1 and xml_archivo2:
            # Nuevo formato: dos XMLs - detectar automáticamente cuál es cuál
            xml_archivo1_bytes = xml_archivo1.read()
            xml_archivo2_bytes = xml_archivo2.read()
            
            # PASO 1: Detectar cuál XML es CFDI válido y cuál es FileMaker
            def es_cfdi_valido(xml_bytes):
                try:
                    tree = etree.fromstring(xml_bytes)
                    # Verificar si es un CFDI (tiene nodo Comprobante)
                    return tree.tag.endswith("Comprobante") or "Comprobante" in tree.tag
                except:
                    return False
            
            def es_archivo_filemaker(xml_bytes):
                try:
                    tree = etree.fromstring(xml_bytes)
                    # Verificar si es un archivo de FileMaker
                    return "FMPDSORESULT" in tree.tag or "FMPXMLRESULT" in tree.tag
                except:
                    return False
            
            # Detectar tipos de archivo
            archivo1_es_cfdi = es_cfdi_valido(xml_archivo1_bytes)
            archivo2_es_cfdi = es_cfdi_valido(xml_archivo2_bytes)
            archivo1_es_filemaker = es_archivo_filemaker(xml_archivo1_bytes)
            archivo2_es_filemaker = es_archivo_filemaker(xml_archivo2_bytes)
            
            # Determinar cuál XML usar para cada propósito
            xml_cfdi_timbrado = None
            xml_para_aplicacion = None
            uuid_extraido = None
            
            if archivo1_es_cfdi and not archivo2_es_cfdi:
                # Archivo 1 es CFDI, archivo 2 no es CFDI válido
                xml_cfdi_timbrado = xml_archivo1_bytes
                xml_para_aplicacion = xml_archivo1_bytes  # Usar el mismo CFDI como base
                uuid_extraido = extraer_uuid_de_xml(xml_archivo1_bytes)
            elif archivo2_es_cfdi and not archivo1_es_cfdi:
                # Archivo 2 es CFDI, archivo 1 no es CFDI válido
                xml_cfdi_timbrado = xml_archivo2_bytes
                xml_para_aplicacion = xml_archivo2_bytes  # Usar el mismo CFDI como base
                uuid_extraido = extraer_uuid_de_xml(xml_archivo2_bytes)
            elif archivo1_es_cfdi and archivo2_es_cfdi:
                # Ambos son CFDI - usar el que tiene UUID
                uuid_archivo1 = extraer_uuid_de_xml(xml_archivo1_bytes)
                uuid_archivo2 = extraer_uuid_de_xml(xml_archivo2_bytes)
                
                if uuid_archivo1 and not uuid_archivo2:
                    xml_cfdi_timbrado = xml_archivo1_bytes
                    xml_para_aplicacion = xml_archivo2_bytes
                    uuid_extraido = uuid_archivo1
                elif uuid_archivo2 and not uuid_archivo1:
                    xml_cfdi_timbrado = xml_archivo2_bytes
                    xml_para_aplicacion = xml_archivo1_bytes
                    uuid_extraido = uuid_archivo2
                else:
                    # Ambos tienen UUID o ninguno tiene - usar el primero como base
                    xml_cfdi_timbrado = xml_archivo1_bytes
                    xml_para_aplicacion = xml_archivo1_bytes
                    uuid_extraido = uuid_archivo1 if uuid_archivo1 else uuid_archivo2
            else:
                # Ninguno es CFDI válido
                return jsonify({"error": "Ninguno de los archivos es un CFDI válido. Se requiere al menos un XML de CFDI.", "success": False})
            
            if not uuid_extraido:
                return jsonify({"error": "No se encontró UUID en ninguno de los archivos CFDI. Se requiere un CFDI timbrado.", "success": False})
            
            
            # PASO 2: No crear CfdiRelacionados antes del timbrado (causa errores)
            # El UUID se agregará después del timbrado exitoso
            xml_aplicacion_modificado = xml_para_aplicacion
            
            
            # PASO 3: Determinar método y forma de pago para aplicación de anticipo
            metodo_pago = "PPD"  # Pago diferido
            forma_pago = "99"    # Por definir (obligatorio para PPD)
            
            
            # PASO 4: Extraer conceptos y moneda del FileMaker antes del procesamiento
            conceptos_filemaker = None
            moneda_filemaker = "MXN"
            tipo_cambio_filemaker = "1"
            
            if archivo1_es_filemaker:
                conceptos_filemaker = extraer_conceptos_filemaker(xml_archivo1_bytes)
                moneda_filemaker, tipo_cambio_filemaker = extraer_moneda_filemaker(xml_archivo1_bytes)
            elif archivo2_es_filemaker:
                conceptos_filemaker = extraer_conceptos_filemaker(xml_archivo2_bytes)
                moneda_filemaker, tipo_cambio_filemaker = extraer_moneda_filemaker(xml_archivo2_bytes)
            
            # PASO 5: Procesar y timbrar el XML de aplicación de anticipo
            xml_filemaker_bytes = xml_archivo1_bytes if archivo1_es_filemaker else xml_archivo2_bytes
            xml_resultado = procesar_aplicacion_anticipo(xml_aplicacion_modificado, forma_pago, metodo_pago, uuid_extraido, conceptos_filemaker, moneda_filemaker, tipo_cambio_filemaker, xml_filemaker_bytes)
            
            # PASO 6: Generar respuesta dual - usar el archivo FileMaker correcto
            xml_filemaker = xml_archivo1_bytes if archivo1_es_filemaker else xml_archivo2_bytes
            respuesta = generar_respuesta_dual_anticipo(xml_resultado, xml_filemaker, xml_aplicacion_modificado)
            
            return jsonify(respuesta)
            
        else:
            # Formato anterior: un solo XML (mantener compatibilidad)
            xml_file = request.files.get("xml")
            if not xml_file:
                return jsonify({"error": "No se recibieron los archivos XML necesarios. Se requieren: XML original (con UUID) y XML de aplicación de anticipo", "success": False})

            xml_original = xml_file.read()
            
            # VALIDAR DATOS FALTANTES
            faltantes = detectar_datos_faltantes(xml_original)
            if faltantes:
                mensaje_faltantes = "El XML tiene datos faltantes o incompletos:\n"
                for faltante in faltantes[:5]:
                    mensaje_faltantes += f"- {faltante['elemento']}.{faltante['atributo']}: {faltante['valor_actual']}\n"
                if len(faltantes) > 5:
                    mensaje_faltantes += f"... y {len(faltantes) - 5} más."
                
                return jsonify({
                    "error": mensaje_faltantes,
                    "success": False,
                    "datos_faltantes": faltantes
                })
            
            # Obtener forma de pago del formulario
            forma_pago = request.form.get("forma_pago", "99")  # Default: Por definir
            
            xml_resultado = procesar_aplicacion_anticipo(xml_original, forma_pago, "PPD", None, None)
            
            # Generar respuesta dual (XML + PDF)
            respuesta = generar_respuesta_dual(xml_resultado, "I")
            
            return jsonify(respuesta)

    except Exception as e:
        return jsonify({"error": str(e), "success": False})

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

@app.route("/validar", methods=["GET"])
def validar():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True, ssl_context=context)