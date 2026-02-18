
let xmlOriginal = null;
const inputXMLAplicacion = document.querySelector('#xmlAplicacion');

// VALIDACIONES 
function validarRFC(rfc) {
    const regex = /^([A-ZÑ&]{3,4})(\d{6})([A-Z0-9]{3})$/i;
    return regex.test(rfc);
}

function validarNombre(nom){
    return nom.trim().length > 0;
}

function validarCP(cp){
    return /^[0-9]{5}$/.test(cp);
}

function validarRegimen(reg){
    return /^[0-9]{3}$/.test(reg);
}

function validarUsoCFDI(uso){
    return uso.trim() !== "";
}

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

function validarFolio(folio) {
    folio.trim();
    if (folio === '') {
        alert('El folio no puede tener espacios en blanco');
        if (folio.length < 4 || folio.length > 4) {
            alert('El folio debe ser de 4 digitos');
        }
        return;
    }
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

    // Resetear TODO al cambiar de tipo
    formaPagoSection.classList.add("hidden");
    formaPagoSelect.required = false;
    cancelacionSection.classList.add("hidden");
    motivoCancelacion.required = false;
    subirXMLSection.classList.add("hidden");
    xmlUnicoSection.classList.add("hidden");
    xmlAnticipoSection.classList.add("hidden");
    btnContinuar.classList.remove("hidden"); // Volver a mostrar el botón Continuar

    if (tipoSeleccionado === "complemento") {
        formaPagoSection.classList.remove("hidden");
        formaPagoSelect.required = true;
    } else if (tipoSeleccionado === "anticipo") {
        formaPagoSelect.value = "99";
    } else if (tipoSeleccionado === "cancelar") {
        cancelacionSection.classList.remove("hidden");
        motivoCancelacion.required = true;
    }
}

document.getElementById("tipoTimbrado").onchange = function() {
    actualizarSecciones(this.value);
};

// Ejecutar al cargar la página por si el navegador restauró
// un valor previo en el select (problema del estado al recargar)
document.addEventListener("DOMContentLoaded", () => {
    const tipoSeleccionado = document.getElementById("tipoTimbrado").value;
    if (tipoSeleccionado) {
        actualizarSecciones(tipoSeleccionado);
    }
});


// CONTINUAR
document.getElementById("btnContinuarTimbrado").onclick = () => {
    const tipoSeleccionado = document.getElementById("tipoTimbrado").value;
    
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
    } else {
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
    const tipoSeleccionado = document.getElementById("tipoTimbrado").value;
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
        console.log(base);
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


function validarFechaXML(xmlDoc) {
    const comprobante = xmlDoc.getElementsByTagName("cfdi:Comprobante")[0];
    const fechaXML = comprobante.getAttribute("Fecha");
    const fechaNomina = comprobante.getAttribute("fecha");
    
    if (!fechaXML && !fechaNomina) {
        alert("El XML no contiene una fecha válida.");
        return false;
    }
    
    const fechaComprobante = new Date(fechaXML);
    if (isNaN(fechaComprobante.getTime())) {
        alert("La fecha en el XML tiene un formato inválido.");
        return false;
    }
    
    const ahora = new Date();
    const maxPermitida = new Date(ahora.getTime() + (72 * 60 * 60 * 1000));
    if (fechaComprobante > maxPermitida) {
        alert("Error: La fecha del comprobante no puede ser mayor a 72 horas desde ahora.\n\nFecha en el XML: " + fechaXML + "\nFecha máxima permitida: " + maxPermitida.toISOString());
        return false;
    }
    
    return true;
}


// PROCESAR XML
document.getElementById("procesarXML").onclick = () => {
    const tipoSeleccionado = document.getElementById("tipoTimbrado").value;
    
    if (tipoSeleccionado === "anticipo") {
        const archivoProductos  = document.getElementById("xmlProductos").files[0];
        const archivoAplicacion = document.getElementById("xmlAplicacion").files[0];
        if (!archivoProductos)  { alert("Sube el Primer XML.");  return; }
        if (!archivoAplicacion) { alert("Sube el Segundo XML."); return; }
        procesarXMLsAnticipo(archivoProductos, archivoAplicacion);
    } else if (tipoSeleccionado === "complemento" || tipoSeleccionado === "nomina") {
        const archivo = document.getElementById("xmlFile").files[0];
        if (!archivo) { alert("Sube un XML."); return; }
        procesarXMLUnico(archivo);
    }
};


function procesarXMLUnico(archivo) {
    const tipoSeleccionado = document.getElementById("tipoTimbrado").value;
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
    
    if (xmlOriginal && !validarFechaXML(xmlOriginal)) {
        return;
    } else if (faltan.length === 0) {
        alert("XML COMPLETO: Enviado a timbrar.");
        enviarParaTimbrar(xmlOriginal);
        return;
    }
    
    let html = "";
    faltan.forEach(f => {
        html += `<label class="campo-label">${f.attr}</label>
     <input type="text" class="entrada-texto" data-campo="${f.attr}" value="">`;
    });
    
    document.getElementById("faltantesCampos").innerHTML = html;
    document.getElementById("faltantesSection").classList.remove("hidden");
}


// --- ENVIAR PARA TIMBRAR ---
function enviarParaTimbrar(xmlDom){
    const tipoSeleccionado = document.getElementById("tipoTimbrado").value;
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
    // console.log("Tipo seleccionado:", tipoSeleccionado);
    // console.log("Forma de pago seleccionada:", formaPagoSeleccionada, "-", formaPagoTexto);
    
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
            console.warn("Error generando PDF:", data.pdf_error);
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
        console.error("Error enviando a timbrar:", err);
        alert("Error enviando a timbrar: " + err.message);
    });
}