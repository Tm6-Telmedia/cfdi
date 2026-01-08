let datos = [];
let datosFiltrados = [];
let productosIndexados = {};       // meta info: nombre, imagen, url, descripción
let productosPorSkuIndex = {};     // índice rápido: sku → array de productos
let paginaActual = 1;
const porPagina = 100;

document.addEventListener('DOMContentLoaded', init);

async function init() {
  try {
    const [productosRes, imagenesRes] = await Promise.all([
      fetch('/tm/assets/json/especificaciones.json').then(res => res.ok ? res.json() : []),
      fetch('/tm/assets/json/indexing-sin-npm.json').then(res => res.ok ? res.json() : [])
    ]);

    datos = (productosRes || []).filter(p => p.id_sku);
    datosFiltrados = datos;

    // -------------------------
    // INDEXAR META INFO
    imagenesRes.forEach(item => {
      if (!item?.id_sku) return;
      const sku = String(item.id_sku);
      productosIndexados[sku] = {
        nombre: item.d_nombre_sku || '', 
        url: fixProductUrl(item.d_url) || '',
        descripcion: item.d_descripcion || '',
        imagen: fixImagePath(item.img) || '/productos/thumb2/telmedia_0.webp'
      };
    });

    // -------------------------
    // INDEXAR PRODUCTOS POR SKU
    productosRes.forEach(item => {
      if (!item?.id_sku) return;
      const sku = String(item.id_sku);

      // índice de productos
      if (!productosPorSkuIndex[sku]) productosPorSkuIndex[sku] = [];
      productosPorSkuIndex[sku].push(item);

      // meta info nombre
      const marca = productosPorSkuIndex[sku].find(p => p.nombre?.toLowerCase() === "marca")?.valor || "";
      const modelo = productosPorSkuIndex[sku].find(p => p.nombre?.toLowerCase() === "modelo")?.valor || "";

      if (!productosIndexados[sku]) productosIndexados[sku] = {};

      productosIndexados[sku].nombre = productosIndexados[sku].nombre && productosIndexados[sku].nombre !== 'Sin nombre'
        ? productosIndexados[sku].nombre
        : (marca || modelo ? `${marca} ${modelo}`.trim() : "Sin nombre");

      if (!productosIndexados[sku].imagen) {
        productosIndexados[sku].imagen = '/productos/thumb2/telmedia_0.webp';
      }
    });

    // -------------------------
    // LÓGICA PARA URL DIRECTA DE SKUs
    const rawQuery = window.location.search; // "?1001,1002" o "?sku=1001,1002"
    if (rawQuery) {
      let skusParam = rawQuery.substring(1); // quita "?"
      if (skusParam.toLowerCase().startsWith("sku=")) {
        skusParam = skusParam.substring(4);
      }

      const listaSKUs = skusParam
        .split(',')
        .map(s => s.trim())
        .filter(s => s !== "")
        .slice(0, 5); // máximo 5 SKUs

      if (listaSKUs.length === 1) {
        // búsqueda rápida usando índice
        datosFiltrados = productosPorSkuIndex[listaSKUs[0]] || [];
        mostrarTabla();
        renderPaginacion();
      } else if (listaSKUs.length >= 2) {
        document.getElementById("skus").value = listaSKUs.join(",");
        compararSKUs(listaSKUs);
      }
    }

  } catch (err) {
    console.error("Error al cargar datos:", err);
  }
}

// -------------------------
// COMPARACIÓN DE SKUs OPTIMIZADA
function compararSKUs(skuList = null) {
  const input = skuList ? skuList.join(",") : (document.getElementById("skus")?.value || '');
  const listaSKUs = input
    .split(',')
    .map(s => s.trim())
    .filter(s => s !== "");

  const tabla = document.getElementById("tabla-comparador");
  const encabezado = document.getElementById("encabezadoComparacion");

  // Limpiar tabla previa
  tabla.innerHTML = "";
  encabezado.innerHTML = `<th id="col-especificacion">Especificación</th>`;

  if (listaSKUs.length < 2 || listaSKUs.length > 5) {
    tabla.innerHTML = `<tr><td colspan="99">Debes ingresar entre 2 y 5 SKUs separados por coma.</td></tr>`;
    return;
  }

  const productosPorSKU = {};
  const nombresGlobales = new Set();

  listaSKUs.forEach(sku => {
    const productos = productosPorSkuIndex[sku] || [];
    if (productos.length === 0) {
      tabla.innerHTML = `<tr><td colspan="99">El SKU ${sku} no fue encontrado en los datos.</td></tr>`;
      return;
    }
    productosPorSKU[sku] = productos;

    productos.forEach(p => nombresGlobales.add(normalizarTexto(p.nombre)));
  });

  const anchoCol = `${100 / (listaSKUs.length + 1)}%`;
  listaSKUs.forEach(sku => {
    const meta = productosIndexados[sku] || {};
    const rutaImagen = meta.imagen || '/productos/thumb2/telmedia_0.webp';
    const nombreProd = meta.nombre || 'Sin nombre';
    const url = meta.url || "#";

    encabezado.innerHTML += `
      <th style="width:${anchoCol}; text-align:center;">
        <a href="${url}" target="_blank" style="text-decoration:none; color:inherit; display:block;">
          <img src="${rutaImagen}" alt="SKU ${sku}" 
              style="height: 60px; display:block; margin:auto; margin-bottom:5px;"
              onerror="this.src='/productos/thumb2/telmedia_0.webp';">
          <div style="font-weight:bold;">${nombreProd}</div>
        </a>
      </th>`;
  });

  const filaSKU = document.createElement("tr");
  filaSKU.innerHTML = `<td><strong>SKU</strong></td>` + listaSKUs.map(sku => `<td style="text-align:center;">${sku}</td>`).join("");
  tabla.appendChild(filaSKU);

  nombresGlobales.forEach(nombreNorm => {
    let nombreOriginal = "";
    for (let sku of listaSKUs) {
      const prod = productosPorSKU[sku].find(p => normalizarTexto(p.nombre) === nombreNorm);
      if (prod) { nombreOriginal = prod.nombre; break; }
    }

    const fila = document.createElement("tr");
    fila.innerHTML = `<td><strong>${nombreOriginal}</strong></td>` +
      listaSKUs.map(sku => {
        const val = productosPorSKU[sku].find(p => normalizarTexto(p.nombre) === nombreNorm)?.valor || "-";
        return `<td style="text-align:center;">${val}</td>`;
      }).join("");

    tabla.appendChild(fila);
  });

  wrapTableResponsive();
  injectTableStyles();
}




  function renderPaginacion() {
    
    const totalPaginas = Math.ceil(datosFiltrados.length / porPagina);
    const contenedor = document.getElementById("paginacion");
    contenedor.innerHTML = "";

    const maxBotones = 5;
    let inicio = Math.max(1, paginaActual - Math.floor(maxBotones / 2));
    let fin = inicio + maxBotones - 1;

    if (fin > totalPaginas) {
      fin = totalPaginas;
      inicio = Math.max(1, fin - maxBotones + 1);
    }

    if (paginaActual > 1) {
      const prev = document.createElement("button");
      prev.textContent = " « ";
      prev.className = "btn btn-default btn-sm";
      prev.onclick = () => {
        paginaActual--;
        mostrarTabla();
        renderPaginacion();
      };
      contenedor.appendChild(prev);
    }

    if (inicio > 1) {
      contenedor.appendChild(document.createTextNode("..."));
    }

    for (let i = inicio; i <= fin; i++) {
      const btn = document.createElement("button");
      btn.textContent = i;
      btn.className = "btn btn-sm " + (i === paginaActual ? "btn-primary" : "btn-default");
      btn.onclick = () => {
        paginaActual = i;
        mostrarTabla();
        renderPaginacion();
      };
      contenedor.appendChild(btn);
    }
    if (fin < totalPaginas) {
      contenedor.appendChild(document.createTextNode(" ... "));
    }

    if (paginaActual < totalPaginas) {
      const next = document.createElement("button");
      next.textContent = " » ";
      next.className = "btn btn-default btn-sm";
      next.onclick = () => {
        paginaActual++;
        mostrarTabla();
        renderPaginacion();
      };
      contenedor.appendChild(next);
    }
  }

function buscar() {
  const filtro = (document.getElementById("busqueda")?.value || '').toLowerCase();

  datosFiltrados = datos.filter(item => {
    const sku = String(item.id_sku || '').toLowerCase();
    const nombreProd = (productosIndexados[sku]?._meta?.nombre || '').toLowerCase();
    return sku.includes(filtro) || nombreProd.includes(filtro);
  });

  paginaActual = 1;
  mostrarTabla();
  renderPaginacion();
}

function normalizarTexto(texto) {
  return texto
    .normalize("NFD")               // separa tildes
    .replace(/[\u0300-\u036f]/g, "") // elimina tildes
    .toLowerCase()
    .trim();
}

function compararSKUs() {
  const input = document.getElementById("skus").value;
  const skuList = input
    .split(',')
    .map(s => s.trim())
    .filter(s => s !== "");

  const tabla = document.getElementById("tabla-comparador");
  const encabezado = document.getElementById("encabezadoComparacion");

  // Limpiar tabla previa
  tabla.innerHTML = "";
  encabezado.innerHTML = `<th id="col-especificacion">Especificación</th>`;

  if (skuList.length < 2 || skuList.length > 5) {
    tabla.innerHTML = `<tr><td colspan="99">Debes ingresar entre 2 y 5 SKUs separados por coma.</td></tr>`;
    return;
  }

  const productosPorSKU = {};
  const nombresGlobales = new Set();

  for (let sku of skuList) {
    const productos = datos.filter(p => p.id_sku && String(p.id_sku) === sku);

    if (productos.length === 0) {
      tabla.innerHTML = `<tr><td colspan="99">El SKU ${sku} no fue encontrado en los datos.</td></tr>`;
      return;
    }
    productosPorSKU[sku] = productos;

    productos.forEach(p => {
      nombresGlobales.add(normalizarTexto(p.nombre));
    });
  }

  const anchoCol = `${100 / (skuList.length + 1)}%`; // +1 por columna de especificación
  skuList.forEach(sku => {
    const meta = productosIndexados[sku] || {};
    const rutaImagen = meta.imagen || '/productos/thumb2/telmedia_0.webp';
    const nombreProd = meta.nombre || 'Sin nombre';
    const url = meta.url || "#";

    encabezado.innerHTML += `
      <th style="width:${anchoCol}; text-align:center;">
        <a href="${url}" target="_blank" style="text-decoration:none; color:inherit; display:block;">
          <img src="${rutaImagen}" alt="SKU ${sku}" 
              style="height: 60px; display:block; margin:auto; margin-bottom:5px;"
              onerror="this.src='/productos/thumb2/telmedia_0.webp';">
          <div style="font-weight:bold;">${nombreProd}</div>
        </a>
      </th>`;
  });

  const filaSKU = document.createElement("tr");
  let htmlSKU = `<td><strong>SKU</strong></td>`;
  skuList.forEach(sku => {
    htmlSKU += `<td style="text-align:center;">${sku}</td>`;
  });
  filaSKU.innerHTML = htmlSKU;
  tabla.appendChild(filaSKU);

  nombresGlobales.forEach(nombreNorm => {
    let nombreOriginal = "";
    for (let sku of skuList) {
      const prod = productosPorSKU[sku].find(p => normalizarTexto(p.nombre) === nombreNorm);
      if (prod) {
        nombreOriginal = prod.nombre;
        break;
      }
    }

    const fila = document.createElement("tr");
    let html = `<td><strong>${nombreOriginal}</strong></td>`;

    skuList.forEach(sku => {
      const val = productosPorSKU[sku].find(p => normalizarTexto(p.nombre) === nombreNorm)?.valor || "-";
      html += `<td style="text-align:center;">${val}</td>`;
    });

    fila.innerHTML = html;
    tabla.appendChild(fila);
  });

  wrapTableResponsive();
  injectTableStyles();
}


function wrapTableResponsive() {
  const tbody = document.getElementById("tabla-comparador");
  if (!tbody) return;

  const tabla = tbody.closest("table"); 
  if (!tabla) return;

  // evitar duplicado
  if (tabla.parentElement.classList.contains("tabla-comparador-wrapper")) return;

  const wrapper = document.createElement("div");
  wrapper.className = "tabla-comparador-wrapper";
  tabla.parentNode.insertBefore(wrapper, tabla);
  wrapper.appendChild(tabla);
}

function injectTableStyles() {
  if (document.getElementById("compare-styles")) return; // evitar duplicado
  const style = document.createElement("style");
  style.id = "compare-styles";
  style.innerHTML = `
html, body {
  overflow-x: hidden; 
}

.tabla-comparador-wrapper {
  display: block;
  width: 100%;           
  max-width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  -webkit-overflow-scrolling: touch;
  margin: 0 auto;
  box-sizing: border-box;
}

.tabla-comparador-wrapper table {
  border-collapse: collapse;
  width: 100%;
  min-width: 600px;
}

#tabla-comparador th,
#tabla-comparador td {
  text-align: left;
  white-space: nowrap;
  padding: 8px;
}

@media (max-width: 768px) {
  .tabla-comparador-wrapper {
    width: 95vw;       
    max-width: 95vw;
  }

  #tabla-comparador th, 
  #tabla-comparador td {
    min-width: 140px;
    font-size: 13px;
  }
}    
  #tabla-comparador {
  table-layout: auto; 
  width: 100%;
}

#tabla-comparador th,
#tabla-comparador td {
  padding: 8px;
  white-space: nowrap; 
}

#tabla-comparador th#col-especificacion,
#tabla-comparador td:first-child {
  text-align: left;  
  white-space: nowrap; 
  width: 1%;           
}

#tabla-comparador th:not(#col-especificacion),
#tabla-comparador td:not(:first-child) {
  text-align: center;
}
  `;
  document.head.appendChild(style);
}


function renderPaginacionComparador() {
  const totalFilas = Math.max(datosSKU1.length, datosSKU2.length);
  const totalPaginas = Math.ceil(totalFilas / porPaginaComparador);
  const contenedor = document.getElementById("paginacion-comparador");
  contenedor.innerHTML = "";

  for (let i = 1; i <= totalPaginas; i++) {
    const btn = document.createElement("button");
    btn.className = "btn btn-sm " + (i === paginaComparador ? "btn-primary" : "btn-default");
    btn.textContent = i;
    btn.onclick = () => {
      paginaComparador = i;
      renderComparador();
      renderPaginacionComparador();
    };
    contenedor.appendChild(btn);
  }
}
function fixImagePath(img) {
  if (!img || img.trim() === '') return '/productos/thumb2/telmedia_0.webp';
  const p = img.trim();
  if (/^https?:\/\//i.test(p)) return p;
  if (p.startsWith('/productos')) return p;
  return '/productos/' + p.replace(/^\/?/, '');
}

function fixProductUrl(d_url) {
  if (!d_url || !String(d_url).trim()) return '';
  const url = String(d_url).trim();

  // URL absoluta (no modificar)
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith('/productos/')) return url;
  if (url.startsWith('/')) return '/productos' + url;
  if (url.startsWith('productos/')) return '/' + url;
  return '/productos/' + url.replace(/^\/?/, '');
}

