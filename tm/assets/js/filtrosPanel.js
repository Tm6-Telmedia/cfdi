let bloqueandoRegeneracionFiltros = false;

(async function () {
  const normalizar = txt =>
    String(txt || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "") 
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();

  async function cargarJSON(url) {
    try {
      const res = await fetch(url);
      return res.ok ? res.json() : [];
    } catch (e) {
      console.warn("Error cargando", url, e);
      return [];
    }
  }

   function detectarJSONProductos() {
    const basePath = window.location.pathname.replace(/\/[^\/]*$/, "/");
    return `${basePath}archivo.json`; }   
    const PATHS = {
      filtrosBase: "/tm/assets/json/filtros.json",
      productosWoo: "/tm/assets/json/woo.json",
      especificaciones: "/tm/assets/json/especificaciones.json",
      productosCategoria: detectarJSONProductos()
    };

    const [
      filtrosJSON,wooJSON,atributosJSON,archivoJSON
    ] = await Promise.all([
      cargarJSON(PATHS.filtrosBase),cargarJSON(PATHS.productosWoo),cargarJSON(PATHS.especificaciones)
      .catch(() => []),cargarJSON(PATHS.productosCategoria)
    ]);

    if (!archivoJSON) {
      console.warn("Archivo.json no se pudo cargar");
    }

  // Construir atributos por SKU: { sku: { attrNorm: [ { norm, original }, ...
  const atributosBySku = {};
  if (Array.isArray(atributosJSON)) {
    atributosJSON.forEach(row => {
      const sku = String(row.id_sku || row.sku || "").trim();
      if (!sku) return;
      
     const nombreOriginal = (row.d_nombre_especificacion || row.nombre || row.Nombre || "").trim();
    const valorOriginal = (row.d_valor_especificacion || row.valor || "").trim();
    if (!nombreOriginal || !valorOriginal) return;

    const nombreNorm = normalizar(nombreOriginal);

    // inicializar estructuras
    atributosBySku[sku] = atributosBySku[sku] || {};
    atributosBySku[sku][nombreNorm] = atributosBySku[sku][nombreNorm] || [];

    // split si parece lista numérica
    let valoresFinales = [valorOriginal];
    if (valorOriginal.includes(",") && /\d/.test(valorOriginal)) {
      valoresFinales = valorOriginal
        .split(",")
        .map(v => v.trim())
        .filter(Boolean);
    }

    // push correcto
    valoresFinales.forEach(v => {
      atributosBySku[sku][nombreNorm].push({
        norm: normalizar(v),
        original: v
      });
    });

    });
  }

  const productos = Array.isArray(archivoJSON.response)
    ? archivoJSON.response[0] || archivoJSON.response
    : Array.isArray(archivoJSON[0])
    ? archivoJSON[0]
    : archivoJSON || [];

  const skusProductos = productos.map(p => String(p.id_sku || p.sku || p.ID || "").trim()).filter(Boolean);
  const productosWooRelacionados = wooJSON.filter(w => skusProductos.includes(String(w.id_sku)));

  let layout = document.getElementById("layoutProductos");
  if (!layout) {
    const cards = document.getElementById("cardsContent");
    const tabla = document.getElementById("table");
    if (tabla && !tabla.parentElement.classList.contains("tabla-scroll-wrapper")) {
      const wrapper = document.createElement("div");
      wrapper.className = "tabla-scroll-wrapper";
      tabla.parentNode.insertBefore(wrapper, tabla);
      wrapper.appendChild(tabla);
    }
    layout = document.createElement("div");
    layout.id = "layoutProductos";
    layout.style.display = "flex";
    layout.style.alignItems = "flex-start";
    layout.style.gap = "20px";
    if (cards && cards.parentNode) cards.parentNode.insertBefore(layout, cards);
    if (cards) layout.appendChild(cards);
    if (tabla) layout.appendChild(tabla);
  }

  const panel = document.createElement("aside");
  panel.id = "panelFiltros";
  panel.innerHTML = `
    <div class="panel-header">
      <h3>Filtros</h3>
      <button id="btnLimpiarFiltros">Borrar filtros</button>
    </div>
    <div id="contenedorFiltros"></div>
  `;
    //Si no hay productos ni tabla, no mostrar filtros 
  const hayCards = document.querySelectorAll("#cardsContent .card_item").length > 0;
  const hayTabla = document.querySelectorAll("#table tbody tr").length > 0;

  if (!hayCards && !hayTabla) {
    console.log("No hay productos");
    return; 
  }

  layout.insertAdjacentElement("afterbegin", panel);

  const style = document.createElement("style");
  style.textContent = `
 #layoutProductos { 
  display: flex;
  gap: 20px;
  align-items: flex-start;
  width: 100%;
}

#panelFiltros {
  flex: 0 0 280px;
  background: #f8f9fa;
  border: 1px solid #d0d0d0;
  border-radius: 8px;
  padding: 15px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.08);
  font-family: "Segoe UI", sans-serif;
  color: #333;
  overflow: visible;
  max-height: none;
}

#panelFiltros .panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f8f9fa;
  padding-bottom: 5px;
}

#panelFiltros h3 {
  font-size: 17px;
  color: #2b6cb0;
  margin-bottom: 5px;
  text-transform: uppercase;
}

#btnLimpiarFiltros {
    background: #0b3b6eff;
    color: #fff;
    border: none;
    border-radius: 5px;
    font-size: 12px;
    padding: 5px 10px;
    cursor: pointer;
    transition: background 0.3s;
  }

  #btnLimpiarFiltros:hover {
    background: #2c80f7ff;
  }


#panelFiltros .bloque-filtro {
  max-height: 180px;
  overflow-y: auto;
  padding-right: 6px;
  margin-bottom: 14px;
  border-bottom: 1px solid #eee;
  background: #fff;
  border-radius: 5px;
}

#panelFiltros .bloque-filtro h4 {
  position: sticky;
  top: 0;
  background: #fff;
  z-index: 5;
  font-size: 14px;
  margin: 0;
  color: #444;
  border-bottom: 1px solid #ddd;
  padding: 8px 6px;
  box-shadow: 0 2px 3px rgba(0,0,0,0.05);
}

#panelFiltros label {
  display: block;
  font-size: 13px;
  margin-left: 6px;
  color: #333;
  cursor: pointer;
}

#panelFiltros input[type="checkbox"],
#panelFiltros input[type="radio"] {
  margin-right: 5px;
  accent-color: #2b6cb0;
}

#panelFiltros select {
  width: 100%;
  padding: 5px;
  margin-top: 5px;
  border-radius: 4px;
  border: 1px solid #ccc;
  font-size: 13px;
}

#panelFiltros .bloque-filtro::-webkit-scrollbar {
  width: 6px;
}

#panelFiltros .bloque-filtro::-webkit-scrollbar-thumb {
  background: #ccc;
  border-radius: 4px;
}

#cardsContent, #table {
  flex: 1 1 auto;
}

@media (max-width: 991px) {
  #layoutProductos {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }

  #panelFiltros {
    margin-bottom: 20px;
  }

  #compareButtonContainer,
  #btnCompararProductos {
    position: relative !important;
    bottom: auto !important;
    margin: 10px 0 20px 0;
    background: #fff;
    z-index: 2;
  }

}
  /* un card */
#cardsContent .card_item.solo-un-card {
  flex: 1 1 280px !important;
  max-width: 320px !important;
  min-width: 260px !important;
  margin: 0 auto !important;
  display: block !important;
}
#cardsContent .card_item {
  flex: 0 0 260px;
  max-width: 260px;
}
`;
document.head.appendChild(style);

const cards = document.querySelectorAll("#cardsContent .card_item");
cards.forEach(c => c.classList.remove("solo-un-card"));

if (cards.length === 1) {
    cards[0].classList.add("solo-un-card");
}

(() => {
  const id = 'fix-boton-comparar-responsive';
  document.getElementById(id)?.remove();

  const st = document.createElement('style');
  st.id = id;
  st.textContent = `
 
   /* Contenedor del botón */
    #table > .panel + div {
      position: relative;
      width: 100%;
      clear: both;
      margin: 8px 0 10px;
      min-height: 44px;
      box-sizing: border-box;
    }

    /* Botón comparar */
    #compareButtonTable {
      position: absolute;
      right: 8px;
      top: 50%;
      transform: translateY(-50%);
      background: #53bfe0;
      color: white;
      border: none;
      border-radius: 4px;
      padding: 6px 12px;
      cursor: pointer;
      white-space: nowrap;
    }
   @media (max-width: 768px) {
    #compareButtonTable {
    right: -97%;         
    font-size: 13px;
    padding: 6px 12px;
  }}
    
#cardsContent {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;             
  margin-bottom: 60px;   
  justify-content: flex-start;
}

.card_item {
  margin-bottom: 20px;   /* seguridad adicional */
}

#compareButtonContainer {
  position: sticky;
  bottom: 0;
  background: #fff;
  z-index: 10;
  padding: 10px 0;
  border-top: 1px solid #ccc;
}
@media (max-width: 991px) {
  #layoutProductos {
    display: flex;
    flex-direction: column !important;
    align-items: stretch !important;
    gap: 20px !important;
    width: 100% !important;
  }

  /* Panel primero */
  #panelFiltros {
    margin-bottom: 20px;
  }

  /* Botón comparar */
  #compareButtonContainer,
  #btnCompararProductos {
    position: relative !important;
    bottom: auto !important;
    margin: 10px 0 20px 0;
    background: #fff;
    z-index: 2;
  }

  /* Luego los productos */
  #table,
  #cardsContent,.tabla-scroll-wrapper {
    margin-top: 10px;
    gap: 15px;
  }
}
  `;
  document.head.appendChild(st);
})();

function capitalizarTitulo(texto) {
  if (!texto) return "";

  return texto
    .toLowerCase()
    .split(" ")
    .map(palabra =>
      palabra.charAt(0).toLocaleUpperCase("es-ES") +
      palabra.slice(1)
    )
    .join(" ");
}


function regenerarPanelFiltros() {
  //if (!productosRenderizados) return;

    const contenedor = document.getElementById("contenedorFiltros");
    if (!contenedor) return;
  
    requestAnimationFrame(() => {
        let totalGruposRenderizados = 0;

        // Recuperar selección actual
        const seleccionados = obtenerFiltrosActivosPorAtributo();

        // Obtener SKUs visibles
        const visibles = [];
        document.querySelectorAll("#cardsContent .card_item, table tbody tr").forEach(el => {
            if (el.style.display !== "none") {
                const sku = obtenerSkuDesdeDom(el);
                if (sku) visibles.push(sku);
            }
        });

        contenedor.innerHTML = "";

       if (!visibles.length) {
          return;
        }


        // Seleccionar productos visibles
        const productosVisibles = productos.filter(p =>
            visibles.includes(String(p.id_sku || p.sku))
        );

        const wooVisibles = wooJSON.filter(p =>
            visibles.includes(String(p.id_sku || p.sku))
        );
        
        // Generar grupos dinámicos según filtros.json
        const grupos = {};

        filtrosRelevantes.forEach(f => {


          const nombreOriginal = (f.Nombre || "Otros").trim();
          const nombreNorm = normalizar(nombreOriginal);
          const tipo = (f.Tipo_Filtro || "checkbox").toLowerCase();
          const atributo = (f.Nombre_Atributo || "").trim();

          if (!grupos[nombreNorm]) {
          grupos[nombreNorm] = {
            tipo,
            attrs: new Set(),
            label: capitalizarTitulo(nombreOriginal)
          };
        }

          if (atributo) {
            grupos[nombreNorm].attrs.add(atributo);
          }
        });


        // Construcción de panel
        Object.entries(grupos).forEach(([nombreFiltro, info]) => {
         
            //if (nombreFiltro.toLowerCase().includes("marca")) return; //Descomentar si queremos que no se muestre el filtro de marcas
            const bloque = document.createElement("div");
            bloque.className = "bloque-filtro";
           bloque.innerHTML = `<h4>${info.label}</h4>`;


            const valoresPorAttr = {};
            [...info.attrs].forEach(a => valoresPorAttr[a] = new Set());

            visibles.forEach(sku => {
                const attrs = atributosBySku[sku];
                if (!attrs) return;

                [...info.attrs].forEach(attr => {
                    const attrNorm = normalizar(attr);
                    for (const key in attrs) {
                        if (key === attrNorm) {
                          attrs[key].forEach(v =>
                            valoresPorAttr[attr].add(v.original)
                          );
                        }
                    }
                });
            });
			
			// 🔥 SOPORTE PARA TAGS DESDE woo.json
			if (info.attrs.has("Tag")) {
			  visibles.forEach(sku => {
				const wooItem = wooJSON.find(w => String(w.id_sku) === String(sku));
				if (!wooItem || !wooItem.d_tags) return;

				wooItem.d_tags
				  .split(",")
				  .map(t => t.trim())
				  .filter(Boolean)
				  .forEach(tag => {
					valoresPorAttr["Tag"].add(tag);
				  });
			  });
			}

            let hayOpciones = false;

            [...info.attrs].forEach(attr => {
                let valores = [...valoresPorAttr[attr]];
               
                // detectar si son numéricos o texto y ordenar adecuadamente
               valores.sort((a, b) => {
                const na = parseFloat(String(a).replace(",", "."));
                const nb = parseFloat(String(b).replace(",", "."));

                const aEsNumero = !isNaN(na);
                const bEsNumero = !isNaN(nb);

                //si Ambos son números = orden numérico
                if (aEsNumero && bEsNumero) {
                  return na - nb;
                }

                //Si Ambos son texto =orden alfabético
                if (!aEsNumero && !bEsNumero) {
                  return a.localeCompare(b, "es", { sensitivity: "base" });
                }

                //si mezcla número + texto =números primero
                return aEsNumero ? -1 : 1;
              });



                if (!valores.length) return;

                hayOpciones = true;

                //
				if (info.tipo === "dropdown") {
				  const select = document.createElement("select");

				  const empty = document.createElement("option");
				  empty.value = "";
				  empty.textContent = "Seleccionar";
				  select.appendChild(empty);

				  valores.forEach(v => {
					const opt = document.createElement("option");

					// 🔥 FIX CLAVE: guardar JSON
					opt.value = JSON.stringify({
					  attr: normalizar(attr),
					  val: v
					});

					opt.textContent = v;

					if (seleccionados[normalizar(attr)]?.includes(normalizar(v))) {
					  opt.selected = true;
					}

					select.appendChild(opt);
				  });

				  select.addEventListener("change", filtrarProductos);
				  bloque.appendChild(select);
				  hayOpciones = true;
				  return;
				}


                valores.forEach(v => {
                    const label = document.createElement("label");
                    const input = document.createElement("input");

                    input.type = info.tipo === "radio" ? "radio" : "checkbox";
                    input.dataset.attr = normalizar(attr);
                    input.dataset.valorNorm = normalizar(v);
                    input.value = v;

                    if (seleccionados[normalizar(attr)]?.includes(normalizar(v))) {
                        input.checked = true;
                    }

                    input.addEventListener("change", filtrarProductos);

                    label.appendChild(input);
                    label.append(" " + v);
                    bloque.appendChild(label);
                });
            });

            if (hayOpciones) {
            contenedor.appendChild(bloque);
            totalGruposRenderizados++;
          }

        });
        if (totalGruposRenderizados === 0) {
          panel.style.display = "none";
        } else {
          panel.style.display = "";
        }
    });
}


(function fixBotonCompararOrden() {
  const layout = document.getElementById("layoutProductos");
  const panel = document.getElementById("panelFiltros");
  const boton = document.getElementById("compareButtonContainer") || document.getElementById("btnCompararProductos");
  const cards = document.getElementById("cardsContent");
  if (layout && panel && boton && cards) {
    layout.insertBefore(panel, boton);
    layout.insertBefore(boton, cards);
  }
})();


  const contenedor = document.getElementById("contenedorFiltros");
  if (!contenedor) return;

  const detectarCategoriaActiva = () => {
    const path = decodeURIComponent(window.location.pathname || "").toLowerCase();
    const partes = path.split("/").filter(Boolean);
    const idx = partes.indexOf("productos");
    if (idx === -1) {
      const cand = partes.filter(p => !p.endsWith(".shtml")).pop();
      return cand || null;
    }
    const secciones = partes.slice(idx + 1).filter(p => !p.endsWith(".shtml"));
    if (!secciones.length) return null;
    let candidata = secciones.at(-1);
    if (!candidata || candidata.startsWith("index")) candidata = secciones.at(-2) || secciones.at(-1);
    return candidata || null;
  };

  const categoriaActivaRaw = detectarCategoriaActiva();
  const catActivaNorm = normalizar(categoriaActivaRaw || "");
  console.log("Categoría activa raw:", categoriaActivaRaw, "norm:", catActivaNorm);

  const categoriasFull = [
    ...new Set(productosWooRelacionados.map(p => (p.d_categoria_woo || "").trim()).filter(Boolean))
  ];
  if (!categoriasFull.length) {
    categoriasFull.push(...new Set(wooJSON.map(p => (p.d_categoria_woo || "").trim()).filter(Boolean)));
  }

  function scoreCategoriaRuta(ruta, urlSegmentNormArray) {
    if (!ruta) return 0;
    const segs = ruta.split(">").map(s => normalizar(s.trim())).filter(Boolean);
    let k = 0;
    for (let i = 1; i <= Math.min(segs.length, urlSegmentNormArray.length); i++) {
      const rutaSeg = segs[segs.length - i];
      const urlSeg = urlSegmentNormArray[urlSegmentNormArray.length - i];
      if (!rutaSeg || !urlSeg) break;
      if (rutaSeg.includes(urlSeg) || urlSeg.includes(rutaSeg)) k = i;
      else break;
    }
    return k;
  }

  const urlSegs = (categoriaActivaRaw || "").split("/").filter(Boolean).map(s => normalizar(s));
  const fullUrlParts = (() => {
    const path = decodeURIComponent(window.location.pathname || "").toLowerCase();
    const parts = path.split("/").filter(Boolean);
    const idx = parts.indexOf("productos");
    if (idx === -1) return parts.map(p => normalizar(p));
    return parts.slice(idx + 1).filter(p => !p.endsWith(".shtml")).map(p => normalizar(p));
  })();

  let bestScore = 0;
  const matchedRoutes = [];
  categoriasFull.forEach(ruta => {
    const score1 = scoreCategoriaRuta(ruta, fullUrlParts);
    const score2 = scoreCategoriaRuta(ruta, urlSegs);
    const score = Math.max(score1, score2);
    if (score > bestScore) {
      bestScore = score;
      matchedRoutes.length = 0;
      matchedRoutes.push(ruta);
    } else if (score > 0 && score === bestScore) {
      matchedRoutes.push(ruta);
    }
  });

  let categoriasActivasRutas = matchedRoutes.length ? matchedRoutes : [
    ...new Set(productosWooRelacionados.map(p => p.d_categoria_woo?.split(">")[0]?.trim()).filter(Boolean))
  ];
  categoriasActivasRutas = categoriasActivasRutas.filter(Boolean);
  console.log("Rutas de categoría seleccionadas:", categoriasActivasRutas, "puntaje:", bestScore);
  if (!categoriasActivasRutas.length) {
    contenedor.innerHTML = `<p style="color:#666"> </p>`;
    return;
  }

  // Filtros relevantes
  const filtrosRelevantes = filtrosJSON.filter(f => {
    const vinculadas = (f.Categorias_Vinculadas || "").split(",").map(s => normalizar(s));
    return categoriasActivasRutas.some(ruta => {
      const rutaSegs = ruta.split(">").map(s => normalizar(s.trim()));
      return vinculadas.some(v => rutaSegs.some(rs => rs.includes(v) || v.includes(rs)));
    });
  });

  contenedor.innerHTML = "";

  // generar filtros extra
  function generarFiltroExtra(nombre, tipo, valores) {
    if (!valores || !valores.length) return;
    const bloque = document.createElement("div");
    bloque.className = "bloque-filtro";
    bloque.innerHTML = `<h4>${nombre}</h4>`;
    switch (tipo) {
      case "checkbox":
        valores.forEach(v => {
          const label = document.createElement("label");
          const input = document.createElement("input");
          input.type = "checkbox";
          input.dataset.attr = normalizar(nombre);
          input.dataset.valorNorm = normalizar(v);
          input.value = v;
          const attrNorm = grupo.attrNorm;
          const valorNorm = normalizar(v);

          if (seleccionados[attrNorm]?.includes(valorNorm)) {
            input.checked = true;
          }

          input.addEventListener("change", filtrarProductos);
          label.appendChild(input);
          label.append(" " + v);
          bloque.appendChild(label);
        });
        break;
      case "radio":
        valores.forEach(v => {
          const label = document.createElement("label");
          const input = document.createElement("input");
          input.type = "radio";
          input.name = normalizar(nombre);
          input.dataset.attr = normalizar(nombre);
          input.dataset.valorNorm = normalizar(v);
          input.value = v;
          input.addEventListener("change", filtrarProductos);
          label.appendChild(input);
          label.append(" " + v);
          bloque.appendChild(label);
        });
        break;
      case "dropdown":
        const select = document.createElement("select");
        select.innerHTML = `<option value="">Seleccionar</option>`;
        valores.forEach(v => {
          const opt = document.createElement("option");
          opt.value = JSON.stringify({ attr: normalizar(nombre), val: v });
          opt.textContent = v;
          select.appendChild(opt);
        });
        select.addEventListener("change", filtrarProductos);
        bloque.appendChild(select);
        break;
    }
    contenedor.appendChild(bloque);
  }

  // Obtener filtros activos pero retornando por atributo normalizado: { attrNorm: [valNorm,...] }
  function obtenerFiltrosActivosPorAtributo() {
    const mapa = {};
    
    document.querySelectorAll('#panelFiltros input[type="checkbox"], #panelFiltros input[type="radio"]').forEach(i => {
      if (!i.checked) return;
      const attr = i.dataset.attr || normalizar(i.closest('.bloque-filtro')?.querySelector('h4')?.textContent || "");
      const valNorm = i.dataset.valorNorm || normalizar(i.value);
      mapa[attr] = mapa[attr] || new Set();
      mapa[attr].add(valNorm);
    });
    // selects
    document.querySelectorAll('#panelFiltros select').forEach(s => {
      if (!s.value) return;
      try {
        const obj = JSON.parse(s.value);
        const attr = obj.attr || normalizar(s.closest('.bloque-filtro')?.querySelector('h4')?.textContent || "");
        const valNorm = normalizar(obj.val || "");
        mapa[attr] = mapa[attr] || new Set();
        mapa[attr].add(valNorm);
      } catch (e) {
        const attr = normalizar(s.closest('.bloque-filtro')?.querySelector('h4')?.textContent || "");
        const valNorm = normalizar(s.value);
        mapa[attr] = mapa[attr] || new Set();
        mapa[attr].add(valNorm);
      }
    });
    const out = {};
    Object.keys(mapa).forEach(k => out[k] = [...mapa[k]]);
    return out;
  }

  function obtenerCamposNormalizadosProducto(sku, wooItem, prodItem) {
    const fields = new Set();

    // aquí sólo llenamos campos específicos
    if (wooItem) {
      if (wooItem.d_tags) {
        wooItem.d_tags.split(",").map(t => t.trim()).filter(Boolean).forEach(t => fields.add(normalizar(t)));
      }
      if (wooItem.d_categoria_woo) fields.add(normalizar(wooItem.d_categoria_woo));
      if (wooItem.d_brand) fields.add(normalizar(wooItem.d_brand));
      if (wooItem.nombre || wooItem.name) fields.add(normalizar(wooItem.nombre || wooItem.name));
    }

    if (sku && atributosBySku[sku]) {
      Object.entries(atributosBySku[sku]).forEach(([attrNorm, arr]) => {
        // almacenar también el nombre de atributo 
        fields.add(attrNorm);
        arr.forEach(({ norm, original }) => {
          if (norm) fields.add(norm);
          if (original) fields.add(normalizar(original));
        });
      });
    }

    // datossi tiene campos adicionales
    if (prodItem) {
      if (prodItem.d_tags) prodItem.d_tags.split(",").map(t => t.trim()).filter(Boolean).forEach(t => fields.add(normalizar(t)));
      if (prodItem.d_categoria_woo) fields.add(normalizar(prodItem.d_categoria_woo));
      if (prodItem.d_brand) fields.add(normalizar(prodItem.d_brand));
    }

    return fields;
  }
    function esNumeroExacto(a, b) {
      const na = Number(a);
      const nb = Number(b);
      if (Number.isNaN(na) || Number.isNaN(nb)) return false;
      return na === nb;
    }

    let ultimoSetVisible = "";

    function actualizarPanelSiEsNecesario() {
      const visibles = [...document.querySelectorAll(
        "#cardsContent .card_item, table tbody tr"
      )]
        .filter(el => el.style.display !== "none")
        .map(el => obtenerSkuDesdeDom(el))
        .filter(Boolean)
        .sort()
        .join("|");

      if (visibles === ultimoSetVisible) return;

      ultimoSetVisible = visibles;

      requestAnimationFrame(() => {
        regenerarPanelFiltros();
      });
    }

  function filtrarProductos() {
    const filtrosPorAtributo = obtenerFiltrosActivosPorAtributo();
    const inputMin = document.getElementById("inputMinPrecio");
    const inputMax = document.getElementById("inputMaxPrecio");
    const rangoMin = document.getElementById("precioMin");
    const rangoMax = document.getElementById("precioMax");

    const minPrecioSel = Number(inputMin?.value || rangoMin?.value) || 0;
    const maxPrecioSel = Number(inputMax?.value || rangoMax?.value) || Infinity;

    const filas = document.querySelectorAll("table tbody tr, #table tbody tr, #tbody tr");
    const mosaicos = document.querySelectorAll("#cardsContent .card_item");

    const items = [...filas, ...mosaicos];

    // Si no hay filtros activos por atributo, mostrar todos
    const atributosActivos = Object.keys(filtrosPorAtributo);
    items.forEach(el => {
      const sku = obtenerSkuDesdeDom(el);
      const wooItem = wooJSON.find(p => String(p.id_sku) === String(sku) || String(p.sku) === String(sku));
      const prodItem = productos.find(p => String(p.id_sku) === String(sku) || String(p.sku) === String(sku));

      const textoVisibleRaw = el.textContent || "";
      const textoVisibleNorm = normalizar(textoVisibleRaw);
      let precio = 0;
      const precioMatch = textoVisibleRaw.match(/\b\d{1,3}(?:[.,]\d{3})*(?:\s*mxn)?/i);
      if (precioMatch) {
        precio = parseFloat(precioMatch[0].replace(/[^\d.]/g, "")) || 0;
      }
      const coincidePrecio = precio >= minPrecioSel && precio <= maxPrecioSel;

      if (!atributosActivos.length) {
        const visible = coincidePrecio;
        if (el.tagName === "TR") el.style.display = visible ? "table-row" : "none";
        else el.style.display = visible ? "" : "none";
        return;
      }

      // construir set de campos normalizados del producto
      const campos = obtenerCamposNormalizadosProducto(sku, wooItem, prodItem);
      
      campos.add(textoVisibleNorm);

      // Para cada atributo activo, al menos uno de sus valores debe coincidir 
      let cumpleTodo = true;
      for (const attrNorm of atributosActivos) {
        const valoresReq = filtrosPorAtributo[attrNorm]; 
        if (!valoresReq || !valoresReq.length) continue;

        // caso 1: producto tiene ese atributo en atributosBySku[sku]
        let pudo = false;
        if (sku && atributosBySku[sku]) {
          const posibles = atributosBySku[sku][attrNorm] || []; // array {norm, original}
          const posiblesNorms = new Set(posibles.map(x => x.norm));
          for (const vr of valoresReq) {

          for (const pn of posiblesNorms) {
            if (esNumeroExacto(pn, vr)) {
              pudo = true;
              break;
            }
          }
          if (pudo) break;
          //Coincidencia exacta texto
          if (posiblesNorms.has(vr)) {
            pudo = true;
            break;
          }
        }
        }

        // caso 2: si no halló en atributosBySku, comprobar campos genéricos (tags/brand/categoria/texto)
        if (!pudo) {
          for (const vr of valoresReq) {
            for (const campo of campos) {
              if (!campo) continue;
                //numérico exacto
                if (esNumeroExacto(campo, vr)) {
                  pudo = true;
                  break;
                }
                // texto parcial solo si no es número
                if (isNaN(Number(vr)) && campo.includes(vr)) {
                  pudo = true;
                  break;
                }
            }
            if (pudo) break;
            const numF = parseFloat(vr);
            if (!isNaN(numF)) {
              if (textoVisibleNorm.match(new RegExp(`\\b${String(numF).replace(".", "\\.")}\\b`))) { pudo = true; break; }
            }
          }
        }

        if (!pudo) {
          cumpleTodo = false;
          break;
        }
      }

      const visible = cumpleTodo && coincidePrecio;
      if (el.tagName === "TR") el.style.display = visible ? "table-row" : "none";
      else el.style.display = visible ? "" : "none";
    });

    if (typeof actualizarBotonComparar === "function") {
      actualizarBotonComparar();
    }

    actualizarPanelSiEsNecesario();
  }

  function obtenerSkuDesdeDom(el) {
    try {
      const cb = el.querySelector && (el.querySelector('.compare-checkbox') || el.querySelector('input.compare-checkbox'));
      if (cb && cb.value) {
        try {
          const parsed = JSON.parse(decodeURIComponent(cb.value));
          if (parsed?.sku) return String(parsed.sku).trim();
        } catch (e) {
          if (/^\d+$/.test(cb.value)) return cb.value.trim();
        }
      }
      const posibleSku = el.querySelector('td') ? [...el.querySelectorAll('td')].map(td => td.innerText.trim()) : [];
      const candidato = posibleSku.find(txt => /^\d{4,6}$/.test(txt));
      if (candidato) return candidato;
      const text = el.textContent || "";
      const match = text.match(/\b\d{4,6}\b/);
      if (match) return match[0];
      const skuP = el.querySelector && el.querySelector('.card_category p:nth-child(3)');
      if (skuP && skuP.innerText) {
        const m = skuP.innerText.match(/\b\d{3,}\b/);
        if (m) return m[0];
      }
    } catch (e) {
      console.warn("Error extrayendo SKU:", e);
    }
    return null;
  }

  document.getElementById("btnLimpiarFiltros").addEventListener("click", () => {
    bloqueandoRegeneracionFiltros = true;

    document
      .querySelectorAll("#panelFiltros input, #panelFiltros select")
      .forEach(el => {
        if (el.type === "checkbox" || el.type === "radio") el.checked = false;
        if (el.tagName === "SELECT") el.value = "";
      });

    document.querySelectorAll("#cardsContent .card_item, table tbody tr")
      .forEach(el => {
        el.style.display = el.tagName === "TR" ? "table-row" : "";
      });

    ultimoSetVisible = "";

    setTimeout(() => {
      bloqueandoRegeneracionFiltros = false;
      filtrarProductos();
      regenerarPanelFiltros();
    }, 80);
  });


  filtrarProductos();
} )();