fetch('https://api.ipify.org?format=json')
    .then(response => response.json())
    .then(data => {
        const ip = data.ip;
        if (ip) {
            document.getElementById('ipId').textContent = ip;
            //document.getElementById('ipIpInput').value = ip;
        } else {
            document.getElementById('ipId').textContent = '0.0.0.0';
        }
    })
    .catch(error => {
        console.error('Error al obtener la dirección IP:', error);
        document.getElementById('ipId').textContent = '0.0.0.0';
    });
	
function hacerPeticion() {
    mostrarPopUp();
  }
	
//Script para el envio de correo electronico de contacto del formulario
function mostrarPopUp() {
    document.getElementById("miPopUp").style.display = "block";
    document.getElementById("nombre").value = "";
    document.getElementById("email").value = "";
    document.getElementById("telefono").value = "";
    document.getElementById("notas").value = "";
    document.getElementById('Enviar').style.display = 'block';
    document.getElementById('Carga').style.display = 'none';
}
function ocultarPopUp() {
    document.getElementById("miPopUp").style.display = "none";
    document.getElementById("nombre").value = "";
    document.getElementById("email").value = "";
    document.getElementById("telefono").value = "";
    document.getElementById("notas").value = "";
    document.getElementById('Enviar').style.display = 'block';
    document.getElementById('Carga').style.display = 'none';
}

var respuesta = document.getElementById('miPopUpRespuesta');
function ocultarPopUpRespuesta() {
    respuesta.style.display = "none";
}
function verRespuesta() {
    respuesta.style.display = 'block';
    document.getElementById('Enviar').style.display = 'block';
    document.getElementById('Carga').style.display = 'none';
}
function ocultarPopUpError() {
    document.getElementById('miPopUp-error').style.display = "none";
    boton.style.display = 'block';
    carga.style.display = 'none';
}
function ocultarPopUpRespuesta() {
    document.getElementById("miPopUpRespuesta").style.display = 'none';
    document.getElementById('Enviar').style.display = 'block';
    document.getElementById('Carga').style.display = 'none';
}

//---Funciones de validación
//validar solo numero en el input de telefono
function filtro() {
    var tecla = event.key;
    if ([".", "e", "-"].includes(tecla)) event.preventDefault();
}

// ... código de la función obtenerIPCliente() aquí ...
function obtenerIPCliente() {    
    // Crea un objeto XMLHttpRequest
    var xhr = new XMLHttpRequest();
    // Abre una conexión a un servicio externo que devuelve la IP del cliente
    xhr.open('GET', 'https://api.ipify.org?format=json', false);
    // Envía la solicitud
    xhr.send();
    // Parsea la respuesta JSON
    var respuesta = JSON.parse(xhr.responseText);
    // Devuelve la dirección IP del cliente
    return respuesta.ip;
}


//Funcion de envio de correo
//meter la ip en hidden
function func() {
    console.log("Enviando correo...");
    var Correo = document.getElementById("email").value;
    var Nombre = document.getElementById("nombre").value;
    var Telefono = document.getElementById("telefono").value;
    var Notas = document.getElementById("notas").value;
    //var Ip = document.getElementById("respuesta").innerHTML;

    //loadaer

    var button = document.getElementById('Enviar');
    var error_popup = document.getElementById('miPopUp-error');
    var Pop_up = document.getElementById('miPopUp');
    var carga = document.getElementById('Carga');
    var respuesta = document.getElementById('miPopUpRespuesta');
	var ip = document.getElementById('ipId').textContent;
    //var ip = obtenerIPCliente();
    // Mostrar loader
    //Pop_up.style.display = 'none';
    carga.style.display = 'block';
    // Deshabilitar botón durante la petición
    //button.disabled = true;
    button.style.display = 'none';


    //campos incorporados a nuevo formulario https://tm7.telmedia.com.mx/demo/karoll/MensajeNotificacion.shtml
    var rutaSitio = window.location.href;

    $.ajax({
        method: "POST",
        async: true,
        data: JSON.stringify({
            data:{
                access:"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJDb250YWN0IHRva2VuIiwiaWF0IjoxNzQ1NTE1MjU2LCJleHAiOjE3NzcwNTEyNTYsImF1ZCI6InRlbG1lZGlhLmNvbSIsInN1YiI6IiIsIkVtYWlsIjoiY29udGFjdG9AdGVsbWVkaWEuY29tIn0.ErjVxFB2Gaj8M4zWyPgcc_55vM3516j9L2EIATx0y0w",
                correo: Correo,
                nombre: Nombre,
                pais: "sin definir",
                estado: "sin definir",
                telefono: Telefono,
                empresa: "sin definir",
                notas:
                    Notas + " | Enviado desde: " +
                    rutaSitio,
                ip: ip
            }
            
        }), 
        
        url: "https://contact.1f9551mj0o83.us-south.codeengine.appdomain.cloud",
        contentType: "application/json",
        success: function (result) {
           

            // Habilitar botón después de la petición
            button.style.display = 'none';
            Pop_up.style.display = 'none';
            respuesta.style.display = 'block';
            //window.location.href = "/tm/ssi/registro.shtml";

        },
        error: function (error) {
            //alert('Error ${error}');
            console.log("hubo un error");
            // window.location.href = "/tm/ssi/errorForms.shtml";
            Pop_up.style.display = 'none';
            error_popup.style.display = 'block';
            // Habilitar botón después de la petición
            button.disabled = false;
        },
    })
        .done(function (data) { })
        .fail(function () { })
        .always(function () { });
    return false;
}

//---Agregamos eventos a Textarea notas
const textarea = document.getElementById('notas');
textarea.addEventListener("paste", (event) => {
    event.preventDefault();
});
textarea.addEventListener('paste', function (event) {
    event.preventDefault();
});

//Evento para envio de formulario
$("#Enviar").submit(function () { });