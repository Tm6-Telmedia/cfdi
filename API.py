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
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_CER = os.path.join(BASE_DIR, "CSD_Sucursal_1_EKU9003173C9_20230517_223850.cer")
RUTA_KEY = os.path.join(BASE_DIR, "CSD_Sucursal_1_EKU9003173C9_20230517_223850.key")
PASSWORD_KEY = b"12345678a"  

RUTA_XSLT = r"xslt\cadenaoriginal_4_0.xslt"

# Constantes globales
FILEMAKER_NAMESPACE = "http://www.filemaker.com/fmpdsoresult"

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
        # print(factura)

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