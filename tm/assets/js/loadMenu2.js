const tbody = document.getElementById('tbody');
const cardsContent = document.getElementById('cardsContent');
const view = document.getElementById('view');
const table = document.getElementById('table');
const h1 = document.getElementById('h1');

let response = "";
const acent = {
  "CATEGORIA": "CATEGORÍA",
  "CATALOGO": "CATÁLOGO",
  "EOS": "EOS",
  "EOS CON STOCK": "EOS",  
  "SUSCRIPCIONES": "SUSCRIPCIONES",
  "LIQUIDACION": "LIQUIDACION"
};
(() => {
  const s = document.createElement('style');
  s.textContent = `
    .compare-checkbox {
      cursor: pointer;
      accent-color: #2b6cb0; 
      width: 18px;
      height: 18px;
      cursor: pointer;
    }
     td:has(.compare-checkbox) {
      text-align: center;
      vertical-align: middle;
    }

    td.category-header:last-child{
    tr td:last-child {
    width: 1%;
    white-space: nowrap;
    }}
    
    #compareButtonMosaico {
    position: absolute;         
    right: 10%;             
    z-index: 1000;
    padding: 8px 14px;
    font-size: 14px;
    border-radius: 6px;
  }
    @media (max-width: 768px) {
    #compareButtonMosaico {
    right: 10%;         
    font-size: 13px;
    padding: 6px 12px;
  }}

  @media (max-width: 768px) {
  .table-container {
    width: 100%;               
    overflow-x: auto;          
    -webkit-overflow-scrolling: touch; 
  }

  .table-container table {
    width: 100%;             
    min-width: 600px;          
    border-collapse: collapse;
  }
}
  @media (max-width: 768px) {
  .panel.panel-default {
    display: block;
    min-width: 600px;  
  }
}

  #compareButtonTable {
    position: absolute;     
    right: 1%;             
    z-index: 1500;
    padding: 8px 14px;
    font-size: 14px;
    border-radius: 6px;
  }
    @media (max-width: 768px) {
    #compareButtonTable {
    right: -47%;         
    font-size: 13px;
    padding: 6px 12px;
  }}
  
#cardsContent .card_category_item {
  flex: 0 0 260px !important;
  max-width: 260px !important;
}

/* Imagen no controla el ancho */
#cardsContent .card_category_item img {
  max-width: 100%;
  height: auto;
}

  `;
  document.head.appendChild(s);
})();

(function interceptAt2xRequests(){
  const stripAt2x = url => url.replace(/@2x(?=\.[a-z0-9]+(?:[?#]|$))/i, '');


  const origFetch = window.fetch;
  window.fetch = function(resource, init) {
    if (typeof resource === 'string' && resource.includes('@2x')) {
      resource = stripAt2x(resource);
    } else if (resource instanceof Request && resource.url.includes('@2x')) {
      resource = new Request(stripAt2x(resource.url), resource);
    }
    return origFetch.call(this, resource, init);
  };

  const origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    if (typeof url === 'string' && url.includes('@2x')) {
      url = stripAt2x(url);
    }
    return origOpen.call(this, method, url, ...rest);
  };

 
  document.addEventListener("error", e => {
    if (e.target.tagName === "IMG" || e.target.tagName === "SOURCE") {
      if (e.target.src && e.target.src.includes("@2x")) {
        e.target.src = stripAt2x(e.target.src);
      }
      if (e.target.srcset && e.target.srcset.includes("@2x")) {
        e.target.srcset = e.target.srcset.split(",")
          .map(s => s.trim())
          .filter(s => !/@2x\./i.test(s))
          .join(", ");
      }
    }
  }, true);
})();

(function disableImageSet(){
  const s = document.createElement("style");
  s.textContent = `
    img, source {
      content: normal !important;
    }
  `;
  document.head.appendChild(s);
})();

function stripAt2x(url) {
  if (typeof url !== 'string') return url;
  return url.replace(/@2x(?=\.[a-z0-9]+(?:[?#]|$))/i, '');
}
function cleanImg(img) {
  try {
    // src
    if (img.src && img.src.includes('@2x')) img.src = stripAt2x(img.src);
    // srcset
    if (img.srcset) {
      const clean = img.srcset
        .split(',')
        .map(s => s.trim())
        .filter(s => !/@2x\./i.test(s))
        .join(', ');
      if (clean) img.srcset = clean; else img.removeAttribute('srcset');
    }
  } catch(_) {}
}

Array.from(document.images).forEach(cleanImg);

(function patchImgSetters(){
  const descSrc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
  const descSrcset = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'srcset');
  Object.defineProperty(HTMLImageElement.prototype, 'src', {
    get: descSrc.get,
    set(v){ return descSrc.set.call(this, stripAt2x(String(v||''))); }
  });
  Object.defineProperty(HTMLImageElement.prototype, 'srcset', {
    get: descSrcset.get,
    set(v){
      if (!v) return descSrcset.set.call(this, v);
      const clean = String(v).split(',')
        .map(s => s.trim())
        .filter(s => !/@2x\./i.test(s))
        .join(', ');
      return clean ? descSrcset.set.call(this, clean) : this.removeAttribute('srcset');
    }
  });

  const origSetAttribute = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function(name, value){
    if (this.tagName === 'IMG' && typeof value === 'string') {
      if (name === 'src') value = stripAt2x(value);
      if (name === 'srcset') {
        value = value.split(',').map(s => s.trim()).filter(s => !/@2x\./i.test(s)).join(', ');
      }
    }
    return origSetAttribute.call(this, name, value);
  };
})();


const obs = new MutationObserver(muts => {
  for (const m of muts) {
    if (m.type === 'childList') {
      m.addedNodes.forEach(n => {
        if (n && n.tagName === 'IMG') cleanImg(n);
        else if (n && n.querySelectorAll) n.querySelectorAll('img').forEach(cleanImg);
      });
    } else if (m.type === 'attributes' && (m.attributeName === 'src' || m.attributeName === 'srcset') && m.target.tagName === 'IMG') {
      cleanImg(m.target);
    }
  }
});
obs.observe(document.documentElement, {
  childList: true, subtree: true, attributes: true, attributeFilter: ['src','srcset']
});

(function killImageSetCSS(){
  const s = document.createElement('style');
  s.textContent = `
    img.product-img { background-image: none !important; content: normal !important; }
  `;
  document.head.appendChild(s);
})();

document.addEventListener('error', function(e){
  if (e.target && e.target.tagName === 'IMG' && e.target.src.includes('@2x')) {
    e.target.src = stripAt2x(e.target.src);
  }
}, true);


function getCurrentBasePath() {
  return window.location.pathname.replace(/\/[^\/]*$/, '/');
}

let vistaInicialForzada = null; 

async function run() {
  try {
    const basePath = getCurrentBasePath();
    response = await fetch(basePath + 'archivo.json').then(res => res.json());
    if (!response) throw new Error('No existen datos');

    const totalProductos = response[0].filter(e => e.type !== 'CATEGORIA').length;

    if (totalProductos <= 5) {
      document.getElementById('view').value = 'mosaico';
      styleList('mosaico');
    } else {
      styleList('tabla');
    }

    await products(response[0].filter(e => normalizarTipo(e.type) == 'CATALOGO'), 'CATÁLOGO');
    await products(response[0].filter(e => normalizarTipo(e.type) == 'EOS'), 'EOS');
    await products(response[0].filter(e => normalizarTipo(e.type) == 'SUSCRIPCIONES'), 'SUSCRIPCIONES');
    await products(response[0].filter(e => normalizarTipo(e.type) == 'LIQUIDACION'), 'LIQUIDACION');
    await category(response[0].filter(e => normalizarTipo(e.type) == 'CATEGORIA'), 'Familias');
    await route(response[1][0].dir);
    
    actualizarBotonComparar();
    
    const mainContainer = document.createElement('div');
    mainContainer.id = 'layoutProductos';
    mainContainer.style.display = 'flex';
    mainContainer.style.alignItems = 'flex-start';
    mainContainer.style.gap = '20px';

    // Mover productos dentro del layout
    const cards = document.getElementById('cardsContent');
    const tabla = document.getElementById('table');
    if (cards && cards.parentNode) cards.parentNode.insertBefore(mainContainer, cards);
    mainContainer.appendChild(cards);
    if (tabla) mainContainer.appendChild(tabla);

    // Cargar el panel de filtros 
    if (response[0].some(e => e.type !== 'CATEGORIA')) {
      const script = document.createElement('script');
      script.src = '/tm/assets/js/filtrosPanel.js';
      script.defer = true;
      document.head.appendChild(script);
    }
    if (window.inicializarFiltrosProductos) inicializarFiltrosProductos();


  } catch (error) {
    console.log(error);
  }
  h1.innerText = firstUppperCase(h1.innerText);
 
}


function actualizarColorIcono(idIcono) {
  const icono = document.getElementById(idIcono);
  if (!icono) return;

  const haySeleccionados = document.querySelectorAll('.compare-checkbox:checked').length > 0;
  icono.style.color = haySeleccionados ? '#2b6cb0' : '#4f5154';
}

document.addEventListener('change', (e) => {
  if (e.target.classList.contains('compare-checkbox')) {
    actualizarBotonComparar();
    actualizarColorIcono('btnBorrarTabla');
    actualizarColorIcono('btnBorrarMosaico');
  }
});

function fixImagePath(img) {
  const DEFAULT_IMG = '/productos/thumb2/telmedia_0.webp';
  if (!img) return DEFAULT_IMG;
  const s = String(img).trim();
  if (!s || s[0] === '#' || /imagen\s*generica/i.test(s)) return DEFAULT_IMG;

  // URL absoluta
  if (/^https?:\/\//i.test(s)) return s;
  let p = s.replace(/^\/?productos\//i, '/productos/');
  if (!p.startsWith('/')) p = '/' + p;
  return p;
}


/**
 * @param {HTMLImageElement} imgEl - Elemento de imagen.
 * @param {string} fallback - Ruta de imagen fallback.
 * @param {number} maxIntentos - Número máximo de intentos.
 */

const erroresImagen = {};

function controlarErroresImagen(imgEl, sku, fallback = '/productos/thumb2/telmedia_0.webp') {
  imgEl.onerror = function () {
    console.warn(`Imagen SKU ${sku} no encontrada. Usando default.`);
    imgEl.onerror = null;
    imgEl.src = fallback;
  };
}



function hfer(path) {
  // Si la ruta ya es absoluta, usarla directamente
  if (path.startsWith('/')) {
    window.location.href = path;
  } else {
    // Si no, concatenar con la ruta base actual
    const basePath = window.location.pathname.replace(/\/[^\/]*$/, '/');
    window.location.href = basePath + path;
  }
}

async function category(data, textDiv) {
    if (data.length > 0) {
        const div = divider(textDiv);
        tbody.appendChild(div);

        const imgSearch = document.createElement('img');
        imgSearch.setAttribute('src', data[0].img);
        imgSearch.id = "buscador";
        imgSearch.style.display = "none"
        table.appendChild(imgSearch);

        for await (const element of data) {
            const tr = document.createElement('tr');
            tr.addEventListener('click', () => hfer(element.link + "index.shtml"))

            const tdImg = document.createElement('td');
            const img = document.createElement('img');

            img.setAttribute('src', fixImagePath(element.img));
            img.setAttribute('class', 'product-img img-responsive');
            img.setAttribute('width', '80');
            img.setAttribute('height', '80');
            img.alt = altImg(element.img)

            tdImg.appendChild(img);

            const tdName = document.createElement('td');
            tdName.innerText = firstUppperCase(element.name || element.link.replaceAll('/', ''));
            tdName.setAttribute('colspan', '4');

            
             tr.appendChild(tdImg);
            tr.appendChild(tdName);
           

            tbody.appendChild(tr);
        }
    }
}

async function products(data, textDiv) {
  if (data.length > 0) {
    const div = divider(textDiv);
    tbody.appendChild(div);
    tbody.appendChild(theader());

    const basePath = window.location.pathname.replace(/\/[^\/]*$/, '/');

    const imgSearch = document.createElement('img');
    imgSearch.setAttribute('src', fixImagePath(data[0].img));
    imgSearch.id = "buscador";
    imgSearch.style.display = "none";
    table.appendChild(imgSearch);

    for await (const element of data) {
      const tr = document.createElement('tr');
      tr.addEventListener('click', (event) => {
        if (event.target.tagName.toLowerCase() === 'input' && event.target.type === 'checkbox') {
          event.stopPropagation();
          return;
        }

        // Redireccionar dinámicamente al path del producto
        const targetLink = element.link.startsWith('/')
          ? basePath + element.link.slice(1)
          : basePath + element.link;
        hfer(targetLink);
      });

      const checkboxTd = document.createElement('td');
      checkboxTd.style.cursor = "pointer";

      const checkboxLabel = document.createElement('label');
      checkboxLabel.className = 'checkbox-icon';

      checkboxTd.addEventListener('click', (e) => {
      e.stopPropagation();

    if (e.target.tagName !== 'INPUT') {
        checkbox.checked = !checkbox.checked;
        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
    }
    
});

      const tdImg = document.createElement('td');
      const img = document.createElement('img');
      const resolved = fixImagePath(element.img);
      img.src = resolved;
      controlarErroresImagen(img, element.sku);
      img.setAttribute('class', 'product-img img-responsive');
      img.setAttribute('width', '80');
      img.setAttribute('height', '80');
      img.alt = altImg(resolved);
      tdImg.appendChild(img);


      const tdName = document.createElement('td');
      tdName.innerText = firstUppperCase(element?.name);

      const tdType = document.createElement('td');
      tdType.innerText = acent[element?.type] || element?.type;

      const tdNumerPart = document.createElement('td');
      tdNumerPart.innerText = element?.numberPart;

      const tdSku = document.createElement('td');
      tdSku.innerText = element?.sku;

      // Construir el path relativo dinámicamente
      const currentPath = window.location.pathname.replace(/\/index\.shtml$/, '').replace(/\/$/, '');

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'compare-checkbox';

      checkbox.value = JSON.stringify({
        name: element.name,
        numberPart: element.numberPart,
        sku: element.sku,
        type: element.type,
        link: window.location.pathname.replace(/\/index\.shtml$/, ''),
        img: element.img,
        path: window.location.pathname.replace(/\/index\.shtml$/, '') 
        
    });

    const icon = document.createElement('span');
    icon.className = 'ai ai-signup';
    checkboxLabel.appendChild(checkbox);
    checkboxLabel.appendChild(icon);
    
      checkboxTd.appendChild(checkbox);
      // Ensamblar la fila
      tr.appendChild(checkboxTd);
      tr.appendChild(tdImg);
      tr.appendChild(tdName);
      tr.appendChild(tdNumerPart);
      tr.appendChild(tdSku);
      tr.appendChild(tdType);
      tr.appendChild(checkboxTd); // para columna de selección
      tbody.appendChild(tr);

      
    }
  }
  actualizarBotonComparar();
 mostrarBotonBorrar();

}


function divider(text) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.innerText = text;
    td.setAttribute('colspan', '6');
    td.setAttribute('class', 'theader category-header')
    tr.appendChild(td);
    return tr;
}



function theader() {
  const tr = document.createElement('tr');
  tr.setAttribute('class', 'additional-row');

  tr.appendChild(tdElement(''));
  tr.appendChild(tdElement('Nombre'));
  tr.appendChild(tdElement('No.Parte'));
  tr.appendChild(tdElement('SKU'));
  tr.appendChild(tdElement('Tipo'));

  const tdSeleccionar = document.createElement('td');
  tdSeleccionar.setAttribute('class', 'category-header');
  tdSeleccionar.style.whiteSpace = 'nowrap';   
  tdSeleccionar.style.width = '1%'; 
  
  const wrapper = document.createElement('div');
  Object.assign(wrapper.style, {
    display: 'flex',
    alignItems: 'center',
    gap: '10px'
  });

  Object.assign(tdSeleccionar.style, {
    alignItems: 'center'
  });

  const label = document.createElement('span');
  label.innerText = 'Comparar';
  tdSeleccionar.appendChild(label);

  if (!document.getElementById('btnBorrarTabla')) {
    const icono = document.createElement('i');
    icono.className = 'ai ai-signup';
    icono.id = 'btnBorrarTabla';
    icono.title = 'Limpiar selección o seleccionar primeros 5';
    Object.assign(icono.style, {
      fontSize: '2.5rem',
      color: '#4f5154',
      cursor: 'pointer',
      marginLeft: '5px'
    });

    icono.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleSeleccionProductos();
      actualizarColorIcono('btnBorrarTabla');
    });

    tdSeleccionar.appendChild(icono);
  }

  tr.appendChild(tdSeleccionar);
  return tr;
}


function toggleSeleccionProductos() {
  const esModoMosaico = document.getElementById('view').value === 'mosaico';
  const selector = esModoMosaico
    ? '#cardsContent .compare-checkbox'
    : 'table .compare-checkbox';

  const checkboxes = Array.from(document.querySelectorAll(selector));
  const seleccionados = checkboxes.filter(cb => cb.checked);
  if (seleccionados.length > 0) {
    seleccionados.forEach(cb => cb.click()); 
  } else {
    // marcar primeros 5
    checkboxes.slice(0, 5).forEach(cb => { if (!cb.checked) cb.click(); }); 
  }

  actualizarBotonComparar();
}

function hayProductos() {
  return document.querySelectorAll('.compare-checkbox').length > 0;
}

function colocarBoton(btn) {
  const headerCell = document.querySelector('#tbody tr.additional-row td.category-header:last-child');
  if (!headerCell) return;

  const wrapper = table.parentNode; 
  wrapper.style.position = 'relative';

  Object.assign(btn.style, {
    position: 'absolute',
    top: '5px',   
    zIndex: 10
    
  });

  const update = () => {
    //const cellRect = headerCell.getBoundingClientRect();
    //const wrapRect = wrapper.getBoundingClientRect();

    const top = (cellRect.top - wrapRect.top) + wrapper.scrollTop + 5; 
    const left = (table.offsetWidth - btn.offsetWidth) + wrapper.scrollLeft;
   // const left = (cellRect.right - wrapRect.left) + wrapper.scrollLeft - btn.offsetWidth - 5;

    btn.style.top = `${top}px`;
    btn.style.left = `${left}px`;
  };

  wrapper.appendChild(btn);
  update();

  window.addEventListener('resize', update);
  wrapper.addEventListener('scroll', update, { passive: true });
  document.addEventListener('scroll', update, { passive: true });

  const ro = new ResizeObserver(update);
  ro.observe(wrapper);
  ro.observe(table);
  ro.observe(headerCell);
}


function mostrarBotonBorrar() {
  const vista = document.getElementById('view').value;

  if (!hayProductos()) {
    document.getElementById('btnBorrarTabla')?.remove();
    document.getElementById('btnBorrarMosaico')?.remove();
    return;
  }

  if (vista === 'tabla') {
    document.getElementById('btnBorrarMosaico')?.remove();
    return; 
  }

  if (vista === 'mosaico') {
    document.getElementById('btnBorrarMosaico')?.remove();

    const icono = document.createElement('i');
    icono.className = 'ai ai-signup';
    icono.id = 'btnBorrarMosaico';
    icono.title = 'Limpiar selección o seleccionar primeros 5';
    Object.assign(icono.style, {
      fontSize: '2.5rem',
      color: '#4f5154',
      cursor: 'pointer',
      marginLeft: '8px'
    });

    icono.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleSeleccionProductos();
      actualizarColorIcono('btnBorrarMosaico');
      icono.style.color = (icono.style.color === '#2b6cb0') ? '#4f5154' : '#2b6cb0';
    });

    let cont = document.getElementById('contenedorBotonMosaico');
    if (!cont) {
      cont = document.createElement('div');
      cont.id = 'contenedorBotonMosaico';
      Object.assign(cont.style, {
        display: 'flex',
        justifyContent: 'flex-start',
        marginBottom: '10px',
      });
      cardsContent.parentNode.insertBefore(cont, cardsContent);
    }
    cont.appendChild(icono);
  }
}

// Desmarca todos los checkboxes de ambos modos
function deseleccionarTodos() {
  document.querySelectorAll('.compare-checkbox').forEach(cb => cb.checked = false);
  actualizarBotonComparar(); 
}


function tdElement(text) {
    const td = document.createElement('td')
    td.innerText = text;
    td.setAttribute('class', 'category-header')
    return td;
}

function cardsCategory(link, img, title) {
  const fullPath = link.replace(/^\/?/, '');
  const resolved = fixImagePath(img);
  const altText = altImg(resolved);

  return `
    <div class="card_item card_category_item">
      <div class="card_inner">
        <div class="card_top">
          <a href="${fullPath}index.shtml">
            <img src="${resolved}"
                 alt="${altText}"
                 class="product-img img-responsive"
                 width="400"
                 height="240">
          </a>
        </div>
        <div class="card_bottom">
          <div class="card_info">
            <div class="card_category">${firstUppperCase(title)}</div>
          </div>
        </div>
      </div>
    </div>`;
}

function cardsProduct(link, img, name, numberPart, sku, type) {
  const path = getCurrentBasePath().replace(/\/$/, '');
  const productData = encodeURIComponent(JSON.stringify({ name, numberPart, sku, type, link, img, path }));

  const resolved = fixImagePath(img);
  const altText = altImg(resolved);

  const imgTag = document.createElement('img');
  imgTag.setAttribute('image-id', altText);
  imgTag.src = resolved;
  imgTag.alt = altText;
  imgTag.className = 'product-img img-responsive';
  imgTag.width = 400;
  imgTag.height = 240;
  controlarErroresImagen(imgTag, sku, '/productos/thumb2/telmedia_0.webp', 3);

  return `
    <div class="card_item" style="position: relative;">
      <div class="card_inner">
        <input type="checkbox" class="compare-checkbox" value="${productData}"
               style="position:absolute; top:10px; right:10px; z-index:10; appearance:auto; -webkit-appearance:auto; width:18px; height:18px;">
        <div class="card_top">
          <a href="${link}">
            ${imgTag.outerHTML}
          </a>
        </div>
        <div class="card_bottom">
          <div class="card_category">
            <p>${firstUppperCase(name)}</p>
            <p>NUM.PARTE: ${numberPart}</p>
            <p>SKU: ${sku}</p>
            <p>TIPO: ${acent[type] || type}</p>
          </div>
        </div>
      </div>
    </div>`;
}


async function cards(categorys, products) {
    for await (const element of categorys) {
        cardsContent.innerHTML += cardsCategory(element.link, element.img, element.name || element.link.replaceAll('/', ''))
    }
    for await (const element of products) {
        cardsContent.innerHTML += cardsProduct(element.link, element.img, element.name || element.link.replaceAll('/', ''), element.numberPart, element.sku, element.type)
    }
}

let cambioManualVista = false;

view.addEventListener('change', () => {
  cambioManualVista = true;
  deseleccionarTodos();
  styleList(view.value);
  mostrarBotonBorrar();

});


async function loadCard() {
  // Guardar los SKUs o valores seleccionados antes de borrar
  const seleccionados = new Set(
    Array.from(document.querySelectorAll('.compare-checkbox:checked'))
      .map(cb => cb.value)
  );

  cardsContent.innerHTML = "";
  const categorys = response[0].filter(e => e.type == 'CATEGORIA');
  const products = response[0].filter(e => e.type != 'CATEGORIA');

  await cards(categorys, products);

 mostrarBotonBorrar();


  document.querySelectorAll('.compare-checkbox').forEach(cb => {
    if (seleccionados.has(cb.value)) {
      cb.checked = true;
    }
  });

habilitarSeleccionEnMosaico();
actualizarBotonComparar();

}


function habilitarSeleccionEnMosaico() {
  document.querySelectorAll('#cardsContent .card_item').forEach(card => {
  const checkbox = card.querySelector('.compare-checkbox');
  if (!checkbox) return; // si no hay checkbox, saltar

  checkbox.addEventListener('click', e => {
    e.stopPropagation();
    actualizarBotonComparar();
  });

  card.addEventListener('click', e => {
    if (!e.target.closest('a') && e.target.type !== 'checkbox') {
      checkbox.checked = !checkbox.checked;
      checkbox.dispatchEvent(new Event('change', { bubbles: true }));
      actualizarBotonComparar();
    }
  });
});
}


async function route(list) {
    const routeList = document.getElementById('routeList');
    const afterLink = document.getElementById('afterLink');

    const liCategory = document.createElement('li');
    const aCategory = document.createElement('a');
    aCategory.innerText = 'Categorías';
    aCategory.href = '/productos/index.shtml'; // ruta absoluta
    liCategory.appendChild(aCategory);
    routeList.appendChild(liCategory);

    let basePath = '/productos';

    for (let index = 0; index < list.length; index++) {
        const element = list[index];
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.innerText = firstUppperCase(element);

        let link = basePath;
        for (let sub = 0; sub <= index; sub++) {
            link += '/' + list[sub];
        }
        link += '/index.shtml';

        a.href = link;
        li.appendChild(a);
        routeList.appendChild(li);

        // actualizar el href (solo cuando sea la penúltima)
        if (index === list.length - 2) {
            afterLink.href = link;
        }
    }
}


function firstUppperCase(text) {
  if (!text || typeof text !== "string") return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}


async function styleList(value) {
  renderizandoVista = true;

  const compareBtnTable = document.getElementById('compareButtonTable');
  const compareBtnMosaico = document.getElementById('compareButtonMosaico');

  if (value === 'tabla') {
  cardsContent.style.display = 'none';
  table.style.display = '';
  compareBtnTable.style.display = 'none';
  compareBtnMosaico.style.display = 'none';

  tbody.innerHTML = ''; 

  await products(response[0].filter(e => normalizarTipo(e.type) == 'CATALOGO'), 'CATÁLOGO');
  await products(response[0].filter(e => normalizarTipo(e.type) == 'EOS'), 'EOS');
  await products(response[0].filter(e => normalizarTipo(e.type) == 'SUSCRIPCIONES'), 'SUSCRIPCIONES');
  await products(response[0].filter(e => normalizarTipo(e.type) == 'LIQUIDACION'), 'LIQUIDACION');
  await category(response[0].filter(e => normalizarTipo(e.type) == 'CATEGORIA'), 'Familias');

  const compareBtnTable = document.getElementById('compareButtonTable');
  if (compareBtnTable) {
    colocarBoton(compareBtnTable);
  }


  if (!tbody.querySelector('tr')) {
    const allProducts = response[0].filter(e => e.type !== 'CATEGORIA');
    if (allProducts.length > 0) {
      await products(allProducts, 'Productos');
    }
  }
  //mostrar productos con otros tipos 
  const conocidos = ["CATALOGO", "EOS", "SUSCRIPCIONES", "LIQUIDACION", "CATEGORIA"];
  const otros = response[0].filter(e => !conocidos.includes(e.type));
  if (otros.length > 0) {
    await products(otros, 'Otros');
  }

  mostrarBotonBorrar();
}

  if (value === 'mosaico') {
    cardsContent.style.display = '';
    table.style.display = 'none';
    compareBtnTable.style.display = 'none';
    compareBtnMosaico.style.display = 'none';

    await loadCard();
    mostrarBotonBorrar();
  }

  setTimeout(() => {
    renderizandoVista = false;
    actualizarBotonComparar();
  }, 50);
}

function normalizarTipo(type) {
  if (!type) return "";
  if (type.startsWith("EOS")) return "EOS";  
  return type;
}

function altImg(img) {
  if (!img) return 'telmedia_0.webp';
  const s = String(img);
  const last = s.split('/').pop();
  return last && last.trim() ? last : 'telmedia_0.webp';
}



function compareMosaico() {
  const selected = Array.from(document.querySelectorAll('.compare-checkbox:checked'))
    .map(cb => JSON.parse(decodeURIComponent(cb.value)));

  if (selected.length < 2) {
    alert('Seleccione al menos dos productos para comparar.');
    return;
  }
  //cambiar si se quiere comparar más de 5 productos
  if (selected.length > 5) {
    alert('Solo puede comparar un máximo de 5 productos.');
    return;
  }

  const skus = selected.map(p => p.sku);
  const rutaBase = selected[0].path;

  const url = `/productos/comparar.html?skus=${encodeURIComponent(skus.join(','))}&path=${encodeURIComponent(rutaBase)}`;
  window.location.href = url;
}

function compare() {
  const selected = Array.from(document.querySelectorAll('.compare-checkbox:checked'))
    .map(cb => JSON.parse(cb.value));

  if (selected.length < 2) {
    alert('Seleccione al menos dos productos para comparar.');
    return;
  }
  //cambiar si se quiere comparar más de 5 productos
  if (selected.length > 5) {
    alert('Solo puede comparar un máximo de 5 productos.');
    return;
  }

  const skus = selected.map(p => p.sku);
  const rutaBase = selected[0].path;

  const url = `/productos/comparar.html?skus=${encodeURIComponent(skus.join(','))}&path=${encodeURIComponent(rutaBase)}`;
  window.location.href = url;
}



let renderizandoVista = false; 

function styleList(value) {
    renderizandoVista = true; 
    const compareBtnTable = document.getElementById('compareButtonTable');
    const compareBtnMosaico = document.getElementById('compareButtonMosaico');

    if (value === 'tabla') {
        cardsContent.style.display = 'none';
        table.style.display = '';
        compareBtnTable.style.display = 'none';
        compareBtnMosaico.style.display = 'none';
    }

    if (value === 'mosaico') {
        cardsContent.style.display = '';
        table.style.display = 'none';
        compareBtnTable.style.display = 'none';
        compareBtnMosaico.style.display = 'none';
        loadCard();
    }

    setTimeout(() => {
        renderizandoVista = false; 
        actualizarBotonComparar();
    }, 50);
}
//document.getElementById('compareButtonTable').style.display = 'none';
// Solo ocultar botones si se detecta una vista válida ya seleccionada
const vistaSelect = document.getElementById('view');
if (vistaSelect && vistaSelect.value !== 'value2') {
    document.getElementById('compareButtonTable').style.display = 'none';
    document.getElementById('compareButtonMosaico').style.display = 'none';
}

//document.getElementById('compareButtonMosaico').style.display = 'none';

function actualizarBotonComparar() {
  const seleccionados = document.querySelectorAll('.compare-checkbox:checked').length;

  const compareBtnTable = document.getElementById('compareButtonTable');
  const compareBtnMosaico = document.getElementById('compareButtonMosaico');

  const esModoTabla = document.getElementById('view').value === 'tabla';
  const esModoMosaico = document.getElementById('view').value === 'mosaico';

  if (seleccionados >= 2) {
    if (esModoTabla) {
      compareBtnTable.style.display = 'inline-block';
      compareBtnMosaico.style.display = 'none';
    } else if (esModoMosaico) {
      compareBtnTable.style.display = 'none';
      compareBtnMosaico.style.display = 'inline-block';
    }
  } else {
    compareBtnTable.style.display = 'none';
    compareBtnMosaico.style.display = 'none';
  }
}

document.getElementById('compareButtonTable').style.display = 'none';
document.getElementById('compareButtonMosaico').style.display = 'none';

// Escuchar cambios en cualquier checkbox de comparación
document.addEventListener('change', (e) => {
  if (e.target.classList.contains('compare-checkbox')) {
    actualizarBotonComparar();
  }
});


function detectarVistaReal() {
  try {
    const select = document.getElementById('view');
    if (select && (select.value === 'tabla' || select.value === 'mosaico')) {
      return select.value;
    }

    // Si hay tarjetas y alguna es visible -> mosaico
    const cardItems = document.querySelectorAll('#cardsContent .card_item');
    const hayCardVisible = Array.from(cardItems).some(el => el.offsetParent !== null);

    if (hayCardVisible) return 'mosaico';

    // Si la tabla tiene filas (tbody) y está visible -> tabla
    const tbodyEl = document.getElementById('tbody');
    if (tbodyEl && tbodyEl.querySelectorAll('tr').length > 0) {
      // comprobar visibilidad de la tabla
      const tableEl = document.getElementById('table');
      if (tableEl && window.getComputedStyle(tableEl).display !== 'none') {
        return 'tabla';
      }
    }

    // Fallback: si cardsContent no está vacío preferimos mosaico
    const cardsContent = document.getElementById('cardsContent');
    if (cardsContent && cardsContent.children.length > 0) return 'mosaico';

    return 'tabla'; // default
  } catch (e) {
    console.error('detectarVistaReal error:', e);
    return 'tabla';
  }
}

function sincronizarVistaConDOM() {
   if (cambioManualVista) return;
  // Si hay una vista inicial forzada, no la cambiamos
  if (vistaInicialForzada) {
    styleList(vistaInicialForzada);
    actualizarBotonComparar();
    return;
  }

  const vista = detectarVistaReal();
  const select = document.getElementById('view');

  if (select && select.value !== vista) {
    select.value = vista;
  }
  styleList(vista);
  actualizarBotonComparar();
}


function iniciarObserversDeVista() {
    const cardsContent = document.getElementById('cardsContent');
    const tbodyEl = document.getElementById('tbody');

    const observerCfg = { childList: true, subtree: true };

    const callback = () => {
        if (renderizandoVista) return; // evitar recursión infinita
        clearTimeout(window.__syncVistaTimeout);
        window.__syncVistaTimeout = setTimeout(sincronizarVistaConDOM, 80);
    };

    if (cardsContent) {
        new MutationObserver(callback).observe(cardsContent, observerCfg);
    }

    if (tbodyEl) {
        new MutationObserver(callback).observe(tbodyEl, observerCfg);
    }
}

(function inicializarVistaYBotones() {
  const btnTable = document.getElementById('compareButtonTable');
  const btnMosaico = document.getElementById('compareButtonMosaico');
  if (btnTable) btnTable.style.display = 'none';
  if (btnMosaico) btnMosaico.style.display = 'none';

  // Listener delegante (por si no existe aún al cargar)
  document.addEventListener('change', (e) => {
    if (e.target && e.target.matches && e.target.matches('.compare-checkbox')) {
      actualizarBotonComparar();
      mostrarBotonBorrar();

    }
  });

  sincronizarVistaConDOM();
  iniciarObserversDeVista();
})();

run();

window.addEventListener('DOMContentLoaded', () => {
  if (vistaInicialForzada) {
    styleList(vistaInicialForzada);
  } else {
    const vistaSelect = document.getElementById('view');
    if (!vistaSelect.value || vistaSelect.value === 'elige') {
      if (cardsContent && cardsContent.style.display !== 'none') {
        vistaSelect.value = 'mosaico';
      } else if (table && table.style.display !== 'none') {
        vistaSelect.value = 'tabla';
        mostrarBotonBorrar();
      }
    }
    if (vistaSelect.value) {
      styleList(vistaSelect.value);
    }
  }

  document.getElementById('compareButtonTable').style.display = 'none';
  document.getElementById('compareButtonMosaico').style.display = 'none';

   if (window.innerWidth <= 768) { // solo móviles
    const table = document.getElementById('table');
    if (table && !table.parentElement.classList.contains('table-container')) {
      const wrapper = document.createElement('div');
      wrapper.className = 'table-container';
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);
    }
  }
});

function envolverTablaM() {
  if (window.innerWidth <= 768) {
    const table = document.getElementById('table');
    if (table && !table.parentElement.classList.contains('table-container')) {
      const wrapper = document.createElement('div');
      wrapper.className = 'table-container';
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);
    }
  } else {
    // Si vuelve a escritorio, eliminar el wrapper
    const table = document.getElementById('table');
    if (table && table.parentElement.classList.contains('table-container')) {
      const wrapper = table.parentElement;
      wrapper.parentNode.insertBefore(table, wrapper);
      wrapper.remove();
    }
  }
}

//FILTROS 
async function cargarFiltrosProductos() {
  try {
    const script = document.createElement('script');
    script.src = '/tm/assets/js/filtrosPanel.js';
    script.defer = true;
    document.head.appendChild(script);

    script.onload = () => console.log('js cargado correctamente');
    script.onerror = () => console.warn('No se pudo cargar el js');
  } catch (err) {
    console.error('Error al intentar cargar filtros.js:', err);
  }
}

window.addEventListener('DOMContentLoaded', () => {
  envolverTablaM();
});

window.addEventListener('resize', () => {
  envolverTablaM();
});

