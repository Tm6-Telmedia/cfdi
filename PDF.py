from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional
import os
import base64
from datetime import datetime
from lxml import etree
import qrcode
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# Importar constantes desde API.py para evitar duplicación
try:
    from API import CFDI_NS, PAGO_NS, TFD_NS
except ImportError:
    # Fallback si no se puede importar (no debería ocurrir en producción)
    CFDI_NS = "http://www.sat.gob.mx/cfd/4"
    PAGO_NS = "http://www.sat.gob.mx/Pagos20"
    TFD_NS = "http://www.sat.gob.mx/TimbreFiscalDigital"

# Constantes
FILEMAKER_NAMESPACE = "http://www.filemaker.com/fmpdsoresult"

# CONFIGURACIÓN
RUTA_LOGO = r"Logo.jpg"
QR_SAT_BASE_URL = "https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx"

# Mapeo de códigos de moneda a nombres completos
NOMBRES_MONEDAS = {
    "USD": "Dólar",
    "EUR": "Euro", 
    "JPY": "Yen",
    "GBP": "Libra Esterlina",
    "CNY": "Yuan",
    "CAD": "Dólar Canadiense", 
    "CHF": "Franco Suizo",
    "MXN": "PESOS MN",
    "XXX": "PESOS MN"  # Para complementos de pago, por defecto mostrar PESOS MN
}

# Mapeo de códigos de productos y servicios del SAT
# Solo el código que necesitas actualmente
CODIGOS_PROD_SERV = {
    "84111506": "Servicios de facturación"
}

# Mapeo de códigos de forma de pago del SAT
# Solo los códigos que necesitas actualmente
CODIGOS_FORMA_PAGO = {
    "02": "02: Cheque nominativo",
    "03": "03: Transferencia electrónica de fondos (para PUE o PPD)",
    "04": "04: Tarjeta de crédito",
    "28": "28: Tarjeta de débito",
    "99": "99: Por definir (usualmente con PPD)"
}

# Configuración del encabezado
HEADER_CONFIG = {
    "logo": {
        "x": 50,
        "y_offset": 40,
        "width": 100,
        "height": 50
    },
    "company_info": {
        "x": 170,
        "y_start_offset": 10,
        "line_spacing": 12,
        "fonts": {
            "company_name": ("Helvetica-Bold", 10),
            "description": ("Helvetica", 8),
            "details": ("Helvetica", 7)
        }
    },
    "right_panel": {
        "title_x": 420,
        "date_x": 430,
        "qr_x": 480,
        "qr_y_offset": 70,
        "qr_size": 70
    }
}

# Configuración de colores y fuentes
PDF_CONFIG = {
    "colors": {
        "header_bg": colors.Color(0.216, 0.373, 0.522),  # #375F85
        "header_text": colors.white,
        "client_bg": colors.Color(0.216, 0.373, 0.522),  # #375F85
        "border": colors.black,
        "text": colors.black
    },
    "fonts": {
        "title": 14,
        "header": 10,
        "body": 9,
        "small": 8
    }
}

class PDFGenerationError(Exception):
    """Excepción para errores en la generación de PDF"""
    pass

@dataclass
class ConceptoCFDI:
    """Representa un concepto del CFDI"""
    clave_prod_serv: str
    cantidad: Decimal
    unidad: str
    descripcion: str
    valor_unitario: Decimal
    importe: Decimal
    descuento: Decimal = Decimal('0')

@dataclass
class ImpuestoCFDI:
    """Representa un impuesto del CFDI"""
    base: Decimal
    impuesto: str
    tipo_factor: str
    tasa_cuota: str
    importe: Decimal

@dataclass
class DocumentoRelacionadoData:
    """Datos de documentos relacionados para complementos de pago"""
    id_documento: str
    serie: str
    folio: str
    moneda: str
    equivalencia_dr: str
    num_parcialidad: str
    imp_saldo_ant: Decimal
    imp_pagado: Decimal
    imp_saldo_insoluto: Decimal
    objeto_imp_dr: str

@dataclass
class ComplementoPagoData:
    """Datos específicos para Complemento de Pago"""
    fecha_pago: str
    forma_pago: str
    moneda: str
    monto: Decimal
    documento_relacionado_uuid: str
    saldo_anterior: Decimal
    importe_pagado: Decimal
    saldo_insoluto: Decimal

@dataclass
class AplicacionAnticipoData:
    """Datos específicos para Aplicación de Anticipo"""
    monto_anticipo_aplicado: Decimal
    descripcion_anticipo: str

@dataclass
class CFDIData:
    """Estructura de datos completa del CFDI para PDF"""
    # Datos obligatorios del SAT
    folio_fiscal: str
    metodo_pago: str
    forma_pago: str
    uso_cfdi: str
    lugar_emision: str
    numero_serie_csd: str
    fecha_emision: str
    tipo_comprobante: str
    
    # Datos del emisor
    emisor_rfc: str
    emisor_nombre: str
    emisor_regimen: str
    
    # Datos del receptor
    receptor_rfc: str
    receptor_nombre: str
    receptor_uso_cfdi: str
    
    # Datos financieros
    subtotal: Decimal
    descuento: Decimal
    total: Decimal
    moneda: str
    
    # Conceptos e impuestos
    conceptos: List[ConceptoCFDI]
    impuestos: List[ImpuestoCFDI]
    
    # Timbre fiscal
    uuid: str
    fecha_timbrado: str
    sello_sat: str
    
    # Campos opcionales (con valores por defecto al final)
    serie: str = ""  # Serie del comprobante
    folio: str = ""  # Folio del comprobante
    sello_cfdi: str = ""  # Sello del CFDI (diferente al del SAT)
    rfc_prov_certif: str = ""  # RFC del proveedor de certificación
    uuid_relacionado: str = ""  # UUID del documento relacionado (para aplicación de anticipo)
    no_certificado_sat: str = ""  # Número de certificado del SAT
    emisor_direccion: str = ""
    emisor_contacto: str = ""
    receptor_regimen: str = ""
    receptor_domicilio: str = ""
    tipo_cambio: str = "1"  # Tipo de cambio, por defecto 1 para MXN
    
    # Datos específicos por tipo
    datos_complemento_pago: Optional[ComplementoPagoData] = None
    datos_aplicacion_anticipo: Optional[AplicacionAnticipoData] = None
    documentos_relacionados: List[DocumentoRelacionadoData] = None

def obtener_descripcion_clave_prod_serv(clave: str) -> str:
    """Obtiene la descripción de la clave de producto/servicio"""
    return CODIGOS_PROD_SERV.get(clave, "Servicio no especificado")

def obtener_descripcion_forma_pago(codigo: str) -> str:
    """Obtiene la descripción de la forma de pago"""
    return CODIGOS_FORMA_PAGO.get(codigo, f"{codigo}: Forma de pago no especificada")

def extraer_datos_receptor_filemaker(xml_filemaker: bytes) -> dict:
    """
    Extrae datos del receptor del archivo FileMaker
    """
    try:
        tree = etree.fromstring(xml_filemaker)
        
        # Buscar el primer ROW
        row = tree.find(f".//{{{FILEMAKER_NAMESPACE}}}ROW")
        if row is None:
            row = tree.find(".//ROW")
        
        if row is None:
            return {}
        
        receptor_data = {}
        
        # Mapeo de campos FileMaker a datos del receptor
        campos_receptor = {
            "Receptor_Nombre_Cliente_opc": "nombre",
            "Receptor_RFC": "rfc", 
            "Receptor_CP_opc": "domicilio",  # Este es el CP correcto
            "Receptor_UsoCFDI": "uso_cfdi",
            "Receptor_regimen": "regimen"
        }
        
        # Buscar campos del receptor
        for child in row:
            tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            
            if tag_name in campos_receptor:
                data_node = child.find(f"{{{FILEMAKER_NAMESPACE}}}DATA") if FILEMAKER_NAMESPACE else child.find("DATA")
                if data_node is not None and data_node.text:
                    campo_destino = campos_receptor[tag_name]
                    receptor_data[campo_destino] = data_node.text.strip()
        
        print(f"✓ Datos del receptor extraídos de FileMaker: {receptor_data}")
        return receptor_data
        
    except Exception as e:
        print(f"⚠ Error extrayendo datos del receptor de FileMaker: {e}")
        return {}

def extraer_datos_anticipo(xml_productos: bytes, xml_aplicacion: bytes) -> CFDIData:
    """
    Extrae datos de anticipo combinando dos XMLs:
    - xml_productos: XML con conceptos, cliente, importes (puede ser CFDI o datos de FileMaker)
    - xml_aplicacion: XML con UUID del anticipo (CFDI timbrado)
    """
    try:
        # Verificar si xml_productos es un CFDI válido o datos de FileMaker
        try:
            tree_productos = etree.fromstring(xml_productos)
            root_tag = tree_productos.tag
            
            # Si es un archivo de FileMaker (FMPDSORESULT), usar el XML de aplicación como base
            if "FMPDSORESULT" in root_tag or "FMPXMLRESULT" in root_tag:
                print("✓ Detectado archivo FileMaker como xml_productos, extrayendo conceptos")
                # Usar el XML de aplicación (que es un CFDI válido) como base
                cfdi_data = extraer_datos_xml(xml_aplicacion)
                
                # IMPORTANTE: Sobrescribir datos del receptor con los del FileMaker
                receptor_filemaker = extraer_datos_receptor_filemaker(xml_productos)
                if receptor_filemaker:
                    if "nombre" in receptor_filemaker:
                        cfdi_data.receptor_nombre = receptor_filemaker["nombre"]
                    if "rfc" in receptor_filemaker:
                        cfdi_data.receptor_rfc = receptor_filemaker["rfc"]
                    if "domicilio" in receptor_filemaker:
                        cfdi_data.receptor_domicilio = receptor_filemaker["domicilio"]  # CP correcto del FileMaker
                    if "uso_cfdi" in receptor_filemaker:
                        cfdi_data.receptor_uso_cfdi = receptor_filemaker["uso_cfdi"]
                    if "regimen" in receptor_filemaker:
                        cfdi_data.receptor_regimen = receptor_filemaker["regimen"]
                    print(f"✓ Datos del receptor actualizados desde FileMaker")
                
                # Extraer conceptos del archivo FileMaker
                conceptos_filemaker = extraer_conceptos_filemaker(xml_productos)
                if conceptos_filemaker:
                    cfdi_data.conceptos = conceptos_filemaker
                    print(f"✓ Extraídos {len(conceptos_filemaker)} conceptos del archivo FileMaker")
                    
                    # Recalcular subtotal basado en los conceptos de FileMaker
                    nuevo_subtotal = sum(concepto.importe for concepto in conceptos_filemaker)
                    cfdi_data.subtotal = nuevo_subtotal
                    
                    # Recalcular total (subtotal + impuestos)
                    # Asumir IVA 16% sobre el subtotal
                    iva_calculado = nuevo_subtotal * Decimal('0.16')
                    cfdi_data.total = nuevo_subtotal + iva_calculado
                    
                    print(f"✓ Subtotal recalculado: {nuevo_subtotal}")
                    print(f"✓ Total recalculado: {cfdi_data.total}")
                
                # IMPORTANTE: Buscar el UUID relacionado en CfdiRelacionados del XML de aplicación
                tree_aplicacion = etree.fromstring(xml_aplicacion)
                uuid_relacionado_encontrado = ""
                for elem in tree_aplicacion.iter():
                    if elem.tag.endswith("CfdiRelacionado"):
                        uuid_relacionado_encontrado = elem.get("UUID") or ""
                        if uuid_relacionado_encontrado:
                            cfdi_data.uuid_relacionado = uuid_relacionado_encontrado
                            print(f"✓ UUID relacionado encontrado en CfdiRelacionados: {uuid_relacionado_encontrado}")
                            break
                
                if not uuid_relacionado_encontrado:
                    print("⚠ No se encontró UUID relacionado en CfdiRelacionados")
                
            else:
                # Es un CFDI válido, procesar normalmente
                print("✓ xml_productos es un CFDI válido, procesando normalmente")
                cfdi_data = extraer_datos_xml(xml_productos)
                
                # Extraer UUID y lugar de emisión del XML de aplicación
                tree_aplicacion = etree.fromstring(xml_aplicacion)
                
                # Buscar el UUID relacionado en el nodo CfdiRelacionado
                uuid_relacionado = ""
                for elem in tree_aplicacion.iter():
                    if elem.tag.endswith("CfdiRelacionado"):
                        uuid_relacionado = elem.get("UUID") or ""
                        print(f"✓ Nodo CfdiRelacionado encontrado con UUID: {uuid_relacionado}")
                        break
                
                if not uuid_relacionado:
                    print("⚠ No se encontró nodo CfdiRelacionado o no tiene UUID")
                
                # Buscar el comprobante del XML de aplicación para extraer LugarExpedicion
                comprobante_aplicacion = tree_aplicacion
                if comprobante_aplicacion.tag.endswith("Comprobante"):
                    # Extraer lugar de emisión del XML que tiene el UUID
                    lugar_emision_uuid = comprobante_aplicacion.get("LugarExpedicion") or ""
                    if lugar_emision_uuid:
                        cfdi_data.lugar_emision = lugar_emision_uuid
                        print(f"✓ Lugar de emisión actualizado desde XML con UUID: {lugar_emision_uuid}")
                
                # Buscar el UUID del anticipo en el XML de aplicación
                uuid_anticipo = ""
                for elem in tree_aplicacion.iter():
                    if elem.tag.endswith("TimbreFiscalDigital"):
                        uuid_anticipo = elem.get("UUID") or ""
                        break
                
                # Buscar datos específicos del anticipo en el XML de aplicación
                monto_anticipo = Decimal("0")
                
                # Buscar en conceptos del XML de aplicación
                for elem in tree_aplicacion.iter():
                    if elem.tag.endswith("Concepto"):
                        monto_anticipo = Decimal(elem.get("Importe", "0"))
                        break
                
                # Crear datos específicos de aplicación de anticipo
                cfdi_data.datos_aplicacion_anticipo = AplicacionAnticipoData(
                    monto_anticipo_aplicado=monto_anticipo,
                    descripcion_anticipo=f"Aplicación de anticipo - UUID: {uuid_anticipo}"
                )
                
                # Actualizar el UUID principal con el del anticipo si es necesario
                if uuid_anticipo:
                    cfdi_data.uuid = uuid_anticipo
                
                # Agregar el UUID relacionado
                if uuid_relacionado:
                    cfdi_data.uuid_relacionado = uuid_relacionado
        
        except etree.XMLSyntaxError as xml_error:
            print(f"⚠ Error parseando xml_productos como XML: {xml_error}")
            print("✓ Usando xml_aplicacion como única fuente de datos")
            # Si no se puede parsear xml_productos, usar solo xml_aplicacion
            cfdi_data = extraer_datos_xml(xml_aplicacion)
        
        return cfdi_data
        
    except Exception as e:
        raise PDFGenerationError(f"Error extrayendo datos de anticipo: {str(e)}")

def extraer_conceptos_filemaker(xml_filemaker: bytes) -> List[ConceptoCFDI]:
    """
    Extrae conceptos del archivo FileMaker FMPDSORESULT
    """
    conceptos = []
    try:
        tree = etree.fromstring(xml_filemaker)
        print(f"✓ Parseando archivo FileMaker, root tag: {tree.tag}")
        
        # El namespace de FileMaker
        fm_ns = "http://www.filemaker.com/fmpdsoresult"
        
        # Buscar todos los ROW (filas de datos) con namespace
        rows = tree.findall(f".//{{{fm_ns}}}ROW")
        if not rows:
            # Intentar sin namespace
            rows = tree.findall(".//ROW")
        
        print(f"✓ Encontradas {len(rows)} filas ROW")
        
        for i, row in enumerate(rows):
            print(f"✓ Procesando ROW {i+1}")
            
            # Extraer datos del concepto de esta fila
            concepto_data = {}
            
            # Buscar todos los elementos hijo
            for child in row:
                tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                
                if tag_name in ["ClaveProdServ", "cantidad", "Clave_unidad", "unidad", "ConceptoItem", "Monto", "Importe", "DescuentoItem"]:
                    # Extraer el valor - puede estar en texto directo o en nodo DATA
                    valor = None
                    if child.text and child.text.strip():
                        valor = child.text.strip()
                    else:
                        # Buscar nodo DATA (con o sin namespace)
                        data_node = child.find(f"{{{fm_ns}}}DATA") if fm_ns else None
                        if data_node is None:
                            data_node = child.find("DATA")
                        
                        if data_node is not None and data_node.text:
                            valor = data_node.text.strip()
                    
                    if valor:
                        concepto_data[tag_name] = valor
                        print(f"    {tag_name}: {valor}")
            
            # Crear concepto si tiene los datos mínimos
            if "ConceptoItem" in concepto_data and "Importe" in concepto_data:
                try:
                    concepto = ConceptoCFDI(
                        clave_prod_serv=concepto_data.get("ClaveProdServ", "84111506"),
                        cantidad=Decimal(concepto_data.get("cantidad", "1")),
                        unidad=concepto_data.get("Clave_unidad", "EA"),
                        descripcion=concepto_data.get("ConceptoItem", "Concepto"),
                        valor_unitario=Decimal(concepto_data.get("Monto", "0")),
                        importe=Decimal(concepto_data.get("Importe", "0")),
                        descuento=Decimal(concepto_data.get("DescuentoItem", "0"))
                    )
                    conceptos.append(concepto)
                    print(f"✓ Concepto FileMaker creado: {concepto.descripcion} - ${concepto.importe}")
                except Exception as e:
                    print(f"⚠ Error creando concepto: {e}")
                    print(f"   Datos: {concepto_data}")
            else:
                print(f"⚠ ROW sin datos suficientes para concepto")
                print(f"   Datos encontrados: {list(concepto_data.keys())}")
                
                # Debug: mostrar todos los elementos de esta fila
                print("   Elementos en esta fila:")
                for child in row:
                    tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    print(f"     - {tag_name}")
        
        print(f"✓ Total conceptos extraídos: {len(conceptos)} de {len(rows)} filas")
        return conceptos
        
    except Exception as e:
        print(f"Error extrayendo conceptos de FileMaker: {e}")
        import traceback
        traceback.print_exc()
        return []

def extraer_datos_xml(xml_bytes: bytes) -> CFDIData:

    try:
        tree = etree.fromstring(xml_bytes)
        
        # Buscar nodo Comprobante
        comprobante = tree
        
        # Extraer datos básicos del comprobante
        folio_fiscal = ""
        fecha_timbrado = ""
        sello_sat = ""
        sello_cfdi = ""
        uuid = ""
        rfc_prov_certif = ""
        no_certificado_sat = ""
        
        # Extraer sello del CFDI del comprobante principal
        sello_cfdi = comprobante.get("Sello") or ""

        
        # Buscar TimbreFiscalDigital con mejor manejo de datos
        timbre_encontrado = False
        for elem in tree.iter():
            if elem.tag.endswith("TimbreFiscalDigital"):
                uuid = elem.get("UUID") or ""
                fecha_timbrado = elem.get("FechaTimbrado") or ""
                sello_sat = elem.get("SelloSAT") or ""
                rfc_prov_certif = elem.get("RfcProvCertif") or ""
                no_certificado_sat = elem.get("NoCertificadoSAT") or ""
                folio_fiscal = uuid  # UUID completo como folio fiscal
                timbre_encontrado = True

                break
        

        
        # Datos del comprobante con mejor manejo de valores
        tipo_comprobante = comprobante.get("TipoDeComprobante") or ""
        fecha_emision = comprobante.get("Fecha") or ""
        subtotal = Decimal(comprobante.get("SubTotal") or "0")
        descuento = Decimal(comprobante.get("Descuento") or "0")
        total = Decimal(comprobante.get("Total") or "0")
        moneda = comprobante.get("Moneda") or "MXN"
        tipo_cambio = comprobante.get("TipoCambio") or "1"  # Extraer tipo de cambio del XML
        metodo_pago = comprobante.get("MetodoPago") or ""
        forma_pago = comprobante.get("FormaPago") or ""
        lugar_emision = comprobante.get("LugarExpedicion") or ""
        numero_serie_csd = comprobante.get("NoCertificado") or ""
        serie = comprobante.get("Serie") or ""
        folio = comprobante.get("Folio") or ""
        
        # Para complementos de pago (tipo P), buscar FormaDePagoP en el nodo Pago
        if tipo_comprobante == "P" and not forma_pago:
            for elem in tree.iter():
                if elem.tag.endswith("Pago"):
                    forma_pago_p = elem.get("FormaDePagoP")
                    if forma_pago_p:
                        forma_pago = forma_pago_p
                        print(f"✓ FormaDePagoP extraída: {forma_pago}")
                        break
        

        
        # Buscar Emisor
        emisor = None
        for elem in tree.iter():
            if elem.tag.endswith("Emisor"):
                emisor = elem
                break
        
        if emisor is None:
            raise PDFGenerationError("No se encontró el nodo Emisor")
        
        emisor_rfc = emisor.get("Rfc") or ""
        emisor_nombre = emisor.get("Nombre") or ""
        emisor_regimen = emisor.get("RegimenFiscal") or ""
        

        
        # Buscar Receptor
        receptor = None
        for elem in tree.iter():
            if elem.tag.endswith("Receptor"):
                receptor = elem
                break
        
        if receptor is None:
            raise PDFGenerationError("No se encontró el nodo Receptor")
        
        receptor_rfc = receptor.get("Rfc") or ""
        receptor_nombre = receptor.get("Nombre") or ""
        receptor_uso_cfdi = receptor.get("UsoCFDI") or ""
        uso_cfdi = receptor_uso_cfdi
        
        # Extraer campos adicionales del receptor que estaban faltando
        receptor_regimen = receptor.get("RegimenFiscal") or receptor.get("RegimenFiscalReceptor") or ""
        receptor_domicilio = receptor.get("DomicilioFiscal") or receptor.get("DomicilioFiscalReceptor") or ""
        
        # También buscar en atributos alternativos comunes del SAT
        if not receptor_regimen:
            receptor_regimen = receptor.get("Regimen") or ""
        if not receptor_domicilio:
            receptor_domicilio = receptor.get("CodigoPostal") or receptor.get("CP") or ""
        

        
        # Extraer conceptos
        conceptos = []
        for elem in tree.iter():
            if elem.tag.endswith("Concepto"):
                concepto = ConceptoCFDI(
                    clave_prod_serv=elem.get("ClaveProdServ", ""),
                    cantidad=Decimal(elem.get("Cantidad", "0")),
                    unidad=elem.get("ClaveUnidad", ""),
                    descripcion=elem.get("Descripcion", ""),
                    valor_unitario=Decimal(elem.get("ValorUnitario", "0")),
                    importe=Decimal(elem.get("Importe", "0")),
                    descuento=Decimal(elem.get("Descuento", "0"))
                )
                conceptos.append(concepto)
        
        # Extraer impuestos
        impuestos = []
        for elem in tree.iter():
            if elem.tag.endswith("Traslado"):
                impuesto = ImpuestoCFDI(
                    base=Decimal(elem.get("Base", "0")),
                    impuesto=elem.get("Impuesto", ""),
                    tipo_factor=elem.get("TipoFactor", ""),
                    tasa_cuota=elem.get("TasaOCuota", ""),
                    importe=Decimal(elem.get("Importe", "0"))
                )
                impuestos.append(impuesto)
        
        # Datos específicos por tipo
        datos_complemento_pago = None
        datos_aplicacion_anticipo = None
        documentos_relacionados = []
        
        if tipo_comprobante == "P":
            # Extraer datos de Complemento de Pago y documentos relacionados
            for elem in tree.iter():
                if elem.tag.endswith("Pago"):
                    # Buscar todos los DoctoRelacionado
                    for child in elem:
                        if child.tag.endswith("DoctoRelacionado"):
                            documento = DocumentoRelacionadoData(
                                id_documento=child.get("IdDocumento", ""),
                                serie=child.get("Serie", ""),
                                folio=child.get("Folio", ""),
                                moneda=child.get("MonedaDR", "MXN"),
                                equivalencia_dr=child.get("EquivalenciaDR", "1"),
                                num_parcialidad=child.get("NumParcialidad", "1"),
                                imp_saldo_ant=Decimal(child.get("ImpSaldoAnt", "0")),
                                imp_pagado=Decimal(child.get("ImpPagado", "0")),
                                imp_saldo_insoluto=Decimal(child.get("ImpSaldoInsoluto", "0")),
                                objeto_imp_dr=child.get("ObjetoImpDR", "01")
                            )
                            documentos_relacionados.append(documento)
                    
                    # Crear datos de complemento de pago (para compatibilidad)
                    if documentos_relacionados:
                        primer_doc = documentos_relacionados[0]
                        datos_complemento_pago = ComplementoPagoData(
                            fecha_pago=elem.get("FechaPago", ""),
                            forma_pago=elem.get("FormaDePagoP", ""),
                            moneda=elem.get("MonedaP", "MXN"),
                            monto=Decimal(elem.get("Monto", "0")),
                            documento_relacionado_uuid=primer_doc.id_documento,
                            saldo_anterior=primer_doc.imp_saldo_ant,
                            importe_pagado=primer_doc.imp_pagado,
                            saldo_insoluto=primer_doc.imp_saldo_insoluto
                        )
                    break
        
        elif tipo_comprobante == "I" and descuento > 0:
            # Es una Aplicación de Anticipo
            datos_aplicacion_anticipo = AplicacionAnticipoData(
                monto_anticipo_aplicado=descuento,
                descripcion_anticipo="Aplicación de anticipo recibido"
            )
        
        # Buscar UUID relacionado en CfdiRelacionados
        uuid_relacionado = ""
        for elem in tree.iter():
            if elem.tag.endswith("CfdiRelacionado"):
                uuid_relacionado = elem.get("UUID") or ""
                if uuid_relacionado:
                    print(f"✓ UUID relacionado encontrado: {uuid_relacionado}")
                    break
        
        return CFDIData(
            folio_fiscal=folio_fiscal,
            metodo_pago=metodo_pago,
            forma_pago=forma_pago,
            uso_cfdi=uso_cfdi,
            lugar_emision=lugar_emision,
            numero_serie_csd=numero_serie_csd,
            fecha_emision=fecha_emision,
            tipo_comprobante=tipo_comprobante,
            emisor_rfc=emisor_rfc,
            emisor_nombre=emisor_nombre,
            emisor_regimen=emisor_regimen,
            receptor_rfc=receptor_rfc,
            receptor_nombre=receptor_nombre,
            receptor_uso_cfdi=receptor_uso_cfdi,
            receptor_regimen=receptor_regimen,
            receptor_domicilio=receptor_domicilio,
            subtotal=subtotal,
            descuento=descuento,
            total=total,
            moneda=moneda,
            tipo_cambio=tipo_cambio,
            conceptos=conceptos,
            impuestos=impuestos,
            datos_complemento_pago=datos_complemento_pago,
            datos_aplicacion_anticipo=datos_aplicacion_anticipo,
            documentos_relacionados=documentos_relacionados,
            uuid=uuid,
            uuid_relacionado=uuid_relacionado,  # Agregar UUID relacionado
            fecha_timbrado=fecha_timbrado,
            sello_sat=sello_sat,
            sello_cfdi=sello_cfdi,
            rfc_prov_certif=rfc_prov_certif,
            no_certificado_sat=no_certificado_sat,
            serie=serie,
            folio=folio
        )
        
    except Exception as e:
        raise PDFGenerationError(f"Error extrayendo datos del XML: {str(e)}")

def render_logo(canvas, y_position: float) -> bool:
    
    try:
        logo_config = HEADER_CONFIG["logo"]
        path = RUTA_LOGO
        

        
        if os.path.exists(path):
            x_pos = logo_config["x"]
            y_pos = y_position - logo_config["y_offset"]
            width = logo_config["width"]
            height = logo_config["height"]
            

            
            canvas.drawImage(
                path, 
                x_pos, 
                y_pos, 
                width=width, 
                height=height, 
                preserveAspectRatio=True,
                mask='auto'
            )

            return True
        else:

            return False
    except Exception as e:
        print(f"Error renderizando logo: {e}")
        import traceback
        traceback.print_exc()
        return False

def render_company_info(canvas, y_position: float, cfdi_data: CFDIData):
 

    
    # LOGO (lado izquierdo)
    logo_rendered = render_logo(canvas, y_position)
    
    # Descripción debajo del logo 
    x_logo = 50
    y_logo_desc = y_position - 35  
    canvas.setFont("Helvetica", 6)  
    canvas.drawString(x_logo, y_logo_desc, "Infraestructura de Comunicaciones")
    canvas.drawString(x_logo, y_logo_desc - 6, "y de Tecnologías de la Información")
    
    # INFORMACIÓN DE LA EMPRESA 
    x_info = 200 
    y_info = y_position - 10
    spacing = 8  
    
    # TELECOMUNICACIONES MULTIMEDIA (texto normal negro)
    draw_text_with_style(canvas, x_info, y_info, "TELECOMUNICACIONES MULTIMEDIA")
    
    # RFC (en negrita)
    y_info -= spacing
    draw_text_with_style(canvas, x_info, y_info, "RFC: TMU091016Q10", "Helvetica-Bold")
    
    # Régimen fiscal (en negrita)
    y_info -= spacing
    draw_text_with_style(canvas, x_info, y_info, "RÉGIMEN GENERAL DE LEY PERSONAS MORALES", "Helvetica-Bold")
    
    # Email (texto normal negro, sin enlace)
    y_info -= spacing
    draw_text_with_style(canvas, x_info, y_info, "contacto@telmedia.com.mx")
    
    # Página web (texto normal negro, sin enlace)
    y_info -= spacing
    draw_text_with_style(canvas, x_info, y_info, "https://www.telmedia.com.mx")
    
    # Teléfono (texto normal negro)
    y_info -= spacing
    draw_text_with_style(canvas, x_info, y_info, "+52 (55) 9035-9505")
    


def render_right_panel(canvas, y_position: float, cfdi_data: CFDIData, qr_buffer: BytesIO, width: float):

    right_config = HEADER_CONFIG["right_panel"]
    
    # Título FACTURA
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawString(right_config["title_x"], y_position - 15, "FACTURA")
    
    # Fecha
    canvas.setFont("Helvetica", 8)
    fecha_formato = cfdi_data.fecha_emision[:10] if cfdi_data.fecha_emision else ""
    canvas.drawString(right_config["date_x"], y_position - 30, fecha_formato)
    
    # Código QR
    if qr_buffer and qr_buffer.getvalue():
        try:
            qr_buffer.seek(0)
            from reportlab.lib.utils import ImageReader
            qr_image = ImageReader(qr_buffer)
            canvas.drawImage(
                qr_image, 
                width - 120, 
                y_position - right_config["qr_y_offset"], 
                width=right_config["qr_size"], 
                height=right_config["qr_size"]
            )
        except Exception as e:
            print(f"Error dibujando QR: {e}")

def set_font_and_color(canvas, font_name: str, font_size: int, color=colors.black):
    """Función auxiliar para establecer fuente y color de una vez"""
    canvas.setFont(font_name, font_size)
    canvas.setFillColor(color)

def draw_text_with_style(canvas, x: float, y: float, text: str, font_name: str = "Helvetica", font_size: int = 7, color=colors.black):
    """Función auxiliar para dibujar texto con estilo específico"""
    set_font_and_color(canvas, font_name, font_size, color)
    canvas.drawString(x, y, text)

def draw_label_with_content(canvas, x: float, y: float, label: str, content: str, font_size: int = 7):
    """Función auxiliar para dibujar etiqueta en negrita seguida de contenido normal"""
    # Dibujar etiqueta en negrita
    draw_text_with_style(canvas, x, y, label, "Helvetica-Bold", font_size)
    # Calcular posición para el contenido
    label_width = canvas.stringWidth(label, "Helvetica-Bold", font_size)
    # Dibujar contenido en texto normal
    draw_text_with_style(canvas, x + label_width, y, content, "Helvetica", font_size)
    return x + label_width + canvas.stringWidth(content, "Helvetica", font_size)

def draw_multiline_text(canvas, x: float, y: float, text: str, max_chars_per_line: int, font_size: int = 6):
    """Función auxiliar para dibujar texto largo en múltiples líneas"""
    set_font_and_color(canvas, "Helvetica", font_size)
    current_y = y
    
    if len(text) <= max_chars_per_line:
        canvas.drawString(x, current_y, text)
        return current_y - 8
    
    # Dividir texto en líneas
    lines = []
    remaining_text = text
    while remaining_text:
        if len(remaining_text) <= max_chars_per_line:
            lines.append(remaining_text)
            break
        lines.append(remaining_text[:max_chars_per_line])
        remaining_text = remaining_text[max_chars_per_line:]
    
    # Dibujar cada línea
    for line in lines:
        canvas.drawString(x, current_y, line)
        current_y -= 8
    
    return current_y

def numero_a_letras(numero: float) -> str:
    """Convierte un número a su representación en letras para CFDI"""
    try:
        entero = int(numero)
        centavos = int(round((numero - entero) * 100))
        
        if entero == 0:
            return "CERO PESOS CON 00/100 M.N."
        
        # Diccionarios para conversión
        unidades = ["", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE"]
        decenas = ["", "", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
        especiales = {10: "DIEZ", 11: "ONCE", 12: "DOCE", 13: "TRECE", 14: "CATORCE", 15: "QUINCE", 
                     16: "DIECISEIS", 17: "DIECISIETE", 18: "DIECIOCHO", 19: "DIECINUEVE"}
        centenas = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS", 
                   "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"]
        
        def convertir_centenas(num):
            if num == 0:
                return ""
            elif num == 100:
                return "CIEN"
            elif num < 10:
                return unidades[num]
            elif num < 20:
                return especiales.get(num, "")
            elif num < 100:
                d = num // 10
                u = num % 10
                if u == 0:
                    return decenas[d]
                else:
                    return f"{decenas[d]} Y {unidades[u]}"
            else:
                c = num // 100
                resto = num % 100
                texto = centenas[c]
                if resto > 0:
                    texto += f" {convertir_centenas(resto)}"
                return texto
        
        def convertir_miles(num):
            if num == 0:
                return ""
            elif num == 1:
                return "MIL"
            elif num < 1000:
                return f"{convertir_centenas(num)} MIL"
            else:
                miles = num // 1000
                resto = num % 1000
                texto_miles = convertir_centenas(miles)
                if miles == 1:
                    texto = "UN MIL"
                else:
                    texto = f"{texto_miles} MIL"
                if resto > 0:
                    texto += f" {convertir_centenas(resto)}"
                return texto
        
        # Convertir el número
        if entero < 1000:
            texto = convertir_centenas(entero)
        elif entero < 1000000:
            miles = entero // 1000
            resto = entero % 1000
            texto = convertir_miles(miles * 1000)
            if resto > 0:
                if miles > 0:
                    texto += f" {convertir_centenas(resto)}"
                else:
                    texto = convertir_centenas(resto)
        else:
            # Para números muy grandes, usar formato simplificado
            millones = entero // 1000000
            resto = entero % 1000000
            if millones == 1:
                texto = "UN MILLON"
            else:
                texto = f"{convertir_centenas(millones)} MILLONES"
            if resto > 0:
                if resto >= 1000:
                    miles = resto // 1000
                    unidades_resto = resto % 1000
                    if miles > 0:
                        texto += f" {convertir_miles(miles * 1000)}"
                    if unidades_resto > 0:
                        texto += f" {convertir_centenas(unidades_resto)}"
                else:
                    texto += f" {convertir_centenas(resto)}"
        
        # Agregar "PESOS" y centavos
        if entero == 1:
            return f"UN PESO CON {centavos:02d}/100 M.N."
        else:
            return f"{texto} PESOS CON {centavos:02d}/100 M.N."
        
    except Exception as e:
        print(f"Error convirtiendo número a letras: {e}")
        return f"{numero:,.2f} PESOS CON 00/100 M.N."

def generar_codigo_qr(cfdi_data: CFDIData) -> BytesIO:
    
    try:
        from decimal import Decimal, ROUND_HALF_UP

        total_fiscal = cfdi_data.total.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

        # Construir URL del SAT
        params = {
            "id": cfdi_data.uuid,
            "re": cfdi_data.emisor_rfc,
            "rr": cfdi_data.receptor_rfc,
            "tt": f"{total_fiscal:.6f}",
            "fe": cfdi_data.sello_cfdi[-8:] if cfdi_data.sello_cfdi else ""
        }
        
        url_params = "&".join([f"{k}={v}" for k, v in params.items()])
        qr_url = f"{QR_SAT_BASE_URL}?{url_params}"
        
        # Generar QR
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_url)
        qr.make(fit=True)
        
        # Crear imagen
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Convertir a BytesIO
        img_buffer = BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        return img_buffer
        
    except Exception as e:
        print(f"Error generando código QR: {e}")
        # Retornar QR vacío en caso de error
        return BytesIO()

def generar_pdf_factura(xml_timbrado: bytes, tipo_comprobante: str, xml_anticipo: bytes = None) -> bytes:
    """
    Genera PDF de factura desde XML timbrado
    
    Args:
        xml_timbrado: XML principal timbrado
        tipo_comprobante: Tipo de comprobante (I, P, E)
        xml_anticipo: XML adicional para anticipos (opcional)
    
    Returns:
        bytes: PDF generado
    """

    try:
        # Determinar si es anticipo y extraer datos apropiadamente
        if tipo_comprobante == "I" and xml_anticipo is not None:
            # Es aplicación de anticipo - usar ambos XMLs (ambos son Ingreso)
            cfdi_data = extraer_datos_anticipo(xml_anticipo, xml_timbrado)
        else:
            # Proceso normal - usar solo un XML
            cfdi_data = extraer_datos_xml(xml_timbrado)
        
        # Generar código QR
        qr_buffer = generar_codigo_qr(cfdi_data)
        
        # Crear PDF en memoria
        pdf_buffer = BytesIO()
        
        # Crear documento PDF con canvas personalizado
        from reportlab.pdfgen.canvas import Canvas
        
        c = Canvas(pdf_buffer, pagesize=letter)
        width, height = letter
        
        # Configurar fuentes
        c.setFont("Helvetica", 9)
        
        # HEADER SECTION
        y_position = height - 30
        

        # Renderizar información de la empresa 
        render_company_info(c, y_position, cfdi_data)

        
        # Renderizar panel derecho (título, fecha, QR)
        render_right_panel(c, y_position, cfdi_data, qr_buffer, width)
        
        # Espacio después del header (ajustado para no chocar con QR)
        y_position -= 60
        
        # DATOS FISCALES SECTION - formato como en la imagen 
        y_position -= 25
        
        # Columna izquierda - justificación uniforme
        draw_label_with_content(c, 50, y_position, "Folio fiscal: ", cfdi_data.uuid or "Sin UUID", 8)
        
        # Para aplicación de anticipo (tipo I): primero método de pago, después forma de pago
        if cfdi_data.tipo_comprobante == "I":
            # Método de pago primero
            if cfdi_data.metodo_pago == "PUE":
                metodo_texto = "PUE - Pago en una sola exhibición"
            elif cfdi_data.metodo_pago == "PPD":
                metodo_texto = "PPD - Pago en parcialidades o diferido"
            else:
                metodo_texto = cfdi_data.metodo_pago or "Sin método especificado"
            
            draw_label_with_content(c, 50, y_position - 12, "Método de pago: ", metodo_texto, 8)
            
            # Forma de pago después
            forma_texto = obtener_descripcion_forma_pago(cfdi_data.forma_pago) if cfdi_data.forma_pago else "Sin forma de pago"
            draw_label_with_content(c, 50, y_position - 24, "Forma de pago: ", forma_texto, 8)
            
            uso_y_offset = -36  # Mover uso CFDI más abajo
        else:
            # Para complemento de pago (tipo P): solo forma de pago
            forma_texto = obtener_descripcion_forma_pago(cfdi_data.forma_pago) if cfdi_data.forma_pago else "Sin forma de pago"
            draw_label_with_content(c, 50, y_position - 12, "Forma de pago: ", forma_texto, 8)
            uso_y_offset = -24  # Posición normal para complemento de pago
        
        uso_texto = "G01 Adquisición de mercancías" if cfdi_data.uso_cfdi == "G01" else cfdi_data.uso_cfdi
        draw_label_with_content(c, 50, y_position + uso_y_offset, "Uso del CFDI: ", uso_texto, 8)
        
        # Columna derecha - justificación uniforme
        lugar_texto = f"{cfdi_data.lugar_emision}, MÉXICO" if cfdi_data.lugar_emision else "Sin lugar"
        draw_label_with_content(c, 350, y_position, "Lugar de emisión: ", lugar_texto, 8)
        
        draw_label_with_content(c, 350, y_position - 12, "Número de serie del CSD: ", cfdi_data.numero_serie_csd or "Sin número", 8)
        
        fecha_formato = cfdi_data.fecha_emision.replace("T", " ") if cfdi_data.fecha_emision else "Sin fecha"
        draw_label_with_content(c, 350, y_position - 24, "Fecha y hora de emisión: ", fecha_formato, 8)
        
        tipo_texto = "INGRESO" if cfdi_data.tipo_comprobante == "I" else "COMPLEMENTO DE PAGO" if cfdi_data.tipo_comprobante == "P" else cfdi_data.tipo_comprobante
        # Ajustar posición del tipo de comprobante según si hay método de pago
        tipo_y_offset = -36 if cfdi_data.tipo_comprobante == "I" else -36
        draw_label_with_content(c, 350, y_position + tipo_y_offset, "Tipo de comprobante: ", tipo_texto, 8)
        
        # DATOS DEL CLIENTE - ajustar espacio según si hay método de pago
        if cfdi_data.tipo_comprobante == "I":
            y_position -= 45  # Espacio reducido para aplicación de anticipo (con método de pago)
        else:
            y_position -= 43  # Espacio normal para complemento de pago
        # Fondo azul para "Datos del Cliente" - 
        c.setFillColor(PDF_CONFIG["colors"]["client_bg"])  # Color del encabezado de tabla
        c.setLineWidth(0.25)  # Grosor del borde de tabla
        c.rect(36, y_position - 12, 540, 12, fill=1, stroke=1)
        
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)  # Tamaño de fuente del título de tabla
        c.drawString(41, y_position - 9, "Datos del Cliente")
        
        # Contenido de la tabla del cliente con borde negro
        c.setFillColor(colors.black)
        y_position -= 15  # Reducir el espacio inicial
        
        # Calcular altura del contenido del cliente (reducir altura para texto más compacto)
        client_content_height = 28  # Altura de la tabla del cliente
        
        # Dibujar borde negro alrededor del contenido del cliente
        c.setLineWidth(0.25)  # Grosor del borde de contenido
        c.rect(36, y_position - client_content_height, 540, client_content_height, fill=0, stroke=1)
        
        # COLUMNA IZQUIERDA (alineada con datos fiscales x=50)
        # Nombre del cliente (en negrita) - con margen superior adecuado
        c.setFont("Helvetica-Bold", 8)  # Tamaño de fuente del nombre
        c.setFillColor(colors.black)
        c.drawString(50, y_position - 10, cfdi_data.receptor_nombre)
        
        # RFC - más cerca del nombre pero con espacio suficiente
        c.setFont("Helvetica-Bold", 8)  # Tamaño de fuente de etiquetas
        c.drawString(50, y_position - 22, "RFC: ")
        rfc_width = c.stringWidth("RFC: ", "Helvetica-Bold", 8)
        c.setFont("Helvetica", 8)  # Tamaño de fuente de contenido
        c.drawString(50 + rfc_width, y_position - 22, cfdi_data.receptor_rfc)
        
        # COLUMNA DERECHA (alineada con datos fiscales x=350)
        # RÉGIMEN (lado derecho) - alineado con el nombre
        if cfdi_data.receptor_regimen:
            if cfdi_data.receptor_regimen == "601":
                regimen_contenido = "601 (GENERAL DE LEY PERSONAS MORALES)"
            elif cfdi_data.receptor_regimen == "612":
                regimen_contenido = "612 (PERSONAS FÍSICAS CON ACTIVIDADES EMPRESARIALES Y PROFESIONALES)"
            else:
                regimen_contenido = cfdi_data.receptor_regimen
        else:
            regimen_contenido = "Sin régimen"
        
        c.setFont("Helvetica-Bold", 8)
        c.drawString(350, y_position - 10, "RÉGIMEN: ")
        regimen_width = c.stringWidth("RÉGIMEN: ", "Helvetica-Bold", 8)
        c.setFont("Helvetica", 8)
        c.drawString(350 + regimen_width, y_position - 10, regimen_contenido)
        
        # C.P. DOMICILIO (lado derecho) - alineado con el RFC
        domicilio_contenido = cfdi_data.receptor_domicilio if cfdi_data.receptor_domicilio else "Sin C.P."
        c.setFont("Helvetica-Bold", 8)
        c.drawString(350, y_position - 22, "C.P. DOMICILIO: ")
        domicilio_width = c.stringWidth("C.P. DOMICILIO: ", "Helvetica-Bold", 8)
        c.setFont("Helvetica", 8)
        c.drawString(350 + domicilio_width, y_position - 22, domicilio_contenido)
        
        # Ajustar y_position para continuar después de la tabla
        y_position -= client_content_height
        
        # TABLA DE CONCEPTOS 
        y_position -= 1  # Espacio estandarizado entre tabla de cliente y conceptos
        
        # Headers de la tabla
        headers = ["CANTIDAD", "UNIDAD", "CONCEPTO", "PRECIO UNITARIO", "IMPORTE"]
        col_widths = [70, 70, 280, 60, 60]  # Ancho de columnas (total: 540 puntos)
        
        # Fondo azul para headers (sin divisiones verticales)
        c.setFillColor(PDF_CONFIG["colors"]["header_bg"])  # Color del encabezado
        c.setLineWidth(0.5)  # Grosor del borde del encabezado
        c.rect(36, y_position - 15, sum(col_widths), 15, fill=1, stroke=1)
        
        # Texto de headers
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 8)  # Tamaño de fuente de encabezados de tabla
        x_pos = 36
        for i, header in enumerate(headers):
            # Centrar el texto en cada celda del header
            text_width = c.stringWidth(header, "Helvetica", 8)
            text_x = x_pos + (col_widths[i] - text_width) / 2
            c.drawString(text_x, y_position - 10, header)
            x_pos += col_widths[i]
        
        # Filas de conceptos - comportamiento diferente según el tipo
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 7)  # Tamaño de fuente del contenido de tabla
        y_position -= 17
        
        # Para aplicación de anticipo (tipo I): tabla sin líneas internas
        if cfdi_data.tipo_comprobante == "I":
            # Calcular la altura total de la tabla de conceptos
            total_rows = len(cfdi_data.conceptos)
            row_height = 22  # Altura de cada fila para cálculos de posición
            display_row_height = 112#umentado para tabla más grande en aplicación de anticipo
            total_table_height = total_rows * display_row_height  # Usar altura visual para dibujar
            
            # Dibujar el borde exterior de toda la tabla de conceptos (sin líneas internas)
            c.setLineWidth(0.25)
            c.rect(36, y_position - total_table_height, sum(col_widths), total_table_height, fill=0, stroke=1)
        
        for concepto in cfdi_data.conceptos:
            # Para complemento de pago (tipo P): dibujar líneas individuales como antes
            if cfdi_data.tipo_comprobante == "P":
                row_height = 22  # Altura de fila
                c.setLineWidth(0.25)  # Grosor del borde de filas
                c.rect(36, y_position - row_height, sum(col_widths), row_height, fill=0, stroke=1)
            
            # Contenido de las celdas (igual para ambos tipos)
            x_pos = 36
            # Centrar cantidad
            cantidad_text = str(concepto.cantidad)
            cantidad_width = c.stringWidth(cantidad_text, "Helvetica", 7)
            cantidad_x = x_pos + (col_widths[0] - cantidad_width) / 2
            c.drawString(cantidad_x, y_position - 12, cantidad_text)
            x_pos += col_widths[0]
            
            # Centrar unidad
            unidad_width = c.stringWidth(concepto.unidad, "Helvetica", 7)
            unidad_x = x_pos + (col_widths[1] - unidad_width) / 2
            c.drawString(unidad_x, y_position - 12, concepto.unidad)
            x_pos += col_widths[1]
            
            # Descripción - formato diferente según tipo de comprobante
            if cfdi_data.tipo_comprobante == "P":
                # Para complemento de pago: formato completo con clave
                if concepto.clave_prod_serv:
                    descripcion_clave = obtener_descripcion_clave_prod_serv(concepto.clave_prod_serv)
                    descripcion_completa = f"Clave Prod Serv - {concepto.clave_prod_serv} - {descripcion_clave}"
                else:
                    descripcion_completa = concepto.descripcion
            else:
                # Para aplicación de anticipo: descripción limpia
                descripcion_completa = concepto.descripcion
            
            # Verificar si el texto cabe en el ancho de la columna
            max_width = col_widths[2] - 10  # Restar margen
            font_size = 7
            
            # Calcular el ancho del texto
            text_width = c.stringWidth(descripcion_completa, "Helvetica", font_size)
            
            # Calcular offset vertical para centrar el contenido en la fila
            if cfdi_data.tipo_comprobante == "I":
                vertical_offset = 15  # Para filas visuales de 30px, centrar mejor
            else:
                vertical_offset = 12  # Para filas de 22px, posición original
            
            if text_width <= max_width:
                # El texto cabe completo
                c.drawString(x_pos + 5, y_position - vertical_offset, descripcion_completa)
            else:
                # Dividir el texto en dos líneas
                palabras = descripcion_completa.split()
                linea1 = ""
                linea2 = ""
                
                # Construir la primera línea
                for palabra in palabras:
                    test_line = linea1 + " " + palabra if linea1 else palabra
                    if c.stringWidth(test_line, "Helvetica", font_size) <= max_width:
                        linea1 = test_line
                    else:
                        # El resto va a la segunda línea
                        linea2 = " ".join(palabras[len(linea1.split()):])
                        break
                
                # Dibujar las dos líneas
                c.drawString(x_pos + 5, y_position - (vertical_offset - 4), linea1)
                if linea2:
                    c.drawString(x_pos + 5, y_position - (vertical_offset + 8), linea2[:60] + "..." if len(linea2) > 60 else linea2)
            x_pos += col_widths[2]
            
            # Alinear a la derecha los valores monetarios
            precio_text = f"{concepto.valor_unitario:,.2f}"
            precio_width = c.stringWidth(precio_text, "Helvetica", 7)
            precio_x = x_pos + col_widths[3] - precio_width - 5
            c.drawString(precio_x, y_position - vertical_offset, precio_text)
            x_pos += col_widths[3]
            
            importe_text = f"{concepto.importe:,.2f}"
            importe_width = c.stringWidth(importe_text, "Helvetica", 7)
            importe_x = x_pos + col_widths[4] - importe_width - 5
            c.drawString(importe_x, y_position - vertical_offset, importe_text)
            
            y_position -= 22  # Ajustar espacio entre filas para que se vea más compacto
        
        # Restablecer grosor de línea normal
        c.setLineWidth(1)
        
        # TABLA DE DOCUMENTOS RELACIONADOS (solo para complementos de pago)
        if cfdi_data.tipo_comprobante == "P" and cfdi_data.documentos_relacionados:
            y_position -= 3  # Espacio estandarizado antes de tabla de documentos
            
            # Título "Documentos Relacionados" con fondo azul
            c.setFillColor(PDF_CONFIG["colors"]["client_bg"])  # Color del encabezado de tabla
            c.setLineWidth(0.25)  # Grosor del borde de tabla
            c.rect(36, y_position - 12, 540, 12, fill=1, stroke=1)
            
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 9)  # Tamaño de fuente del título de tabla
            c.drawString(41, y_position - 9, "Documentos Relacionados")
            
            # Contenido de la tabla con borde negro
            c.setFillColor(colors.black)
            y_position -= 15  # Espacio después del título
            
            # Calcular altura del contenido de documentos relacionados
            doc_content_height = 330  # Aumentado  para tabla más grande de complelemnto pago
            
            # Dibujar borde negro alrededor del contenido
            c.setLineWidth(0.25)  # Grosor del borde de contenido
            c.rect(36, y_position - doc_content_height, 540, doc_content_height, fill=0, stroke=1)
            
            # Mostrar información del primer documento relacionado (formato de dos columnas)
            if cfdi_data.documentos_relacionados:
                documento = cfdi_data.documentos_relacionados[0]  # Tomar el primer documento
                
                # FILA 1: ID DOCUMENTO (izquierda) | NUM. PARCIALIDAD (derecha)
                c.setFont("Helvetica-Bold", 8)  # Tamaño de fuente de etiquetas
                c.drawString(50, y_position - 10, "ID. DOCUMENTO: ")
                id_width = c.stringWidth("ID. DOCUMENTO: ", "Helvetica-Bold", 8)
                c.setFont("Helvetica", 8)  # Mismo tamaño para UUID
                
                # Mostrar UUID completo
                c.drawString(50 + id_width, y_position - 10, documento.id_documento)
                
                # COLUMNA DERECHA - NUM. PARCIALIDAD
                c.setFont("Helvetica-Bold", 8)
                c.drawString(350, y_position - 10, "NUM. PARCIALIDAD: ")
                parcialidad_width = c.stringWidth("NUM. PARCIALIDAD: ", "Helvetica-Bold", 8)
                c.setFont("Helvetica", 8)
                c.drawString(350 + parcialidad_width, y_position - 10, documento.num_parcialidad)
                
                # FILA 2: SERIE (izquierda) | IMP. PAGADO (derecha)
                c.setFont("Helvetica-Bold", 8)
                c.drawString(50, y_position - 25, "SERIE: ")
                serie_width = c.stringWidth("SERIE: ", "Helvetica-Bold", 8)
                c.setFont("Helvetica", 8)
                # Usar la serie del comprobante principal
                c.drawString(50 + serie_width, y_position - 25, cfdi_data.serie or "C")
                
                # COLUMNA DERECHA - IMP. PAGADO
                c.setFont("Helvetica-Bold", 8)
                c.drawString(350, y_position - 25, "IMP. PAGADO: ")
                pagado_width = c.stringWidth("IMP. PAGADO: ", "Helvetica-Bold", 8)
                c.setFont("Helvetica", 8)
                c.drawString(350 + pagado_width, y_position - 25, f"${documento.imp_pagado:,.2f}")
                
                # FILA 3: FOLIO (izquierda) | IMP.SALDO ANT (derecha)
                c.setFont("Helvetica-Bold", 8)
                c.drawString(50, y_position - 40, "FOLIO: ")
                folio_width = c.stringWidth("FOLIO: ", "Helvetica-Bold", 8)
                c.setFont("Helvetica", 8)
                c.drawString(50 + folio_width, y_position - 40, cfdi_data.folio or "1951")
                
                # COLUMNA DERECHA - IMP.SALDO ANT
                c.setFont("Helvetica-Bold", 8)
                c.drawString(350, y_position - 40, "IMP.SALDO ANT: ")
                saldo_ant_width = c.stringWidth("IMP.SALDO ANT: ", "Helvetica-Bold", 8)
                c.setFont("Helvetica", 8)
                c.drawString(350 + saldo_ant_width, y_position - 40, f"${documento.imp_saldo_ant:,.2f}")
                
                # FILA 4: TIPO DE CAMBIO (izquierda) | IMP. SALDO INSOLUTO (derecha)
                c.setFont("Helvetica-Bold", 8)
                c.drawString(50, y_position - 55, "TIPO DE CAMBIO: ")
                cambio_width = c.stringWidth("TIPO DE CAMBIO: ", "Helvetica-Bold", 8)
                c.setFont("Helvetica", 8)
                c.drawString(50 + cambio_width, y_position - 55, documento.equivalencia_dr)
                
                # COLUMNA DERECHA - IMP. SALDO INSOLUTO
                c.setFont("Helvetica-Bold", 8)
                c.drawString(350, y_position - 55, "IMP. SALDO INSOLUTO: ")
                insoluto_width = c.stringWidth("IMP. SALDO INSOLUTO: ", "Helvetica-Bold", 8)
                c.setFont("Helvetica", 8)
                c.drawString(350 + insoluto_width, y_position - 55, f"${documento.imp_saldo_insoluto:,.2f}")
                
                # FILA 5: MONEDA (solo izquierda)
                c.setFont("Helvetica-Bold", 8)
                c.drawString(50, y_position - 70, "MONEDA: ")
                moneda_width = c.stringWidth("MONEDA: ", "Helvetica-Bold", 8)
                c.setFont("Helvetica", 8)
                c.drawString(50 + moneda_width, y_position - 70, NOMBRES_MONEDAS.get(documento.moneda, documento.moneda))
            
            # Ajustar y_position para continuar después de la tabla
            # Compensar para mantener los datos inferiores en la misma posición
            y_position -= 75  # Usar la altura original para no mover datos inferiores
            # Restablecer grosor de línea
            c.setLineWidth(1)
        
        # Espacio después de la tabla de conceptos
        y_position -= 3
        
        # SECCIÓN FISCAL INFERIOR 
        y_position -= 250  # Aumentado de 220 a 250 para mover los totales más abajo
        
        # Primera línea: Folio fiscal relacionado y Tipo de relación (datos reales del XML)
        # Para complementos de pago, buscar el documento relacionado
        folio_relacionado = "N/A"
        if cfdi_data.tipo_comprobante == "P" and cfdi_data.datos_complemento_pago:
            folio_relacionado = cfdi_data.datos_complemento_pago.documento_relacionado_uuid
            print(f"✓ Usando UUID de complemento de pago: {folio_relacionado}")
        elif cfdi_data.tipo_comprobante == "I" and cfdi_data.uuid_relacionado:
            # Para aplicación de anticipo, usar el UUID relacionado
            folio_relacionado = cfdi_data.uuid_relacionado
            print(f"✓ Usando UUID relacionado de aplicación de anticipo: {folio_relacionado}")
        else:
            # Para otros tipos, usar el UUID del propio documento
            folio_relacionado = cfdi_data.uuid if cfdi_data.uuid else "N/A"
            print(f"✓ Usando UUID del documento actual: {folio_relacionado}")
            print(f"   Tipo comprobante: {cfdi_data.tipo_comprobante}")
            print(f"   UUID relacionado disponible: {cfdi_data.uuid_relacionado}")
        
        draw_label_with_content(c, 50, y_position, "Folio fiscal relacionado: ", folio_relacionado, 7)
        
        # Agregar "Tipo de relación:" solo para aplicación de anticipo
        if cfdi_data.tipo_comprobante == "I" and cfdi_data.uuid_relacionado:
            y_position -= 12  # Espacio entre folio relacionado y tipo de relación
            draw_label_with_content(c, 50, y_position, "Tipo de relación: ", "CFDI por aplicación de anticipo", 7)
        
        # Total con letra - PRIMERO (guardar posición para alinear totales)
        # Espacio adicional solo para aplicación de anticipo
        if cfdi_data.tipo_comprobante == "I":  # Solo para aplicación de anticipo
            y_position -= 28  # Espacio extra entre folio relacionado y total con letra
        y_position -= 15  # Espacio base para todos los tipos  
        y_totales_inicio = y_position  # Guardar esta posición para los totales de la derecha
        draw_text_with_style(c, 50, y_position, "Total con letra:", "Helvetica-Bold", 8)
        
        y_position -= 8   
        total_letras = numero_a_letras(float(cfdi_data.total))
        draw_text_with_style(c, 50, y_position, total_letras, "Helvetica", 7)
        
        # Favor de realizar su pago en - DESPUÉS
        y_position -= 15  
        draw_text_with_style(c, 50, y_position, "Favor de realizar su pago en:", "Helvetica-Bold", 7)
        
        y_position -= 10  
        draw_text_with_style(c, 50, y_position, "BANCO: BBVA BANCOMER S.A. CUENTA M.N.: 0450820761, CLABE: 012540004508207617 SWIFT: BCMRMXMM", "Helvetica", 7)
        
        # Columna derecha - totales alineados con "Total con letra:"
        y_totales = y_totales_inicio  # Usar la misma altura que "Total con letra:"
        draw_text_with_style(c, 456, y_totales, "SUBTOTAL", "Helvetica-Bold", 8, PDF_CONFIG["colors"]["header_bg"])
        draw_text_with_style(c, 516, y_totales, f"{cfdi_data.subtotal:,.2f}", "Helvetica-Bold", 8)
        
        y_totales -= 10  
        draw_text_with_style(c, 456, y_totales, "I.V.A.", "Helvetica-Bold", 8, PDF_CONFIG["colors"]["header_bg"])
        iva_amount = cfdi_data.total - cfdi_data.subtotal
        draw_text_with_style(c, 516, y_totales, f"{iva_amount:,.2f}", "Helvetica-Bold", 8)
        
        y_totales -= 10  
        draw_text_with_style(c, 456, y_totales, "TOTAL", "Helvetica-Bold", 8, PDF_CONFIG["colors"]["header_bg"])
        draw_text_with_style(c, 516, y_totales, f"{cfdi_data.total:,.2f}", "Helvetica-Bold", 8)
        
        y_totales -= 10  
        draw_text_with_style(c, 456, y_totales, "MONEDA", "Helvetica-Bold", 8, PDF_CONFIG["colors"]["header_bg"])
        
        # Para complementos de pago (tipo P), usar nombre completo de la moneda
        if cfdi_data.tipo_comprobante == "P" and cfdi_data.datos_complemento_pago:
            moneda_real = cfdi_data.datos_complemento_pago.moneda  # MonedaP
            moneda_display = NOMBRES_MONEDAS.get(moneda_real, moneda_real)
        # Para aplicación de anticipo (tipo I), mostrar el código de moneda directamente
        elif cfdi_data.tipo_comprobante == "I":
            moneda_display = cfdi_data.moneda  # USD, EUR, MXN, etc.
        else:
            # Para otros tipos, usar el mapeo de nombres completos
            moneda_display = NOMBRES_MONEDAS.get(cfdi_data.moneda, cfdi_data.moneda)
        
        draw_text_with_style(c, 516, y_totales, moneda_display, "Helvetica-Bold", 8)
        
        # No. de Serie del Certificado del SAT 
        y_position -= 10  
        numero_serie_sat = cfdi_data.no_certificado_sat if cfdi_data.no_certificado_sat else cfdi_data.numero_serie_csd
        cert_end_x = draw_label_with_content(c, 50, y_position, "No. de Serie del Certificado del SAT: ", numero_serie_sat, 7)
        
        # Fecha y Hora de Certificación pegada al número de serie
        fecha_cert = cfdi_data.fecha_timbrado if cfdi_data.fecha_timbrado else "N/A"
        draw_label_with_content(c, cert_end_x + 20, y_position, "Fecha y Hora de Certificación: ", fecha_cert, 7)
        
        # Cadena original
        y_position -= 12  
        draw_text_with_style(c, 50, y_position, "Cadena original:", "Helvetica-Bold", 7)  
        rfc_prov_certif = cfdi_data.rfc_prov_certif if cfdi_data.rfc_prov_certif else "SAT970701NN3"
        cadena_original = f"||1.1|{cfdi_data.uuid}|{cfdi_data.fecha_timbrado}|{rfc_prov_certif}|{cfdi_data.no_certificado_sat}||"
        y_position = draw_multiline_text(c, 50, y_position - 8, cadena_original, 120, 6)
        
        # Sello digital del CFDI 
        y_position -= 12  
        draw_text_with_style(c, 50, y_position, "Sello digital del CFDI:", "Helvetica-Bold", 6)  
        sello_cfdi = cfdi_data.sello_cfdi if cfdi_data.sello_cfdi else "N/A"
        y_position = draw_multiline_text(c, 50, y_position - 8, sello_cfdi, 130, 6)
        
        # Sello del SAT 
        y_position -= 12  
        draw_text_with_style(c, 50, y_position, "Sello del SAT:", "Helvetica-Bold", 6)  
        sello_sat_real = cfdi_data.sello_sat if cfdi_data.sello_sat else "N/A"
        y_position = draw_multiline_text(c, 50, y_position - 8, sello_sat_real, 130, 6)
        
        # Leyenda final centrada en la parte inferior
        y_position -= 20  # Espacio antes de la leyenda
        c.setFont("Helvetica-Bold", 7)  # Fuente más pequeña y en negrita
        leyenda = "Este documento es una representación impresa de un CFDI v. 4.0"
        leyenda_width = c.stringWidth(leyenda, "Helvetica-Bold", 7)
        # Centrar la leyenda (ancho de página 612, menos márgenes)
        x_centrado = (612 - leyenda_width) / 2
        c.drawString(x_centrado, y_position, leyenda)
        
        # Finalizar PDF
        c.save()
        
        # Obtener bytes del PDF
        pdf_buffer.seek(0)
        pdf_bytes = pdf_buffer.getvalue()
        pdf_buffer.close()
        
        return pdf_bytes
        
    except Exception as e:
        raise PDFGenerationError(f"Error generando PDF: {str(e)}")