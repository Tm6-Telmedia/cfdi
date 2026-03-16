"""
DEPENDENCIAS QUE REQUIEREN INSTALACIÓN:
pip install Flask==3.0.0 flask-cors==4.0.0 lxml==5.1.0 zeep==4.2.1 cryptography==41.0.7
"""
from flask import Flask, request, jsonify
from lxml import etree
import xml.etree.ElementTree as ET
from io import BytesIO
import base64
from datetime import datetime
# from zeep import Client
# from cryptography.hazmat.primitives import serialization, hashes
# from cryptography.hazmat.primitives.asymmetric import padding
# from cryptography.hazmat.backends import default_backend
# from cryptography import x509
import os
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
        cfdi_bytes, error_timbrado = timbrar_con_pac(xml_bytes)

        if error_timbrado:
            return jsonify({
                "success": False,
                "error": error_timbrado
            }), 400

        respuesta = generar_xml_timbrado(cfdi_bytes)

        # print(respuesta["xml"]) importante para generar xml
        xml_base64 = base64.b64encode(respuesta["xml"].encode('utf-8')).decode('utf-8')
        
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
    

#extraer valores emisor, receptor para crear dict
def parse_xml_complemento(xml_cfdi: str, forma_pago: str) -> dict:
    ns = {
        "cfdi": "http://www.sat.gob.mx/cfd/4",
        "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital"
    }

    root = ET.fromstring(xml_cfdi)

     # EXTRAER UUID ANTES DE ELIMINAR EL TIMBRE
    timbre_element = root.find('.//tfd:TimbreFiscalDigital', ns)
    if timbre_element is not None:
        uuid_factura = timbre_element.attrib['UUID']
        # print(f" UUID extraído: {uuid_factura}")
    else:
        # print("No se encontró TimbreFiscalDigital en el XML")
        raise ValueError("No se encontró el UUID de la factura original. El XML debe contener un TimbreFiscalDigital.")

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
    # timbre = root.find('.//tfd:TimbreFiscalDigital', ns).attrib

    # Extraer Impuestos
    impuestos_nodo = root.find('cfdi:Impuestos', ns)
    traslados = impuestos_nodo.find('cfdi:Traslados', ns)
    traslado = traslados.find('cfdi:Traslado', ns).attrib
    
    # Extraer Concepto
    conceptos_nodo = root.find('cfdi:Conceptos', ns)
    concepto = conceptos_nodo.find('cfdi:Concepto', ns).attrib
    
    # UUID de la factura original
    # uuid_factura = timbre['UUID']
    
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
    fecha_factura = comprobante.get('Fecha')
    
    # Certificado (para el complemento de pago)
    certificado = comprobante.get('Certificado')
    no_certificado = comprobante.get('NoCertificado')
    
    # Fecha actual 
    # fecha_actual = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    # fecha_actual = "2026-01-08T13:12:50"
    
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
            'Fecha': fecha_factura,
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
                    'FechaPago': fecha_factura,
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
        cfdi_bytes, error_timbrado = timbrar_con_pac(xml_bytes) #bytes solo  es cfdi

        if error_timbrado:
            return jsonify({
                "success": False,
                "error": error_timbrado
            }), 400

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
    # print(f"xml_sinSellar: {xml_sin_sellar}")
    
    # Sellar el CFDI
    xml_sellado = sellar_cfdi(xml_sin_sellar, llave_privada,certificado_base64, xslt_path)
    
    return xml_sellado


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

        #timbrar con pac
        cfdi_bytes, error_timbrado = timbrar_con_pac(xml_bytes) #bytes solo  es cfdi - listo
        if error_timbrado:
            return jsonify({
                "success": False,
                "error": error_timbrado
            }), 400

        parseo_del_pac = generar_xml_timbrado(cfdi_bytes)

        # print(respuesta["xml"]) importante para generar xml
        
        xml_timbrado_str = parseo_del_pac["xml"]
        xml_timbrado_bytes = xml_timbrado_str.encode('utf-8')   


        # Generar respuesta dual (XML + PDF)
        respuesta = generar_respuesta_dual(xml_timbrado_bytes, "Nomina")

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

        #timbrar con pac
        cfdi_bytes, error_timbrado = timbrar_con_pac(xml_bytes) #bytes solo  es cfdi - listo
        if error_timbrado:
            return jsonify({
                "success": False,
                "error": error_timbrado
            }), 400

        parseo_del_pac = generar_xml_timbrado(cfdi_bytes)

        # print(respuesta["xml"]) importante para generar xml
        
        xml_timbrado_str = parseo_del_pac["xml"]
        xml_timbrado_bytes = xml_timbrado_str.encode('utf-8')   

        # Generar respuesta dual (XML + PDF)
        respuesta = generar_respuesta_dual(xml_timbrado_bytes, "Ingreso")

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
            return jsonify({"success": False, "error": error}), 400

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


@app.route("/timbrar-complemento-pago-ruta", methods=["GET"])
def timbrar_complemento_pago_ruta():
    try:
        ruta_xml = request.args.get("ruta_xml")
        forma_pago = request.args.get("forma_pago")

        if not ruta_xml or not forma_pago:
            return jsonify({
                "success": False,
                "error": "Faltan parámetros: ruta_xml y forma_pago"
            }), 400

        if not os.path.exists(ruta_xml):
            return jsonify({
                "success": False,
                "error": f"Archivo no encontrado: {ruta_xml}"
            }), 404

        with open(ruta_xml, 'r', encoding='utf-8') as file:
            xml_cfdi_string = file.read()

        # Proceso de timbrado
        factura = parse_xml_complemento(xml_cfdi_string, forma_pago)
        llave_privada = cargar_llave_privada(RUTA_KEY, PASSWORD_KEY)
        certificado_base64, no_certificado = cargar_certificado(RUTA_CER)
        xml_sin_sellar = crear_cfdi_complemento(factura, no_certificado, certificado_base64)
        xml_sellado = sellar_cfdi_complemento(xml_sin_sellar, llave_privada, RUTA_XSLT)

        xml_bytes = xml_sellado.encode("utf-8")
        guardar_xml(xml_bytes, tipo_comprobante="anticipo")

        xml_timbrado_tuple, _ = timbrar_con_pac(xml_bytes)
        xml_timbrado_result = generar_xml_timbrado(xml_timbrado_tuple)

        xml_timbrado_bytes = xml_timbrado_result["xml"].encode('utf-8')
        respuesta_dual = generar_respuesta_dual(xml_timbrado_bytes, "P")

        # Armar ZIP con PDF y XML
        pdf_bytes = base64.b64decode(respuesta_dual["pdf"])
        pdf_filename = respuesta_dual["pdf_filename"]
        xml_filename = pdf_filename.replace(".pdf", ".xml")

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(xml_filename, xml_timbrado_bytes)
            zip_file.writestr(pdf_filename, pdf_bytes)
        zip_buffer.seek(0)

        zip_filename = pdf_filename.replace(".pdf", ".zip")

        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=zip_filename
        )

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


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
            return jsonify({"success": False, "error": "No se encontró UUID en CFDI origen"}), 400

        factura = parse_filemaker_xml(xml_filemaker_string)

        contexto = {
            "uuid_origen": uuid_origen,
            "factura": factura
        }

        xml_cfdi = crear_cfdi_desde_contexto(
            contexto=contexto,
            certificado_path=RUTA_CER,
            key_path=RUTA_KEY,
            password=PASSWORD_KEY,
            xslt_path=RUTA_XSLT
        )

        xml_bytes = xml_cfdi.encode("utf-8")
        guardar_xml(xml_bytes, tipo_comprobante="anticipo")

        # Fix: desempacar tupla
        xml_timbrado_tuple, _ = timbrar_con_pac(xml_bytes)
        xml_timbrado_result = generar_xml_timbrado(xml_timbrado_tuple)

        xml_timbrado_bytes = xml_timbrado_result["xml"].encode('utf-8')

        with open(ruta_xml_filemaker, 'rb') as file:
            xml_filemaker_bytes = file.read()

        pdf_bytes = generar_pdf_factura(
            xml_timbrado=xml_timbrado_bytes,
            tipo_comprobante="I",
            xml_anticipo=xml_filemaker_bytes
        )

        guardar_pdf(pdf_bytes, tipo_comprobante="anticipo")

        fecha_actual = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Armar ZIP con PDF y XML
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(f"CFDI_Anticipo_{fecha_actual}.xml", xml_timbrado_bytes)
            zip_file.writestr(f"CFDI_Anticipo_{fecha_actual}.pdf", pdf_bytes)
        zip_buffer.seek(0)

        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"CFDI_Anticipo_{fecha_actual}.zip"
        )

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

@app.route("/cancelar-cfdi-ruta", methods=["GET"])
def cancelar_cfdi_ruta():
    try:
        uuid = request.args.get("uuid")
        rfc_emisor = request.args.get("rfc_emisor")
        motivo_cancelacion = request.args.get("motivo_cancelacion")
        uuid_sustituto = request.args.get("uuid_sustituto", "")
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
            # csd_password='12345678a'
            csd_password= PASSWORD_KEY
        )

        if error:
            return jsonify({"success": False, "error": error}), 400

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
            return jsonify({"success": False, "error": error_timbrado}), 400

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