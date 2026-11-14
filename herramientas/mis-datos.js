/* Mis datos: la persona escribe sus datos una vez (o los toma de la foto de su INE) y llenan cualquier formato.
   - Se guardan solo en este dispositivo, cifrados con AES-GCM. La llave se abre con una llave de acceso
     (passkey con la extensión PRF de WebAuthn) o con una frase (PBKDF2-SHA256, 600 000 vueltas).
   - Nada sale del dispositivo: ni los datos ni la foto de la INE, que se lee aquí mismo y no se guarda.
   - El diccionario de datos (datos-personales.yaml) llega en <script type="application/json" id="datos-personales">.
   llenar.js usa window.MisDatos.barra() y window.MisDatos.ofrecerGuardar(). */
(function () {
  'use strict';
  var CLAVE = 'compartido-mis-datos-v1';
  var VUELTAS = 600000;
  var TESSERACT = 'https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';
  var TESSERACT_SRI = 'sha384-GJqSu7vueQ9qN0E9yLPb3Wtpd7OrgK8KmYzC8T1IysG1bcvxvIO4qtYR/D3A991F';
  var ALFA_CURP = '0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ';
  var nodo = document.getElementById('datos-personales');
  if (!nodo) return;
  var DIC = JSON.parse(nodo.textContent);
  var CAMPO = {};
  DIC.fields.forEach(function (c) { CAMPO[c.key] = c; });
  var YO = DIC.relations[0];

  /* ---------- utilidades ---------- */
  var te = new TextEncoder(), td = new TextDecoder();
  function b64(buf) { var s = '', a = new Uint8Array(buf); for (var i = 0; i < a.length; i++) s += String.fromCharCode(a[i]); return btoa(s); }
  function deb64(s) { var b = atob(s), a = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) a[i] = b.charCodeAt(i); return a; }
  function azar(n) { return crypto.getRandomValues(new Uint8Array(n)); }
  function nuevoId() { return Array.prototype.map.call(azar(8), function (x) { return x.toString(16).padStart(2, '0'); }).join(''); }
  function el(tag, attrs, hijos) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (k === 'on') Object.keys(v).forEach(function (ev) { n.addEventListener(ev, v[ev]); });
      else if (v === true) n.setAttribute(k, '');
      else if (v !== false && v != null) n.setAttribute(k, v);
    });
    (hijos || []).forEach(function (h) { if (h != null) n.append(h); });
    return n;
  }
  function leer() { try { return JSON.parse(localStorage.getItem(CLAVE) || 'null'); } catch (e) { return null; } }
  var enMemoria = null; // si el navegador no deja guardar, la bóveda vive solo mientras la página está abierta
  function escribir(b) {
    try { localStorage.setItem(CLAVE, JSON.stringify(b)); enMemoria = null; return true; } catch (e) { enMemoria = b; return false; }
  }
  function boveda() { return enMemoria || leer(); }
  function nombreDe(p) { return [p.datos.nombre, p.datos.apellido1].filter(Boolean).join(' ') || 'Sin nombre'; }

  /* ---------- CURP ---------- */
  // Estructura: Instructivo Normativo para la asignación de la CURP (DOF 2018), apartado TERCERO.
  // Dígito verificador: mismo cálculo que python-stdnum (stdnum/mx/curp.py).
  function curp(s) {
    s = String(s || '').toUpperCase().replace(/[\s-]/g, '');
    if (!s) return null;
    if (s.length !== 18) return { ok: false, error: 'La CURP tiene 18 letras y números; esta tiene ' + s.length + '.' };
    if (!/^[A-ZÑ]{4}\d{6}[HMX][A-Z]{2}[A-ZÑ]{3}[0-9A-J]\d$/.test(s)) return { ok: false, error: 'Revisa la CURP: algo no tiene la forma esperada.' };
    var suma = 0;
    for (var i = 0; i < 17; i++) suma += ALFA_CURP.indexOf(s[i]) * (18 - i);
    if (String((10 - suma % 10) % 10) !== s[17]) return { ok: false, error: 'Revisa la CURP: parece que una letra o un número no está bien.' };
    var anio = (/\d/.test(s[16]) ? 1900 : 2000) + Number(s.slice(4, 6));
    var mes = s.slice(6, 8), dia = s.slice(8, 10);
    var f = new Date(anio + '-' + mes + '-' + dia + 'T12:00:00');
    if (isNaN(f) || f.getUTCDate() !== Number(dia) || f > new Date()) return { ok: false, error: 'Revisa la CURP: la fecha de nacimiento no existe.' };
    var edo = s.slice(11, 13);
    if (!DIC.curp_states || !DIC.curp_states[edo]) return { ok: false, error: 'Revisa la CURP: la clave del estado de nacimiento no existe.' };
    return {
      ok: true, curp: s, nacimiento: anio + '-' + mes + '-' + dia,
      sexo: s[10] === 'H' || s[10] === 'M' ? s[10] : '',
      estado: edo === 'NE' ? '' : DIC.curp_states[edo],
      pais: edo === 'NE' ? '' : 'México',
      extranjero: edo === 'NE',
    };
  }

  /* ---------- cifrado ---------- */
  function kekFrase(frase, sal, vueltas) {
    return crypto.subtle.importKey('raw', te.encode(frase.normalize('NFC')), 'PBKDF2', false, ['deriveKey']).then(function (base) {
      return crypto.subtle.deriveKey({ name: 'PBKDF2', hash: 'SHA-256', salt: sal, iterations: vueltas }, base, { name: 'AES-GCM', length: 256 }, false, ['wrapKey', 'unwrapKey']);
    });
  }
  function kekPrf(bytes) {
    return crypto.subtle.importKey('raw', bytes, 'HKDF', false, ['deriveKey']).then(function (base) {
      return crypto.subtle.deriveKey({ name: 'HKDF', hash: 'SHA-256', salt: new Uint8Array(32), info: te.encode('compartido mis datos v1') }, base, { name: 'AES-GCM', length: 256 }, false, ['wrapKey', 'unwrapKey']);
    });
  }
  function envolver(dek, kek) {
    var iv = azar(12);
    return crypto.subtle.wrapKey('raw', dek, kek, { name: 'AES-GCM', iv: iv }).then(function (w) { return { iv: b64(iv), key: b64(w) }; });
  }
  function desenvolver(w, kek) {
    return crypto.subtle.unwrapKey('raw', deb64(w.key), kek, { name: 'AES-GCM', iv: deb64(w.iv) }, { name: 'AES-GCM' }, true, ['encrypt', 'decrypt']);
  }
  function cifrar(dek, obj) {
    var iv = azar(12);
    return crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv }, dek, te.encode(JSON.stringify(obj))).then(function (c) { return { iv: b64(iv), ct: b64(c) }; });
  }
  function descifrar(dek, d) {
    return crypto.subtle.decrypt({ name: 'AES-GCM', iv: deb64(d.iv) }, dek, deb64(d.ct)).then(function (p) { return JSON.parse(td.decode(p)); });
  }

  /* Llave de acceso: la extensión PRF da 32 bytes secretos que solo salen con la huella, la cara o el PIN. */
  function prfDisponible() { return !!(window.PublicKeyCredential && navigator.credentials && window.isSecureContext); }
  function prfLeer(credId, sal) {
    return navigator.credentials.get({
      publicKey: {
        challenge: azar(32), rpId: location.hostname, userVerification: 'required', timeout: 120000,
        allowCredentials: credId ? [{ type: 'public-key', id: deb64(credId) }] : [],
        extensions: { prf: { eval: { first: sal } } },
      },
    }).then(function (c) {
      var r = c.getClientExtensionResults().prf;
      if (!r || !r.results || !r.results.first) throw new Error('sin-prf');
      return { id: b64(c.rawId), bytes: new Uint8Array(r.results.first) };
    });
  }
  function prfCrear(sal) {
    return navigator.credentials.create({
      publicKey: {
        challenge: azar(32), rp: { name: 'Compartido', id: location.hostname },
        user: { id: azar(16), name: 'mis-datos', displayName: 'Mis datos (Compartido)' },
        pubKeyCredParams: [{ type: 'public-key', alg: -7 }, { type: 'public-key', alg: -257 }],
        authenticatorSelection: { residentKey: 'required', userVerification: 'required' },
        timeout: 120000, extensions: { prf: { eval: { first: sal } } },
      },
    }).then(function (c) {
      var r = c.getClientExtensionResults().prf;
      if (!r || r.enabled === false) throw new Error('sin-prf');
      var id = b64(c.rawId);
      if (r.results && r.results.first) return { id: id, bytes: new Uint8Array(r.results.first) };
      return prfLeer(id, sal); // algunos teléfonos solo dan el secreto al usar la llave, no al crearla
    });
  }

  /* ---------- estado ---------- */
  var dek = null, datos = null, oyentes = [], reloj = null;
  function estado() { return dek ? 'abierto' : boveda() ? 'cerrado' : 'nuevo'; }
  function avisar() { oyentes.forEach(function (f) { try { f(); } catch (e) { /* nada */ } }); }
  function personas() { return datos ? datos.personas.slice() : []; }
  function persona(id) { return datos && datos.personas.find(function (p) { return p.id === id; }); }
  function cerrar() { dek = null; datos = null; clearTimeout(reloj); avisar(); }
  // Si la página pasa 10 minutos en segundo plano, se cierra con llave.
  document.addEventListener('visibilitychange', function () {
    clearTimeout(reloj);
    if (document.hidden && dek) reloj = setTimeout(cerrar, 10 * 60 * 1000);
  });
  function guardar() {
    var b = boveda();
    datos.actualizado = new Date().toISOString();
    return cifrar(dek, datos).then(function (c) { b.data = c; escribir(b); avisar(); });
  }
  function crearBoveda(proteccion) {
    // proteccion: {frase} o {llave: {id, bytes, sal}}
    return crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']).then(function (k) {
      var sal = azar(16);
      var w = proteccion.frase
        ? kekFrase(proteccion.frase, sal, VUELTAS).then(function (kek) { return envolver(k, kek); }).then(function (x) { return Object.assign({ tipo: 'frase', sal: b64(sal), vueltas: VUELTAS }, x); })
        : kekPrf(proteccion.llave.bytes).then(function (kek) { return envolver(k, kek); }).then(function (x) { return Object.assign({ tipo: 'llave', cred: proteccion.llave.id, sal: b64(proteccion.llave.sal) }, x); });
      return w.then(function (wrap) {
        dek = k;
        datos = datos || { personas: [] };
        var guardado = escribir({ v: 1, llaves: [wrap], data: null });
        return guardar().then(function () { return guardado; });
      });
    });
  }
  function abrirCon(wrap, secreto) {
    var kek = wrap.tipo === 'frase' ? kekFrase(secreto, deb64(wrap.sal), wrap.vueltas) : kekPrf(secreto);
    return kek.then(function (k) { return desenvolver(wrap, k); }).then(function (k) {
      return descifrar(k, boveda().data).then(function (d) { dek = k; datos = d; avisar(); });
    });
  }

  /* ---------- diálogos ---------- */
  function dialogo(titulo, cuerpo, clase) {
    var d = el('dialog', { class: 'llenar misdatos ' + (clase || ''), 'aria-label': titulo }, [
      el('div', { class: 'llenar-cabeza' }, [el('h2', {}, [titulo]), el('button', { type: 'button', class: 'cerrar', 'aria-label': 'Cerrar', on: { click: function () { d.close(); } } }, ['×'])]),
      el('div', { class: 'misdatos-cuerpo' }, cuerpo),
    ]);
    d.addEventListener('close', function () { setTimeout(function () { d.remove(); }, 0); });
    document.body.append(d);
    d.showModal();
    return d;
  }
  function estadoTxt() { return el('p', { class: 'llenar-estado', role: 'status', 'aria-live': 'polite' }); }

  // Pide abrir la bóveda. Resuelve true si quedó abierta.
  function pedirAbrir() {
    if (dek) return Promise.resolve(true);
    var b = boveda();
    if (!b) return Promise.resolve(false);
    return new Promise(function (ok) {
      var listo = false;
      var msg = estadoTxt();
      var hijos = [el('p', { class: 'llenar-nota' }, ['Tus datos están guardados con llave en este teléfono. Ábrelos para llenar el formato.'])];
      b.llaves.forEach(function (w) {
        if (w.tipo === 'llave') {
          hijos.push(el('button', { type: 'button', class: 'boton boton--primario', on: { click: function () {
            msg.textContent = 'Esperando tu huella, tu cara o tu PIN…';
            prfLeer(w.cred, deb64(w.sal)).then(function (r) { return abrirCon(w, r.bytes); }).then(function () { listo = true; d.close(); },
              function () { msg.textContent = 'No se pudo abrir con la llave de acceso. Intenta otra vez' + (b.llaves.length > 1 ? ' o usa tu frase.' : '.'); });
          } } }, ['Abrir con huella o cara']));
        } else {
          var inp = el('input', { type: 'password', id: 'md-frase', autocomplete: 'current-password', required: true });
          hijos.push(el('form', { class: 'misdatos-frase', on: { submit: function (ev) {
            ev.preventDefault();
            msg.textContent = 'Abriendo…';
            abrirCon(w, inp.value).then(function () { listo = true; d.close(); }, function () { msg.textContent = 'Esa frase no abre tus datos. Revisa mayúsculas y espacios.'; inp.select(); });
          } } }, [el('label', { for: 'md-frase' }, ['Tu frase']), inp, el('button', { type: 'submit', class: 'boton' }, ['Abrir'])]));
        }
      });
      hijos.push(msg);
      var d = dialogo('Abrir mis datos', hijos, 'misdatos--chico');
      d.addEventListener('close', function () { ok(listo); });
    });
  }

  // Elegir cómo proteger los datos la primera vez. Resuelve true si quedó creada.
  function pedirProteccion() {
    return new Promise(function (ok) {
      var listo = false, msg = estadoTxt();
      var f1 = el('input', { type: 'password', id: 'md-f1', autocomplete: 'new-password', minlength: 8, required: true });
      var f2 = el('input', { type: 'password', id: 'md-f2', autocomplete: 'new-password', minlength: 8, required: true });
      var hijos = [
        el('p', { class: 'llenar-nota' }, ['Tus datos se guardan solo en este teléfono, con llave. Nadie más puede leerlos: ni nosotros, ni quien tome tu teléfono sin tu huella o tu frase.']),
      ];
      if (prfDisponible()) {
        hijos.push(el('button', { type: 'button', class: 'boton boton--primario', on: { click: function () {
          var sal = azar(32);
          msg.textContent = 'Esperando tu huella, tu cara o tu PIN…';
          prfCrear(sal).then(function (r) { return crearBoveda({ llave: { id: r.id, bytes: r.bytes, sal: sal } }); })
            .then(function (g) { listo = true; d.close(); if (!g) alertaMemoria(); }, function (e) {
              msg.textContent = e && e.message === 'sin-prf'
                ? 'Tu teléfono todavía no permite guardar con huella o cara. Usa una frase.'
                : 'No se pudo usar la huella o la cara. Puedes usar una frase.';
            });
        } } }, ['Proteger con huella o cara']));
        hijos.push(el('p', { class: 'misdatos-o' }, ['o con una frase']));
      }
      hijos.push(el('form', { class: 'misdatos-frase', on: { submit: function (ev) {
        ev.preventDefault();
        if (f1.value !== f2.value) { msg.textContent = 'Las dos frases no son iguales.'; return; }
        msg.textContent = 'Guardando…';
        crearBoveda({ frase: f1.value }).then(function (g) { listo = true; d.close(); if (!g) alertaMemoria(); }, function () { msg.textContent = 'No se pudo guardar en este navegador.'; });
      } } }, [
        el('label', { for: 'md-f1' }, ['Escribe una frase']),
        el('small', {}, ['Mínimo 8 letras. Por ejemplo, cuatro palabras que solo tú sepas. Si la olvidas, nadie puede abrir tus datos, ni nosotros.']),
        f1,
        el('label', { for: 'md-f2' }, ['Escríbela otra vez']), f2,
        el('button', { type: 'submit', class: 'boton' + (prfDisponible() ? '' : ' boton--primario') }, ['Guardar con esta frase']),
      ]));
      hijos.push(msg);
      var d = dialogo('Guarda tus datos con llave', hijos, 'misdatos--chico');
      d.addEventListener('close', function () { ok(listo); });
    });
  }
  function alertaMemoria() {
    dialogo('Solo por ahora', [el('p', { class: 'llenar-nota' }, ['Este navegador no deja guardar datos. Puedes usarlos mientras esta página siga abierta; al cerrarla se borran. Abre la página en tu navegador de siempre para guardarlos.'])], 'misdatos--chico');
  }

  /* ---------- foto de la INE ---------- */
  // El reverso de la credencial tiene una zona de lectura mecánica (ABC de la Credencial para Votar, INE, 2026, p. 16):
  // tres renglones de 30 caracteres con el formato internacional TD1. El frente trae la CURP.
  var ocr = null;
  function cargarOcr() {
    if (window.Tesseract) return Promise.resolve(window.Tesseract);
    if (ocr) return ocr;
    ocr = new Promise(function (ok, mal) {
      var s = document.createElement('script');
      s.src = TESSERACT; s.crossOrigin = 'anonymous';
      s.integrity = TESSERACT_SRI;
      s.onload = function () { ok(window.Tesseract); };
      s.onerror = function () { ocr = null; mal(new Error('No se pudo cargar el lector de fotos.')); };
      document.head.appendChild(s);
    });
    return ocr;
  }
  function preparar(archivo) {
    return createImageBitmap(archivo).then(function (img) {
      var ancho = Math.min(2000, Math.max(1400, img.width)), esc = ancho / img.width;
      var c = document.createElement('canvas');
      c.width = ancho; c.height = Math.round(img.height * esc);
      var x = c.getContext('2d');
      x.filter = 'grayscale(1) contrast(1.4)';
      x.drawImage(img, 0, 0, c.width, c.height);
      if (img.close) img.close();
      return c;
    });
  }
  function digitoIcao(s) {
    var p = [7, 3, 1], t = 0;
    for (var i = 0; i < s.length; i++) {
      var ch = s[i], v = ch === '<' ? 0 : /\d/.test(ch) ? +ch : ch.charCodeAt(0) - 55;
      t += v * p[i % 3];
    }
    return String(t % 10);
  }
  function aDigitos(s) { return s.replace(/O/g, '0').replace(/[IL]/g, '1').replace(/Z/g, '2').replace(/S/g, '5').replace(/B/g, '8'); }
  function aLetras(s) { return s.replace(/0/g, 'O').replace(/1/g, 'I').replace(/5/g, 'S').replace(/8/g, 'B'); }
  // Lee la zona de lectura mecánica del reverso. Solo se aceptan datos cuyo dígito verificador cuadra.
  function leerMrz(texto) {
    var lineas = texto.toUpperCase().split(/\n/).map(function (l) { return l.replace(/\s/g, '').replace(/[«‹(\[{]/g, '<'); })
      .filter(function (l) { return /^[A-Z0-9<]{24,34}$/.test(l) && l.indexOf('<') >= 0; });
    var r = {};
    lineas.forEach(function (l) {
      var f = aDigitos(l.slice(0, 7)), s = l[7], cad = aDigitos(l.slice(8, 15));
      if (/^\d{7}$/.test(f) && /[MF<]/.test(s) && /^\d{7}$/.test(cad) && digitoIcao(f.slice(0, 6)) === f[6]) {
        var yy = +f.slice(0, 2), hoy = new Date().getFullYear() % 100;
        r.nacimiento = (yy > hoy ? 1900 : 2000) + yy + '-' + f.slice(2, 4) + '-' + f.slice(4, 6);
        if (s !== '<') r.sexo = s === 'F' ? 'M' : 'H';
      } else if (/^[A-Z0-9]+(<[A-Z0-9]+)*<<[A-Z0-9]/.test(l) && !/^ID/.test(l)) {
        var partes = aLetras(l).split('<<').filter(Boolean);
        var ap = partes[0].split('<');
        r.apellido1 = ap.length > 2 ? ap.slice(0, -1).join(' ') : ap[0];
        r.apellido2 = ap.length > 1 ? ap[ap.length - 1] : '';
        r.nombre = (partes[1] || '').split('<').filter(Boolean).join(' ');
      }
    });
    return r;
  }
  // Busca la CURP en el texto del frente; solo se acepta si su dígito verificador cuadra.
  // La lectura a veces confunde O con 0 o mete un carácter de más al final; se prueban esas variantes.
  function buscarCurp(texto) {
    var m = [];
    texto.toUpperCase().split('\n').forEach(function (l) {
      l = l.replace(/[^A-Z0-9Ñ]/g, '');
      for (var i = 0; i + 18 <= l.length; i++) m.push(l.slice(i, i + 20));
    });
    for (var i = 0; i < m.length; i++) {
      var s = m[i], base = aLetras(s.slice(0, 4)) + aDigitos(s.slice(4, 10)) + aLetras(s.slice(10, 16));
      var cola = s.slice(16), colas = [cola.slice(0, 2)];
      for (var a = 0; a < cola.length; a++) for (var b = a + 1; b < cola.length; b++) colas.push(cola[a] + cola[b]);
      for (var k = 0; k < colas.length; k++) {
        var c = colas[k];
        var variantes = [aDigitos(c[0]) + aDigitos(c[1]), c[0] + aDigitos(c[1])];
        for (var v = 0; v < variantes.length; v++) {
          var r = curp(base + variantes[v]);
          if (r && r.ok) return r;
        }
      }
    }
    return null;
  }
  function titulo(s) { return s.toLowerCase().replace(/(^|\s)(\S)/g, function (m, a, b) { return a + b.toUpperCase(); }); }

  // Pide una o dos fotos de la INE, las lee aquí mismo y regresa los datos que la persona confirma.
  // Con roles (personas de un formato), también pregunta de quién es la INE y lo regresa en _rol.
  function leerIne(roles) {
    return new Promise(function (ok) {
      var resultado = null, msg = estadoTxt();
      var archivos = el('input', { type: 'file', accept: 'image/*', multiple: true, id: 'md-ine', class: 'misdatos-archivo' });
      var revisar = el('div', { class: 'misdatos-revisar', hidden: true });
      var cuerpo = [
        el('p', { class: 'llenar-nota' }, ['Toma una foto del frente y otra del reverso, con buena luz y sin reflejos. La foto se lee aquí en tu teléfono y no se guarda ni se manda a ningún lado.']),
        el('label', { for: 'md-ine', class: 'boton boton--primario' }, ['Tomar o elegir fotos']),
        archivos, msg, revisar,
      ];
      var d = dialogo('Llenar con tu INE', cuerpo, 'misdatos--chico');
      d.addEventListener('close', function () { ok(resultado); });
      archivos.addEventListener('change', function () {
        var fs = Array.prototype.slice.call(archivos.files, 0, 2);
        if (!fs.length) return;
        msg.textContent = 'Leyendo la foto… la primera vez tarda un poco más.';
        revisar.hidden = true;
        cargarOcr().then(function (T) {
          return T.createWorker('eng').then(function (w) {
            var hallado = {};
            return fs.reduce(function (p, f) {
              return p.then(function () { return preparar(f); }).then(function (c) { return w.recognize(c); }).then(function (r) {
                var t = r.data.text;
                var m = leerMrz(t), c = buscarCurp(t);
                Object.keys(m).forEach(function (k) { if (m[k]) hallado[k] = m[k]; });
                if (c) hallado.curp = c.curp;
              });
            }, Promise.resolve()).then(function () { w.terminate(); return hallado; }, function (e) { w.terminate(); throw e; });
          });
        }).then(function (h) {
          if (h.curp && h.nacimiento && curp(h.curp).nacimiento !== h.nacimiento) delete h.curp; // no cuadra con el reverso: se leyó mal
          if (h.curp) {
            var c = curp(h.curp);
            h.nacimiento = c.nacimiento; h.sexo = c.sexo || h.sexo;
            if (c.estado) { h.nacimiento_estado = c.estado; h.nacimiento_pais = c.pais; }
          }
          ['nombre', 'apellido1', 'apellido2'].forEach(function (k) { if (h[k]) h[k] = titulo(h[k]); });
          var claves = ['nombre', 'apellido1', 'apellido2', 'curp', 'nacimiento', 'sexo', 'nacimiento_estado', 'nacimiento_pais'].filter(function (k) { return h[k]; });
          if (!claves.length) { msg.textContent = 'No pudimos leer la foto. Intenta con más luz, sin reflejos y con la credencial llenando la foto.'; return; }
          msg.textContent = claves.length < 5 ? 'Leímos una parte. Revisa y completa lo que falte.' : 'Revisa que todo esté bien.';
          revisar.replaceChildren();
          var rol = roles && roles.length > 1 ? el('select', { id: 'md-ine-rol' }, roles.map(function (r) { return el('option', { value: r.key }, [r.label]); })) : null;
          var f = el('form', {}, (rol ? [el('div', { class: 'campo' }, [el('label', { for: 'md-ine-rol' }, ['¿De quién es esta INE?']), rol])] : []).concat(claves.map(function (k) { return campoDato(CAMPO[k], h[k], 'md-ine-'); })).concat([
            el('button', { type: 'submit', class: 'boton boton--primario' }, ['Usar estos datos']),
          ]));
          f.addEventListener('submit', function (ev) { ev.preventDefault(); resultado = leerCampos(f, claves, 'md-ine-'); if (roles) resultado._rol = rol ? rol.value : roles[0].key; d.close(); });
          revisar.append(f);
          revisar.hidden = false;
        }).catch(function (e) { msg.textContent = (e && e.message) || 'No se pudo leer la foto.'; });
      });
    });
  }

  /* ---------- editar a una persona ---------- */
  function campoDato(c, valor, pre) {
    var id = pre + c.key;
    var ayuda = c.help ? el('small', { id: id + '-ayuda' }, [c.help]) : null;
    if (c.type === 'choice') {
      return el('fieldset', { class: 'campo' }, [el('legend', {}, [c.label])].concat(c.options.map(function (o) {
        return el('label', { class: 'opcion' }, [el('input', { type: 'radio', name: id, value: o.value, checked: valor === o.value }), ' ' + o.label]);
      })));
    }
    var tipo = { date: 'date', tel: 'tel', email: 'email' }[c.type] || 'text';
    var input = el('input', { id: id, name: id, type: tipo, value: valor || null, 'aria-describedby': ayuda ? id + '-ayuda' : null, autocomplete: 'off' });
    var nodo = el('div', { class: 'campo' }, [el('label', { for: id }, [c.label]), input, ayuda]);
    if (c.type === 'curp') {
      input.setAttribute('autocapitalize', 'characters');
      input.setAttribute('spellcheck', 'false');
      var aviso = el('small', { class: 'misdatos-curp', 'aria-live': 'polite' });
      nodo.append(aviso);
      input.addEventListener('input', function () {
        var r = curp(input.value);
        if (!r || input.value.replace(/\s/g, '').length < 18) { aviso.textContent = ''; return; }
        if (!r.ok) { aviso.textContent = r.error; return; }
        aviso.textContent = 'CURP correcta. Llenamos la fecha, el sexo y el estado de nacimiento.';
        var form = input.form;
        poner(form, pre, 'nacimiento', r.nacimiento);
        poner(form, pre, 'sexo', r.sexo);
        if (r.estado) { poner(form, pre, 'nacimiento_estado', r.estado, true); poner(form, pre, 'nacimiento_pais', r.pais, true); }
      });
    }
    return nodo;
  }
  function poner(form, pre, k, v, soloVacio) {
    if (!form || !v) return;
    var c = CAMPO[k];
    if (c && c.type === 'choice') {
      var r = form.querySelector('input[name="' + pre + k + '"][value="' + v + '"]');
      if (r) r.checked = true;
      return;
    }
    var i = form.querySelector('#' + pre + k);
    if (i && (!soloVacio || !i.value)) i.value = v;
  }
  function leerCampos(form, claves, pre) {
    var r = {};
    claves.forEach(function (k) {
      var c = CAMPO[k];
      if (c.type === 'choice') { var x = form.querySelector('input[name="' + pre + k + '"]:checked'); if (x) r[k] = x.value; }
      else { var i = form.querySelector('#' + pre + k); if (i && i.value.trim()) r[k] = c.type === 'curp' ? i.value.toUpperCase().replace(/\s/g, '') : i.value.trim(); }
    });
    return r;
  }

  function editarPersona(p, alTerminar) {
    p = p || { id: nuevoId(), relacion: personas().some(function (x) { return x.relacion === YO; }) ? DIC.relations[1] : YO, datos: {} };
    var pre = 'md-p-';
    var rel = el('select', { id: pre + 'relacion' }, DIC.relations.map(function (r) { return el('option', { value: r, selected: r === p.relacion }, [r]); }));
    var padres = ['madre', 'padre'].map(function (k) {
      var s = el('select', { id: pre + k }, [el('option', { value: '' }, ['No está guardada'])].concat(personas().filter(function (x) { return x.id !== p.id; }).map(function (x) {
        return el('option', { value: x.id, selected: p[k] === x.id }, [nombreDe(x)]);
      })));
      return el('div', { class: 'campo' }, [el('label', { for: pre + k }, [k === 'madre' ? 'Su mamá' : 'Su papá']), s]);
    });
    var grupos = [];
    DIC.fields.forEach(function (c) {
      var g = grupos.find(function (x) { return x.n === c.group; });
      if (!g) { g = { n: c.group, h: [] }; grupos.push(g); }
      g.h.push(campoDato(c, p.datos[c.key], pre));
    });
    var form = el('form', { class: 'llenar-form' }, [el('div', { class: 'campo' }, [el('label', { for: pre + 'relacion' }, ['¿Quién es?']), rel])]
      .concat([el('button', { type: 'button', class: 'boton', on: { click: function () {
        leerIne().then(function (r) { if (r) Object.keys(r).forEach(function (k) { poner(form, pre, k, r[k]); }); });
      } } }, ['Llenar con foto de su INE'])])
      .concat(grupos.map(function (g) { return el('fieldset', { class: 'grupo' }, [el('legend', {}, [g.n])].concat(g.h)); }))
      .concat([el('fieldset', { class: 'grupo' }, [el('legend', {}, ['Familia'])].concat(padres))])
      .concat([el('div', { class: 'llenar-pie' }, [el('button', { type: 'submit', class: 'boton boton--primario' }, ['Guardar'])])]));
    var d = dialogo(p.datos.nombre ? nombreDe(p) : 'Agregar a una persona', [form]);
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      p.datos = leerCampos(form, DIC.fields.map(function (c) { return c.key; }), pre);
      p.relacion = rel.value;
      ['madre', 'padre'].forEach(function (k) { var v = form.querySelector('#' + pre + k).value; if (v) p[k] = v; else delete p[k]; });
      if (!persona(p.id)) datos.personas.push(p);
      guardar().then(function () { d.close(); if (alTerminar) alTerminar(); });
    });
  }

  /* ---------- Mis datos: lista de personas ---------- */
  function gestor() {
    (estado() === 'nuevo' ? pedirProteccion() : pedirAbrir()).then(function (ok) {
      if (!ok) return;
      var lista = el('ul', { class: 'misdatos-lista' });
      var msg = estadoTxt();
      function pintar() {
        lista.replaceChildren.apply(lista, personas().map(function (p) {
          return el('li', {}, [
            el('button', { type: 'button', class: 'misdatos-persona', on: { click: function () { editarPersona(p, pintar); } } }, [
              el('strong', {}, [nombreDe(p)]), el('span', {}, [p.relacion]),
            ]),
            el('button', { type: 'button', class: 'misdatos-quitar', 'aria-label': 'Borrar a ' + nombreDe(p), on: { click: function (ev) {
              if (ev.currentTarget.dataset.seguro !== '1') { ev.currentTarget.dataset.seguro = '1'; ev.currentTarget.textContent = '¿Seguro?'; return; }
              datos.personas = datos.personas.filter(function (x) { return x.id !== p.id; });
              datos.personas.forEach(function (x) { if (x.madre === p.id) delete x.madre; if (x.padre === p.id) delete x.padre; });
              guardar().then(pintar);
            } } }, ['Borrar']),
          ]);
        }));
        if (!personas().length) lista.append(el('li', { class: 'misdatos-vacio' }, ['Todavía no hay nadie. Empieza contigo.']));
      }
      pintar();
      var archivo = el('input', { type: 'file', accept: '.json,application/json', id: 'md-importar', class: 'misdatos-archivo' });
      archivo.addEventListener('change', function () {
        var f = archivo.files[0];
        if (!f) return;
        f.text().then(function (t) {
          var b = JSON.parse(t);
          if (b.v !== 1 || !b.llaves || !b.data) throw new Error();
          return pedirFraseCopia(b);
        }).then(function (otros) {
          if (!otros) return;
          otros.personas.forEach(function (p) { if (!persona(p.id)) datos.personas.push(p); });
          return guardar().then(function () { pintar(); msg.textContent = 'Listo: agregamos ' + otros.personas.length + ' persona(s).'; });
        }).catch(function () { msg.textContent = 'Ese archivo no es una copia de Mis datos.'; });
      });
      dialogo('Mis datos', [
        el('p', { class: 'llenar-nota' }, ['Lo que guardas aquí llena cualquier formato con un toque. Vive solo en este teléfono, con llave.']),
        lista,
        el('div', { class: 'misdatos-acciones' }, [
          el('button', { type: 'button', class: 'boton boton--primario', on: { click: function () { editarPersona(null, pintar); } } }, ['Agregar a una persona']),
          el('button', { type: 'button', class: 'boton', on: { click: function () { exportar(msg); } } }, ['Guardar una copia con llave']),
          el('label', { for: 'md-importar', class: 'boton' }, ['Cargar una copia']), archivo,
          el('button', { type: 'button', class: 'boton', on: { click: function (ev) { cerrar(); ev.target.closest('dialog').close(); } } }, ['Cerrar con llave']),
          el('button', { type: 'button', class: 'boton boton--peligro', on: { click: function (ev) {
            if (ev.target.dataset.seguro !== '1') { ev.target.dataset.seguro = '1'; ev.target.textContent = 'Toca otra vez para borrar todo'; return; }
            try { localStorage.removeItem(CLAVE); } catch (e) { /* nada */ }
            enMemoria = null; cerrar(); ev.target.closest('dialog').close();
          } } }, ['Borrar todo de este teléfono']),
        ]),
        msg,
      ]);
    });
  }
  // Copia con llave para otro teléfono o para la familia: se cifra con una frase nueva, no con la de este teléfono.
  function exportar(msg) {
    var f = el('input', { type: 'password', id: 'md-fc', minlength: 8, required: true, autocomplete: 'new-password' });
    var form = el('form', { class: 'misdatos-frase' }, [
      el('label', { for: 'md-fc' }, ['Frase para abrir la copia']),
      el('small', {}, ['Mínimo 8 letras. Dísela solo a quien vaya a abrir la copia, y no la mandes en el mismo mensaje que el archivo.']),
      f, el('button', { type: 'submit', class: 'boton boton--primario' }, ['Descargar la copia']),
    ]);
    var d = dialogo('Copia con llave', [form], 'misdatos--chico');
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var sal = azar(16), dekCopia;
      crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']).then(function (k) {
        dekCopia = k;
        return kekFrase(f.value, sal, VUELTAS);
      }).then(function (kek) { return envolver(dekCopia, kek); }).then(function (w) {
        return cifrar(dekCopia, { personas: datos.personas }).then(function (c) {
          var blob = new Blob([JSON.stringify({ v: 1, llaves: [Object.assign({ tipo: 'frase', sal: b64(sal), vueltas: VUELTAS }, w)], data: c })], { type: 'application/json' });
          descargar(blob, 'mis-datos-con-llave.json');
          d.close();
          msg.textContent = 'Listo. La copia solo se abre con la frase que escribiste.';
        });
      });
    });
  }
  function pedirFraseCopia(b) {
    return new Promise(function (ok) {
      var r = null, msg = estadoTxt();
      var f = el('input', { type: 'password', id: 'md-fi', required: true, autocomplete: 'off' });
      var form = el('form', { class: 'misdatos-frase' }, [el('label', { for: 'md-fi' }, ['Frase de la copia']), f, el('button', { type: 'submit', class: 'boton boton--primario' }, ['Abrir la copia']), msg]);
      var d = dialogo('Cargar una copia', [form], 'misdatos--chico');
      d.addEventListener('close', function () { ok(r); });
      form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var w = b.llaves[0];
        kekFrase(f.value, deb64(w.sal), w.vueltas).then(function (kek) { return desenvolver(w, kek); }).then(function (k) { return descifrar(k, b.data); })
          .then(function (x) { r = x; d.close(); }, function () { msg.textContent = 'Esa frase no abre la copia.'; });
      });
    });
  }
  var bajar = null;
  if (window.claude && window.claude.use) window.claude.use('downloads').then(function (x) { bajar = x; }, function () {});
  function descargar(blob, nombre) {
    if (bajar) return bajar.save({ filename: nombre, data: blob }).catch(function () {});
    var a = el('a', { href: URL.createObjectURL(blob), download: nombre });
    document.body.append(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
  }

  /* ---------- puente con el formulario de un formato ---------- */
  function camposDe(def, quien) { return def.fields.filter(function (f) { return f.person === quien && f.profile; }); }
  function plantilla(t) { return /\{/.test(t); }
  function llenarPersona(def, form, quien, d) {
    camposDe(def, quien).forEach(function (f) {
      var v;
      if (plantilla(f.profile)) {
        v = f.profile.replace(/\{([^}]+)\}/g, function (_, k) { return d[k] || ''; })
          .replace(/\s+/g, ' ').replace(/(^[\s,]+|[\s,]+$)/g, '').replace(/,\s*,/g, ',');
      } else v = d[f.profile];
      if (!v) return;
      if (f.type === 'choice') {
        var o = (f.options || []).find(function (x) { return (x.profile || x.value) === v; });
        var r = o && form.querySelector('input[name="' + f.key + '"][value="' + o.value + '"]');
        if (r) r.checked = true;
      } else {
        var i = form.elements[f.key];
        if (i) { i.value = v; i.dispatchEvent(new Event('input', { bubbles: true })); }
      }
    });
  }
  function datosDelForm(def, form, quien) {
    var r = {};
    camposDe(def, quien).forEach(function (f) {
      if (plantilla(f.profile)) return; // un texto armado con varios datos no se puede separar de regreso
      if (f.type === 'choice') {
        var x = form.querySelector('input[name="' + f.key + '"]:checked');
        var o = x && (f.options || []).find(function (y) { return y.value === x.value; });
        if (o) r[f.profile] = o.profile || o.value;
      } else {
        var i = form.elements[f.key];
        if (i && i.value.trim()) r[f.profile] = i.value.trim();
      }
    });
    return r;
  }

  // Barra arriba del formulario: elegir a quién de tus datos usar para cada persona del formato, o leer una INE.
  function barra(def, form) {
    var gente = def.people || [];
    if (!gente.length) return null;
    var caja = el('section', { class: 'misdatos-barra', 'aria-label': 'Llenar con tus datos' });
    var eleccion = {};
    function elegir(quien, id) {
      eleccion[quien] = id;
      var x = persona(id);
      if (x) llenarPersona(def, form, quien, x.datos);
      // La mamá y el papá de esa persona, si están guardados, se eligen solos.
      gente.forEach(function (p) {
        if (p.relative && p.relative.of === quien && x && x[p.relative.link] && persona(x[p.relative.link])) {
          var s = caja.querySelector('[data-persona="' + p.key + '"]');
          if (s) { s.value = x[p.relative.link]; elegir(p.key, s.value); }
        }
      });
    }
    var botonIne = function (texto) {
      return el('button', { type: 'button', class: 'boton boton--chico', on: { click: function () {
        leerIne(gente).then(function (r) { if (r) { llenarPersona(def, form, r._rol, r); eleccion[r._rol] = eleccion[r._rol] || ''; } });
      } } }, [texto]);
    };
    function pintar() {
      caja.replaceChildren();
      var st = estado();
      if (st !== 'abierto') {
        caja.append(el('p', {}, [st === 'cerrado' ? 'Tienes datos guardados en este teléfono.' : '¿Tienes una INE a la mano? Tómale foto y llenamos los datos por ti.']));
        var fila = el('div', { class: 'misdatos-botones' });
        if (st === 'cerrado') fila.append(el('button', { type: 'button', class: 'boton boton--chico boton--primario', on: { click: function () { pedirAbrir(); } } }, ['Usar mis datos']));
        fila.append(botonIne('Llenar con foto de INE'));
        caja.append(fila);
        return;
      }
      caja.append(el('h3', {}, ['Llenar con mis datos']));
      var yo = (personas().find(function (x) { return x.relacion === YO; }) || {}).id;
      var inicial = [];
      gente.forEach(function (p) {
        var sel = eleccion[p.key] != null ? eleccion[p.key] : p.default === 'yo' ? yo : null;
        var id = 'md-' + def.id + '-' + p.key;
        var s = el('select', { id: id, 'data-persona': p.key }, [el('option', { value: '' }, ['Escribir a mano'])].concat(personas().map(function (x) {
          return el('option', { value: x.id, selected: sel === x.id }, [nombreDe(x) + ' · ' + x.relacion]);
        })));
        s.addEventListener('change', function () { elegir(p.key, s.value); });
        caja.append(el('div', { class: 'misdatos-fila' }, [el('label', { for: id }, [p.label]), s]));
        if (sel && eleccion[p.key] == null) inicial.push([p.key, sel]);
      });
      caja.append(el('div', { class: 'misdatos-botones' }, [botonIne('Llenar con foto de INE'),
        el('button', { type: 'button', class: 'enlace', on: { click: gestor } }, ['Ver y editar mis datos'])]));
      inicial.forEach(function (x) { elegir(x[0], x[1]); });
    }
    oyentes.push(pintar);
    pintar();
    caja._eleccion = eleccion;
    return caja;
  }

  function normal(s) { return String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s+/g, ' ').trim(); }
  function nombreCompleto(d) { return normal([d.nombre, d.apellido1, d.apellido2].join(' ')); }
  // Lo que se escribió en un campo armado con varios datos («{nacimiento_estado}, {nacimiento_pais}»), separado de regreso.
  // Solo si los separadores tienen algo más que espacios, para no partir mal un nombre de dos palabras.
  function separar(tpl, valor) {
    var partes = tpl.split(/\{[^}]+\}/), claves = (tpl.match(/\{([^}]+)\}/g) || []).map(function (k) { return k.slice(1, -1); });
    if (partes.slice(1, -1).some(function (s) { return !s.trim(); })) return null;
    var re = new RegExp('^' + partes.map(function (s) { return s.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }).join('\\s*(.*?)\\s*') + '$');
    var m = re.exec(String(valor || '').trim());
    if (!m) return null;
    var r = {};
    claves.forEach(function (k, i) { if (m[i + 1]) r[k] = m[i + 1]; });
    return r;
  }

  // Después de armar el PDF: guardar lo que se escribió para la próxima vez.
  function ofrecerGuardar(def, form, barraNodo, donde) {
    var gente = def.people || [];
    if (!gente.length) return;
    var viejo = form.querySelector('.misdatos-guardar');
    if (viejo) viejo.remove();
    var eleccion = (barraNodo && barraNodo._eleccion) || {};
    var d = {};
    gente.forEach(function (p) {
      d[p.key] = datosDelForm(def, form, p.key);
      camposDe(def, p.key).forEach(function (f) {
        if (!plantilla(f.profile) || !form.elements[f.key]) return;
        var r = separar(f.profile, form.elements[f.key].value);
        if (r) Object.keys(r).forEach(function (k) { if (!d[p.key][k]) d[p.key][k] = r[k]; });
      });
    });
    // ¿Quien firma es otra persona del formato? Se compara el nombre completo que escribió.
    var mismo = {};
    gente.forEach(function (p) {
      var f = camposDe(def, p.key).find(function (c) { return plantilla(c.profile) && /\{nombre\}/.test(c.profile); });
      var escrito = f && form.elements[f.key] && normal(form.elements[f.key].value);
      if (!escrito) return;
      gente.forEach(function (q) { if (q.key !== p.key && d[q.key].nombre && nombreCompleto(d[q.key]) === escrito) mismo[p.key] = q.key; });
    });
    var yoRol = (gente.find(function (p) { return p.default === 'yo'; }) || {}).key;
    if (mismo[yoRol]) yoRol = mismo[yoRol];
    var hayYo = personas().some(function (x) { return x.relacion === YO; });
    function relacionSugerida(p) {
      if (!hayYo && p.key === yoRol) return YO;
      var rolYo = gente.find(function (q) { return q.key === yoRol; });
      if (rolYo && rolYo.relative && rolYo.relative.of === p.key) return DIC.relations[1]; // yo soy su mamá o su papá
      if (p.relative && p.relative.of === yoRol) return p.relative.link === 'madre' ? DIC.relations[2] : DIC.relations[3];
      return DIC.relations[DIC.relations.length - 1];
    }
    var filas = gente.map(function (p) {
      if (mismo[p.key]) { Object.keys(d[p.key]).forEach(function (k) { if (!d[mismo[p.key]][k]) d[mismo[p.key]][k] = d[p.key][k]; }); return null; }
      var existente = persona(eleccion[p.key]);
      if (!existente && !d[p.key].nombre && !d[p.key].apellido1) return null; // sin nombre no se guarda a nadie nuevo
      return { p: p, existente: existente };
    }).filter(Boolean);
    if (!filas.length) return;
    var msg = estadoTxt();
    var rels = filas.map(function (f, i) {
      if (f.existente) return null;
      var sug = relacionSugerida(f.p);
      return el('select', { id: 'md-rel-' + i }, DIC.relations.map(function (r) { return el('option', { value: r, selected: r === sug }, [r]); }));
    });
    var caja = el('section', { class: 'misdatos-guardar', tabindex: '-1' }, [
      el('h3', {}, ['¿Lo guardas para la próxima vez?']),
      el('p', {}, ['Así no vuelves a escribir estos datos en ningún formato. Se guardan solo en este teléfono, con llave.']),
      el('ul', {}, filas.map(function (f, i) {
        var x = d[f.p.key];
        var n = [x.nombre, x.apellido1].filter(Boolean).join(' ') || nombreDe(f.existente);
        return el('li', {}, [
          el('label', { for: rels[i] ? 'md-rel-' + i : null }, [f.p.label + ': ', el('strong', {}, [n]), f.existente ? el('span', { class: 'misdatos-ya' }, [' · se actualiza']) : ' · ¿quién es?']),
          rels[i],
        ]);
      })),
      el('button', { type: 'button', class: 'boton boton--primario', on: { click: function () {
        var listo = estado() === 'abierto' ? Promise.resolve(true) : estado() === 'cerrado' ? pedirAbrir() : pedirProteccion();
        listo.then(function (ok) {
          if (!ok) return;
          var ids = {};
          filas.forEach(function (f, i) {
            var x = d[f.p.key];
            var y = f.existente || personas().find(function (z) { return z.datos.nombre && nombreCompleto(z.datos) === nombreCompleto(x); });
            if (!y) { y = { id: nuevoId(), relacion: rels[i] ? rels[i].value : DIC.relations[DIC.relations.length - 1], datos: {} }; datos.personas.push(y); }
            Object.assign(y.datos, x);
            ids[f.p.key] = y.id;
          });
          Object.keys(mismo).forEach(function (k) { if (ids[mismo[k]]) ids[k] = ids[mismo[k]]; });
          gente.forEach(function (p) {
            if (p.relative && ids[p.relative.of] && ids[p.key]) persona(ids[p.relative.of])[p.relative.link] = ids[p.key];
          });
          Object.assign(eleccion, ids);
          return guardar().then(function () {
            caja.replaceChildren(el('p', { class: 'misdatos-hecho' }, ['Guardado. La próxima vez, elige a la persona arriba y el formato se llena solo.']));
          });
        }).catch(function () { msg.textContent = 'No se pudo guardar.'; });
      } } }, ['Guardar en mi teléfono']),
      msg,
    ]);
    donde.parentNode.insertBefore(caja, donde);
    caja.scrollIntoView({ block: 'nearest' });
  }

  // Con la persona que usa el teléfono, el navegador también puede sugerir sus datos (autocomplete).
  function autocompletar(def, f) {
    var p = (def.people || []).find(function (x) { return x.key === f.person; });
    if (!p || p.default !== 'yo' || !f.profile || plantilla(f.profile)) return null;
    return (CAMPO[f.profile] || {}).autocomplete || null;
  }

  window.MisDatos = { barra: barra, ofrecerGuardar: ofrecerGuardar, gestor: gestor, curp: curp, leerMrz: leerMrz, buscarCurp: buscarCurp, autocompletar: autocompletar };
})();
