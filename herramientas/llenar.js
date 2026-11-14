/* Llena un formato oficial en el navegador y entrega el PDF listo para firmar.
   Cada botón [data-formato] apunta a un <script type="application/json"> con la definición del formato
   (formatos/<lugar>/<id>.yaml, convertida por ficha.py) y a la copia del PDF en blanco (data-pdf).
   Los datos no salen del dispositivo: el PDF se arma aquí mismo con pdf-lib. */
(function () {
  var PDFLIB = 'https://cdnjs.cloudflare.com/ajax/libs/pdf-lib/1.17.1/pdf-lib.min.js';
  var MESES = 'enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split(' ');
  var lib = null;

  function cargarLib() {
    if (window.PDFLib) return Promise.resolve(window.PDFLib);
    if (lib) return lib;
    lib = new Promise(function (ok, mal) {
      var s = document.createElement('script');
      s.src = PDFLIB;
      s.onload = function () { ok(window.PDFLib); };
      s.onerror = function () { lib = null; mal(new Error('No se pudo cargar el generador de PDF.')); };
      document.head.appendChild(s);
    });
    return lib;
  }

  function hoyISO() {
    var d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }

  function el(tag, attrs, hijos) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] === true) n.setAttribute(k, '');
      else if (attrs[k] !== false && attrs[k] != null) n.setAttribute(k, attrs[k]);
    });
    (hijos || []).forEach(function (h) { n.append(h); });
    return n;
  }

  function campo(def, f) {
    var id = 'f-' + def.id + '-' + f.key;
    var ayuda = f.help ? el('small', { id: id + '-ayuda' }, [f.help]) : null;
    var desc = ayuda ? id + '-ayuda' : null;
    if (f.type === 'choice') {
      var opciones = (f.options || []).map(function (o) {
        return el('label', { class: 'opcion' }, [el('input', { type: 'radio', name: f.key, value: o.value, required: !!f.required }), ' ' + o.label]);
      });
      return el('fieldset', { class: 'campo', 'aria-describedby': desc }, [el('legend', {}, [f.label + (f.required ? '' : ' (opcional)')])].concat(opciones, ayuda ? [ayuda] : []));
    }
    var tipo = f.type === 'date' ? 'date' : f.type === 'tel' ? 'tel' : 'text';
    var input = el('input', {
      id: id, name: f.key, type: tipo, required: !!f.required, 'aria-describedby': desc,
      autocomplete: tipo === 'tel' ? 'tel' : 'off', value: f.default === 'today' ? hoyISO() : (f.default || null),
    });
    return el('div', { class: 'campo' }, [el('label', { for: id }, [f.label + (f.required ? '' : ' (opcional)')]), input].concat(ayuda ? [ayuda] : []));
  }

  function construir(def, pdf) {
    var form = el('form', { class: 'llenar-form', novalidate: false });
    var grupos = [];
    def.fields.forEach(function (f) {
      var g = grupos.find(function (x) { return x.nombre === (f.group || ''); });
      if (!g) { g = { nombre: f.group || '', campos: [] }; grupos.push(g); }
      g.campos.push(campo(def, f));
    });
    grupos.forEach(function (g) {
      form.append(el('fieldset', { class: 'grupo' }, [el('legend', {}, [g.nombre])].concat(g.campos)));
    });
    var estado = el('p', { class: 'llenar-estado', role: 'status', 'aria-live': 'polite' });
    var enlace = el('a', { class: 'boton boton--descargar', hidden: true, download: def.id + '.pdf' }, ['Descargar el PDF']);
    var dlg = el('dialog', { class: 'llenar', 'aria-labelledby': 'tit-' + def.id }, [
      el('div', { class: 'llenar-cabeza' }, [
        el('h2', { id: 'tit-' + def.id }, [def.title]),
        el('button', { type: 'button', class: 'cerrar', 'aria-label': 'Cerrar' }, ['×']),
      ]),
      el('p', { class: 'llenar-nota' }, ['Escribe tus datos y armamos el formato oficial para que solo lo firmes. Es gratis, y tus datos no salen de tu teléfono: el PDF se arma aquí mismo.']),
      form,
    ]);
    form.append(el('div', { class: 'llenar-pie' }, [el('button', { type: 'submit', class: 'boton boton--primario' }, ['Armar mi PDF']), enlace, estado]));
    dlg.querySelector('.cerrar').addEventListener('click', function () { dlg.close(); });
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var datos = {};
      new FormData(form).forEach(function (v, k) { datos[k] = String(v).trim(); });
      estado.textContent = 'Armando el PDF…';
      enlace.hidden = true;
      armar(def, pdf, datos).then(function (blob) {
        if (enlace.href) URL.revokeObjectURL(enlace.href);
        enlace.href = URL.createObjectURL(blob);
        enlace.hidden = false;
        estado.textContent = 'Listo. ' + (def.sign || 'Imprímelo y fírmalo con tu letra.');
        enlace.focus();
      }, function (err) {
        estado.textContent = err.message + ' Puedes descargar el formato en blanco y llenarlo a mano.';
      });
    });
    document.body.append(dlg);
    return dlg;
  }

  function valor(datos, ref) {
    var partes = ref.split('.');
    var v = datos[partes[0]] || '';
    if (partes.length === 1 || !v) return v;
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v);
    if (!m) return '';
    return { dia: String(+m[3]), mes: MESES[+m[2] - 1], 'año': m[1] }[partes[1]] || '';
  }

  function armar(def, pdf, datos) {
    return Promise.all([cargarLib(), fetch(pdf).then(function (r) {
      if (!r.ok) throw new Error('No se pudo abrir el formato.');
      return r.arrayBuffer();
    })]).then(function (r) {
      var L = r[0];
      return L.PDFDocument.load(r[1]).then(function (doc) {
        return doc.embedFont(L.StandardFonts.Helvetica).then(function (fuente) {
          var paginas = doc.getPages();
          def.draw.forEach(function (d) {
            if (d.when && Object.keys(d.when).some(function (k) { return datos[k] !== d.when[k]; })) return;
            var texto = d.text.replace(/\{([^}]+)\}/g, function (_, ref) { return valor(datos, ref); }).trim();
            if (!texto) return;
            var pag = paginas[d.page || 0];
            var tam = d.size || 10;
            while (d.width && tam > 6 && fuente.widthOfTextAtSize(texto, tam) > d.width) tam -= 0.5;
            var ancho = fuente.widthOfTextAtSize(texto, tam);
            var x = d.align === 'center' ? d.x - ancho / 2 : d.x;
            pag.drawText(texto, { x: x, y: pag.getHeight() - d.y, size: tam, font: fuente, color: L.rgb(0, 0, 0.35) });
          });
          return doc.save();
        });
      });
    }).then(function (bytes) { return new Blob([bytes], { type: 'application/pdf' }); });
  }

  var abiertos = {};
  document.querySelectorAll('[data-formato]').forEach(function (b) {
    b.hidden = false;
    b.addEventListener('click', function () {
      var id = b.getAttribute('data-formato');
      if (!abiertos[id]) {
        var def = JSON.parse(document.getElementById('formato-' + id).textContent);
        abiertos[id] = construir(def, b.getAttribute('data-pdf'));
      }
      abiertos[id].showModal();
    });
  });
})();
