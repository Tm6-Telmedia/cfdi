const searchInput = document.getElementById('search-input');
const searchForm = document.getElementById('search-form');
const modal = document.getElementById("modal");
const openModalBtn = document.getElementById("openModalBtn");
const closeBtn = document.querySelector(".modal .close");
const searchList = document.getElementById('searchList');
let results = [];
searchForm.addEventListener('submit', (e) => {
    const searchLength = document.getElementById('searchLength')
    const searchWord = document.getElementById('searchWord')
    e.preventDefault();
    const value = document.querySelector("#search-form input[name='search-indexing']").value;
if (value.trim()) {
    Promise.all([
        fetch('/tm/assets/json/indexing-sin-sku.json').then(r => r.json()),
        fetch('/tm/assets/json/indexing-sin-npm.json').then(r => r.json())
    ])
    .then(([data1, data2]) => {
        const results1 = filtrarResultados(data1, value);
        const results2 = filtrarResultados(data2, value);

        // Guardamos todo junto para la paginación
        results = [
            ...results1.map(r => ({ ...r, origen: "JSON1" })),
            ...results2.map(r => ({ ...r, origen: "JSON2" }))
        ];

        if (results.length) {
            searchWord.innerText = value;
            searchLength.innerText = results.length;

            modal.style.display = "block";
            pag(Math.ceil(results.length / 10));
            showPage(1);
        } else {
            alert("No se encontraron resultados");
        }
    })
    .catch(e => {
        alert('Ocurrió algún error: ' + e);
        console.log(e);
    });
}

function filtrarResultados(data, value) {
    const searchWords = removeAccents(value.toLowerCase()).split(" ");
    return data.filter(element => {
        const fieldsToSearch = [
            removeAccents(String(element.id_sku || "").toLowerCase()),
            removeAccents(element.id_num_parte?.toLowerCase() || ""),
            removeAccents(element.d_nombre_sku?.toLowerCase() || ""),
            removeAccents(element.d_descripcion?.toLowerCase() || "")
        ].join(" ");

        return searchWords.every(word =>
            fieldsToSearch.includes(word) || fieldsToSearch.includes(aSingular(word))
        );
    });
}

});

function aSingular(palabra) {
    if (palabra.endsWith("es") && palabra.length > 4) {
        return palabra.slice(0, -2);
    } else if (palabra.endsWith("s") && palabra.length > 3) {
        return palabra.slice(0, -1);
    }
    return palabra;
}

function removeAccents(str) {
    return str.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}
// JavaScript para abrir y cerrar el modal
function pag(totalPages, currentPage = 1) {
    const paginationContainer = document.getElementById("pagination");
    paginationContainer.innerHTML = ""; // Limpiar paginación previa

    if (totalPages <= 1) return; // No mostrar paginación si hay solo una página

    const maxVisiblePages = 5; // Número máximo de páginas visibles
    const halfVisible = Math.floor(maxVisiblePages / 2);

    function createPageItem(page) {
        let li = document.createElement("li");
        let a = document.createElement("a");
        a.textContent = page;
        a.href = "#";
        a.onclick = function () { showPage(page); };

        if (page === currentPage) a.classList.add("active");

        li.appendChild(a);
        return li;
    }

    // Botón "Anterior"
    if (currentPage > 1) {
        let prev = document.createElement("li");
        let a = document.createElement("a");
        a.textContent = "«";
        a.href = "#";
        a.onclick = function () { showPage(currentPage - 1); };
        prev.appendChild(a);
        paginationContainer.appendChild(prev);
    }

    // Primera página siempre visible
    paginationContainer.appendChild(createPageItem(1));

    if (currentPage - halfVisible > 2) {
        let dots = document.createElement("li");
        dots.textContent = "...";
        paginationContainer.appendChild(dots);
    }

    let start = Math.max(2, currentPage - halfVisible);
    let end = Math.min(totalPages - 1, currentPage + halfVisible);

    for (let i = start; i <= end; i++) {
        paginationContainer.appendChild(createPageItem(i));
    }

    if (currentPage + halfVisible < totalPages - 1) {
        let dots = document.createElement("li");
        dots.textContent = "...";
        paginationContainer.appendChild(dots);
    }

    // Última página siempre visible
    if (totalPages > 1) {
        paginationContainer.appendChild(createPageItem(totalPages));
    }

    // Botón "Siguiente"
    if (currentPage < totalPages) {
        let next = document.createElement("li");
        let a = document.createElement("a");
        a.textContent = "»";
        a.href = "#";
        a.onclick = function () { showPage(currentPage + 1); };
        next.appendChild(a);
        paginationContainer.appendChild(next);
    }
}

function showPage(pageNumber) {
    const itemsPerPage = 10;
    let start = (pageNumber - 1) * itemsPerPage;
    let end = start + itemsPerPage;
    let pageItems = results.slice(start, end);
    searchList.innerHTML = "";

    pageItems.forEach(element => {
        let skuNumerPart = "";

        if (element?.id_sku && element?.id_num_parte) {
            console.log("✅ Entró en Caso 1: SKU + Num.Parte", element.id_sku, element.id_num_parte);
            skuNumerPart = `<p class="no-bottom-margin" style="color:#999">SKU : ${element.id_sku} Num.Parte : ${element.id_num_parte}</p>`;
        } else if (element?.id_sku) {
            console.log("✅ Entró en Caso 2: Solo SKU", element.id_sku);
            skuNumerPart = `<p class="no-bottom-margin" style="color:#999">SKU : ${element.id_sku}</p>`;
        } else if (element?.id_num_parte) {
            console.log("✅ Entró en Caso 3: Solo Num.Parte", element.id_num_parte);
            skuNumerPart = `<p class="no-bottom-margin" style="color:#999">Num.Parte : ${element.id_num_parte}</p>`;
        } else {
            console.log("⚠️ Entró en Caso 4: Sin SKU ni Num.Parte");
        }

        searchList.innerHTML += `
          <div class="col-md-12 media features--feature-wrap hoverGray" style="padding:1rem 2rem;">
             <a href="${element?.d_url}">
                <div class="col-md-3">
                    <img class="img-responsive" width="150"
                    src="${element?.img}" onerror="this.onerror=null; this.src='https://telmedia.com.mx/tm/assets/img/icon1.svg';"/>
                </div>
                <div class="col-md-9">
                    <div class="media-heading">
                        <h3 class="no-bottom-margin">${element?.d_nombre_sku}</h3>
                        ${skuNumerPart}
                    </div>
                    <p style="color:#222;">${element?.d_descripcion}</p>
                </div>
              </a>
          </div>`;
    });

    modal.scrollTop = 0;
    pag(Math.ceil(results.length / itemsPerPage), pageNumber);
}



// Cerrar modal con el botón "X"
closeBtn.addEventListener("click", () => {
    modal.style.display = "none";
});

// Cerrar modal al hacer clic fuera del contenido
window.addEventListener("click", (event) => {
    if (event.target === modal) {
        modal.style.display = "none";
    }
});
