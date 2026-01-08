const tbody = document.getElementById('tbody');
const cardsContent = document.getElementById('cardsContent');
const view = document.getElementById('view');
const table = document.getElementById('table');
const h1 = document.getElementById('h1');
var response = "";
const acent = {
    "CATEGORIA" : "CATEGORÍA",
    "CATALOGO":"CATÁLOGO"
}
async function run() {
    try {
        response = await fetch('./archivo.json').then(res => res.json()).then(data => data);
        if (!response) throw new Error('No existen datos');
        if (response[0].length <= 6) {
            styleList('mosaico')
        }

        await products(response[0].filter(e => e.type == 'CATALOGO'), 'CATÁLOGO')
        await products(response[0].filter(e => e.type == 'EOS'), 'EOS')
        await products(response[0].filter(e => e.type == 'SUSCRIPCIONES'), 'SUSCRIPCIONES')
        await products(response[0].filter(e => e.type == 'LIQUIDACION'), 'LIQUIDACION')
        await category(response[0].filter(e => e.type == 'CATEGORIA'), 'Familias')
        await route(response[1][0].dir)
    } catch (error) {
        console.log(error)
    }
    h1.innerText = firstUppperCase(h1.innerText);
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

            img.setAttribute('src', element.img);
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
        tbody.appendChild(theader())

        const imgSearch = document.createElement('img');
        imgSearch.setAttribute('src', data[0].img);
        imgSearch.id = "buscador";
        imgSearch.style.display = "none";
        table.appendChild(imgSearch);

        for await (const element of data) {

            const tr = document.createElement('tr');
            tr.addEventListener('click', () => hfer(element.link))

            const tdImg = document.createElement('td');
            const img = document.createElement('img');

            img.setAttribute('src', element.img);
            img.setAttribute('class', 'product-img img-responsive');
            img.setAttribute('width', '80');
            img.setAttribute('height', '80');
            img.alt = altImg(element.img)
            tdImg.appendChild(img);

            const tdName = document.createElement('td');
            tdName.innerText = firstUppperCase(element?.name);

            const tdType = document.createElement('td');
            tdType.innerText = acent[element?.type] || element?.type; 

            const tdNumerPart = document.createElement('td');
            tdNumerPart.innerText = element?.numberPart;

            const tdSku = document.createElement('td');
            tdSku.innerText = element?.sku;


            tr.appendChild(tdImg);
            tr.appendChild(tdName);
            tr.appendChild(tdNumerPart);
            tr.appendChild(tdSku);
            tr.appendChild(tdType);

            tbody.appendChild(tr);

        }
    }
}
function hfer(path) {
    window.location.href = path;
}
function divider(text) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.innerText = text;
    td.setAttribute('colspan', '5');
    td.setAttribute('class', 'theader category-header')
    tr.appendChild(td);
    return tr;
}
function theader() {
    const tr = document.createElement('tr');
    tr.setAttribute('class', 'additional-row')
    tr.appendChild(tdElement(''));
    tr.appendChild(tdElement('Nombre'));
    tr.appendChild(tdElement('No.Parte'));
    tr.appendChild(tdElement('SKU'));
    tr.appendChild(tdElement('Tipo'));
    return tr;
}
function tdElement(text) {
    const td = document.createElement('td')
    td.innerText = text;
    td.setAttribute('class', 'category-header')
    return td;
}
function cardsCategory(link, img, title) {
    return `
                                <div class="card_item">
                                    <div class="card_inner">
                                        <div class="card_top">
                                            <a href="${link + "index.shtml"}"> <img
                                                    image-id="${altImg(img)}" src="${img}"
                                                    alt="${altImg(img)}" class="product-img img-responsive "
                                                    width="400" height="240"></a>
                                        </div>
                                        <div class="card_bottom">
                                            <div class="card_info">
                                                <div class="card_category">
                                                    ${firstUppperCase(title)}
                                                </div>
                                            </div>
                                        </div>

                                    </div>

                                </div>`;
}
function cardsProduct(link, img, name, numberPart, sku, type) {
    return `
                                <div class="card_item">
                                    <div class="card_inner">
                                        <div class="card_top">
                                            <a href="${link}"> <img
                                                    image-id="${altImg(img)}" src="${img}"
                                                    alt="${altImg(img)}" class="product-img img-responsive "
                                                    width="400" height="240"></a>
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
view.addEventListener('change', () => styleList(view.value))
async function loadCard() {
    cardsContent.innerHTML = "";
    const categorys = response[0].filter(e => e.type == 'CATEGORIA');
    const products = response[0].filter(e => e.type != 'CATEGORIA');

    await cards(categorys, products)

}
async function route(list) {
    const routeList = document.getElementById('routeList');
    const afterLink = document.getElementById('afterLink');

    const liCategory = document.createElement('li');
    const aCategory = document.createElement('a');
    aCategory.innerText = 'Categorías';
    aCategory.href = '/productos/index.shtml'
    liCategory.appendChild(aCategory);
    routeList.appendChild(liCategory);

    for (let index = 0; index <= list.length - 1; index++) {
        const element = list[index];
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.innerText = firstUppperCase(element);
        let link = "";
        link = "/productos";

        for (let sub = 0; sub <= index; sub++) {
            link += "/" + list[sub]
        }
        link += "/index.shtml"
        a.href = link;
        li.appendChild(a);
        routeList.appendChild(li);
        if (index == list.length - 2) {
            afterLink.href = link;
        }
    }

}
function firstUppperCase(text) {
    return text.charAt(0).toUpperCase() + text.substring(1, text.length)

}
function styleList(value) {
    if (value == 'tabla') {
        cardsContent.style.display = 'none';
        table.style.display = '';

    }
    if (value == 'mosaico') {
        cardsContent.style.display = '';
        table.style.display = 'none';

        loadCard()
    }
}
function altImg(img) {
    return img.split("/")[img.split("/").length - 1]
}
run();