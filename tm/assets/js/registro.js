
var Ip=1;

$.get("https://ipinfo.io", function(response) { 
Ip=response.ip;
}, "json"); 


$('#Alta').submit(function(){
  var Correo=document.getElementById('Email').value;
  var Nombre=document.getElementById('Nombre').value;
  var Pais=document.getElementById('Pais').value;
  var Estado=document.getElementById('Estado').value;
  var Telefono=document.getElementById('Telefono').value;
  var Empresa=document.getElementById('Empresa').value;
  var Comentarios=document.getElementById('Comentarios').value;
  

 $.ajax({
  method: "POST",
  url: "https://tm6.telmedia.com.mx:2096/FormulariosContacto/formularios/recibedatosAlta",
  data: JSON.stringify({ email:Correo,nombre: Nombre,pais: Pais,estado:Estado,telefono:Telefono,empresa:Empresa,notas:Comentarios,ip:Ip}),
  contentType: "application/json",
  success:function(result){
      console.log(JSON.stringify({ email:Correo,nombre: Nombre,pais: Pais,estado:Estado,telefono:Telefono,empresa:Empresa,notas:Comentarios,ip:Ip}));
    //alert("Respuesta recibida");
  },error:function(error){
    console.log("entro en error");
    window.location.href = "/tm/ssi/errorForms.shtml" ;
  }
}).done(function(data) {
    console.log("entro al done");
   window.location.href = "/tm/ssi/registro.shtml" ;
   
  }).fail(function() {
    console.log("entro al fail");
    window.location.href = "/tm/ssi/errorForms.shtml" ;
    
  }).always(function() {
    
});
});

