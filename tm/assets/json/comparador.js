
let datos = [];
let datosFiltrados = [];
let imagenesPorSku = {}; //indexar las imágenes
let paginaActual = 1;
const porPagina = 100;

window.onload = async function () {
  try {
    const [productosRes, imagenesRes] = await Promise.all([
      fetch('/tm/assets/json/productos.json').then(res => res.json()),
      fetch('/tm/assets/json/indexing.json').then(res => res.json())
    ]);

    // Solo productos válidos
    datos = productosRes.filter(p => p.id_sku);
    datosFiltrados = datos;

    // Indexar imágenes por SKU desde indexing
    imagenesRes.forEach(item => {
      if (item.id_sku && item.img) {
        imagenesPorSku[item.id_sku] = fixImagePath(item.img);
      }
    });

   // mostrarTabla();
   // renderPaginacion();
  } catch (err) {
    console.error("Error al cargar datos:", err);
  }
};


function mostrarTabla() {
  const tbody = document.querySelector("#tabla tbody");
  tbody.innerHTML = "";

  const inicio = (paginaActual - 1) * porPagina; 
  const fin = inicio + porPagina;
  const datosPagina = datosFiltrados.slice(inicio, fin);

  datosPagina.forEach(item => {
    if (!item.id_sku) return; // saltar si no tiene SKU

    const fila = document.createElement("tr");

    const imagenSrc = imagenesPorSku[item.id_sku] || '/productos/thumb2/telmedia_0.webp'; 

    fila.innerHTML = `
      <td>${item.id_sku}</td>
      <td>
        <img src="${imagenSrc}" alt="${item.nombre || ''}" style="height: 40px; vertical-align: middle; margin-right: 8px;"
             onerror="this.src='/productos/thumb2/telmedia_0.webp';">
        ${item.nombre || ''}
      </td>
      <td>${item.valor || '-'}</td>
    `;

    tbody.appendChild(fila);
  });
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
    const filtro = document.getElementById("busqueda").value.toLowerCase();
    datosFiltrados = datos.filter(item =>
      String(item.id_sku).toLowerCase().includes(filtro) ||
      String(item.nombre).toLowerCase().includes(filtro)
    );
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
  encabezado.innerHTML = "<th>Especificación</th>";

  if (skuList.length < 2 || skuList.length > 5) {
    tabla.innerHTML = `<tr><td colspan="99">Debes ingresar entre 2 y 5 SKUs separados por coma.</td></tr>`;
    return;
  }

  const productosPorSKU = {};
  const nombresGlobales = new Set();

  // Recopilar productos y nombres únicos de todos los SKUs
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

  // Encabezado con imagen y SKU
 skuList.forEach(sku => {
  const rutaImagen = imagenesPorSku[sku] || '/productos/thumb2/telmedia_0.webp';

  encabezado.innerHTML += `
    <th>
      <img src="${rutaImagen}" alt="SKU ${sku}" style="height: 50px; display:block; margin:auto; margin-bottom:5px;"
           onerror="this.src='/productos/thumb2/telmedia_0.webp';">
      SKU ${sku}
    </th>`;
});



  // Mostrar todas las especificaciones 
  nombresGlobales.forEach(nombreNorm => {
    // Obtener el nombre original desde cualquier SKU
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
      html += `<td>${val}</td>`;
    });

    fila.innerHTML = html;
    tabla.appendChild(fila);
  });
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
  return img.replace(/^\/?productos\//, '/productos/');
}

