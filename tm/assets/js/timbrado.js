
let xmlOriginal = null;
const inputXMLAplicacion = document.querySelector('#xmlAplicacion');
function getTipo() {
    return document.getElementById("tipoTimbrado").value;
}

// VALIDACIONES 
function validarCFDI(archivoXML) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        
        reader.onload = function(e) {
            const contenido = e.target.result;
            
            try {
                const parser = new DOMParser();
                const xmlDoc = parser.parseFromString(contenido, "text/xml");
                
                const parseError = xmlDoc.querySelector('parsererror');
                if (parseError) {
                    reject({ valido: false, errores: ['El XML tiene errores de sintaxis'] });
                    return;
                }
                
                const errores = [];
                const advertencias = [];
                
                const timbre = xmlDoc.querySelector('TimbreFiscalDigital, tfd\\:TimbreFiscalDigital');
                if (timbre) {
                    const uuid = timbre.getAttribute('UUID');
                    const regexUUID = /^[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}$/i;
                    if (!uuid || uuid.trim() === '') {
                        errores.push('El UUID está vacío. Debe contener un identificador válido antes de timbrar.');
                    } else if (!regexUUID.test(uuid)) {
                        errores.push('El UUID no tiene el formato correcto');
                    }
                } else {
                    advertencias.push('No se encontró el nodo TimbreFiscalDigital. Se agregará al timbrar.');
                }
                
                const conceptos = xmlDoc.querySelectorAll('Concepto, cfdi\\:Concepto');
                if (conceptos.length === 0) {
                    errores.push('No se encontraron conceptos en el CFDI');
                } else {
                    conceptos.forEach((concepto) => {
                        const claveProdServ = concepto.getAttribute('ClaveProdServ');
                        const regexClave = /^\d{8}$/;
                        if (!claveProdServ) {
                            errores.push('Falta el atributo ClaveProdServ');
                        } else if (!regexClave.test(claveProdServ)) {
                            errores.push('ClaveProdServ con formato incorrecto');
                        }
                        
                        const claveUnidad = concepto.getAttribute('ClaveUnidad');
                        if (!claveUnidad) {
                            errores.push('Falta el atributo ClaveUnidad');
                        } else if (claveUnidad !== 'ACT') {
                            errores.push('ClaveUnidad con formato incorrecto');
                        }
                        
                        const descripcion = concepto.getAttribute('Descripcion');
                        if (!descripcion) {
                            errores.push('Falta el atributo Descripcion');
                        } else if (!descripcion.toLowerCase().includes('anticipo')) {
                            errores.push('Descripción con formato incorrecto');
                        }
                    });
                }

                const emisor = xmlDoc.querySelector('Emisor, cfdi\\:Emisor');
                if (emisor) {
                    const rfcEmisor = emisor.getAttribute('Rfc');
                    const regexRFC = /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/;
                    if (!rfcEmisor || !regexRFC.test(rfcEmisor)) {
                        errores.push(`RFC del Emisor inválido: "${rfcEmisor}"`);
                    }
                }
                
                const receptor = xmlDoc.querySelector('Receptor, cfdi\\:Receptor');
                if (receptor) {
                    const rfcReceptor = receptor.getAttribute('Rfc');
                    const regexRFC = /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/;
                    if (!rfcReceptor || !regexRFC.test(rfcReceptor)) {
                        errores.push(`RFC del Receptor inválido: "${rfcReceptor}"`);
                    }
                }
                
                if (errores.length === 0) {
                    resolve({ valido: true, mensaje: 'XML válido para timbrar', advertencias, xml: contenido, xmlDoc });
                } else {
                    reject({ valido: false, errores, advertencias });
                }
                
            } catch (error) {
                reject({ valido: false, errores: [`Error al procesar el XML: ${error.message}`] });
            }
        };
        
        reader.onerror = () => reject({ valido: false, errores: ['Error al leer el archivo'] });
        reader.readAsText(archivoXML);
    });
}


// =====================================================
// MOSTRAR/OCULTAR SECCIONES SEGÚN TIPO SELECCIONADO
// =====================================================
function actualizarSecciones(tipoSeleccionado) {
    const formaPagoSection   = document.getElementById("formaPagoSection");
    const formaPagoSelect    = document.getElementById("formaPago");
    const cancelacionSection = document.getElementById("cancelacionSection");
    const motivoCancelacion  = document.getElementById("motivoCancelacion");
    const subirXMLSection    = document.getElementById("subirXMLSection");
    const xmlUnicoSection    = document.getElementById("xmlUnicoSection");
    const xmlAnticipoSection = document.getElementById("xmlAnticipoSection");
    const btnContinuar       = document.getElementById("btnContinuarTimbrado");
    // const btnContinuarTimbrado = document.getElementById("procesarXML");
    const btnCancelarFactura = document.getElementById("cancelarCFDI");

    // Resetear TODO al cambiar de tipo
    formaPagoSection.classList.add("hidden");
    formaPagoSelect.required = false;
    cancelacionSection.classList.add("hidden");
    motivoCancelacion.required = false;
    subirXMLSection.classList.add("hidden");
    xmlUnicoSection.classList.add("hidden");
    xmlAnticipoSection.classList.add("hidden");
    
    btnContinuar.classList.remove("hidden"); // Volver a mostrar el botón Continuar

    btnCancelarFactura.classList.add("hidden");


    if (tipoSeleccionado === "complemento") {
        formaPagoSection.classList.remove("hidden");
        formaPagoSelect.required = true;
    } else if (tipoSeleccionado === "anticipo") {
        formaPagoSelect.value = "99";
    } else if (tipoSeleccionado === "cancelar") {
        cancelacionSection.classList.remove("hidden");
        btnContinuar.classList.add("hidden");
        // btnContinuarTimbrado.classList.add("hidden");
        btnCancelarFactura.classList.remove("hidden");
        motivoCancelacion.required = true;
    }
}

document.getElementById("tipoTimbrado").onchange = function() {
    actualizarSecciones(this.value);
};

// Ejecutar al cargar la página por si el navegador restauró
// un valor previo en el select (problema del estado al recargar)
document.addEventListener("DOMContentLoaded", () => {
    const tipoSeleccionado = getTipo();
    if (tipoSeleccionado) {
        actualizarSecciones(tipoSeleccionado);
    }
});


// CONTINUAR
document.getElementById("btnContinuarTimbrado").onclick = () => {
    const tipoSeleccionado = getTipo();
    if (!tipoSeleccionado) {
        alert("Selecciona un tipo.");
        return;
    }
    
    if (tipoSeleccionado === "complemento" && !document.getElementById("formaPago").value) {
        alert("Selecciona una forma de pago.");
        return;
    }
    
    document.getElementById("subirXMLSection").classList.remove("hidden");
    
    const xmlUnicoSection   = document.getElementById("xmlUnicoSection");
    const xmlAnticipoSection = document.getElementById("xmlAnticipoSection");
    
    if (tipoSeleccionado === "anticipo") {
        xmlUnicoSection.classList.add("hidden");
        xmlAnticipoSection.classList.remove("hidden");
    } else if( tipoSeleccionado === "complemento") {
        xmlUnicoSection.classList.remove("hidden");
        xmlAnticipoSection.classList.add("hidden");
    }

    if (tipoSeleccionado === "nomina") {
        xmlUnicoSection.classList.remove("hidden");
        xmlAnticipoSection.classList.add("hidden");
    }

    document.querySelector('#btnContinuarTimbrado').classList.add('hidden');
};


// MOSTRAR NOMBRE DEL ARCHIVO
document.getElementById("xmlFile").onchange = function() {
    const tipoSeleccionado = getTipo();
    const archivo = this.files[0];
    const fileNameDiv = document.getElementById("fileName");
    if (archivo) {
        fileNameDiv.textContent = archivo.name;
        if (tipoSeleccionado === "complemento") validarEntradasXML(archivo);
    } else {
        fileNameDiv.textContent = "";
    }
};

// MOSTRAR NOMBRES DE ARCHIVOS PARA ANTICIPO
document.getElementById("xmlProductos").onchange = function() {
    const archivo = this.files[0];
    const fileNameDiv = document.getElementById("fileNameProductos");
    if (archivo) {
        fileNameDiv.textContent = archivo.name;
        validarCFDI(archivo)
            .then(res => {
                alert("CFDI válido\n\n" + res.mensaje);
                inputXMLAplicacion.disabled = false;
            })
            .catch(err => {
                alert("CFDI inválido\n\n" + err.errores.join("\n"));
                fileNameDiv.textContent = "";
            });
    } else {
        fileNameDiv.textContent = "";
    }
};

document.getElementById("xmlAplicacion").onchange = function() {
    const archivo = this.files[0];
    const fileNameDiv = document.getElementById("fileNameAplicacion");
    fileNameDiv.classList.remove("hidden");
    if (archivo) {
        fileNameDiv.textContent = archivo.name;
    } else {
        fileNameDiv.textContent = "";
    }
};


function validarEntradasXML(xmlDom) {
    const reader = new FileReader();

    reader.onload = function(e) {
        const xmlString = e.target.result;
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlString, "text/xml");
        
        xmlOriginal = xmlDoc;

        const comprobante = xmlDoc.getElementsByTagName("cfdi:Comprobante")[0];

        const impuestosDelComprobante = Array.from(comprobante.children).find(
            child => child.tagName === 'cfdi:Impuestos'
        );

        if (!impuestosDelComprobante) {
            alert("No se encontró el nodo de Impuestos a nivel de Comprobante");
            return;
        }

        const traslados = impuestosDelComprobante.getElementsByTagName("cfdi:Traslados")[0];
        const trasladoGlobal = traslados.getElementsByTagName("cfdi:Traslado")[0];

        const folio = comprobante.getAttribute("Folio") || "";
        const fechaOriginal = comprobante.getAttribute("Fecha") || "";
        const base = trasladoGlobal.getAttribute("Base") || "";
        // console.log(base);
        const importe = trasladoGlobal.getAttribute("Importe") || "";

        const section = document.querySelector('#xmlUnicoSection');

        // FECHA Y HORA
        const lbFecha = document.createElement('label');
        lbFecha.classList.add('campo-label');
        lbFecha.textContent = 'Fecha y Hora:';
        let fechaParaInput = fechaOriginal ? fechaOriginal.substring(0, 16) : "";
        const entradaFecha = document.createElement('input');
        entradaFecha.classList.add('entradas');
        entradaFecha.type = 'datetime-local';
        entradaFecha.value = fechaParaInput;
        section.appendChild(lbFecha);
        section.appendChild(entradaFecha);
        entradaFecha.addEventListener('input', () => {
            if (entradaFecha.value) {
                comprobante.setAttribute("Fecha", entradaFecha.value + ":00");
            }
        });

        // FOLIO
        const lbFolio = document.createElement('label');
        lbFolio.classList.add('campo-label');
        lbFolio.textContent = 'Folio:';
        const entradaFolio = document.createElement('input');
        entradaFolio.classList.add('entradas');
        entradaFolio.type = 'text';
        entradaFolio.value = folio;
        section.appendChild(lbFolio);
        section.appendChild(entradaFolio);
        entradaFolio.addEventListener('input', () => {
            comprobante.setAttribute("Folio", entradaFolio.value);
        });

        // BASE
        const lbBase = document.createElement('label');
        lbBase.classList.add('campo-label');
        lbBase.textContent = 'Base:';
        const entradaBase = document.createElement('input');
        entradaBase.classList.add('entradas');
        entradaBase.type = 'text';
        entradaBase.value = base;
        section.appendChild(lbBase);
        section.appendChild(entradaBase);
        entradaBase.addEventListener('input', () => {
            trasladoGlobal.setAttribute("Base", entradaBase.value);
        });

        // IMPORTE
        const lbImporte = document.createElement('label');
        lbImporte.classList.add('campo-label');
        lbImporte.textContent = 'Importe:';
        const entradaImporte = document.createElement('input');
        entradaImporte.classList.add('entradas');
        entradaImporte.type = 'text';
        entradaImporte.value = importe;
        section.appendChild(lbImporte);
        section.appendChild(entradaImporte);
        entradaImporte.addEventListener('input', () => {
            trasladoGlobal.setAttribute("Importe", entradaImporte.value);
        });
    };
    
    reader.readAsText(xmlDom);
}



// PROCESAR XML para anticipo, complemento y nomina
document.getElementById("procesarXML").onclick = () => {
    const tipoSeleccionado = getTipo();
    if (tipoSeleccionado === "anticipo") {
        const archivoProductos  = document.getElementById("xmlProductos").files[0];
        const archivoAplicacion = document.getElementById("xmlAplicacion").files[0];
        if (!archivoProductos)  { alert("Sube el Primer XML.");  return; }
        if (!archivoAplicacion) { alert("Sube el Segundo XML."); return; }
        procesarXMLsAnticipo(archivoProductos, archivoAplicacion);
    } else if (tipoSeleccionado === "complemento" || tipoSeleccionado === "nomina" ) {
        const archivo = document.getElementById("xmlFile").files[0];
        if (!archivo) { alert("Sube un XML."); return; }
        procesarXMLUnico(archivo);
    }
};


function procesarXMLUnico(archivo) {
    const tipoSeleccionado = getTipo();
    const lector = new FileReader();
    lector.onload = e => {
        const parser = new DOMParser();
        const xml = parser.parseFromString(e.target.result, "text/xml");
        if (tipoSeleccionado === "nomina") {
            xmlOriginal = xml;
        }
        procesarDatosFaltantes(xml);
    };
    lector.readAsText(archivo);
}


function procesarXMLsAnticipo(archivoProductos, archivoAplicacion) {
    let xmlProductos  = null;
    let xmlAplicacion = null;
    let procesados = 0;
    
    const lectorProductos = new FileReader();
    lectorProductos.onload = e => {
        const parser = new DOMParser();
        xmlProductos = parser.parseFromString(e.target.result, "text/xml");
        procesados++;
        if (procesados === 2) {
            xmlOriginal = xmlProductos;
            procesarDatosFaltantes(xmlProductos);
        }
    };
    lectorProductos.readAsText(archivoProductos);
    
    const lectorAplicacion = new FileReader();
    lectorAplicacion.onload = e => {
        const parser = new DOMParser();
        xmlAplicacion = parser.parseFromString(e.target.result, "text/xml");
        procesados++;
        if (procesados === 2) {
            xmlOriginal = xmlProductos;
            procesarDatosFaltantes(xmlProductos);
        }
    };
    lectorAplicacion.readAsText(archivoAplicacion);
}


function procesarDatosFaltantes(xml) {
    const tipoSeleccionado = getTipo();
    let faltan = [];
    const todosElementos = xml.getElementsByTagName("*");
    
    for (let el of todosElementos) {
        for (let attr of el.attributes) {
            let esPlantilla = attr.value.includes("{{");
            let esVacio = attr.value.trim() === "";
            let sinComillas = esVacio && !el.outerHTML.includes(attr.name + "=\"");
            if (esPlantilla || esVacio || sinComillas) {
                faltan.push({ elemento: el, attr: attr.name, valor: attr.value });
            }
        }
    }
    
    if (!xmlOriginal) {
        return;
    }else if (faltan.length === 0) {
        alert("XML COMPLETO: Enviado a timbrar.");
        enviarParaTimbrar(xmlOriginal);
        return;
    } 
    
}


// --- ENVIAR PARA TIMBRAR ---
function enviarParaTimbrar(xmlDom){
    const tipoSeleccionado = getTipo();
    const xmlString = new XMLSerializer().serializeToString(xmlDom);
    const formData = new FormData(); 
    const xmlBlob = new Blob([xmlString], { type: "text/xml" });
    
    if (tipoSeleccionado === "anticipo") {
        // Para anticipo: enviar ambos XMLs
        const archivoProductos = document.getElementById("xmlProductos").files[0];
        const archivoAplicacion = document.getElementById("xmlAplicacion").files[0];
        
        if (archivoProductos && archivoAplicacion) {
            formData.append("xml_archivo1", archivoProductos, "archivo1.xml");
            formData.append("xml_archivo2", archivoAplicacion, "archivo2.xml");
        } else {
            alert("Error: Faltan archivos XML para anticipo.");
            return;
        }
    } else if( tipoSeleccionado === "complemento" || tipoSeleccionado === "nomina") {
        // Para complemento: enviar un XML
        formData.append("xml", xmlBlob, "factura.xml");
        // console.log(xmlBlob)
    }
    
    // Agregar forma de pago seleccionada
    let formaPagoSeleccionada;
    if (tipoSeleccionado === "anticipo") {
        formaPagoSeleccionada = "99"; // Siempre "99" para anticipo
    } else {
        formaPagoSeleccionada = document.getElementById("formaPago").value || "03";
    }
    
    const formaPagoTexto = tipoSeleccionado === "anticipo" ? 
        "99: Por definir (Aplicación de Anticipo)" : 
        document.getElementById("formaPago").options[document.getElementById("formaPago").selectedIndex]?.text || "03: Transferencia electrónica de fondos";
    
    formData.append("forma_pago", formaPagoSeleccionada);

    // Determinar endpoint según el tipo seleccionado
    let endpoint;
    if (tipoSeleccionado === "complemento") {
    // tm7.telmedia.com.mx
        endpoint = "https://127.0.0.1:5001/timbrar-complemento-pago2"; 
    } else if (tipoSeleccionado === "anticipo") {
        endpoint = "https://127.0.0.1:5001/timbrar-aplicacion-anticipo";
    } else if(tipoSeleccionado === "nomina"){
        endpoint = "https://127.0.0.1:5001/timbrar-nomina";
    } else {
        alert("Selecciona un tipo válido.");
        return;
    }

    fetch(endpoint, {
        method:"POST",
        body:formData
    })
    .then(r => {
        // Verificar si el servidor respondió con error HTTP
        if (!r.ok) {
            return r.json().then(data => {
                throw new Error(data.error || `Error del servidor (${r.status})`);
            });
        }
        return r.json();
    })
    .then(data => {
        // Verificar si hay error en la respuesta JSON
        if (!data.success) {
            alert(" Error al timbrar:\n\n" + (data.error || "Error desconocido"));
            return;
        }

        let archivosDescargados = 0;
        let mensajes = [];

        // Descargar el XML timbrado
        if(data.xml) {
            const xmlBytes = atob(data.xml);
            const xmlBlob = new Blob([xmlBytes], { type: "text/xml" });
            const xmlUrl = URL.createObjectURL(xmlBlob);
            const xmlLink = document.createElement("a");
            xmlLink.href = xmlUrl;
            xmlLink.download = data.xml_filename || `CFDI_${tipoSeleccionado}_Timbrado.xml`;
            xmlLink.click();
            URL.revokeObjectURL(xmlUrl);
            archivosDescargados++;
            mensajes.push("XML descargado");
        }

        // Descargar el XML timbrado
        if (data.xml_timbrado) {
            const xmlBase64 = data.xml_timbrado;

            // Decodificar base64 → bytes
            const binaryString = atob(xmlBase64);
            const len = binaryString.length;
            const bytes = new Uint8Array(len);

            for (let i = 0; i < len; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            const xmlBlob = new Blob([bytes], { type: "text/xml;charset=utf-8;" });
            const xmlUrl = URL.createObjectURL(xmlBlob);

            const xmlLink = document.createElement("a");
            xmlLink.href = xmlUrl;
            xmlLink.download = `CFDI_${tipoSeleccionado}_Timbrado.xml`;
            document.body.appendChild(xmlLink);
            xmlLink.click();
            document.body.removeChild(xmlLink);

            URL.revokeObjectURL(xmlUrl);
        }

        // Descargar el PDF si existe
        if(data.pdf) {
            const pdfBytes = atob(data.pdf);
            const pdfBlob = new Blob([pdfBytes], { type: "application/pdf" });
            const pdfUrl = URL.createObjectURL(pdfBlob);
            const pdfLink = document.createElement("a");
            pdfLink.href = pdfUrl;
            pdfLink.download = data.pdf_filename || `CFDI_${tipoSeleccionado}_Factura.pdf`;
            pdfLink.click();
            URL.revokeObjectURL(pdfUrl);
            archivosDescargados++;
            mensajes.push("PDF descargado");
        } else if(data.pdf_error) {
            // console.warn("Error generando PDF:", data.pdf_error);
            mensajes.push("PDF no disponible: " + data.pdf_error);
        }

        // Mensaje de éxito
        let mensaje = `CFDI ${tipoSeleccionado} Timbrado exitosamente.\n`;
        
        // Solo mostrar forma de pago si es complemento de pago
        if (tipoSeleccionado === "complemento") {
            mensaje += `Forma de pago aplicada: ${formaPagoTexto}\n`;
        }
        
        mensaje += mensajes.join(", ");
        
        alert(mensaje);
    })
    .catch(err=>{
        // console.error("Error enviando a timbrar:", err);
        alert("Error enviando a timbrar: " + err.message);
    });
}

// Al cargar XML, extraer UUID y RFC automáticamente
document.getElementById("xmlCancelacion").addEventListener("change", function() {
    const archivo = this.files[0];
    if (!archivo) return;
    const lector = new FileReader();
    lector.onload = e => {
        const parser = new DOMParser();
        const xml = parser.parseFromString(e.target.result, "text/xml");
        // Extraer UUID del nodo TimbreFiscalDigital
        const tfd = xml.getElementsByTagNameNS("http://www.sat.gob.mx/TimbreFiscalDigital", "TimbreFiscalDigital")[0];
        if (tfd) {
            document.getElementById("inputUUIDCancelar").value = tfd.getAttribute("UUID") || "";
        }
        // Extraer RFC Emisor
        const emisor = xml.getElementsByTagNameNS("http://www.sat.gob.mx/cfd/4", "Emisor")[0]
                    || xml.getElementsByTagNameNS("http://www.sat.gob.mx/cfd/3", "Emisor")[0];
        if (emisor) {
            document.getElementById("inputRFCEmisor").value = emisor.getAttribute("Rfc") || "";
        }
    };
    lector.readAsText(archivo);
});

// Habilitar/deshabilitar UUID sustituto según motivo
document.getElementById("motivoCancelacion").addEventListener("change", function() {
    const sustituto = document.getElementById("inputUUIDSustituto");
    if (this.value === "01") {
        sustituto.disabled = false;
        sustituto.placeholder = "Ingresa el UUID sustituto...";
    } else {
        sustituto.disabled = true;
        sustituto.value = "";
        sustituto.placeholder = "UUID sustituto (solo motivo 01)";
    }
});

// Validación en tiempo real UUID
document.getElementById("inputUUIDCancelar").addEventListener("input", function() {
    const valor = this.value.toUpperCase();
    // Solo permitir caracteres válidos para UUID (hex y guiones)
    this.value = valor.replace(/[^A-F0-9-]/g, "");
    const regexUUID = /^[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}$/;
    if (this.value.length > 0 && !regexUUID.test(this.value)) {
        this.style.borderColor = "red";
    } else {
        this.style.borderColor = "green";
    }
});

// Validación en tiempo real RFC
document.getElementById("inputRFCEmisor").addEventListener("input", function() {
    const valor = this.value.toUpperCase();
    // Solo permitir letras, números, Ñ y &
    this.value = valor.replace(/[^A-ZÑ&0-9]/g, "");
    // Limitar a 13 caracteres (RFC persona moral) o 12 (física)
    if (this.value.length > 13) this.value = this.value.substring(0, 13);
    const regexRFC = /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/;
    if (this.value.length > 0 && !regexRFC.test(this.value)) {
        this.style.borderColor = "red";
    } else {
        this.style.borderColor = "green";
    }
});

// Validación en tiempo real UUID Sustituto
document.getElementById("inputUUIDSustituto").addEventListener("input", function() {
    const valor = this.value.toUpperCase();
    this.value = valor.replace(/[^A-F0-9-]/g, "");
    const regexUUID = /^[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}$/;
    if (this.value.length > 0 && !regexUUID.test(this.value)) {
        this.style.borderColor = "red";
    } else {
        this.style.borderColor = "green";
    }
});

// Botón cancelar
document.getElementById("cancelarCFDI").onclick = () => {
    const tipoSeleccionado = getTipo();
    if (tipoSeleccionado === "cancelar") {
        const uuid = document.getElementById("inputUUIDCancelar").value.trim();
        const rfc = document.getElementById("inputRFCEmisor").value.trim();
        const motivo = document.getElementById("motivoCancelacion").value;
        const uuidSustituto = document.getElementById("inputUUIDSustituto").value.trim();

        const regexUUID = /^[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}$/i;
        const regexRFC  = /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/i;

        if (!uuid) { alert("Ingresa o carga un XML para obtener el UUID."); return; }
        if (!regexUUID.test(uuid)) { alert("El UUID no tiene el formato correcto.\nEjemplo: FFB7D2D7-92F4-401D-B994-0FD05CBA6E50"); return; }

        if (!rfc) { alert("Ingresa o carga un XML para obtener el RFC Emisor."); return; }
        if (!regexRFC.test(rfc)) { alert("El RFC no tiene el formato correcto.\nEjemplo: RME980171ABZ"); return; }


        if (!motivo) { alert("Selecciona un motivo de cancelación."); return; }
        if (motivo === "01") { 
            if (!uuidSustituto) { alert("El motivo 01 requiere un UUID sustituto."); return; }
            if (!regexUUID.test(uuidSustituto)) { alert("El UUID sustituto no tiene el formato correcto."); return; }
        }

        enviarParaCancelar(uuid, rfc, motivo, uuidSustituto);
    }
};

function enviarParaCancelar(uuid, rfcEmisor, motivoCancelacion, uuidSustituto = "") {
    const formData = new FormData();
    formData.append("uuid", uuid);
    formData.append("rfc_emisor", rfcEmisor);
    formData.append("motivo_cancelacion", motivoCancelacion);
    formData.append("uuid_sustituto", uuidSustituto);

    const endpoint = "https://127.0.0.1:5001/cancelar-cfdi";
    fetch(endpoint, {
        method: "POST",
        body: formData
    })
    .then(r => {
        if (!r.ok) return r.json().then(data => { throw new Error(data.error || `Error del servidor (${r.status})`); });
        return r.json();
    })
    .then(data => {
        if (!data.success) { 
            alert("Error al cancelar:\n\n" + (data.error || "Error desconocido")); 
            return; 
        }
        let mensaje = `CFDI Enviado a Cancelar.\n\nEstado: ${data.descripcion}`;
        if (data.acuse)       mensaje += `\nAcuse: ${data.acuse}`;
        if (data.digest)      mensaje += `\nDigest: ${data.digest}`;
        if (data.certificado) mensaje += `\nCertificado: ${data.certificado}`;
        alert(mensaje);
    })
    .catch(err => {
        // console.error("Error al cancelar CFDI:", err);
        alert("Error al cancelar CFDI: " + err.message);
    });
}