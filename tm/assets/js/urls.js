//urls que tiene  redireccion conformada por el nombre y el sitio
const urls = {
    "store": "https://store.telmedia.com.mx",
    "poe": "https://wp20.telmedia.com.mx/tabla-poe",
    "ethernet":"https://wp20.telmedia.com.mx/tabla-velocidades",
    "mac":"https://telmedia.com.mx/apps/widgets/macCrawler/macCrawler.shtml",
    "whois":"https://telmedia.com.mx/apps/widgets/whois/whois.shtml",
    "zips":"tm7.telmedia.com.mx:8088/all",
    "redhat":"https://wp20.telmedia.com.mx/tabla-redhat-standard",
    "ladas":"https://telmedia.com.mx/intranet/widgets/lada/lada.shtml",
    "mip":"https://telmedia.com.mx/recursos/mip.shtml",
    "tablas":"https://wp20.telmedia.com.mx/indice-de-tablas",
    "comparador":"https://telmedia.com.mx/apps/widgets/comparador/comparador.shtml",
    "contacto":"https://www.telmedia.com.mx/tm/ssi/formregistro.shtml",
}
//Funcion de para iniciar el proceso
function run() {
    //Buscar el parametro a donde se a solicitado mediante un ? 
    var nameUrl = window.location.search.replace("?", "")
    //Verificar si existe un pametro
    if (nameUrl) {
        //Verificar si existe el nombre en nuestros registros
        //Redireccionar al lugar indicado con la url de nuestros registros
        if (urls[nameUrl]) return window.location.href = urls[nameUrl];

        //Si no existe el parametro o el registro de el , enviarlo a la pagina principal o la busqueda para un posible error 404
        else return window.location.href = window.location.origin + "/" + nameUrl;
    }

}
//Activacion del proceso
run();
