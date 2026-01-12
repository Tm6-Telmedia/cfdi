let xmlOriginal = null;

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

function validarCFDIParaTimbrar(archivoXML) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        
        reader.onload = function(e) {
            const contenido = e.target.result;
            
            try {
                // Parsear XML
                const parser = new DOMParser();
                const xmlDoc = parser.parseFromString(contenido, "text/xml");
                
                // Verificar errores de parseo
                const parseError = xmlDoc.querySelector('parsererror');
                if (parseError) {
                    reject({
                        valido: false,
                        errores: ['El XML tiene errores de sintaxis']
                    });
                    return;
                }
                
                // Array para almacenar errores
                const errores = [];
                const advertencias = [];
                
                // 1. Validar UUID (debe existir y no estar vacío)
                const timbre = xmlDoc.querySelector('TimbreFiscalDigital, tfd\\:TimbreFiscalDigital');
                if (timbre) {
                    const uuid = timbre.getAttribute('UUID');
                    const regexUUID = /^[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}$/i;
                    
                    if (!uuid || uuid.trim() === '') {
                        errores.push('El UUID está vacío. Debe contener un identificador válido antes de timbrar.');
                    } else if (!regexUUID.test(uuid)) {
                        errores.push(`El UUID "${uuid}" no tiene el formato correcto (ej: 12345678-1234-1234-1234-123456789012)`);
                    }
                } else {
                    advertencias.push('No se encontró el nodo TimbreFiscalDigital. Se agregará al timbrar.');
                }
                
                // 2. Validar Conceptos
                const conceptos = xmlDoc.querySelectorAll('Concepto, cfdi\\:Concepto');
                
                if (conceptos.length === 0) {
                    errores.push('No se encontraron conceptos en el CFDI');
                } else {
                    conceptos.forEach((concepto, index) => {
                        // 2.1 Validar ClaveProdServ (8 dígitos numéricos)
                        const claveProdServ = concepto.getAttribute('ClaveProdServ');
                        const regexClave = /^\d{8}$/;
                        
                        if (!claveProdServ) {
                            errores.push(`Concepto ${index + 1}: Falta el atributo ClaveProdServ`);
                        } else if (!regexClave.test(claveProdServ)) {
                            errores.push(`Concepto ${index + 1}: ClaveProdServ "${claveProdServ}" debe contener exactamente 8 dígitos numéricos`);
                        }
                        
                        // 2.2 Validar ClaveUnidad (debe ser "ACT")
                        const claveUnidad = concepto.getAttribute('ClaveUnidad');
                        
                        if (!claveUnidad) {
                            errores.push(`Concepto ${index + 1}: Falta el atributo ClaveUnidad`);
                        } else if (claveUnidad !== 'ACT') {
                            errores.push(`Concepto ${index + 1}: ClaveUnidad debe ser "ACT", se encontró "${claveUnidad}"`);
                        }
                        
                        // 2.3 Validar Descripción (debe contener la palabra "Anticipo")
                        const descripcion = concepto.getAttribute('Descripcion');
                        
                        if (!descripcion) {
                            errores.push(`Concepto ${index + 1}: Falta el atributo Descripcion`);
                        } else if (!descripcion.toLowerCase().includes('anticipo')) {
                            errores.push(`Concepto ${index + 1}: La Descripción debe contener la palabra "Anticipo". Se encontró: "${descripcion}"`);
                        }
                    });
                }
                
                // 3. Validaciones adicionales recomendadas
                
                // 3.1 RFC Emisor
                const emisor = xmlDoc.querySelector('Emisor, cfdi\\:Emisor');
                if (emisor) {
                    const rfcEmisor = emisor.getAttribute('Rfc');
                    const regexRFC = /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/;
                    if (!rfcEmisor || !regexRFC.test(rfcEmisor)) {
                        errores.push(`RFC del Emisor inválido: "${rfcEmisor}"`);
                    }
                }
                
                // 3.2 RFC Receptor
                const receptor = xmlDoc.querySelector('Receptor, cfdi\\:Receptor');
                if (receptor) {
                    const rfcReceptor = receptor.getAttribute('Rfc');
                    const regexRFC = /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/;
                    if (!rfcReceptor || !regexRFC.test(rfcReceptor)) {
                        errores.push(`RFC del Receptor inválido: "${rfcReceptor}"`);
                    }
                }
                
                
                // Resultado final
                if (errores.length === 0) {
                    resolve({
                        valido: true,
                        mensaje: 'XML válido para timbrar',
                        advertencias: advertencias,
                        xml: contenido,
                        xmlDoc: xmlDoc
                    });
                } else {
                    reject({
                        valido: false,
                        errores: errores,
                        advertencias: advertencias
                    });
                }
                
            } catch (error) {
                reject({
                    valido: false,
                    errores: [`Error al procesar el XML: ${error.message}`]
                });
            }
        };
        
        reader.onerror = () => {
            reject({
                valido: false,
                errores: ['Error al leer el archivo']
            });
        };
        
        reader.readAsText(archivoXML);
    });
}


// MOSTRAR/OCULTAR FORMA DE PAGO Y SECCIONES XML SEGÚN TIPO SELECCIONADO
document.getElementById("tipoTimbrado").onchange = function() {
    const tipoSeleccionado = this.value;
    const formaPagoSection = document.getElementById("formaPagoSection");
    const formaPagoSelect = document.getElementById("formaPago");
    
    if (tipoSeleccionado === "complemento") {
        // Mostrar forma de pago para complemento de pago
        formaPagoSection.classList.remove("hidden");
        formaPagoSelect.required = true;
    } else if (tipoSeleccionado === "anticipo") {
        // Ocultar forma de pago para aplicación de anticipo
        formaPagoSection.classList.add("hidden");
        formaPagoSelect.required = false;
        formaPagoSelect.value = "99"; // Valor fijo para anticipo (Por definir)
    }
};

//CONTINUAR 
document.getElementById("btnContinuarTimbrado").onclick = () => {
    const tipoSeleccionado = document.getElementById("tipoTimbrado").value;
    
    if(!tipoSeleccionado){
        alert("Selecciona un tipo.");
        return;
    }
    
    // Solo validar forma de pago si es complemento de pago
    if(tipoSeleccionado === "complemento" && !document.getElementById("formaPago").value){
        alert("Selecciona una forma de pago.");
        return;
    }
    
    // Mostrar sección de subir XML
    document.getElementById("subirXMLSection").classList.remove("hidden");
    
    // Mostrar/ocultar secciones según el tipo
    const xmlUnicoSection = document.getElementById("xmlUnicoSection");
    const xmlAnticipoSection = document.getElementById("xmlAnticipoSection");
    
    if (tipoSeleccionado === "anticipo") {
        // Para anticipo: mostrar sección de dos XMLs
        xmlUnicoSection.classList.add("hidden");
        xmlAnticipoSection.classList.remove("hidden");
    } else {
        // Para complemento: mostrar sección de un XML
        xmlUnicoSection.classList.remove("hidden");
        xmlAnticipoSection.classList.add("hidden");
    }
};

// MOSTRAR NOMBRE DEL ARCHIVO
document.getElementById("xmlFile").onchange = function() {
    const archivo = this.files[0];
    const fileNameDiv = document.getElementById("fileName");
    if(archivo) {
        fileNameDiv.textContent = archivo.name;
    } else {
        fileNameDiv.textContent = "";
    }
};

// MOSTRAR NOMBRES DE ARCHIVOS PARA ANTICIPO
document.getElementById("xmlProductos").onchange = function() {
    const archivo = this.files[0];
    const fileNameDiv = document.getElementById("fileNameProductos");
     const btnValidarCFDI = document.getElementById('validarCFDI');
     
    if(archivo) {
        fileNameDiv.textContent = archivo.name;
       
        btnValidarCFDI.onclick = function () {
            validarCFDIParaTimbrar(archivo);
        }
        
    } else {
        fileNameDiv.textContent = "";
    }
};

document.getElementById("xmlAplicacion").onchange = function() {
    const archivo = this.files[0];
    const fileNameDiv = document.getElementById("fileNameAplicacion");
    
    if(archivo) {
        fileNameDiv.textContent = archivo.name;
    } else {
        fileNameDiv.textContent = "";
    }
};

// PROCESAR XML 
document.getElementById("procesarXML").onclick = () => {
    const tipoSeleccionado = document.getElementById("tipoTimbrado").value;
    
    if (tipoSeleccionado === "anticipo") {
        // Para anticipo: validar que se hayan subido ambos XMLs
        const archivoProductos = document.getElementById("xmlProductos").files[0];
        //AQUI DEBO VALIDAR QUE EL PRIMERO XML SEA EL REQUERIDO Y LO MISMO PARA EL SEGUNDO
        const archivoAplicacion = document.getElementById("xmlAplicacion").files[0];
        
        if(!archivoProductos){ 
            alert("Sube el Primer XML."); 
            return; 
        }
        
        if(!archivoAplicacion){ 
            alert("Sube el Segundo XML."); 
            return; 
        }
        
        // Procesar ambos XMLs para anticipo
        procesarXMLsAnticipo(archivoProductos, archivoAplicacion);
        
    } else {
        // Para complemento: validar un solo XML
        const archivo = document.getElementById("xmlFile").files[0];
        if(!archivo){ 
            alert("Sube un XML."); 
            return; 
        }
        
        // Procesar XML único
        procesarXMLUnico(archivo);
    }
};

// PROCESAR XML ÚNICO (COMPLEMENTO DE PAGO)
function procesarXMLUnico(archivo) {
    const lector = new FileReader();
    lector.onload = e => {
        const parser = new DOMParser();
        const xml = parser.parseFromString(e.target.result, "text/xml");
        xmlOriginal = xml;
        procesarDatosFaltantes(xml);
    };
    lector.readAsText(archivo);
}

// PROCESAR XMLs DE ANTICIPO
function procesarXMLsAnticipo(archivoProductos, archivoAplicacion) {
    let xmlProductos = null;
    let xmlAplicacion = null;
    let procesados = 0;
    
    // Leer XML de productos
    const lectorProductos = new FileReader();
    lectorProductos.onload = e => {
        const parser = new DOMParser();
        xmlProductos = parser.parseFromString(e.target.result, "text/xml");
        procesados++;
        
        if (procesados === 2) {
            // Ambos XMLs procesados, usar el de productos como principal
            xmlOriginal = xmlProductos;
            procesarDatosFaltantes(xmlProductos);
        }
    };
    lectorProductos.readAsText(archivoProductos);
    
    
    // Leer XML de aplicación
    const lectorAplicacion = new FileReader();
    lectorAplicacion.onload = e => {
        const parser = new DOMParser();
        xmlAplicacion = parser.parseFromString(e.target.result, "text/xml");
        procesados++;
        
        if (procesados === 2) {
            // Ambos XMLs procesados, usar el de productos como principal
            xmlOriginal = xmlProductos;
            procesarDatosFaltantes(xmlProductos);
        }
    };
    lectorAplicacion.readAsText(archivoAplicacion);
}

// PROCESAR DATOS FALTANTES (COMÚN PARA AMBOS TIPOS)
function procesarDatosFaltantes(xml) {
    let faltan = [];
    const todosElementos = xml.getElementsByTagName("*");

    for(let el of todosElementos){
        for(let attr of el.attributes){
            let esPlantilla = attr.value.includes("{{");
            let esVacio = attr.value.trim() === "";
            let sinComillas = (
                esVacio &&
                !el.outerHTML.includes(attr.name + "=\"")
            );

            if(esPlantilla || esVacio || sinComillas){
                faltan.push({
                    elemento: el,
                    attr: attr.name,
                    valor: attr.value
                });
            }
        }
    }

    if(faltan.length===0){
        alert("XML COMPLETO: Enviado a timbrar.");
        enviarParaTimbrar(xmlOriginal);
        return;
    }

    let html="";
    faltan.forEach(f=>{
        html += `<label>${f.attr}</label>
     <input type="text" data-campo="${f.attr}" value="">`;
    });

    document.getElementById("faltantesCampos").innerHTML = html;
    document.getElementById("faltantesSection").classList.remove("hidden");
}

// GUARDAR DATOS 
document.getElementById("btnGuardarDatos").onclick = () => {

    const inputs = document.querySelectorAll("#faltantesCampos input");
    let errores = [];

    inputs.forEach(input => input.classList.remove("errorCampo"));

    inputs.forEach(input => {
        const campo = input.dataset.campo;
        const val = input.value.trim();

        if(campo.toUpperCase() === "RFC"){
            if(!validarRFC(val)){
                errores.push("RFC incorrecto (deben ser 12/13 caracteres alfanuméricos).");
                input.classList.add("errorCampo");
            }
        }

        if(campo.toUpperCase() === "NOMBRE"){
            if(!validarNombre(val)){
                errores.push("El nombre no puede estar vacío.");
                input.classList.add("errorCampo");
            }
        }

        if(campo.toUpperCase() === "CODIGOPOSTAL" || campo.toUpperCase()==="CP"){
            if(!validarCP(val)){
                errores.push("Código Postal inválido (5 dígitos).");
                input.classList.add("errorCampo");
            }
        }

        if(campo.toUpperCase() === "REGIMENFISCAL"){
            if(!validarRegimen(val)){
                errores.push("Régimen Fiscal inválido (3 dígitos).");
                input.classList.add("errorCampo");
            }
        }

        if(campo.toUpperCase() === "USOCFDI"){
            if(!validarUsoCFDI(val)){
                errores.push("Uso CFDI inválido.");
                input.classList.add("errorCampo");
            }
        }
    });

    if(errores.length > 0){
        alert("No se puede timbrar:\n\n" + errores.join("\n"));
        return;
    }

    inputs.forEach(input=>{
        const campo = input.dataset.campo;
        const valor = input.value;

        const todosElementos = xmlOriginal.getElementsByTagName("*");
        for(let el of todosElementos){
            if(el.hasAttribute(campo)){
                el.setAttribute(campo, valor);
            }
        }
    });

    enviarParaTimbrar(xmlOriginal);
};

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
    } else {
        // Para complemento: enviar un XML
        formData.append("xml", xmlBlob, "factura.xml");
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
    console.log("Tipo seleccionado:", tipoSeleccionado);
    console.log("Forma de pago seleccionada:", formaPagoSeleccionada, "-", formaPagoTexto);
    
    let endpoint;
    if (tipoSeleccionado === "complemento") {
    // tm7.telmedia.com.mx
        endpoint = "https://127.0.0.1:5000/timbrar-complemento-pago"; 
    } else if (tipoSeleccionado === "anticipo") {
        endpoint = "https://127.0.0.1:5000/timbrar-aplicacion-anticipo";
    } else {
        alert("Selecciona un tipo válido.");
        return;
    }

    fetch(endpoint, {
        method:"POST",
        body:formData
    })
    .then(r=>r.json())
    .then(data=>{
        // Verificar si hay error
        if(!data.success || data.error){
            alert("Error del servidor: " + (data.error || "Error desconocido"));
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