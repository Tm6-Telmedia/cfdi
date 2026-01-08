let imagenesPorSku = {};
let erroresImagen = {};

window.onload = async function () {
  const urlParams = new URLSearchParams(window.location.search);
  const skusParam = urlParams.get('skus');
  const pathParam = urlParams.get('path');

  if (!skusParam || !pathParam) {
    document.getElementById("tabla-comparador").innerHTML =
      "<tr><td colspan='99'>No se seleccionaron productos para comparar.</td></tr>";
    return;
  }

  const idSkus = skusParam.split(',').map(s => s.trim());
  const productosFinales = {};

  try {
    const [productosAtributos, productosIndexing] = await Promise.allSettled([
      //cambiar la ruta al archivo
      fetch('/tm/assets/json/especificaciones.json').then(res => res.ok ? res.json() : []),
      fetch('/tm/assets/json/indexing-sin-npm.json').then(res => res.ok ? res.json() : [])
    ]);

    if (productosIndexing.status === "fulfilled" && Array.isArray(productosIndexing.value)) {
      productosIndexing.value.forEach(item => {
        if (item.id_sku && item.img) {
          imagenesPorSku[String(item.id_sku)] = fixImagePath(item.img);
        }
      });

      productosIndexing.value.forEach(p => {
        const sku = String(p.id_sku);
        if (!idSkus.includes(sku)) return;
        if (!productosFinales[sku]) productosFinales[sku] = {};
        productosFinales[sku]._meta = {
          nombre: p.d_nombre_sku || '',
          sku: p.id_sku,
          descripcion: p.d_descripcion || '',
          url: p.d_url || ''
        };
      });
    }
    
    if (productosAtributos.status === "fulfilled" && Array.isArray(productosAtributos.value)) {
    productosAtributos.value.forEach(p => {
      const sku = String(p.id_sku ?? p.id_seq);
      if (!idSkus.includes(sku)) return;
      if (!productosFinales[sku]) productosFinales[sku] = {};
      productosFinales[sku][p.nombre] = p.valor;
    });
}

    mostrarComparacion(productosFinales, idSkus);
  } catch (error) {
    console.error("Error cargando datos:", error);
    document.getElementById("tabla-comparador").innerHTML =
      "<tr><td colspan='99'>Error al cargar datos para comparar.</td></tr>";
  }
  wrapCompareTable();
};

function wrapCompareTable() {
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

function injectCompareStyles() {
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


  `;
  document.head.appendChild(style);
}


function mostrarComparacion(productos, skuList) {
  const tabla = document.getElementById("tabla-comparador");
  const encabezado = document.getElementById("encabezadoComparacion");

  tabla.innerHTML = "";
  encabezado.innerHTML = "<th>Especificación</th>";

  skuList.forEach(sku => {
  const meta = productos[sku]?._meta || {};
  const rutaImagen = imagenesPorSku[sku] || '/productos/thumb2/telmedia_0.webp';
  const url = meta.url || "#";

  encabezado.innerHTML += `
    <th>
      <a href="${url}" target="_blank" style="text-decoration:none; color:inherit;">
        <img src="${rutaImagen}" 
             alt="SKU ${sku}"
             style="height: 50px; display:block; margin:auto; margin-bottom:5px;"
             onerror="manejarErrorImagen(this, '${sku}')">
        <div>${meta.nombre || '-'}</div>
        <div><strong>SKU:</strong> ${meta.sku || sku}</div>
      </a>
    </th>`;
});


  const atributosSet = new Set();
  skuList.forEach(sku => {
    const producto = productos[sku];
    if (!producto) return;
    Object.keys(producto).forEach(k => {
      if (k !== '_meta') atributosSet.add(k);
    });
  });

  const atributos = Array.from(atributosSet);
  atributos.forEach(attr => {
    const fila = document.createElement("tr");
    let html = `<td><strong>${attr}</strong></td>`;
    skuList.forEach(sku => {
      let valor = "-";
      if (attr === 'Descripción') {
        valor = productos[sku]?._meta?.descripcion || "-";
      } else if (attr === 'Link') {
        const url = productos[sku]?._meta?.url || "";
        valor = url ? `<a href="${url}" target="_blank">Ver producto</a>` : "-";
      } else {
        valor = productos[sku]?.[attr] || "-";
      }
      html += `<td>${valor}</td>`;
    });
    fila.innerHTML = html;
    tabla.appendChild(fila);
  });
  injectCompareStyles();
}

function fixImagePath(img) {
  if (!img || img.trim() === '') return '/productos/thumb2/telmedia_0.webp';
  if (img.startsWith('/productos') || img.startsWith('http')) return img;
  return '/productos/' + img.replace(/^\/?/, '');
}

function manejarErrorImagen(img, sku) {
  if (!erroresImagen[sku]) erroresImagen[sku] = 0;
  erroresImagen[sku]++;
  if (erroresImagen[sku] <= 1) {
    img.src = '/productos/thumb2/telmedia_0.webp';
  } else {
    console.warn(`Imagen de SKU ${sku} no encontrada`);
  }
}


