"""
DEPENDENCIAS QUE REQUIEREN INSTALACIÓN:
pip install Flask==3.0.0 flask-cors==4.0.0 lxml==5.1.0 zeep==4.2.1 cryptography==41.0.7
"""
from flask import Flask, request, jsonify
from lxml import etree
import xml.etree.ElementTree as ET
from io import BytesIO
import base64
from datetime import datetime, timedelta
# from zeep import Client
# from cryptography.hazmat.primitives import serialization, hashes
# from cryptography.hazmat.primitives.asymmetric import padding
# from cryptography.hazmat.backends import default_backend
# from cryptography import x509
import os
import ctypes.wintypes
from flask_cors import CORS
from flask import send_file
# from xml.dom.minidom import parseString
from decimal import Decimal
# from typing import List, Optional
import ssl
import re
import io
import zipfile

'''
para produccion cambiar en este archivo la ruta del certificado, key y el password de la key
'''

# Crear un contexto SSL
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certfile='tm7_combined.pem')  # Certificado + clave combinados

# CONFIGURACIÓN GENERAL modo test
RUTA_CER = r"CSD_Sucursal_1_EKU9003173C9_20230517_223850.cer"
RUTA_KEY = r"CSD_Sucursal_1_EKU9003173C9_20230517_223850.key"
PASSWORD_KEY = b"12345678a"
RUTA_XSLT = r"xslt\cadenaoriginal_4_0.xslt"
SALIDA_DIR = r"TimbradoSalida"

app = Flask(__name__)
CORS(app)

# Importar funciones necesarias de PDF.py
from PDF import (
    generar_pdf_factura, PDFGenerationError, 
    ConceptoCFDI, extraer_conceptos_filemaker
)

from cfdi_service import (
    cargar_certificado,
    cargar_llave_privada,
    timbrar_con_pac,
    generar_xml_timbrado,
    sellar_cfdi_complemento,
    generar_xml_cfdi,
    sellar_cfdi,
    cancelar_cfdi_con_pac
)

# RUTA_XSLT = r"xslt\cadenaoriginal_4_0.xslt"
RUTA_CFDI_XSD = r"xsd\cfdv40.xsd"
RUTA_NOMINA_XSD = r"xsd\nomina12.xsd"


#eliminar
app = Flask(__name__)
CORS(app)


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


def generar_respuesta_dual(xml_timbrado, tipo_comprobante, cad_original):
   
    try:
        
        # Intentar generar PDF
        pdf_bytes = None
        nombre_pdf = None
        error_pdf = None
        
        try:
            pdf_bytes = generar_pdf_factura(xml_timbrado, tipo_comprobante,cad_original_pac=cad_original)
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

        # print(xml_cfdi_string)
        # extraer valores del xml a un dict
        factura = parse_xml_complemento(xml_cfdi_string,forma_pago)
        llave_privada = cargar_llave_privada(RUTA_KEY, PASSWORD_KEY)

        # Cargar certificado y llave privada
        certificado_base64, no_certificado = cargar_certificado(RUTA_CER)

        xml_sin_sellar = crear_cfdi_complemento(factura, no_certificado, certificado_base64)

        xml_sellado = sellar_cfdi_complemento(xml_sin_sellar,llave_privada, RUTA_XSLT)

        #transformar xml en stringa bytes
        xml_bytes = xml_sellado.encode("utf-8")
        guardar_xml(xml_bytes, tipo_comprobante="anticipo")

        #timbrar con pac
        resultado_pac = timbrar_con_pac(xml_bytes)
        error_timbrado = resultado_pac["error"]
        cfdi_bytes = resultado_pac["cfdi"]
        cadena_original = resultado_pac["cadena_original"]

        if error_timbrado:
            return jsonify({
                "success": False,
                "error": error_timbrado
            }), 422

        respuesta = generar_xml_timbrado(cfdi_bytes)

        # print(respuesta["xml"]) importante para generar xml
        xml_base64 = base64.b64encode(respuesta["xml"].encode('utf-8')).decode('utf-8')
        
        xml_timbrado_str = respuesta["xml"]
        xml_timbrado_bytes = xml_timbrado_str.encode('utf-8')   


        # Generar respuesta dual (XML + PDF)
        respuesta = generar_respuesta_dual(xml_timbrado_bytes, "P", cadena_original)

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
    

#extraer valores emisor, receptor para crear dict
def parse_xml_complemento(xml_cfdi: str, forma_pago: str) -> dict:
    ns = {
        "cfdi": "http://www.sat.gob.mx/cfd/4",
        "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital",
        "pago20": "http://www.sat.gob.mx/Pagos20",
    }

    root = ET.fromstring(xml_cfdi)

     # EXTRAER UUID ANTES DE ELIMINAR EL TIMBRE
    timbre_element = root.find('.//tfd:TimbreFiscalDigital', ns)
    if timbre_element is not None:
        uuid_factura = timbre_element.attrib['UUID']
    else:
        docto = root.find('.//pago20:DoctoRelacionado', ns)
        if docto is None:
            raise ValueError("No se encontró el UUID de la factura original.")
        uuid_factura = docto.get('IdDocumento')

    #  ELIMINAR EL TIMBRE FISCAL (para evitar duplicados al re-timbrar)
    complemento_nodo = root.find('cfdi:Complemento', ns)
    if complemento_nodo is not None:
        timbre_nodo = complemento_nodo.find('tfd:TimbreFiscalDigital', ns)
        if timbre_nodo is not None:
            # print(" Eliminando TimbreFiscalDigital existente...")
            complemento_nodo.remove(timbre_nodo)
            # Si el Complemento quedó vacío, eliminarlo también
            if len(complemento_nodo) == 0:
                root.remove(complemento_nodo)
                # print(" Nodo Complemento eliminado (estaba vacío)")


    # Extraer datos del nodo Comprobante
    comprobante = root.attrib
    emisor = root.find('cfdi:Emisor', ns).attrib
    receptor = root.find('cfdi:Receptor', ns).attrib 
    pago_nodo = root.find('.//pago20:Pago', ns)
    moneda_pago = pago_nodo.get('MonedaP')  
    monto_pago = float(pago_nodo.get('Monto'))
    fecha_pago = pago_nodo.get('FechaPago')

    # Extraer Impuestos
    # impuestos_nodo = root.find('cfdi:Impuestos', ns)
    # traslados = impuestos_nodo.find('cfdi:Traslados', ns)
    # traslado = traslados.find('cfdi:Traslado', ns).attrib

    # Leer impuestos desde el nodo pago20
    traslado_dr = root.find('.//pago20:TrasladoDR', ns)
    traslado = {
        'Base':        traslado_dr.get('BaseDR'),
        'TasaOCuota':  traslado_dr.get('TasaOCuotaDR'),
        'Importe':     traslado_dr.get('ImporteDR'),
        'Impuesto':    traslado_dr.get('ImpuestoDR'),
        'TipoFactor':  traslado_dr.get('TipoFactorDR'),
    }
    
    # Extraer Concepto
    conceptos_nodo = root.find('cfdi:Conceptos', ns)
    concepto = conceptos_nodo.find('cfdi:Concepto', ns).attrib
    
    # UUID de la factura original
    # uuid_factura = timbre['UUID']
    
    # Valores de la factura original - Nodo: Comprobante
    version_factura = comprobante.get('Version')
    # total_factura = float(comprobante['Total'])
    subtotal_factura = float(comprobante['SubTotal'])
    serie_factura = comprobante.get('Serie', '')
    folio_factura = comprobante.get('Folio', '')
    exportacion_factura = comprobante.get('Exportacion')
    lugar_expedicion = comprobante.get('LugarExpedicion')  
    metodo_pago_original = comprobante.get('MetodoPago')
    moneda_original = comprobante.get('Moneda')
    fecha_factura = comprobante.get('Fecha')
    
    # Certificado (para el complemento de pago)
    certificado = comprobante.get('Certificado')
    no_certificado = comprobante.get('NoCertificado')
    
    # Fecha actual menos 1 hora
    fecha_actual = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')
    
    # Calcular valores del pago (asumiendo pago total)
    # monto_pago = total_factura
    # imp_saldo_ant = total_factura
    # imp_pagado = monto_pago
    # imp_saldo_insoluto = imp_saldo_ant - imp_pagado
    docto_nodo = root.find('.//pago20:DoctoRelacionado', ns)
    monto_pago     = float(pago_nodo.get('Monto'))
    imp_saldo_ant  = float(docto_nodo.get('ImpSaldoAnt'))
    imp_pagado     = float(docto_nodo.get('ImpPagado'))
    imp_saldo_insoluto = float(docto_nodo.get('ImpSaldoInsoluto'))
    
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
                    'FechaPago': fecha_pago,
                    'FormaDePagoP': forma_pago,  # aqui va la seleccion pasada como argumento
                    'MonedaP': moneda_pago,
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
                        'MonedaDR': moneda_pago,
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

#este se ejecuta antes de sellar
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

    # Atributos obligatorios en orden
    pago.set('FechaPago', str(pago_data['FechaPago']))
    pago.set('FormaDePagoP', str(pago_data['FormaDePagoP']))
    pago.set('MonedaP', str(pago_data['MonedaP']))
    pago.set('TipoCambioP', str(pago_data['TipoCambioP']))
    pago.set('Monto', str(pago_data['Monto']))

    # Atributos opcionales en orden correcto
    if pago_data.get('CuentaOrdenante'):
        pago.set('CtaOrdenante', str(pago_data['CuentaOrdenante']))
    if pago_data.get('CuentaBeneficiario'):
        pago.set('CtaBeneficiario', str(pago_data['CuentaBeneficiario']))
    # if pago_data.get('ReferenciaNumerica'):
    #     pago.set('ReferenciaNumerica', str(pago_data['ReferenciaNumerica']))

    if pago_data.get('ReferenciaNumerica'):
        pago.set('NumOperacion', str(pago_data['ReferenciaNumerica']))

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
            return jsonify({"success": False, "error": "No se encontró UUID en CFDI origen"}), 422
        
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

        #timbrar con pac, bytes solo  es cfdi
        resultado_pac = timbrar_con_pac(xml_bytes)
        error_timbrado = resultado_pac["error"]
        cfdi_bytes = resultado_pac["cfdi"]
        cadena_original = resultado_pac["cadena_original"]

        if error_timbrado:
            return jsonify({
                "success": False,
                "error": error_timbrado
            }), 422

        respuesta = generar_xml_timbrado(cfdi_bytes)

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
            xml_anticipo=xml_filemaker_bytes,
            cad_original_pac= cadena_original
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

def crear_cfdi_desde_contexto(contexto: dict, certificado_path: str, key_path: str, password: str, xslt_path: str = None) -> dict:
    uuid_origen = contexto.get("uuid_origen")
    factura = contexto.get("factura")
    
    if not uuid_origen or not factura:
        raise ValueError("Contexto debe contener 'uuid_origen' y 'factura'")
    
    # Cargar certificado y llave privada
    certificado_base64, no_certificado = cargar_certificado(certificado_path)
    llave_privada = cargar_llave_privada(key_path, password)
    
    # Crear el XML del CFDI
    xml_sin_sellar = generar_xml_cfdi(factura, uuid_origen, no_certificado, certificado_base64)
    # print(f"xml_sinSellar: {xml_sin_sellar}")
    
    # Sellar el CFDI
    resultado_de_sellar = sellar_cfdi(xml_sin_sellar, llave_privada,certificado_base64, xslt_path)
    # xml_sellado = resultado_sellar["xml_sellado"]
    # cadena_original = resultado_sellar["cadena_original"]
    
    return resultado_de_sellar


@app.route("/timbrar-nomina", methods=["POST"])
def timbrar_nomina():
    try:
        #  Recibir archivos
        xml_nomina = request.files.get("xml")     # CFDI de nomina

        if not xml_nomina:
            return jsonify({"success": False, "error": "Falta el archivo CFDI origen"}), 400

        #  Leer XMLs en string y bytes
        cfdi_nomina_string = xml_nomina.read().decode("utf-8")
        # print(cfdi_nomina_string)

        llave_privada = cargar_llave_privada(RUTA_KEY, PASSWORD_KEY)

        # Cargar certificado y llave privada
        certificado_base64, no_certificado = cargar_certificado(RUTA_CER)

        #agreagar certificado y no. certificado
        xml_sin_sellar = crear_cfdi_nomina(cfdi_nomina_string, no_certificado, certificado_base64)
        # print(xml_sin_sellar)

        xml_sellado = sellar_cfdi_complemento(xml_sin_sellar,llave_privada, RUTA_XSLT)
        # print(xml_sellado)

        #transformar xml en stringa bytes
        xml_bytes = xml_sellado.encode("utf-8")
        guardar_xml(xml_bytes, tipo_comprobante="nomina")

        #timbrar con pac bytes solo  es cfdi 
        resultado_pac = timbrar_con_pac(xml_bytes)
        error_timbrado = resultado_pac["error"]
        cfdi_bytes = resultado_pac["cfdi"]
        cadena_original = resultado_pac["cadena_original"]

        if error_timbrado:
            return jsonify({
                "success": False,
                "error": error_timbrado
            }), 422

        parseo_del_pac = generar_xml_timbrado(cfdi_bytes)

        # print(respuesta["xml"]) importante para generar xml
        
        xml_timbrado_str = parseo_del_pac["xml"]
        xml_timbrado_bytes = xml_timbrado_str.encode('utf-8')   


        # Generar respuesta dual (XML + PDF)
        respuesta = generar_respuesta_dual(xml_timbrado_bytes, "Nomina", cadena_original)

        return jsonify({
            "success": True,
            "message": "timbrado con exito",
            "xml_timbrado": respuesta["xml"]
            # "pdf": respuesta["pdf"],
            # "pdf_filename": respuesta["pdf_filename"],
            # "archivo_procesado": ruta_xml
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def crear_cfdi_nomina(xml_file, no_certificado, certificado_b64) -> str:
     # Leer XML 
    root = etree.fromstring(xml_file.encode("utf-8"))

    # Agregar atributos al nodo Comprobante
    root.set("Certificado", certificado_b64)
    root.set("NoCertificado", no_certificado)

    # Convertir a string
    xml_string = ET.tostring(root, encoding='unicode', method='xml')
    return xml_string


@app.route("/timbrar-ingreso", methods=["POST"])
def timbrar_ingreso():
    try:
        #  Recibir archivos
        xml_ingreso = request.files.get("xml")     # CFDI de nomina

        if not xml_ingreso:
            return jsonify({"success": False, "error": "Falta el archivo CFDI origen"}), 400

        #  Leer XMLs en string y bytes
        cfdi_nomina_string = xml_ingreso.read().decode("utf-8")
        # print(cfdi_nomina_string)

        llave_privada = cargar_llave_privada(RUTA_KEY, PASSWORD_KEY)

        # Cargar certificado y llave privada
        certificado_base64, no_certificado = cargar_certificado(RUTA_CER)

        #agreagar certificado y no. certificado
        xml_sin_sellar = crear_cfdi_nomina(cfdi_nomina_string, no_certificado, certificado_base64)
        # print(xml_sin_sellar)

        xml_sellado = sellar_cfdi_complemento(xml_sin_sellar,llave_privada, RUTA_XSLT)
        # print(xml_sellado)

        #transformar xml en stringa bytes
        xml_bytes = xml_sellado.encode("utf-8")
        guardar_xml(xml_bytes, tipo_comprobante="nomina")

        #timbrar con pac bytes solo  es cfdi - listo
        resultado_pac = timbrar_con_pac(xml_bytes)
        error_timbrado = resultado_pac["error"]
        cfdi_bytes = resultado_pac["cfdi"]
        cadena_original = resultado_pac["cadena_original"]

        if error_timbrado:
            return jsonify({
                "success": False,
                "error": error_timbrado
            }), 422

        parseo_del_pac = generar_xml_timbrado(cfdi_bytes)

        # print(respuesta["xml"]) importante para generar xml
        
        xml_timbrado_str = parseo_del_pac["xml"]
        xml_timbrado_bytes = xml_timbrado_str.encode('utf-8')   

        # Generar respuesta dual (XML + PDF)
        respuesta = generar_respuesta_dual(xml_timbrado_bytes, "Ingreso", cadena_original)

        return jsonify({
            "success": True,
            "message": "timbrado con exito",
            "xml_timbrado": respuesta["xml"],
            "pdf": respuesta["pdf"],
            "pdf_filename": respuesta["pdf_filename"]
            # "archivo_procesado": ruta_xml
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/cancelar-cfdi", methods=["POST"])
def cancelar_cfdi():
    try:
        uuid = request.form.get("uuid")
        rfc_emisor = request.form.get("rfc_emisor")
        motivo_cancelacion = request.form.get("motivo_cancelacion")
        uuid_sustituto = request.form.get("uuid_sustituto", "")
        email = "ircasarreal@telmedia.com.mx"

        if not uuid or not motivo_cancelacion:
            return jsonify({"success": False, "error": "Faltan datos: uuid o motivo_cancelacion"}), 400

        with open(RUTA_CER, 'rb') as f:
            csd_cer = f.read()
        with open(RUTA_KEY, 'rb') as f:
            csd_key = f.read()

        status, error = cancelar_cfdi_con_pac(
            uuid=uuid,
            motivo=motivo_cancelacion,
            rfc_emisor=rfc_emisor,
            email=email,
            uuid_sustituto=uuid_sustituto,
            csd_cer=csd_cer,
            csd_key=csd_key,
            csd_password='12345678a'
        )

        if error:
            return jsonify({"success": False, "error": error}), 422

        datos_cancelacion = parsear_mensaje_cancelacion(status["mensaje"])
        return jsonify({
            "success": True,
            "descripcion": datos_cancelacion.get("descripcion"),
            "acuse": datos_cancelacion.get("acuse"),
            "digest": datos_cancelacion.get("digest"),
            "certificado": datos_cancelacion.get("certificado")
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def parsear_mensaje_cancelacion(mensaje: str) -> dict:
    resultado = {
        "descripcion": None,
        "acuse": None,
        "digest": None,
        "certificado": None
    }

    # Si el mensaje NO contiene Acuse, es un mensaje simple (proceso, error, etc.)
    if "Acuse:" not in mensaje:
        resultado["descripcion"] = mensaje.strip()
        return resultado

    # Extraer descripcion
    descripcion_match = re.match(r'^(.*?)\s*-\s*Acuse:', mensaje, re.DOTALL)
    if descripcion_match:
        resultado["descripcion"] = descripcion_match.group(1).strip()

    # Extraer Acuse
    accuse_match = re.search(r'Acuse:\s*([\w+/=\n\r]+?)(?=;\s*Digest:)', mensaje, re.DOTALL)
    if accuse_match:
        resultado["acuse"] = accuse_match.group(1).replace('\n', '').replace('\r', '').strip()

    # Extraer Digest
    digest_match = re.search(r'Digest:\s*([\w+/=\n\r]+?)(?=;\s*Certificado:)', mensaje, re.DOTALL)
    if digest_match:
        resultado["digest"] = digest_match.group(1).replace('\n', '').replace('\r', '').strip()

    # Extraer Certificado
    cert_match = re.search(r'Certificado:\s*([A-F0-9]+)', mensaje)
    if cert_match:
        resultado["certificado"] = cert_match.group(1).strip()

    return resultado

def extraer_rfcEmisor_cfdi(xml_cfdi: str) -> str:
    ns = {
        "cfdi": "http://www.sat.gob.mx/cfd/4",
        "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital"
    }
    root = ET.fromstring(xml_cfdi)
    emisor = root.find("cfdi:Emisor", ns)
    return emisor.get("Rfc") if emisor is not None else None


@app.route("/timbrar-complemento-pago-params", methods=["GET"])
def timbrar_complemento_pago_params():
    try:
        # Parámetros requeridos
        ruta_xml = request.args.get("ruta_xml")
        forma_pago = request.args.get("forma_pago")
        fecha_pago = request.args.get("fecha_pago")
        monto = request.args.get("monto")

        print("Parámetros recibidos:")
        print("ruta_xml:", request.args.get("ruta_xml"))
        print("forma_pago:", request.args.get("forma_pago"))
        print("fecha_pago:", request.args.get("fecha_pago"))
        print("monto:", request.args.get("monto"))
        print("URL completa:", request.url)

        if not all([ruta_xml, forma_pago, fecha_pago, monto]):
            return jsonify({
                "success": False,
                "error": "Faltan parámetros requeridos: ruta_xml, forma_pago, fecha_pago, monto"
            }), 400

        # Parámetros opcionales
        moneda = request.args.get("moneda", "MXN")
        serie = request.args.get("serie", "P")
        folio = request.args.get("folio", "")
        cuenta_ordenante = request.args.get("cuenta_ordenante", "")
        cuenta_receptora = request.args.get("cuenta_receptora", "")
        referencia = request.args.get("referencia", "")
        num_parcialidad = request.args.get("num_parcialidad", "1")
        d_lugar_expedicion = request.args.get("d_lugar_expedicion", "")
        d_objeto_impuesto = request.args.get("d_objeto_impuesto", "02")
        saldo_anterior = request.args.get("saldo_anterior", "")
        saldo_insoluto = request.args.get("saldo_insoluto", "")

        if not os.path.exists(ruta_xml):
            return jsonify({
                "success": False,
                "error": f"Archivo no encontrado: {ruta_xml}"
            }), 404

        with open(ruta_xml, 'r', encoding='utf-8') as file:
            xml_cfdi_string = file.read()

        # Parsear XML con los parámetros del pago
        factura = parse_xml_complemento_params(
            xml_cfdi=xml_cfdi_string,
            forma_pago=forma_pago,
            fecha_pago=fecha_pago,
            monto=float(monto),
            moneda=moneda,
            serie=serie,
            folio=folio,
            cuenta_ordenante=cuenta_ordenante,
            cuenta_receptora=cuenta_receptora,
            referencia=referencia,
            num_parcialidad=num_parcialidad,
            d_lugar_expedicion=d_lugar_expedicion,
            d_objeto_impuesto=d_objeto_impuesto,
            saldo_anterior=float(saldo_anterior) if saldo_anterior else None,
            saldo_insoluto=float(saldo_insoluto) if saldo_insoluto else None
        )

        # Proceso de timbrado
        llave_privada = cargar_llave_privada(RUTA_KEY, PASSWORD_KEY)
        certificado_base64, no_certificado = cargar_certificado(RUTA_CER)
        

        xml_sin_sellar = crear_cfdi_complemento(factura, no_certificado, certificado_base64)
        xml_sellado = sellar_cfdi_complemento(xml_sin_sellar, llave_privada, RUTA_XSLT)

        # print("XML completo antes de timbrar:\n", xml_sellado) 


        xml_bytes = xml_sellado.encode("utf-8")
        guardar_xml(xml_bytes, tipo_comprobante="complemento")

        resultado_pac = timbrar_con_pac(xml_bytes)
        error_pac = resultado_pac["error"]
        xml_timbrado_tuple = resultado_pac["cfdi"]
        cadena_original = resultado_pac["cadena_original"]

        if error_pac:
            return jsonify({"success": False, "error": f"Error del PAC: {error_pac}"}), 422

        xml_timbrado_result = generar_xml_timbrado(xml_timbrado_tuple)

        if not xml_timbrado_result.get("success", True) and "error" in xml_timbrado_result:
            return jsonify({"success": False, "error": xml_timbrado_result["error"]}), 422

        xml_timbrado_bytes = xml_timbrado_result["xml"].encode('utf-8')

        # Extraer datos del TFD
        tfd_ns = {"tfd": "http://www.sat.gob.mx/TimbreFiscalDigital"}
        root_timbrado = ET.fromstring(xml_timbrado_bytes)
        tfd = root_timbrado.find(".//tfd:TimbreFiscalDigital", tfd_ns)

        uuid            = tfd.get("UUID", "")
        fecha_timbrado  = tfd.get("FechaTimbrado", "")
        sello_cfdi      = tfd.get("SelloCFD", "")
        sello_sat       = tfd.get("SelloSAT", "")
        no_cert_sat     = tfd.get("NoCertificadoSAT", "")
        rfc_prov_certif = tfd.get("RfcProvCertif", "")
        no_cert_emisor  = root_timbrado.get("NoCertificado", "")

        # Generar PDF
        pdf_bytes = generar_pdf_factura(
            xml_timbrado=xml_timbrado_bytes,
            tipo_comprobante="P"
        )
        guardar_pdf(pdf_bytes, tipo_comprobante="complemento")

        # Crear carpeta por folio
        serie = factura["Comprobante"]["Serie"]
        folio = factura["Comprobante"]["Folio"]
        nombre_carpeta = f"{serie}_{folio}"

        #obtener escritorio dinamicamente
        escritorio = obtener_escritorio()

        carpeta_base = os.path.join(escritorio, "fm", "cfdi", "timbrados", nombre_carpeta)
        os.makedirs(carpeta_base, exist_ok=True)

        ruta_xml_timbrado = os.path.join(carpeta_base, f"CFDI_{nombre_carpeta}.xml")
        ruta_pdf = os.path.join(carpeta_base, f"CFDI_{nombre_carpeta}.pdf")

        with open(ruta_xml_timbrado, 'wb') as f:
            f.write(xml_timbrado_bytes)

        with open(ruta_pdf, 'wb') as f:
            f.write(pdf_bytes)

        return jsonify({
            "success": True,
            "mensaje": "Complemento de pago timbrado correctamente",
            "uuid": uuid,
            "fecha_timbrado": fecha_timbrado,
            "sello_cfdi": sello_cfdi,
            "sello_sat": sello_sat,
            "no_certificado_sat": no_cert_sat,
            "rfc_prov_certif": rfc_prov_certif,
            "no_certificado_emisor": no_cert_emisor,
            "cadena_original": cadena_original,
            "ruta_xml": ruta_xml_timbrado,
            "ruta_pdf": ruta_pdf
        }), 200

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def parse_xml_complemento_params(xml_cfdi: str, forma_pago: str, fecha_pago: str,
                                  monto: float, moneda: str, serie: str, folio: str,
                                  cuenta_ordenante: str, cuenta_receptora: str,
                                  referencia: str, num_parcialidad: str,
                                  d_lugar_expedicion: str, d_objeto_impuesto: str,
                                  saldo_anterior: float, saldo_insoluto: float) -> dict:
    ns = {
        "cfdi": "http://www.sat.gob.mx/cfd/4",
        "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital"
    }

    root = ET.fromstring(xml_cfdi)

    # Extraer UUID
    timbre_element = root.find('.//tfd:TimbreFiscalDigital', ns)
    if timbre_element is not None:
        uuid_factura = timbre_element.attrib['UUID']
    else:
        raise ValueError("No se encontró el UUID de la factura original.")

    # Eliminar timbre para evitar duplicados
    complemento_nodo = root.find('cfdi:Complemento', ns)
    if complemento_nodo is not None:
        timbre_nodo = complemento_nodo.find('tfd:TimbreFiscalDigital', ns)
        if timbre_nodo is not None:
            complemento_nodo.remove(timbre_nodo)
            if len(complemento_nodo) == 0:
                root.remove(complemento_nodo)

    # Extraer datos fijos del XML
    comprobante = root.attrib
    emisor = root.find('cfdi:Emisor', ns).attrib
    receptor = root.find('cfdi:Receptor', ns).attrib

    # Fecha actual menos 1 hora
    fecha_actual = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')

    impuestos_nodo = root.find('cfdi:Impuestos', ns)
    traslados = impuestos_nodo.find('cfdi:Traslados', ns)
    traslado = traslados.find('cfdi:Traslado', ns).attrib

    exportacion_factura = comprobante.get('Exportacion', '01')
    lugar_expedicion = d_lugar_expedicion or comprobante.get('LugarExpedicion', '')
    moneda_original = moneda
    serie_factura = comprobante.get('Serie', '')
    folio_factura = folio or comprobante.get('Folio', '')

    base_dr = float(traslado['Base'])
    tasa_dr = traslado['TasaOCuota']
    importe_dr = float(traslado['Importe'])
    impuesto_tipo = traslado['Impuesto']
    tipo_factor = traslado['TipoFactor']

    # Calcular saldos si no se pasaron
    total_factura = float(comprobante['Total'])
    imp_saldo_ant = saldo_anterior if saldo_anterior is not None else total_factura
    imp_pagado = monto
    imp_saldo_insoluto = saldo_insoluto if saldo_insoluto is not None else (imp_saldo_ant - imp_pagado)

    # Calcular impuestos proporcionales al monto pagado
    proporcion = monto / total_factura if total_factura > 0 else 1
    base_pago = round(base_dr * proporcion, 2)
    importe_pago = round(importe_dr * proporcion, 2)

    pago_dict = {
        'FechaPago': fecha_pago,
        'FormaDePagoP': forma_pago,
        'MonedaP': moneda_original,
        'TipoCambioP': '1',
        'Monto': f'{monto:.2f}',
    }

    # Agregar campos opcionales en el orden correcto ANTES de ImpuestosP
    if cuenta_ordenante:
        pago_dict['CuentaOrdenante'] = cuenta_ordenante
    if cuenta_receptora:
        pago_dict['CuentaBeneficiario'] = cuenta_receptora
    if referencia:
        pago_dict['ReferenciaNumerica'] = referencia

    # Agregar ImpuestosP y DoctoRelacionado al final
    pago_dict['ImpuestosP'] = {
        'TrasladosP': [
            {
                'BaseP': f'{base_pago:.2f}',
                'ImpuestoP': impuesto_tipo,
                'TipoFactorP': tipo_factor,
                'TasaOCuotaP': f'{float(tasa_dr):.6f}',
                'ImporteP': f'{importe_pago:.2f}'
            }
        ]
    }

    pago_dict['DoctoRelacionado'] = {
        'IdDocumento': uuid_factura,
        'Serie': serie_factura,
        'Folio': folio_factura,
        'MonedaDR': moneda_original,
        'EquivalenciaDR': '1',
        'NumParcialidad': num_parcialidad,
        'ImpSaldoAnt': f'{imp_saldo_ant:.2f}',
        'ImpPagado': f'{imp_pagado:.2f}',
        'ImpSaldoInsoluto': f'{imp_saldo_insoluto:.2f}',
        'ObjetoImpDR': d_objeto_impuesto,
        'ImpuestosDR': {
            'TrasladosDR': [
                {
                    'BaseDR': f'{base_pago:.2f}',
                    'ImpuestoDR': impuesto_tipo,
                    'TipoFactorDR': tipo_factor,
                    'TasaOCuotaDR': f'{float(tasa_dr):.6f}',
                    'ImporteDR': f'{importe_pago:.2f}'
                }
            ]
        }
    }


    return {
        'Comprobante': {
            'Version': '4.0',
            'Serie': serie,
            'Folio': folio_factura,
            'Fecha': fecha_actual,
            'SubTotal': '0',
            'Moneda': 'XXX',
            'Total': '0',
            'TipoDeComprobante': 'P',
            'Exportacion': exportacion_factura,
            'LugarExpedicion': lugar_expedicion
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
            'UsoCFDI': 'CP01'
        },
        'Conceptos': {
            'Concepto': {
                'ClaveProdServ': '84111506',
                'Cantidad': '1',
                'ClaveUnidad': 'ACT',
                'Descripcion': 'Pago',
                'ValorUnitario': '0',
                'Importe': '0',
                'ObjetoImp': '01'
            }
        },
        'Complemento': {
            'Pagos': {
                'Version': '2.0',
                'Totales': {
                    'MontoTotalPagos': f'{monto:.2f}',
                    'TotalTrasladosBaseIVA16': f'{base_pago:.2f}',
                    'TotalTrasladosImpuestoIVA16': f'{importe_pago:.2f}'
                },
                'Pago': pago_dict
            }
        }
    }

@app.route("/timbrar-aplicacion-anticipo-ruta", methods=["GET"])
def timbrar_aplicacion_anticipo_ruta():
    try:
        ruta_xml_anticipo = request.args.get("ruta_xml_anticipo")
        ruta_xml_filemaker = request.args.get("ruta_xml_filemaker")

        if not ruta_xml_anticipo:
            return jsonify({"success": False, "error": "Falta el parámetro: ruta_xml_anticipo"}), 400

        if not ruta_xml_filemaker:
            return jsonify({"success": False, "error": "Falta el parámetro: ruta_xml_filemaker"}), 400

        if not os.path.exists(ruta_xml_anticipo):
            return jsonify({"success": False, "error": f"Archivo CFDI origen no encontrado: {ruta_xml_anticipo}"}), 404

        if not os.path.exists(ruta_xml_filemaker):
            return jsonify({"success": False, "error": f"Archivo FileMaker no encontrado: {ruta_xml_filemaker}"}), 404

        with open(ruta_xml_anticipo, 'r', encoding='utf-8') as file:
            xml_cfdi_string = file.read()

        with open(ruta_xml_filemaker, 'r', encoding='utf-8') as file:
            xml_filemaker_string = file.read()

        uuid_origen = extraer_uuid_cfdi(xml_cfdi_string)
        if not uuid_origen:
            return jsonify({"success": False, "error": "No se encontró UUID en CFDI origen"}), 422

        factura = parse_filemaker_xml(xml_filemaker_string)

        contexto = {
            "uuid_origen": uuid_origen,
            "factura": factura
        }

        contexto_result = crear_cfdi_desde_contexto(
            contexto=contexto,
            certificado_path=RUTA_CER,
            key_path=RUTA_KEY,
            password=PASSWORD_KEY,
            xslt_path=RUTA_XSLT
        )

        xml_bytes = contexto_result["xml_sellado"].encode("utf-8")
        guardar_xml(xml_bytes, tipo_comprobante="anticipo")

        resultado_pac = timbrar_con_pac(xml_bytes)
        error_pac = resultado_pac["error"]
        xml_timbrado_tuple = resultado_pac["cfdi"]
        cadena_original = resultado_pac["cadena_original"]
        status_pac = resultado_pac["status_pac"]
        mensaje_pac = resultado_pac["mensaje_pac"]

        if error_pac:
            return jsonify({"success": False, "error": f"Error del PAC: {error_pac}"}), 422

        xml_timbrado_result = generar_xml_timbrado(xml_timbrado_tuple)

        if not xml_timbrado_result.get("success", True) and "error" in xml_timbrado_result:
            return jsonify({"success": False, "error": xml_timbrado_result["error"]}), 422

        xml_timbrado_bytes = xml_timbrado_result["xml"].encode('utf-8')

        # Extraer datos del TFD
        import xml.etree.ElementTree as ET
        tfd_ns = {"tfd": "http://www.sat.gob.mx/TimbreFiscalDigital"}
        root_timbrado = ET.fromstring(xml_timbrado_bytes)
        tfd = root_timbrado.find(".//tfd:TimbreFiscalDigital", tfd_ns)

        uuid            = tfd.get("UUID", "")
        fecha_timbrado  = tfd.get("FechaTimbrado", "")
        sello_cfdi      = tfd.get("SelloCFD", "")
        sello_sat       = tfd.get("SelloSAT", "")
        no_cert_sat     = tfd.get("NoCertificadoSAT", "")
        rfc_prov_certif = tfd.get("RfcProvCertif", "")
        no_cert_emisor  = root_timbrado.get("NoCertificado", "")

        # Generar PDF
        with open(ruta_xml_filemaker, 'rb') as file:
            xml_filemaker_bytes = file.read()

        pdf_bytes = generar_pdf_factura(
            xml_timbrado=xml_timbrado_bytes,
            tipo_comprobante="I",
            xml_anticipo=xml_filemaker_bytes,
            cad_original_pac= cadena_original
        )

        guardar_pdf(pdf_bytes, tipo_comprobante="anticipo")

        # Crear carpeta por factura
        serie = factura["serie"]
        folio = factura["folio"]
        nombre_carpeta = f"{serie}_{folio}"

        #obtener escritorio dinamicamente
        escritorio = obtener_escritorio()

        carpeta_base = os.path.join(escritorio, "fm", "cfdi", "timbrados", nombre_carpeta)
        os.makedirs(carpeta_base, exist_ok=True)

        ruta_xml_timbrado = os.path.join(carpeta_base, f"CFDI_{nombre_carpeta}.xml")
        ruta_pdf = os.path.join(carpeta_base, f"CFDI_{nombre_carpeta}.pdf")

        with open(ruta_xml_timbrado, 'wb') as f:
            f.write(xml_timbrado_bytes)

        with open(ruta_pdf, 'wb') as f:
            f.write(pdf_bytes)

        return jsonify({
            "success": True,
            "mensaje_pac": mensaje_pac,
            "status_pac": status_pac,
            "uuid": uuid,
            "fecha_timbrado": fecha_timbrado,
            "sello_cfdi": sello_cfdi,
            "sello_sat": sello_sat,
            "no_certificado_sat": no_cert_sat,
            "rfc_prov_certif": rfc_prov_certif,
            "no_certificado_emisor": no_cert_emisor,
            "cadena_original": cadena_original,
            "ruta_xml": ruta_xml_timbrado,
            "ruta_pdf": ruta_pdf,
            "cadena_original": contexto_result["cad_original_cfdi"]
        }), 200

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

def obtener_escritorio():
    CSIDL_DESKTOPDIRECTORY = 0x10
    SHGFP_TYPE_CURRENT = 0

    buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(
        None,
        CSIDL_DESKTOPDIRECTORY,
        None,
        SHGFP_TYPE_CURRENT,
        buf
    )
    return buf.value

@app.route("/cancelar-cfdi-ruta", methods=["GET"])
def cancelar_cfdi_ruta():
    try:
        uuid = request.args.get("uuid")
        rfc_emisor = request.args.get("rfc_emisor")
        motivo_cancelacion = request.args.get("motivo_cancelacion")
        uuid_sustituto = request.args.get("uuid_sustituto", "")
        email = "nombre@telmedia.com.mx"

        if not uuid or not motivo_cancelacion:
            return jsonify({"success": False, "error": "Faltan datos: uuid o motivo_cancelacion"}), 400

        with open(RUTA_CER, 'rb') as f:
            csd_cer = f.read()
        with open(RUTA_KEY, 'rb') as f:
            csd_key = f.read()

        status, error = cancelar_cfdi_con_pac(
            uuid=uuid,
            motivo=motivo_cancelacion,
            rfc_emisor=rfc_emisor,
            email=email,
            uuid_sustituto=uuid_sustituto,
            csd_cer=csd_cer,
            csd_key=csd_key,
            # csd_password='12345678a'
            csd_password= PASSWORD_KEY
        )

        if error:
            return jsonify({"success": False, "error": error}), 422

        datos_cancelacion = parsear_mensaje_cancelacion(status["mensaje"])

        # Armar contenido del TXT
        contenido = generar_txt_cancelacion(uuid, rfc_emisor, motivo_cancelacion, uuid_sustituto, datos_cancelacion)

        return send_file(
            io.BytesIO(contenido.encode('utf-8')),
            mimetype="text/plain",
            as_attachment=True,
            download_name=f"cancelacion_{uuid}.txt"
        )

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
    
def generar_txt_cancelacion(uuid, rfc_emisor, motivo, uuid_sustituto, datos_cancelacion):
    return f"""RESULTADO DE CANCELACIÓN
    ========================
    UUID:           {uuid}
    RFC Emisor:     {rfc_emisor}
    Motivo:         {motivo}
    UUID Sustituto: {uuid_sustituto}

    RESPUESTA DEL PAC
    -----------------
    Descripción:  {datos_cancelacion.get("descripcion")}
    Digest:       {datos_cancelacion.get("digest")}
    Certificado:  {datos_cancelacion.get("certificado")}

ACUSE:
{datos_cancelacion.get("acuse")}
"""


@app.route("/timbrar-ingreso-ruta", methods=["GET"])
def timbrar_ingreso_ruta():
    try:
        ruta_xml = request.args.get("ruta_xml")

        if not ruta_xml:
            return jsonify({"success": False, "error": "Falta el parámetro: ruta_xml"}), 400

        if not os.path.exists(ruta_xml):
            return jsonify({"success": False, "error": f"Archivo no encontrado: {ruta_xml}"}), 404

        with open(ruta_xml, 'r', encoding='utf-8') as file:
            cfdi_nomina_string = file.read()

        llave_privada = cargar_llave_privada(RUTA_KEY, PASSWORD_KEY)
        certificado_base64, no_certificado = cargar_certificado(RUTA_CER)

        xml_sin_sellar = crear_cfdi_nomina(cfdi_nomina_string, no_certificado, certificado_base64)
        xml_sellado = sellar_cfdi_complemento(xml_sin_sellar, llave_privada, RUTA_XSLT)

        xml_bytes = xml_sellado.encode("utf-8")
        guardar_xml(xml_bytes, tipo_comprobante="nomina")

        cfdi_bytes, error_timbrado = timbrar_con_pac(xml_bytes)
        if error_timbrado:
            return jsonify({"success": False, "error": error_timbrado}), 422

        parseo_del_pac = generar_xml_timbrado(cfdi_bytes)

        xml_timbrado_bytes = parseo_del_pac["xml"].encode('utf-8')
        respuesta_dual = generar_respuesta_dual(xml_timbrado_bytes, "Ingreso")

        # Armar ZIP con fecha
        fecha_actual = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_bytes = base64.b64decode(respuesta_dual["pdf"])

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(f"CFDI_Ingreso_{fecha_actual}.xml", xml_timbrado_bytes)
            zip_file.writestr(f"CFDI_Ingreso_{fecha_actual}.pdf", pdf_bytes)
        zip_buffer.seek(0)

        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"CFDI_Ingreso_{fecha_actual}.zip"
        )

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True, ssl_context=context)
    # app.run(host='0.0.0.0', port=5001, debug=True)