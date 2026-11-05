/* Spurlos – Oberfläche. Läuft nur lokal, spricht mit dem eigenen Server auf 127.0.0.1. */
(function () {
  'use strict';

  var $app = document.getElementById('app');
  var $modal = document.getElementById('modal-root');
  var $toast = document.getElementById('toast');

  var S = {
    boot: null, overview: null, requests: null, inbox: null, brokers: null, aiStatus: null,
    reqDetail: null, testResult: null, busy: {},
    draft: null,
    ui: { reqFilter: 'all', reqSearch: '', reqSel: null, inboxSel: null, inboxCat: {}, brTab: 'all', brView: 'selected',
          brSearch: '', setTab: 'daten', fullText: false }
  };

  // ------------------------------------------------------------------ Hilfen
  function esc(s) {
    return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || (opts.body ? 'POST' : 'GET'), headers: { 'X-Spurlos': '1' }, credentials: 'same-origin' };
    if (opts.body) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(opts.body); }
    return fetch(path, init).then(function (r) {
      return r.json().catch(function () { return { ok: false, error: 'Unerwartete Antwort (' + r.status + ')' }; });
    }).then(function (d) {
      if (!d || d.ok === false) { throw new Error((d && d.error) || 'Unbekannter Fehler'); }
      return d;
    });
  }
  function toast(msg, bad) {
    var el = document.createElement('div');
    if (bad) el.className = 'bad';
    el.textContent = msg;
    $toast.appendChild(el);
    setTimeout(function () { el.remove(); }, bad ? 7000 : 3500);
  }
  function fail(e) { toast(e && e.message ? e.message : String(e), true); }
  var DAYS = ['So.', 'Mo.', 'Di.', 'Mi.', 'Do.', 'Fr.', 'Sa.'];
  function parseDate(s) {
    if (!s || !/^\d{4}-\d\d-\d\d/.test(s)) return null;
    var d = new Date(s.replace(' ', 'T'));
    return isNaN(d) ? null : d;
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function fmtWhen(s, noTime) {
    var d = parseDate(s);
    if (!d) return esc(s || '');
    var now = new Date();
    var day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var diff = Math.round((day - today) / 86400000);
    var t = pad(d.getHours()) + ':' + pad(d.getMinutes());
    var label = diff === 0 ? 'Heute' : diff === -1 ? 'Gestern' : diff === 1 ? 'Morgen'
      : DAYS[d.getDay()] + ', ' + pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + '.' + (d.getFullYear() !== now.getFullYear() ? d.getFullYear() : '');
    return noTime ? label : label + ' ' + t;
  }
  function fmtDay(s) {
    var d = parseDate(s);
    return d ? pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + '.' : '–';
  }
  function url(u) { return /^https?:\/\//i.test(String(u || '')) ? esc(u) : '#'; }
  function pill(group, label) { return '<span class="pill g-' + esc(group) + '">' + esc(label) + '</span>'; }
  function langLabel(l) { return { de: 'Deutsch', ch: 'Deutsch (Schweiz)', en: 'Englisch' }[l] || 'Englisch'; }
  function groupLabel(g) { var m = S.boot.group_meta[g]; return m ? m.label : g; }

  var I = {
    grid: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
    inbox: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>',
    send: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7z"/></svg>',
    printer: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>',
    db: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/></svg>',
    check: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
    sliders: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>',
    lock: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
    refresh: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg>',
    info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
    warn: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
    ok: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>',
    x: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
    trash: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>',
    ext: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14 21 3"/></svg>'
  };
  var LOGO = '<svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true"><rect width="28" height="28" rx="8" fill="#1F2530"/><circle cx="7.5" cy="20" r="1.8" fill="#3DDCBF" opacity="0.3"/><circle cx="12.5" cy="15.5" r="2.1" fill="#3DDCBF" opacity="0.6"/><circle cx="18.5" cy="10" r="2.6" fill="#3DDCBF"/></svg>';

  // ------------------------------------------------------------------ Ereignisse
  var ACT = {};
  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-act]');
    if (!el || el.disabled) return;
    var fn = ACT[el.dataset.act];
    if (fn) { e.preventDefault(); fn(el, e); }
  });
  document.addEventListener('input', onField);
  document.addEventListener('change', onField);
  function onField(e) {
    var el = e.target;
    if (!el.dataset) return;
    var val = el.type === 'checkbox' ? el.checked : el.value;
    if (el.dataset.p && S.draft) { S.draft.profile[el.dataset.p] = val; }
    if (el.dataset.list && S.draft) {
      var row = S.draft.profile[el.dataset.list][+el.dataset.i];
      if (row) {
        row[el.dataset.k] = val;
        if (el.dataset.k === 'current' && e.type === 'change') {
          if (val) S.draft.profile.addresses.forEach(function (a, j) { if (j !== +el.dataset.i) a.current = false; });
          renderKeep();
        }
      }
    }
    if (el.dataset.m && S.draft) { S.draft.mailbox[el.dataset.m] = val; }
    if (el.dataset.pw !== undefined && S.draft) { S.draft.password = val; }
    if (el.dataset.state !== undefined && S.draft) { S.draft.state = val; }
    if (el.dataset.ui) { S.ui[el.dataset.ui] = val; if (el.dataset.rerender && e.type === 'input') renderKeep(); }
    if (el.dataset.send && S.draft) { S.draft.sending[el.dataset.send] = el.type === 'number' ? +val : val; }
    if (el.dataset.ai && S.draft) { S.draft.ai[el.dataset.ai] = val; }
  }
  function renderKeep() {
    var a = document.activeElement;
    var id = a && a.id;
    var pos = a && a.selectionStart;
    render();
    if (id) {
      var n = document.getElementById(id);
      if (n) { n.focus(); try { n.setSelectionRange(pos, pos); } catch (err) { /* ignore */ } }
    }
  }

  // ------------------------------------------------------------------ Modal
  function openModal(html) {
    $modal.innerHTML = '<div class="modal-back" data-act="modal-back"><div class="modal" role="dialog" aria-modal="true">' + html + '</div></div>';
    var f = $modal.querySelector('button, input, textarea, select');
    if (f) f.focus();
  }
  function closeModal() { $modal.innerHTML = ''; }
  ACT['close-modal'] = closeModal;
  ACT['modal-back'] = function (el, e) { if (e.target === el) closeModal(); };
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && $modal.innerHTML) closeModal(); });
  function textModal(title, sub, subject, text, extra) {
    openModal('<div class="row between"><h2>' + esc(title) + '</h2><button class="btn sm" data-act="close-modal">Schließen</button></div>' +
      (sub ? '<p class="small muted" style="margin:0">' + esc(sub) + '</p>' : '') +
      (subject ? '<div class="field"><span class="lbl">Betreff</span><div class="mono small">' + esc(subject) + '</div></div>' : '') +
      '<pre>' + esc(text) + '</pre>' + (extra || '') +
      '<div class="row"><button class="btn sm" data-act="copy-modal">Text kopieren</button></div>');
    ACT['copy-modal'] = function () {
      var t = (subject ? 'Betreff: ' + subject + '\n\n' : '') + text;
      navigator.clipboard.writeText(t).then(function () { toast('Kopiert'); }, function () { toast('Kopieren nicht möglich', true); });
    };
  }

  // ------------------------------------------------------------------ Laden
  function load() {
    return api('/api/bootstrap').then(function (d) {
      S.boot = d;
      if (!S.draft) resetDraft();
      return d;
    });
  }
  function resetDraft() {
    var b = S.boot;
    S.draft = {
      profile: JSON.parse(JSON.stringify(b.profile)),
      state: b.state, countries: (b.countries || ['de']).slice(),
      mailbox: JSON.parse(JSON.stringify(b.mailbox)), password: '',
      sending: JSON.parse(JSON.stringify(b.sending)), ai: JSON.parse(JSON.stringify(b.ai))
    };
    var p = S.draft.profile;
    ['former_names', 'addresses', 'emails', 'phones', 'companies', 'websites'].forEach(function (k) { if (!Array.isArray(p[k])) p[k] = []; });
    p.addresses = p.addresses.map(splitAddress);
    p.companies = p.companies.map(function (c) { return c.name !== undefined ? c : { name: (c.text || '').split(' · ')[0], role: (c.text || '').split(' · ')[1] || '' }; });
    // Websites standen früher in der Firmenzeile, jetzt haben sie eine eigene Liste
    p.companies.forEach(function (c) {
      var w = (c.website || '').trim();
      if (w && !p.websites.some(function (x) { return (x.url || '').toLowerCase() === w.toLowerCase(); })) p.websites.push({ url: w });
      delete c.website;
    });
    if (!p.addresses.length) p.addresses.push({ street: '', zip: '', city: '', current: true });
    if (!p.emails.length) p.emails.push({ address: '' });
    if (!p.phones.length) p.phones.push({ number: '', label: 'Mobil' });
  }
  function splitAddress(a) {
    if (a.street !== undefined || !a.text) return a;
    var m = /^(.*?),\s*(\d{4,5})\s+(.+)$/.exec(a.text.trim());
    return m ? { street: m[1], zip: m[2], city: m[3], current: !!a.current } : { street: a.text, zip: '', city: '', current: !!a.current };
  }
  function refreshData() {
    var r = route();
    var jobs = [api('/api/overview').then(function (d) { S.overview = d; })];
    if (r.page === 'eingang') jobs.push(api('/api/inbox').then(function (d) { S.inbox = d.items; S.unassigned = d.unassigned || []; S.targets = d.targets || []; }));
    if (r.page === 'anfragen') jobs.push(api('/api/requests').then(function (d) { S.requests = d.requests; }));
    if (r.page === 'anfragen' && S.ui.reqSel) jobs.push(api('/api/requests/' + encodeURIComponent(S.ui.reqSel)).then(function (d) { S.reqDetail = d; }).catch(function () { S.ui.reqSel = null; S.reqDetail = null; }));
    if (r.page === 'haendler' || r.page === 'einrichtung') jobs.push(api('/api/brokers').then(function (d) { S.brokers = d; }));
    return Promise.all(jobs);
  }

  // ------------------------------------------------------------------ Navigation
  function route() {
    var h = location.hash.replace(/^#\/?/, '');
    var parts = h.split('?');
    var seg = parts[0].split('/');
    var q = {};
    (parts[1] || '').split('&').forEach(function (kv) { if (kv) { var p = kv.split('='); q[p[0]] = decodeURIComponent(p[1] || ''); } });
    return { page: seg[0] || '', arg: seg[1] || '', q: q };
  }
  window.addEventListener('hashchange', function () {
    var r = route();
    if (r.page === 'anfragen' && r.q.f) S.ui.reqFilter = r.q.f;
    if (r.page === 'einstellungen' && r.arg) S.ui.setTab = r.arg;
    render();
    refreshData().then(render).catch(fail);
    window.scrollTo(0, 0);
  });
  function go(hash) { if (location.hash === hash) { render(); } else { location.hash = hash; } }

  // ------------------------------------------------------------------ Rahmen
  function render() {
    if (!S.boot) { $app.innerHTML = '<div class="empty"><span class="spin"></span>Lädt …</div>'; return; }
    var r = route();
    if (!S.boot.setup_done || r.page === 'einrichtung') { $app.innerHTML = renderSetup(r); return; }
    var page = r.page || 'uebersicht';
    var body = '';
    if (page === 'uebersicht') body = renderOverview();
    else if (page === 'eingang') body = renderInbox();
    else if (page === 'anfragen') body = renderRequests();
    else if (page === 'haendler') body = renderBrokers();
    else if (page === 'einstellungen') body = renderSettings();
    else body = renderOverview();
    $app.innerHTML = '<div class="layout">' + renderSide(page) + '<main class="main">' + body + '</main></div>';
  }

  function renderSide(page) {
    var o = S.overview || {};
    var mb = (o.mailbox || {});
    var aiName = { none: 'Ohne KI', apple: 'Apple Intelligence', ollama: 'Lokales Modell', cloud: 'Cloud-KI' }[S.boot.ai.provider] || 'Ohne KI';
    function a(id, href, icon, label, extra) {
      return '<a href="' + href + '" class="' + (page === id ? 'on' : '') + '">' + icon + '<span>' + label + '</span>' + (extra || '') + '</a>';
    }
    return '<aside class="side"><div>' +
      '<a class="brand" href="#/uebersicht">' + LOGO + '<b>Spurlos</b><span class="ver">v' + esc(S.boot.version) + '</span></a>' +
      '<nav class="nav" aria-label="Hauptnavigation">' +
      a('uebersicht', '#/uebersicht', I.grid, 'Übersicht') +
      a('eingang', '#/eingang', I.inbox, 'Eingang', o.inbox ? '<span class="badge">' + o.inbox + '</span>' : '') +
      a('anfragen', '#/anfragen', I.send, 'Anfragen', o.total ? '<span class="count">' + o.total + '</span>' : '') +
      '<span class="navitem">' + I.printer + '<span>Briefe</span><span class="soon">bald</span></span>' +
      a('haendler', '#/haendler', I.db, 'Händlerliste') +
      '<span class="navitem">' + I.check + '<span>Weitere Spuren</span><span class="soon">bald</span></span>' +
      '</nav></div>' +
      '<div class="stack" style="gap:14px"><nav class="nav" style="margin:0">' + a('einstellungen', '#/einstellungen', I.sliders, 'Einstellungen') + '</nav>' +
      '<div class="status-box"><div class="row" style="gap:8px"><span class="dot' + (mb.ok === false ? ' bad' : '') + '"></span><span style="color:#E6E9EE;font-size:13px">' +
      (mb.ok === false ? 'Postfach: Problem' : 'Postfach verbunden') + '</span></div>' +
      '<span class="addr">' + esc(mb.address || S.boot.mailbox.address || '') + '</span>' +
      '<div class="row" style="gap:8px"><span class="ki-tag">KI</span><span>' + esc(aiName) + '</span></div>' +
      '<div class="row" style="gap:8px;padding-top:10px;border-top:1px solid var(--side-line)">' + I.lock + '<span>Alle Daten bleiben auf diesem Mac</span></div></div></div></aside>';
  }

  function head(eyebrow, title, actions) {
    return '<header class="page-head"><div><span class="eyebrow">' + eyebrow + '</span><h1>' + esc(title) + '</h1></div>' +
      (actions ? '<div class="row wrap">' + actions + '</div>' : '') + '</header>';
  }

  // ------------------------------------------------------------------ Übersicht
  function renderOverview() {
    var o = S.overview;
    if (!o) return head('', 'Übersicht') + '<div class="empty"><span class="spin"></span></div>';
    var c = o.counts;
    var total = o.total || 0;
    var done = c.done || 0;
    var pct = total ? Math.round(done / total * 100) : 0;
    var segs = [['done', 'Erledigt', '#1F8A5B'], ['wait', 'Wartet auf Antwort', '#3E6FE8'], ['todo', 'Zu tun', '#E07B24'],
      ['overdue', 'Überfällig', '#C93A3A'], ['planned', 'Geplant', '#C9CED6'], ['missing', 'Kontakt fehlt', '#E3E6EB']];
    var bar = segs.filter(function (s) { return c[s[0]]; }).map(function (s) {
      return '<span style="flex:' + c[s[0]] + ';background:' + s[2] + '"></span>';
    }).join('') || '<span style="flex:1;background:#E3E6EB"></span>';
    var legend = segs.map(function (s) {
      return '<span><i style="background:' + s[2] + '"></i>' + s[1] + ' <span class="mono muted">' + (c[s[0]] || 0) + '</span></span>';
    }).join('');
    var outcomes = o.outcomes || {};
    var errors = '';
    if (o.mailbox && o.mailbox.error) errors += '<div class="notice bad">' + I.warn + '<span><b>Postfach:</b> ' + esc(o.mailbox.error) + ' <a href="#/einstellungen/postfach">Postfach prüfen</a></span></div>';
    if (o.mailbox && o.mailbox.send_error) errors += '<div class="notice warn">' + I.warn + '<span><b>Versand:</b> ' + esc(o.mailbox.send_error) + '</span></div>';
    var todos = (o.todos || []).map(function (t) {
      return '<li><span class="num">' + t.n + '</span><div class="grow stack" style="gap:2px"><b style="font-weight:500">' + esc(t.title) + '</b><span class="small muted">' + esc(t.sub) + '</span></div>' +
        '<a class="btn sm" href="' + esc(t.href) + '">' + esc(t.cta) + '</a></li>';
    }).join('') || '<li><span class="muted small">Gerade gibt es nichts zu tun. Spurlos meldet sich, sobald eine Antwort kommt.</span></li>';
    var plan = (o.plan || []).map(function (p) {
      return '<li><div class="rail"><i></i><b></b></div><div class="tx"><span class="when">' + (parseDate(p.when) ? fmtWhen(p.when) : esc(p.when)) + '</span><b style="font-weight:500">' + esc(p.title) + '</b><span class="small muted">' + esc(p.sub).replace(/\d{4}-\d\d-\d\d \d\d:\d\d(:\d\d)?/g, function (m) { return fmtWhen(m); }) + '</span></div></li>';
    }).join('');
    var act = (o.activity || []).map(function (a) {
      return '<li style="flex-wrap:wrap;gap:6px 16px"><span class="mono tiny muted" style="flex:0 0 112px">' + fmtWhen(a.at) + '</span>' +
        '<span class="grow" style="flex:1 1 220px">' + esc(a.name ? a.name + ': ' : '') + esc(a.text) + '</span>' +
        (a.ref ? '<span class="mono tiny muted">' + esc(a.ref) + '</span>' : '') + (a.status ? pill(a.group, a.label) : '') + '</li>';
    }).join('') || '<li><span class="muted small">Noch keine Aktivität.</span></li>';
    var today = new Date().toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' });
    return head(esc(today) + (o.mailbox && o.mailbox.last_poll ? ' · zuletzt abgerufen ' + fmtWhen(o.mailbox.last_poll) : ''), 'Übersicht',
      '<button class="btn" data-act="poll">' + I.refresh + '<span>Postfach abrufen</span></button><a class="btn p" href="#/anfragen">Alle Anfragen</a>') +
      errors +
      '<section class="card"><div class="row wrap between" style="align-items:flex-end"><div class="stack" style="gap:4px"><h2>Fortschritt</h2><p class="small muted" style="margin:0">' +
      o.sent + ' von ' + total + ' Firmen angeschrieben · ' + done + ' abgeschlossen</p></div><div class="row" style="align-items:baseline;gap:6px"><span class="mono" style="font-size:32px;font-weight:500">' + pct + '<span style="font-size:20px">%</span></span><span class="small muted">erledigt</span></div></div>' +
      '<div class="bar" role="img" aria-label="Verteilung der Anfragen">' + bar + '</div><div class="legend">' + legend + '</div></section>' +
      '<div class="grid-auto">' +
      kpi('Angeschrieben', o.sent, '/ ' + total, (c.planned || 0) + ' weitere sind geplant') +
      kpi('Antworten', o.replies, '', (o.inbox || 0) + ' davon musst du ansehen') +
      kpi('Erledigt', done, '', (outcomes.deleted || 0) + ' gelöscht · ' + (outcomes.no_data || 0) + ' ohne Daten', '#166534') +
      kpi('Überfällig', c.overdue || 0, '', 'Erinnerungen gehen automatisch raus', (c.overdue ? '#B91C1C' : '')) +
      '</div>' +
      '<div class="cols"><section class="card"><div class="row between"><h2>Für dich zu tun</h2></div><ul class="list">' + todos + '</ul></section>' +
      '<section class="card"><div class="stack" style="gap:4px"><h2>Das macht Spurlos als Nächstes</h2><p class="small muted" style="margin:0">Automatisch, solange Spurlos läuft.</p></div><ol class="timeline">' + plan + '</ol></section></div>' +
      '<section class="card"><h2>Letzte Aktivität</h2><ul class="list">' + act + '</ul></section>';
  }
  function kpi(label, v, of, sub, color) {
    return '<div class="kpi"><span class="label">' + label + '</span><div class="row" style="align-items:baseline;gap:6px"><span class="v" style="color:' + (color || 'var(--ink)') + '">' + v + '</span><span class="of">' + esc(of) + '</span></div><span class="small muted">' + esc(sub) + '</span></div>';
  }
  ACT.poll = function (el) {
    busy(el, true);
    api('/api/poll', { body: {} }).then(function (d) {
      toast(d.fetched ? d.fetched + ' neue Nachrichten geprüft, ' + d.reply + ' Antworten zugeordnet' + (d.unassigned ? ', ' + d.unassigned + ' nicht zuordenbar' : '') : 'Keine neuen Nachrichten');
      return refreshData();
    }).then(render).catch(fail).then(function () { busy(el, false); });
  };
  function busy(el, on) {
    if (!el) return;
    if (on) { el.dataset.html = el.innerHTML; el.innerHTML = '<span class="spin"></span><span>Bitte warten …</span>'; el.disabled = true; }
    else if (el.dataset.html !== undefined) { el.innerHTML = el.dataset.html; el.disabled = false; }
  }

  // ------------------------------------------------------------------ Eingang
  var CAT_ORDER = ['no_data', 'deleted', 'objection', 'access', 'id_request', 'clarify', 'confirm', 'webform', 'refused', 'unknown'];
  var NEXT = {
    no_data: ['Als erledigt markieren. Es gibt nichts zu löschen.', 'Bestätigen: erledigt'],
    deleted: ['Als erledigt markieren. Die Löschung ist bestätigt.', 'Bestätigen: erledigt'],
    objection: ['Als erledigt markieren. Der Widerspruch ist vermerkt.', 'Bestätigen: erledigt'],
    access: ['Jetzt die Löschung anfordern. Spurlos schickt dafür eine kurze Mail.', 'Löschung anfordern'],
    id_request: ['Antworten, dass es keinen Grund für Zweifel an deiner Identität gibt. Einen Ausweis schickst du nur bei echten Zweifeln, und dann geschwärzt.', 'Antwort senden'],
    clarify: ['Antworten: Bitte alle genannten Angaben prüfen.', 'Antwort senden'],
    webform: ['Die Firma will ihr Webformular. Die Anfrage wird als „Formular offen“ markiert.', 'Übernehmen'],
    confirm: ['Die Firma möchte, dass du deine Anfrage über einen Link bestätigst. Öffne den Link nur, wenn die Mail wirklich von dieser Firma kommt. Danach hier bestätigen.', 'Link geöffnet, weiter warten'],
    refused: ['Die Firma lehnt ab. Spurlos bereitet einen Beschwerde-Text vor.', 'Übernehmen'],
    unknown: ['Bitte selbst lesen und unten einordnen. Passt nichts, wartet Spurlos weiter auf eine Antwort.', 'Weiter warten']
  };
  function renderInbox() {
    var items = S.inbox;
    var top = head((items ? items.length + (S.unassigned || []).length : '…') + ' Antworten warten auf dich', 'Eingang',
      '<button class="btn" data-act="poll">' + I.refresh + '<span>Postfach abrufen</span></button>');
    var drop = '<div class="notice">' + I.info + '<span><b>Brief bekommen?</b> Das Einscannen von Briefen kommt in der nächsten Stufe. Bis dahin kannst du die Anfrage unter „Anfragen“ selbst als erledigt markieren.</span></div>';
    if (!items) return top + '<div class="empty"><span class="spin"></span></div>';
    var un = renderUnassigned();
    if (!items.length) return top + drop + un + (un ? '' : '<div class="card empty"><b>Alles erledigt.</b><span>Neue Antworten tauchen hier auf, sobald Spurlos sie im Postfach findet.</span></div>');
    var sel = items.filter(function (i) { return i.id === S.ui.inboxSel; })[0] || items[0];
    S.ui.inboxSel = sel.id;
    var list = items.map(function (i) {
      var sure = (i.confidence || 0) >= 0.75;
      return '<li><button class="item ' + (i.id === sel.id ? 'on' : '') + '" data-act="inbox-sel" data-id="' + i.id + '">' +
        '<div class="row between" style="width:100%"><b>' + esc(i.broker_name) + '</b><span class="mono tiny muted">' + fmtWhen(i.date) + '</span></div>' +
        '<div class="row wrap" style="gap:6px"><span class="ref">' + esc(i.ref) + '</span><span class="pill nodot ' + (sure ? 'g-done' : 'g-todo') + '">' + esc(i.category_label) + '</span></div></button></li>';
    }).join('');
    var cat = S.ui.inboxCat[sel.id] || sel.category;
    var conf = sel.confidence || 0;
    var n = conf >= 0.75 ? 3 : conf >= 0.5 ? 2 : 1;
    var segColor = n === 3 ? '#1F8A5B' : n === 2 ? '#E0A324' : '#E07B24';
    var segs = [0, 1, 2].map(function (k) { return '<i style="background:' + (k < n ? segColor : '') + '"></i>'; }).join('');
    var text = sel.body || '';
    var m = sel.match_text || '';
    var excerpt;
    var full = S.ui.fullText;
    if (m && text.indexOf(m) >= 0 && !full) {
      var at = text.indexOf(m);
      var start = Math.max(0, text.lastIndexOf('\n', Math.max(0, at - 300)));
      var end = Math.min(text.length, at + m.length + 400);
      excerpt = (start > 0 ? '… ' : '') + esc(text.slice(start, at).trim() ? text.slice(start, at) : '') + '<mark>' + esc(m) + '</mark>' + esc(text.slice(at + m.length, end)) + (end < text.length ? ' …' : '');
    } else if (m && text.indexOf(m) >= 0) {
      var at2 = text.indexOf(m);
      excerpt = esc(text.slice(0, at2)) + '<mark>' + esc(m) + '</mark>' + esc(text.slice(at2 + m.length));
    } else {
      excerpt = esc(full ? text : text.slice(0, 900) + (text.length > 900 ? ' …' : ''));
    }
    var options = CAT_ORDER.map(function (k) {
      return '<option value="' + k + '"' + (k === cat ? ' selected' : '') + '>' + esc(S.boot.categories[k]) + '</option>';
    }).join('');
    var nx = NEXT[cat] || NEXT.unknown;
    if (cat === 'access' && sel.grp === 'credit') nx = ['Bei Auskunfteien reicht die Auskunft. Als erledigt markieren.', 'Bestätigen: erledigt'];
    var detail = '<section class="card" aria-labelledby="det"><div class="row wrap between" style="align-items:flex-start"><div class="stack" style="gap:6px"><h2 id="det" style="font-size:20px">' + esc(sel.broker_name) + '</h2>' +
      '<div class="row wrap small muted" style="gap:8px"><span class="mono">' + esc(sel.ref) + '</span><span>·</span><span>' + esc(sel.from_addr) + '</span><span>·</span><span>' + fmtWhen(sel.date) + '</span>' + (sel.folder && sel.folder !== 'INBOX' ? '<span class="tag">aus dem Spam-Ordner</span>' : '') + '</div></div>' +
      '<span class="pill nodot g-done">' + I.ok + ' Zugeordnet</span></div>' +
      '<div class="stack" style="gap:8px"><span class="label">' + (full ? 'Ganze Antwort' : 'Auszug aus der Antwort') + '</span><p class="excerpt">' + excerpt + '</p>' +
      (sel.attachments ? '<span class="small muted">Anhänge: ' + esc(sel.attachments) + '</span>' : '') + '</div>' +
      '<div class="cols"><div class="card" style="padding:18px;gap:12px"><span class="label">Erkannt als</span><div class="stack" style="gap:2px"><span style="font-size:18px;font-weight:600">' + esc(sel.category_label) + '</span></div>' +
      '<div class="row"><span class="segs" aria-hidden="true">' + segs + '</span><span class="small" style="font-weight:500;color:' + (n === 3 ? '#166534' : '#9A3412') + '">' + (n === 3 ? 'Sicher' : n === 2 ? 'Ziemlich sicher' : 'Unsicher') + '</span></div>' +
      '<div class="stack" style="gap:6px;padding-top:10px;border-top:1px solid var(--line-3)"><div class="row small" style="align-items:flex-start;gap:8px;color:var(--ink-2)"><span class="tag">Regel</span><span>' + esc(sel.rule || '') + '</span></div>' +
      (sel.ai_note ? '<div class="row small" style="align-items:flex-start;gap:8px;color:var(--ink-2)"><span class="tag ki">KI</span><span>' + esc((sel.ai_label ? sel.ai_label + ': ' : '') + sel.ai_note) + '</span></div>' : '') + '</div></div>' +
      '<div class="suggest"><span class="label" style="color:var(--accent)">Vorschlag</span><span style="font-size:15px;line-height:1.5;font-weight:500">' + esc(nx[0]) + '</span>' +
      '<div class="field"><label for="cat">Einordnung</label><select id="cat" class="input" data-act-select="1">' + options + '</select></div>' +
      (sel.link && (cat === 'confirm' || sel.category === 'confirm') ? '<div class="stack" style="gap:4px"><span class="label">Link aus der Mail</span><a class="mono small" style="word-break:break-all" href="' + url(sel.link) + '" target="_blank" rel="noopener noreferrer">' + esc(sel.link) + ' ' + I.ext + '</a></div>' : '') +
      '<div class="row wrap"><button class="btn p sm" data-act="inbox-confirm" data-id="' + sel.id + '">' + esc(nx[1]) + '</button>' +
      '<a class="btn sm" href="#/anfragen" data-act="goto-req" data-ref="' + esc(sel.ref) + '">Anfrage ansehen</a></div></div></div>' +
      '<div class="row wrap between" style="padding-top:12px;border-top:1px solid var(--line-3)"><span class="small muted">Spurlos macht nichts, bevor du bestätigst.</span>' +
      '<button class="btn ghost sm" data-act="toggle-full">' + (full ? 'Nur Auszug zeigen' : 'Ganze Antwort zeigen') + '</button></div></section>';
    return top + drop + un + '<div class="split"><ul class="left list" style="display:flex;flex-direction:column;gap:10px" aria-label="Antworten">' + list.replace(/<li>/g, '<li style="border:none;padding:0">') + '</ul><div class="right">' + detail + '</div></div>';
  }
  document.addEventListener('change', function (e) {
    if (e.target.id === 'cat' && S.ui.inboxSel) { S.ui.inboxCat[S.ui.inboxSel] = e.target.value; render(); }
  });
  function renderUnassigned() {
    var list = S.unassigned || [];
    if (!list.length) return '';
    var opts = '<option value="">Anfrage wählen …</option>' + (S.targets || []).map(function (t) {
      return '<option value="' + esc(t.ref) + '">' + esc(t.name) + ' · ' + esc(t.ref) + '</option>';
    }).join('');
    return '<section class="card"><div class="stack" style="gap:4px"><h2>Nicht zugeordnet</h2><p class="small muted" style="margin:0">Diese Mails konnte Spurlos keiner Anfrage sicher zuordnen. Ordne sie zu, dann geht es normal weiter.</p></div><ul class="list">' +
      list.map(function (m) {
        return '<li style="flex-wrap:wrap;gap:8px 14px;align-items:flex-start"><div class="grow stack" style="gap:4px;flex:1 1 320px;min-width:0"><b style="font-weight:500">' + esc(m.subject || '(ohne Betreff)') + '</b>' +
          '<span class="small muted">' + esc(m.from_addr) + ' · ' + fmtWhen(m.date) + (m.folder && m.folder !== 'INBOX' ? ' · aus dem Spam-Ordner' : '') + '</span>' +
          '<span class="small" style="color:var(--ink-2)">' + esc((m.body || '').slice(0, 280)) + ((m.body || '').length > 280 ? ' …' : '') + '</span></div>' +
          '<div class="row wrap" style="gap:8px"><label class="sr" for="as-' + m.id + '">Anfrage</label><select id="as-' + m.id + '" class="input" style="width:240px;height:36px">' + opts + '</select>' +
          '<button class="btn sm p" data-act="assign" data-id="' + m.id + '">Zuordnen</button><button class="btn sm ghost" data-act="assign-ignore" data-id="' + m.id + '">Ignorieren</button></div></li>';
      }).join('') + '</ul></section>';
  }
  ACT.assign = function (el) {
    var ref = document.getElementById('as-' + el.dataset.id).value;
    if (!ref) { toast('Bitte eine Anfrage wählen.', true); return; }
    busy(el, true);
    api('/api/inbox/' + el.dataset.id + '/assign', { body: { ref: ref } }).then(function () { toast('Zugeordnet'); return refreshData(); })
      .then(render).catch(function (e) { busy(el, false); fail(e); });
  };
  ACT['assign-ignore'] = function (el) {
    api('/api/inbox/' + el.dataset.id + '/assign', { body: { ref: null } }).then(function () { toast('Ignoriert'); return refreshData(); })
      .then(render).catch(fail);
  };
  ACT['inbox-sel'] = function (el) { S.ui.inboxSel = +el.dataset.id; S.ui.fullText = false; render(); };
  ACT['toggle-full'] = function () { S.ui.fullText = !S.ui.fullText; render(); };
  ACT['goto-req'] = function (el) { S.ui.reqSel = el.dataset.ref; S.ui.reqFilter = 'all'; go('#/anfragen'); };
  ACT['inbox-confirm'] = function (el) {
    var id = +el.dataset.id;
    var item = (S.inbox || []).filter(function (i) { return i.id === id; })[0];
    var cat = S.ui.inboxCat[id] || (item && item.category);
    busy(el, true);
    api('/api/inbox/' + id + '/confirm', { body: { category: cat } }).then(function (d) {
      var msg = { done: 'Erledigt', erasure_sent: 'Löschung angefordert', id_reply_sent: 'Antwort gesendet', clarify_sent: 'Antwort gesendet',
        webform: 'Als „Formular offen“ markiert', complaint: 'Beschwerde-Text vorbereitet', confirmed: 'Vermerkt, Frist läuft weiter',
        waiting: 'Spurlos wartet weiter auf eine Antwort' }[d.next] || 'Übernommen';
      toast(msg);
      S.ui.inboxSel = null;
      return refreshData();
    }).then(render).catch(function (e) { busy(el, false); fail(e); });
  };

  // ------------------------------------------------------------------ Anfragen
  var FILTERS = [['all', 'Alle', '#0E1116'], ['todo', 'Zu tun', '#E07B24'], ['wait', 'Wartet', '#3E6FE8'], ['overdue', 'Überfällig', '#C93A3A'],
    ['done', 'Erledigt', '#1F8A5B'], ['planned', 'Geplant', '#9AA1AD'], ['missing', 'Kontakt fehlt', '#C9CED6']];
  function renderRequests() {
    var rows = S.requests;
    var top = head((S.overview ? S.overview.total + ' Firmen · ' + S.overview.sent + ' angeschrieben' : ''), 'Anfragen',
      '<div style="position:relative" class="row"><label for="q" class="sr">Firma oder Aktenzeichen suchen</label><input id="q" class="input" style="width:240px" type="search" placeholder="Firma oder Aktenzeichen" data-ui="reqSearch" data-rerender="1" value="' + esc(S.ui.reqSearch) + '"></div>' +
      '<button class="btn" data-act="send-batch">' + I.send + '<span>Etappe jetzt senden</span></button>');
    if (!rows) return top + '<div class="empty"><span class="spin"></span></div>';
    var counts = { all: rows.length };
    rows.forEach(function (r) { counts[r.group] = (counts[r.group] || 0) + 1; });
    var chips = '<div class="chips" role="group" aria-label="Nach Status filtern">' + FILTERS.map(function (f) {
      var on = S.ui.reqFilter === f[0];
      return '<button class="chip ' + (on ? 'on' : '') + '" aria-pressed="' + on + '" data-act="req-filter" data-f="' + f[0] + '"><span class="d" style="background:' + (on && f[0] === 'all' ? '#3DDCBF' : f[2]) + '"></span>' + f[1] + '<span class="n">' + (counts[f[0]] || 0) + '</span></button>';
    }).join('') + '</div>';
    var q = (S.ui.reqSearch || '').toLowerCase();
    var vis = rows.filter(function (r) {
      return (S.ui.reqFilter === 'all' || r.group === S.ui.reqFilter) &&
        (!q || (r.broker_name + ' ' + r.ref).toLowerCase().indexOf(q) >= 0);
    });
    var cols = 'grid-template-columns:minmax(150px,2fr) minmax(130px,1.4fr) 76px 54px 54px;min-width:560px';
    var list = vis.map(function (r) {
      var overdue = r.group === 'overdue';
      return '<div class="trow ' + (r.ref === S.ui.reqSel ? 'sel' : '') + '" style="' + cols + '"><div class="stack" style="gap:2px;min-width:0"><button class="name" data-act="req-sel" data-ref="' + esc(r.ref) + '">' + esc(r.broker_name) + '</button><span class="tiny muted"><span class="mono">' + esc(r.ref) + '</span> · ' + esc(r.category || groupLabel(r.grp)) + '</span></div>' +
        '<span>' + pill(r.group, r.label) + '</span><span class="small" style="color:var(--ink-2)">' + esc({ email: 'E-Mail', webform: 'Webformular', letter: 'Brief', none: '–' }[r.channel] || r.channel) + '</span>' +
        '<span class="mono tiny" style="color:var(--ink-2)">' + (r.sent_at ? fmtDay(r.sent_at) : r.planned_for ? fmtDay(r.planned_for) : '–') + '</span>' +
        '<span class="mono tiny" style="color:' + (overdue ? '#B91C1C' : 'var(--ink-2)') + ';font-weight:' + (overdue ? 600 : 400) + '">' + (r.due_at && r.group !== 'done' ? fmtDay(r.due_at) : '–') + '</span></div>';
    }).join('') || '<div class="empty">Keine Anfragen mit diesem Status.</div>';
    var table = '<section class="card table-card" style="flex:3 1 560px"><div class="table-scroll"><div class="trow head" style="' + cols + '"><span>Firma</span><span>Status</span><span>Kanal</span><span>Gesendet</span><span>Frist</span></div>' + list + '</div>' +
      '<div class="table-foot"><span>' + vis.length + ' von ' + rows.length + ' angezeigt</span></div></section>';
    var detail = renderReqDetail();
    if (!rows.length) {
      return top + '<div class="card empty"><b>Noch keine Anfragen.</b><span>Schließe die Einrichtung ab und starte die Anfragen.</span><a class="btn p" href="#/einrichtung/5">Zur Einrichtung</a></div>';
    }
    return top + chips + '<div class="split" style="align-items:flex-start">' + table + '<aside class="card" style="flex:1 1 320px" aria-label="Details">' + detail + '</aside></div>';
  }
  function renderReqDetail() {
    var d = S.reqDetail;
    if (!S.ui.reqSel) return '<div class="empty" style="padding:24px 0"><span>Wähle links eine Firma aus.</span></div>';
    if (!d || d.request.ref !== S.ui.reqSel) return '<div class="empty"><span class="spin"></span></div>';
    var r = d.request, b = d.broker;
    var ev = d.events.filter(function (e) { return e.kind !== 'created'; }).map(function (e) {
      return '<li><div class="rail"><i></i><b></b></div><div class="tx" style="padding-bottom:12px"><span class="when">' + fmtWhen(e.at) + '</span><span class="small">' + esc(e.text) + '</span></div></li>';
    }).join('') || '<li class="small muted">Noch nichts passiert.</li>';
    var contact = b.email ? '<span class="mono small" style="word-break:break-all">' + esc(b.email) + '</span>' : b.webform ? '<a href="' + url(b.webform) + '" target="_blank" rel="noopener">Webformular ' + I.ext + '</a>' : '<span class="small" style="color:#9A3412">fehlt</span>';
    var acts = [];
    var st = r.status;
    function btn(label, act, primary) { return '<button class="btn sm ' + (primary ? 'p' : '') + '" data-act="' + act + '" data-ref="' + esc(r.ref) + '">' + label + '</button>'; }
    if (st === 'planned') { acts.push(btn('Jetzt senden', 'req-send', true), btn('Text ansehen', 'req-preview'), btn('Auslassen', 'req-skip')); }
    if (st === 'sent' || st === 'ack' || st === 'followup') { acts.push(btn('Jetzt erinnern', 'req-remind'), btn('Gesendete Anfrage', 'req-preview'), btn('Als erledigt markieren', 'req-done')); }
    if (st === 'overdue' || st === 'reminded') { acts.push(btn('Beschwerde-Text', 'req-complaint', true), btn('Jetzt erinnern', 'req-remind'), btn('Als erledigt markieren', 'req-done')); }
    if (st === 'complaint') { acts.push(btn('Beschwerde-Text', 'req-complaint', true), btn('Als erledigt markieren', 'req-done')); }
    if (st === 'review') { acts.push('<a class="btn sm p" href="#/eingang">Im Eingang ansehen</a>', btn('Als erledigt markieren', 'req-done')); }
    if (st === 'webform') {
      if (b.webform) acts.push('<a class="btn sm p" href="' + url(b.webform) + '" target="_blank" rel="noopener">Formular öffnen ' + I.ext + '</a>');
      acts.push(btn('Text zum Einfügen', 'req-preview'), btn('Formular abgeschickt', 'req-webform-sent'));
    }
    if (st === 'failed') { acts.push(btn('Kontakt bearbeiten', 'req-edit-broker', true), btn('Erneut senden', 'req-send')); }
    if (st === 'no_contact' || st === 'letter') { acts.push(btn('Kontakt ergänzen', 'req-edit-broker', true), btn('Auslassen', 'req-skip')); }
    if (st === 'done') { acts.push(btn('Wieder öffnen', 'req-reopen')); }
    return '<div class="stack" style="gap:8px"><div class="row between"><span class="mono small muted">' + esc(r.ref) + '</span>' + pill(r.group, r.label) + '</div><h2 style="font-size:20px">' + esc(b.name) + '</h2>' +
      (b.what ? '<span class="small muted">' + esc(b.what) + '</span>' : '') + '</div>' +
      '<dl style="margin:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 16px">' +
      dl('Art', esc(b.category || groupLabel(b.grp))) + dl('Sprache', langLabel(b.lang)) +
      dl('Gesendet', '<span class="mono">' + (r.sent_at ? fmtDay(r.sent_at) : '–') + '</span>') + dl('Frist', '<span class="mono">' + (r.due_at ? fmtDay(r.due_at) : '–') + '</span>') +
      '<div class="stack" style="grid-column:1/-1;gap:2px"><dt class="label">Kontakt</dt><dd style="margin:0">' + contact + '</dd></div>' +
      (b.source_url ? '<div style="grid-column:1/-1"><dt class="label">Kontaktdaten aus</dt><dd style="margin:0" class="small"><a href="' + url(b.source_url) + '" target="_blank" rel="noopener">' + esc(sourceName(b)) + ' ' + I.ext + '</a></dd></div>' : '') +
      '</dl><div class="stack" style="gap:10px"><span class="label">Verlauf</span><ol class="timeline">' + ev + '</ol></div>' +
      '<div class="row wrap" style="padding-top:14px;border-top:1px solid var(--line-3)">' + acts.join('') + '</div>';
  }
  function dl(k, v) { return '<div class="stack" style="gap:2px"><dt class="label">' + k + '</dt><dd style="margin:0" class="small">' + v + '</dd></div>'; }
  function sourceName(b) {
    return { datenanfragen: 'datenanfragen.de', incogni: 'Incogni-Liste', kalifornien: 'Register Kalifornien', recherche: 'Datenschutzseite der Firma', eigene: 'Eigene Angabe' }[b.origin] || 'Quelle';
  }
  ACT['req-filter'] = function (el) { S.ui.reqFilter = el.dataset.f; render(); };
  ACT['req-sel'] = function (el) { selectReq(el.dataset.ref); };
  function selectReq(ref) {
    S.ui.reqSel = ref; S.reqDetail = null; render();
    api('/api/requests/' + encodeURIComponent(ref)).then(function (d) { S.reqDetail = d; render(); }).catch(fail);
  }
  function reqAction(el, action, data, msg) {
    busy(el, true);
    return api('/api/requests/' + encodeURIComponent(el.dataset.ref) + '/action', { body: { action: action, data: data || {} } })
      .then(function () { toast(msg); return Promise.all([refreshData(), api('/api/requests/' + encodeURIComponent(el.dataset.ref)).then(function (d) { S.reqDetail = d; }).catch(function () { S.ui.reqSel = null; })]); })
      .then(render).catch(function (e) { busy(el, false); fail(e); });
  }
  ACT['req-send'] = function (el) { reqAction(el, 'send_now', {}, 'Anfrage gesendet'); };
  ACT['req-remind'] = function (el) { reqAction(el, 'remind', {}, 'Erinnerung gesendet'); };
  ACT['req-done'] = function (el) { reqAction(el, 'done', {}, 'Als erledigt markiert'); };
  ACT['req-reopen'] = function (el) { reqAction(el, 'reopen', {}, 'Wieder geöffnet'); };
  ACT['req-webform-sent'] = function (el) { reqAction(el, 'webform_sent', {}, 'Frist läuft ab heute'); };
  ACT['req-skip'] = function (el) { if (confirm('Diese Firma auslassen? Du kannst sie in der Händlerliste wieder einschalten.')) reqAction(el, 'skip', {}, 'Ausgelassen'); };
  ACT['req-preview'] = function (el) {
    api('/api/requests/' + encodeURIComponent(el.dataset.ref) + '/preview').then(function (d) {
      textModal(d.sent ? 'Gesendete Anfrage' : 'Text der Anfrage', 'An: ' + d.to, d.subject, d.body);
    }).catch(fail);
  };
  ACT['req-complaint'] = function (el) {
    api('/api/requests/' + encodeURIComponent(el.dataset.ref) + '/complaint').then(function (d) {
      var a = d.authority;
      var extra;
      if (a) {
        var how = [];
        if (a.webform) how.push('<a href="' + url(a.webform) + '" target="_blank" rel="noopener">Online-Formular ' + I.ext + '</a>');
        if (a.email && !a.form_preferred) how.push('E-Mail: <span class="mono">' + esc(a.email) + '</span>');
        if (!a.webform && a.address) how.push('Per Post: ' + esc(a.address.replace(/\n/g, ', ')));
        extra = '<div class="notice ok">' + I.info + '<span>' + (d.authority_note ? esc(d.authority_note) + '<br>' : '') + '<b>' + esc(a.name) + '</b><br>' + how.join(' · ') +
          (a.form_preferred ? '<br><span class="small">Diese Behörde möchte Beschwerden über ihr Online-Formular bekommen. Kopier den Text dort hinein.</span>' : '') +
          '<br><span class="small muted">Häng deine Anfrage und die Erinnerung an. Beides findest du in deinem Gesendet-Ordner.</span></span></div>';
      } else {
        extra = '<div class="notice warn">' + I.warn + '<span>Trag in den Einstellungen unter „Meine Daten“ dein Bundesland ein, dann zeigt Spurlos die zuständige Behörde.</span></div>';
      }
      textModal('Beschwerde an die Datenschutzbehörde', 'Spurlos verschickt die Beschwerde nicht selbst. Du reichst sie bei der Behörde ein.', d.subject, d.body, extra);
    }).catch(fail);
  };
  ACT['req-edit-broker'] = function (el) {
    var d = S.reqDetail;
    if (d) brokerModal(d.broker);
  };
  ACT['send-batch'] = function (el) {
    busy(el, true);
    api('/api/send', { body: {} }).then(function (d) {
      toast(d.sent ? d.sent + ' Anfragen gesendet' : (d.errors && d.errors.length ? d.errors[0] : 'Gerade ist nichts fällig'), !d.sent && d.errors && d.errors.length);
      return refreshData();
    }).then(render).catch(fail).then(function () { busy(el, false); });
  };

  // ------------------------------------------------------------------ Händlerliste
  function renderBrokers() {
    var d = S.brokers;
    var top = head(d ? d.brokers.filter(function (b) { return b.selected; }).length + ' ausgewählt · ' + d.brokers.length + ' Firmen bekannt' + (d.last_update ? ' · zuletzt geprüft ' + fmtWhen(d.last_update, true) : '') : '', 'Händlerliste',
      '<button class="btn" data-act="brokers-update">' + I.refresh + '<span>Liste aktualisieren</span></button><button class="btn p" data-act="broker-add">Firma hinzufügen</button>');
    if (!d) return top + '<div class="empty"><span class="spin"></span></div>';
    var news = d.brokers.filter(function (b) { return b.is_new && b.relevant; });
    var banner = news.length ? '<div class="card" style="background:var(--side);border-color:var(--side);color:#E6E9EE;flex-direction:row;flex-wrap:wrap;align-items:center;gap:14px 20px;padding:16px 20px">' +
      '<span class="tag" style="background:var(--mint);color:var(--ink)">Neu</span><div class="grow stack" style="gap:2px;flex:1 1 320px"><b style="color:#fff">' + news.length + ' neue Firmen auf der Liste</b><span class="small" style="color:var(--side-ink)">' + esc(news.slice(0, 6).map(function (b) { return b.name; }).join(', ')) + '</span></div>' +
      '<button class="btn sm" data-act="brokers-seen" style="background:transparent;color:#E6E9EE;border-color:#2B3240">Gesehen</button></div>' : '';
    var info = d.update && d.update.errors && d.update.errors.length ? '<div class="notice warn">' + I.warn + '<span>Letzte Aktualisierung unvollständig: ' + esc(d.update.errors.join(' · ')) + '</span></div>' : '';
    var groups = S.boot.group_order.map(function (g) {
      var inGroup = d.brokers.filter(function (b) { return b.grp === g && b.relevant; });
      if (!inGroup.length && g !== 'us') return '';
      var on = !!S.boot.groups[g];
      var withMail = inGroup.filter(function (b) { return b.contact === 'email'; }).length;
      var missing = inGroup.filter(function (b) { return b.contact === 'none'; }).length;
      var usHint = g === 'us' && S.boot.countries.indexOf('us') < 0 ? '<span class="tiny muted">Nur wenn du unter „Meine Daten“ USA angibst.</span>' : '';
      return '<div class="group-row"><button class="switch" role="switch" aria-checked="' + on + '" aria-label="' + esc(groupLabel(g)) + '" data-act="toggle-group" data-g="' + g + '"></button>' +
        '<div class="grow stack" style="gap:2px"><b>' + esc(groupLabel(g)) + '</b><span class="small muted">' + esc(S.boot.group_meta[g].sub) + '</span>' + usHint + '</div>' +
        '<span class="mono small muted" style="text-align:right">' + inGroup.length + ' Firmen<br>' + withMail + ' per E-Mail' + (missing ? ' · ' + missing + ' ohne Kontakt' : '') + '</span></div>';
    }).join('');
    var tabs = [['all', 'Alle']].concat(S.boot.group_order.map(function (g) { return [g, groupLabel(g)]; }));
    var views = [['selected', 'Ausgewählt'], ['all', 'Alle bekannten'], ['missing', 'Kontakt fehlt'], ['new', 'Neu']];
    var q = (S.ui.brSearch || '').toLowerCase();
    var rows = d.brokers.filter(function (b) {
      if (S.ui.brTab !== 'all' && b.grp !== S.ui.brTab) return false;
      if (S.ui.brView === 'selected' && !b.selected) return false;
      if (S.ui.brView === 'missing' && b.contact !== 'none') return false;
      if (S.ui.brView === 'new' && !b.is_new) return false;
      return !q || (b.name + ' ' + (b.email || '') + ' ' + (b.category || '')).toLowerCase().indexOf(q) >= 0;
    });
    var cols = 'grid-template-columns:44px minmax(190px,2fr) minmax(120px,1fr) minmax(210px,1.5fr) 64px minmax(140px,1fr) 60px';
    var list = rows.slice(0, 400).map(function (b) {
      var contact = b.contact === 'email' ? '<span class="mono tiny" style="overflow-wrap:anywhere">' + esc(b.email) + '</span>' : b.contact === 'webform' ? '<a class="small" href="' + url(b.webform) + '" target="_blank" rel="noopener">Webformular ' + I.ext + '</a>' : b.contact === 'letter' ? '<span class="small">Nur per Post</span>' : '<span class="small" style="color:#9A3412;font-weight:600">Kontakt fehlt</span>';
      var req = b.request ? pill(b.request.group, b.request.label) : (b.selected ? '<span class="tiny muted">noch nicht angelegt</span>' : '<span class="tiny muted">–</span>');
      return '<div class="trow" style="' + cols + '"><button class="switch" role="switch" aria-checked="' + b.active + '" aria-label="' + esc(b.name) + ' einbeziehen" data-act="broker-active" data-id="' + esc(b.id) + '"></button>' +
        '<div class="stack" style="gap:2px;min-width:0"><div class="row" style="gap:8px"><b>' + esc(b.name) + '</b>' + (b.is_new ? '<span class="tag mint">Neu</span>' : '') + (b.relevant ? '' : '<span class="tag">anderes Land</span>') + '</div><span class="tiny muted">' + esc(b.what || b.category || '') + '</span></div>' +
        '<span class="small" style="color:var(--ink-2)">' + esc(groupLabel(b.grp)) + '</span>' + contact +
        '<span class="small" style="color:var(--ink-2)">' + langLabel(b.lang) + '</span>' + '<span>' + req + '</span>' +
        '<button class="btn ghost sm" data-act="broker-edit" data-id="' + esc(b.id) + '">Ändern</button></div>';
    }).join('') || '<div class="empty">Keine Firmen in dieser Ansicht.</div>';
    return top + banner + info +
      '<section class="card"><div class="stack" style="gap:4px"><h2>Gruppen</h2><p class="small muted" style="margin:0">Welche Arten von Firmen Spurlos anschreibt. Grundlage sind die Länder unter „Meine Daten“: ' + esc(S.boot.countries.map(function (c) { return S.boot.all_countries[c]; }).join(', ')) + '.</p></div>' + groups + '</section>' +
      '<section class="card table-card"><div class="row wrap between" style="padding:12px 16px;border-bottom:1px solid var(--line);gap:10px">' +
      '<div class="chips">' + tabs.map(function (t) { return '<button class="chip ' + (S.ui.brTab === t[0] ? 'on' : '') + '" data-act="br-tab" data-t="' + t[0] + '">' + esc(t[1]) + '</button>'; }).join('') + '</div>' +
      '<div class="row wrap"><select class="input" style="width:auto;height:36px" data-ui="brView" aria-label="Ansicht">' + views.map(function (v) { return '<option value="' + v[0] + '"' + (S.ui.brView === v[0] ? ' selected' : '') + '>' + v[1] + '</option>'; }).join('') + '</select>' +
      '<label for="bq" class="sr">Firma suchen</label><input id="bq" class="input" style="width:200px;height:36px" type="search" placeholder="Suchen" data-ui="brSearch" data-rerender="1" value="' + esc(S.ui.brSearch) + '"></div></div>' +
      '<div class="table-scroll"><div class="trow head" style="' + cols + '"><span></span><span>Firma</span><span>Gruppe</span><span>Kontakt</span><span>Sprache</span><span>Anfrage</span><span></span></div>' + list + '</div>' +
      '<div class="table-foot"><span>' + Math.min(rows.length, 400) + ' von ' + rows.length + ' angezeigt</span><span class="small">Quellen: datenanfragen.de (CC0), Incogni-Liste, Register Kalifornien, eigene Recherche</span></div></section>';
  }
  document.addEventListener('change', function (e) { if (e.target.dataset && e.target.dataset.ui === 'brView') render(); });
  ACT['br-tab'] = function (el) { S.ui.brTab = el.dataset.t; render(); };
  ACT['toggle-group'] = function (el) {
    var g = el.dataset.g; var groups = {}; groups[g] = !S.boot.groups[g];
    api('/api/groups', { body: { groups: groups } }).then(function (d) { S.boot.groups = d.groups; return refreshData(); }).then(render).catch(fail);
  };
  ACT['broker-active'] = function (el) {
    var on = el.getAttribute('aria-checked') !== 'true';
    api('/api/brokers/' + encodeURIComponent(el.dataset.id) + '/active', { body: { active: on } }).then(refreshData).then(render).catch(fail);
  };
  ACT['brokers-seen'] = function () { api('/api/brokers/seen', { body: {} }).then(refreshData).then(render).catch(fail); };
  ACT['brokers-update'] = function (el) {
    busy(el, true);
    api('/api/brokers/update', { body: {} }).then(function (d) {
      var i = d.info || {};
      var added = ((i.datenanfragen || {}).added || 0) + (((i.incogni || {}).added || []).length) + ((i.kalifornien || {}).added || 0);
      toast(i.errors && i.errors.length ? 'Teilweise aktualisiert: ' + i.errors[0] : 'Liste aktualisiert, ' + added + ' neue Firmen', i.errors && i.errors.length);
      return refreshData();
    }).then(render).catch(fail).then(function () { busy(el, false); });
  };
  ACT['broker-add'] = function () { brokerModal({}); };
  ACT['broker-edit'] = function (el) {
    var b = S.brokers.brokers.filter(function (x) { return x.id === el.dataset.id; })[0];
    if (b) brokerModal(b);
  };
  function brokerModal(b) {
    var groups = S.boot.group_order.map(function (g) { return '<option value="' + g + '"' + ((b.grp || 'consumer') === g ? ' selected' : '') + '>' + esc(groupLabel(g)) + '</option>'; }).join('');
    openModal('<div class="row between"><h2>' + (b.id ? 'Firma ändern' : 'Firma hinzufügen') + '</h2><button class="btn sm" data-act="close-modal">Abbrechen</button></div>' +
      (b.source_url ? '<p class="small muted" style="margin:0">Quelle: <a href="' + url(b.source_url) + '" target="_blank" rel="noopener">' + esc(sourceName(b)) + '</a>. Deine Änderung gilt ab jetzt und wird bei Aktualisierungen nicht überschrieben.</p>' : '') +
      '<div class="form-grid"><div class="field"><label for="bn">Name</label><input id="bn" class="input" value="' + esc(b.name || '') + '"></div>' +
      '<div class="field"><label for="be">Datenschutz-E-Mail</label><input id="be" class="input" type="email" value="' + esc(b.email || '') + '" placeholder="datenschutz@firma.de"></div>' +
      '<div class="field"><label for="bw">Webformular (optional)</label><input id="bw" class="input" type="url" value="' + esc(b.webform || '') + '" placeholder="https://"></div>' +
      '<div class="field"><label for="bg">Gruppe</label><select id="bg" class="input">' + groups + '</select></div>' +
      '<div class="field"><label for="bl">Sprache der Anfrage</label><select id="bl" class="input"><option value="de"' + (b.lang === 'de' ? ' selected' : '') + '>Deutsch (DSGVO)</option><option value="ch"' + (b.lang === 'ch' ? ' selected' : '') + '>Deutsch (Schweizer Recht)</option><option value="en"' + (b.lang !== 'de' && b.lang !== 'ch' ? ' selected' : '') + '>Englisch (DSGVO)</option></select></div></div>' +
      '<label class="check"><input id="bwo" type="checkbox"' + (b.webform_only ? ' checked' : '') + '> Nimmt Anfragen nur über das Webformular an</label>' +
      '<div class="row"><button class="btn p" data-act="broker-save" data-id="' + esc(b.id || '') + '">Speichern</button></div>');
  }
  ACT['broker-save'] = function (el) {
    var body = { id: el.dataset.id || null, name: document.getElementById('bn').value, email: document.getElementById('be').value,
      webform: document.getElementById('bw').value, grp: document.getElementById('bg').value, lang: document.getElementById('bl').value,
      webform_only: document.getElementById('bwo').checked };
    api('/api/brokers', { body: body }).then(function () {
      closeModal(); toast('Gespeichert');
      var p = [refreshData()];
      if (S.ui.reqSel) p.push(api('/api/requests/' + encodeURIComponent(S.ui.reqSel)).then(function (d) { S.reqDetail = d; }));
      return Promise.all(p);
    }).then(render).catch(fail);
  };

  // ------------------------------------------------------------------ Formulare (Daten, Postfach, KI)
  function profileForm() {
    var p = S.draft.profile;
    function rep(list, fields, addLabel) {
      var rows = p[list].map(function (row, i) {
        return '<div class="repeat-row" style="align-items:flex-end">' + fields.map(function (f) {
          var id = list + '-' + i + '-' + f.k;
          var top = i === 0 && f.type !== 'check' ? '<label class="lbl" for="' + id + '" style="font-size:12px;color:var(--muted);font-weight:500">' + f.label + '</label>' : '<label class="sr" for="' + id + '">' + f.label + '</label>';
          if (f.type === 'check') return '<label class="check" style="height:44px"><input id="' + id + '" type="checkbox" data-list="' + list + '" data-i="' + i + '" data-k="' + f.k + '"' + (row[f.k] ? ' checked' : '') + '>' + f.label + '</label>';
          return '<div class="stack" style="gap:4px;flex:' + (f.w ? '0 1 ' + f.w : '1 1 200px') + ';min-width:' + (f.w ? '90px' : '160px') + '">' + top + '<input id="' + id + '" class="input' + (f.mono ? ' mono' : '') + '" placeholder="' + esc(f.ph || '') + '" data-list="' + list + '" data-i="' + i + '" data-k="' + f.k + '" value="' + esc(row[f.k] || '') + '"' + (f.type ? ' type="' + f.type + '"' : '') + (f.mode ? ' inputmode="' + f.mode + '"' : '') + '></div>';
        }).join('') + '<button class="iconbtn" aria-label="Zeile entfernen" data-act="del-row" data-list="' + list + '" data-i="' + i + '">' + I.trash + '</button></div>';
      }).join('');
      return '<div class="repeat">' + rows + '<div><button class="btn sm" data-act="add-row" data-list="' + list + '">+ ' + addLabel + '</button></div></div>';
    }
    var names = S.boot.all_countries;
    var order = ['de', 'at', 'ch'].concat(Object.keys(names).filter(function (c) { return ['de', 'at', 'ch', 'us'].indexOf(c) < 0; })
      .sort(function (a, b) { return names[a].localeCompare(names[b], 'de'); }), ['us']);
    var countries = order.filter(function (c) { return names[c]; }).map(function (c) {
      var on = S.draft.countries.indexOf(c) >= 0;
      return '<button class="chip ' + (on ? 'on' : '') + '" aria-pressed="' + on + '" data-act="toggle-country" data-c="' + c + '">' + esc(S.boot.all_countries[c]) + '</button>';
    }).join('');
    function tip(id, label, html, cls) {
      return '<span class="tipw"><button type="button" class="tipbtn" aria-label="' + label + '" aria-describedby="' + id + '"><span aria-hidden="true">?</span></button><span role="tooltip" id="' + id + '" class="tip' + (cls ? ' ' + cls : '') + '">' + html + '</span></span>';
    }
    function head(title, tipHtml, tipId, hint) {
      return '<div class="stack" style="gap:2px"><div class="row" style="gap:2px"><h3>' + title + '</h3>' + (tipHtml ? tip(tipId, 'Warum fragt Spurlos das?', tipHtml, 'start') : '') + '</div>' + (hint ? '<span class="hint">' + hint + '</span>' : '') + '</div>';
    }
    var states = '<option value="">Bitte wählen</option>' + S.boot.states.map(function (s) { return '<option' + (S.draft.state === s ? ' selected' : '') + '>' + esc(s) + '</option>'; }).join('');
    return '<div class="card"><h3>Name</h3><div class="form-grid">' +
      '<div class="field"><label for="fn">Vorname</label><input id="fn" class="input" data-p="first_name" value="' + esc(p.first_name) + '" autocomplete="given-name"></div>' +
      '<div class="field"><label for="ln">Nachname</label><input id="ln" class="input" data-p="last_name" value="' + esc(p.last_name) + '" autocomplete="family-name"></div>' +
      '<div class="field"><label for="former">Frühere Namen (optional)</label><input id="former" class="input" data-act-none="1" value="' + esc((p.former_names || []).join(', ')) + '" placeholder="z. B. Geburtsname"></div></div></div>' +
      '<div class="card"><div class="stack" style="gap:2px"><h3>Adressen</h3><span class="hint">Deine jetzige Adresse und frühere, etwa der letzten zehn Jahre. Adresshändler speichern auch alte Adressen. Wann du wo gewohnt hast, brauchen die Firmen nicht. Setz nur bei der jetzigen Adresse den Haken „wohne ich jetzt“.</span></div>' +
      rep('addresses', [{ k: 'street', label: 'Straße und Hausnummer', ph: 'Musterstraße 1' }, { k: 'zip', label: 'PLZ', ph: '12345', w: '110px', mode: 'numeric' }, { k: 'city', label: 'Ort', ph: 'Musterstadt', w: '240px' }, { k: 'current', label: 'wohne ich jetzt', type: 'check' }], 'Adresse') + '</div>' +
      '<div class="card"><div class="stack" style="gap:2px"><h3>E-Mail-Adressen</h3><span class="hint">Alle Adressen, die du je benutzt hast, auch alte und geschäftliche, z. B. von früheren Arbeitgebern. Bitte genau prüfen: Die Firmen suchen nach exakt dieser Schreibweise. Gmail und Googlemail sind dasselbe Postfach, eine Schreibweise reicht. Spurlos nennt den Firmen automatisch beide.</span></div>' +
      rep('emails', [{ k: 'address', label: 'E-Mail-Adresse', ph: 'name@beispiel.de', mono: true, type: 'email' }], 'E-Mail-Adresse') + '</div>' +
      '<div class="card"><div class="stack" style="gap:2px"><h3>Telefonnummern</h3><span class="hint">Mobil und Festnetz, auch alte Nummern. Am besten mit Ländervorwahl, z. B. +49 174 1234567. Spurlos nennt den Firmen beide Schreibweisen (+49 … und 0…), weil sie Nummern unterschiedlich speichern.</span></div>' +
      rep('phones', [{ k: 'number', label: 'Telefonnummer', ph: '+49 174 1234567', mono: true, type: 'tel' }, { k: 'label', label: 'Art', ph: 'Mobil', w: '160px' }], 'Nummer') + '</div>' +
      '<div class="card">' + head('Eigene Firmen (optional)', '<strong>Warum eigene Firmen?</strong>Händler für Firmenadressen sammeln Firmendaten aus Impressum, Handelsregister und Branchenbüchern und verkaufen sie für Werbung. Manche führen dich dort nur unter dem Firmennamen. Bei Einzelunternehmen und GbR sind die Firmendaten zugleich deine eigenen Daten. Bei GmbH oder UG gehören sie der Firma, aber dein Name und deine Kontaktdaten als Geschäftsführer sind deine Daten. In beiden Fällen hilft der Firmenname, deinen Eintrag zu finden.', 'tip-job',
        'Firmen, die dir gehören oder gehört haben oder die du als Geschäftsführer geleitet hast, egal in welcher Rechtsform. Frühere Arbeitgeber musst du nicht angeben: Dafür reichen deine alten Arbeits-E-Mail-Adressen oben.') +
      rep('companies', [{ k: 'name', label: 'Firmenname', ph: 'z. B. Mustermann Media' }], 'Firma') + '</div>' +
      '<div class="card">' + head('Eigene Webseiten (optional)', '<strong>Warum Webseiten?</strong>Wer eine Webseite hat, steht mit Name und Anschrift im Impressum, oft auch in der Domain-Registrierung. Firmen, die solche Daten sammeln, finden dich über die Adresse der Seite.', 'tip-web',
        'Webseiten, die dir gehören oder gehört haben, privat oder für deine Firma.') +
      rep('websites', [{ k: 'url', label: 'Webseite', ph: 'meinname.de', mono: true }], 'Webseite') + '</div>' +
      '<div class="card"><div class="stack" style="gap:2px"><h3>Länder</h3><span class="hint">In welchen Ländern hast du gewohnt, gearbeitet oder ein Konto gehabt? Auch wenn du dort nur arbeitest. Danach richtet sich die Firmenliste.</span></div><div class="chips">' + countries + '</div>' +
      '<div class="field" style="max-width:420px"><div class="row" style="gap:2px"><label for="state">Dein Bundesland</label>' +
      tip('tip-state', 'Wofür braucht Spurlos das Bundesland?', '<strong>Nur für den Notfall</strong>Antwortet eine Firma trotz Erinnerung nicht, kannst du dich kostenlos bei einer Datenschutzbehörde beschweren. Die Behörde kann die Firma zur Antwort zwingen. Spurlos schreibt dir den Text. Sitzt die Firma im Ausland, ist die Behörde deines Bundeslands zuständig.', 'start') +
      '</div><select id="state" class="input" data-state="1">' + states + '</select><span class="hint">Nur für eine Beschwerde, falls eine Firma nicht antwortet.</span></div></div>';
  }
  document.addEventListener('input', function (e) {
    if (e.target.id === 'former' && S.draft) {
      S.draft.profile.former_names = e.target.value.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    }
  });
  ACT['add-row'] = function (el) {
    var list = el.dataset.list;
    var tmpl = { addresses: { street: '', zip: '', city: '', current: false }, emails: { address: '' },
      phones: { number: '', label: '' }, companies: { name: '' }, websites: { url: '' } }[list];
    S.draft.profile[list].push(tmpl); render();
  };
  ACT['del-row'] = function (el) { S.draft.profile[el.dataset.list].splice(+el.dataset.i, 1); render(); };
  ACT['toggle-country'] = function (el) {
    var c = el.dataset.c; var i = S.draft.countries.indexOf(c);
    if (i >= 0) S.draft.countries.splice(i, 1); else S.draft.countries.push(c);
    render();
  };
  function cleanProfile() {
    var p = JSON.parse(JSON.stringify(S.draft.profile));
    p.addresses = p.addresses.filter(function (a) { return (a.street || a.city || a.zip || a.text || '').trim(); })
      .map(function (a) { if (a.street || a.city) delete a.text; return a; });
    p.emails = p.emails.filter(function (a) { return (a.address || '').trim(); }).map(function (a) { a.address = a.address.trim(); return a; });
    p.phones = p.phones.filter(function (a) { return (a.number || '').trim(); });
    p.companies = p.companies.filter(function (a) { return (a.name || a.text || '').trim(); }).map(function (a) { return { name: (a.name || a.text || '').trim() }; });
    p.websites = p.websites.filter(function (a) { return (a.url || '').trim(); }).map(function (a) { return { url: a.url.trim() }; });
    return p;
  }
  function saveProfile() {
    var p = cleanProfile();
    if (!(p.first_name || '').trim() || !(p.last_name || '').trim()) return Promise.reject(new Error('Bitte Vor- und Nachnamen eintragen.'));
    if (!p.addresses.length && !p.emails.length) return Promise.reject(new Error('Bitte mindestens eine Adresse oder E-Mail-Adresse eintragen.'));
    if (!S.draft.countries.length) S.draft.countries = ['de'];
    return api('/api/profile', { body: { profile: p, state: S.draft.state, countries: S.draft.countries } }).then(function () {
      S.boot.profile = p; S.boot.state = S.draft.state; S.boot.countries = S.draft.countries.slice();
    });
  }

  var PROV = {
    domain: { name: 'Eigene Domain', sub: 'z. B. all-inkl, Strato, IONOS', tag: 'Empfohlen', open: '', pw: 'Passwort', ph: 'dsgvo@deine-domain.de',
      steps: ['Im Kundenmenü deines Anbieters ein neues Postfach anlegen, zum Beispiel dsgvo@deine-domain.de.', 'Adresse und Passwort unten eintragen.', 'Mit „Serverdaten suchen“ findet Spurlos die Server meist selbst. Sonst stehen sie im Kundenmenü deines Anbieters.'],
      note: 'Kostet nichts extra, wenn dein Hosting-Tarif Postfächer enthält. Die Mails liegen dann bei deinem eigenen Anbieter.' },
    gmx: { name: 'GMX', sub: 'Kostenlos · Server in Deutschland', open: 'https://www.gmx.net/', pw: 'Passwort', ph: 'name@gmx.de',
      steps: ['Kostenloses GMX-Postfach anlegen.', 'In GMX unter Einstellungen › POP3/IMAP Abruf das Häkchen bei „POP3 und IMAP Zugriff erlauben“ setzen und speichern.', 'Adresse und Passwort unten eintragen.'],
      note: 'GMX schaltet diesen Zugriff nach längerer Pause wieder ab. Spurlos merkt das und sagt dir Bescheid.' },
    webde: { name: 'WEB.DE', sub: 'Kostenlos · Server in Deutschland', open: 'https://web.de/', pw: 'Passwort', ph: 'name@web.de',
      steps: ['Kostenloses WEB.DE-Postfach anlegen.', 'In WEB.DE in den E-Mail-Einstellungen den Abruf über POP3 und IMAP einschalten.', 'Adresse und Passwort unten eintragen.'],
      note: 'WEB.DE schaltet diesen Zugriff nach längerer Pause wieder ab. Spurlos merkt das und sagt dir Bescheid.' },
    icloud: { name: 'iCloud Mail', sub: 'Kostenlos · für Mac-Nutzer', open: 'https://www.icloud.com/mail', pw: 'App-spezifisches Passwort', ph: 'name@icloud.com',
      steps: ['Auf icloud.com/mail eine zusätzliche Adresse (Alias) anlegen oder deine iCloud-Adresse nutzen.', 'Unter account.apple.com › Anmelden und Sicherheit › App-spezifische Passwörter ein Passwort für Spurlos erstellen.', 'Adresse und App-Passwort unten eintragen.'],
      note: 'Das App-Passwort gilt nur für Spurlos. Du kannst es jederzeit wieder löschen.' },
    gmail: { name: 'Gmail', sub: 'Kostenlos · Daten liegen bei Google', open: 'https://accounts.google.com/signup', pw: 'App-Passwort', ph: 'name@gmail.com',
      steps: ['Kostenloses Google-Konto anlegen.', 'Im Google-Konto unter Sicherheit die Bestätigung in zwei Schritten einschalten.', 'Unter Sicherheit › App-Passwörter ein Passwort für Spurlos erstellen.', 'Adresse und App-Passwort unten eintragen.'],
      note: 'Funktioniert gut. Deine ganze Korrespondenz mit den Datenhändlern liegt dann aber bei Google.' }
  };
  function mailboxForm() {
    var m = S.draft.mailbox;
    var cur = m.provider || 'domain';
    var tiles = Object.keys(PROV).map(function (k) {
      var p = PROV[k]; var on = k === cur;
      return '<button class="tile ' + (on ? 'on' : '') + '" role="radio" aria-checked="' + on + '" data-act="pick-provider" data-p="' + k + '"><div class="row between" style="width:100%;align-items:flex-start"><b style="font-size:15px">' + esc(p.name) + '</b><span class="radio"></span></div>' +
        '<div class="stack" style="gap:6px;align-items:flex-start">' + (p.tag ? '<span class="tag mint">' + p.tag + '</span>' : '') + '<span class="tiny muted">' + esc(p.sub) + '</span></div></button>';
    }).join('');
    var p = PROV[cur];
    var steps = p.steps.map(function (s, i) { return '<li><span class="k">' + (i + 1) + '</span><span>' + esc(s) + '</span></li>'; }).join('');
    var servers = '';
    if (cur === 'domain' || m._showServers) {
      servers = '<div class="form-grid" style="padding-top:16px;border-top:1px solid var(--line-3)">' +
        '<div class="field"><label for="ih">Posteingang (IMAP)</label><input id="ih" class="input mono" data-m="imap_host" value="' + esc(m.imap_host) + '" placeholder="imap.deine-domain.de"></div>' +
        '<div class="field"><label for="ip">Port</label><input id="ip" class="input mono" data-m="imap_port" value="' + esc(m.imap_port) + '"></div>' +
        '<div class="field"><label for="sh">Postausgang (SMTP)</label><input id="sh" class="input mono" data-m="smtp_host" value="' + esc(m.smtp_host) + '" placeholder="smtp.deine-domain.de"></div>' +
        '<div class="field"><label for="sp">Port</label><input id="sp" class="input mono" data-m="smtp_port" value="' + esc(m.smtp_port) + '"></div>' +
        '<div class="field"><label for="ss">Verschlüsselung Postausgang</label><select id="ss" class="input" data-m="smtp_security"><option value="starttls"' + (m.smtp_security !== 'ssl' ? ' selected' : '') + '>STARTTLS (meist Port 587)</option><option value="ssl"' + (m.smtp_security === 'ssl' ? ' selected' : '') + '>SSL/TLS (meist Port 465)</option></select></div>' +
        '<div class="field"><label for="un">Benutzername (falls anders als die Adresse)</label><input id="un" class="input mono" data-m="username" value="' + esc(m.username && m.username !== m.address ? m.username : '') + '"></div></div>' +
        '<div class="row"><button class="btn sm" data-act="detect-servers">Serverdaten suchen</button>' + (m._detected ? '<span class="small muted">' + esc(m._detected) + '</span>' : '') + '</div>';
    }
    return '<div role="radiogroup" aria-label="Anbieter" class="tiles">' + tiles + '</div>' +
      '<section class="card"><div class="row wrap between"><h2 style="font-size:17px">So geht\'s mit ' + esc(p.name) + '</h2>' + (p.open ? '<a class="btn sm" href="' + esc(p.open) + '" target="_blank" rel="noopener">' + I.ext + '<span>Anbieter öffnen</span></a>' : '') + '</div>' +
      '<ol class="ol">' + steps + '</ol><div class="notice">' + I.info + '<span>' + esc(p.note) + '</span></div>' +
      '<div class="form-grid" style="padding-top:16px;border-top:1px solid var(--line-3)">' +
      '<div class="field"><label for="ma">E-Mail-Adresse</label><input id="ma" class="input" type="email" data-m="address" value="' + esc(m.address) + '" placeholder="' + esc(p.ph) + '" autocomplete="off"></div>' +
      '<div class="field"><label for="mp">' + esc(p.pw) + '</label><input id="mp" class="input" type="password" data-pw="1" value="' + esc(S.draft.password || '') + '" placeholder="' + (S.boot.mailbox.has_password ? 'gespeichert – nur zum Ändern eintragen' : '••••••••••••') + '" autocomplete="new-password"></div>' +
      '<div class="field"><label for="md">Absendername</label><input id="md" class="input" data-m="display_name" value="' + esc(m.display_name || ((S.draft.profile.first_name || '') + ' ' + (S.draft.profile.last_name || '')).trim()) + '"></div></div>' +
      '<span class="row tiny muted" style="gap:4px">' + I.lock + '<span>Dein Passwort wird verschlüsselt im Schlüsselbund deines Macs gespeichert. Nur Spurlos kann diesen einen Eintrag lesen, nicht deine anderen Passwörter.' + (S.boot.secret_storage !== 'Schlüsselbund' ? ' (Hier: ' + esc(S.boot.secret_storage) + ')' : '') + '</span>' +
        '<span class="tipw"><button type="button" class="tipbtn" aria-label="Mehr zum Schlüsselbund" aria-describedby="tip-keychain"><span aria-hidden="true">?</span></button><span role="tooltip" id="tip-keychain" class="tip end"><strong>Warum der Schlüsselbund?</strong>Spurlos meldet sich regelmäßig bei deinem Postfach an und braucht dafür das Passwort. Im Schlüsselbund ist es sicherer als in einer Datei: Andere Programme kommen nur mit deiner Erlaubnis heran. Fragt macOS einmal, ob Spurlos auf den Eintrag „Spurlos“ zugreifen darf, klick auf „Immer erlauben“. Es geht nur um diesen einen Eintrag, nicht um deinen ganzen Schlüsselbund.</span></span></span>' + servers + '</section>' +
      '<span class="tipw"><button class="btn ghost sm" style="color:var(--muted)" aria-describedby="tip-prov">Warum nicht Proton, Tuta oder Outlook.com? <span class="mono">(?)</span></button><span role="tooltip" id="tip-prov" class="tip">Spurlos braucht den normalen Zugang zum Postfach, den jedes Mailprogramm nutzt. Proton erlaubt das nur im Bezahltarif, Tuta gar nicht, und Outlook.com schafft diesen Zugang gerade ab.</span></span>';
  }
  ACT['pick-provider'] = function (el) {
    var k = el.dataset.p;
    S.draft.mailbox.provider = k;
    if (k !== 'domain') {
      api('/api/mailbox/detect', { body: { provider: k } }).then(function (d) {
        Object.assign(S.draft.mailbox, d.servers); delete S.draft.mailbox.label; S.draft.mailbox.provider = k; render();
      }).catch(fail);
    }
    render();
  };
  ACT['detect-servers'] = function (el) {
    var m = S.draft.mailbox;
    if (!m.address || m.address.indexOf('@') < 0) { toast('Bitte zuerst die E-Mail-Adresse eintragen.', true); return; }
    busy(el, true);
    api('/api/mailbox/detect', { body: { provider: 'domain', address: m.address } }).then(function (d) {
      var s = d.servers;
      ['imap_host', 'imap_port', 'smtp_host', 'smtp_port', 'smtp_security'].forEach(function (k) { if (s[k]) m[k] = s[k]; });
      if (s.username) m.username = s.username;
      if (s.provider) m.provider = s.provider;
      m._detected = s.guessed ? 'Nicht gefunden – das sind nur Vermutungen. Bitte im Kundenmenü deines Anbieters prüfen.' : 'Gefunden. Bitte kurz prüfen.';
      render();
    }).catch(fail);
  };
  function saveMailbox(verified) {
    var m = S.draft.mailbox;
    if (!m.address || m.address.indexOf('@') < 0) return Promise.reject(new Error('Bitte die E-Mail-Adresse eintragen.'));
    if (!S.draft.password && !S.boot.mailbox.has_password) return Promise.reject(new Error('Bitte das Passwort eintragen.'));
    if (!m.imap_host || !m.smtp_host) return Promise.reject(new Error('Bitte die Serverdaten eintragen oder suchen lassen.'));
    if (!m.display_name) m.display_name = ((S.draft.profile.first_name || '') + ' ' + (S.draft.profile.last_name || '')).trim();
    var clean = {};
    Object.keys(m).forEach(function (k) { if (k[0] !== '_') clean[k] = m[k]; });
    if (!clean.username) clean.username = clean.address;
    return api('/api/mailbox/save', { body: { mailbox: clean, password: S.draft.password || undefined, verified: verified } }).then(function () {
      if (S.draft.password) S.boot.mailbox.has_password = true;
      S.draft.password = '';
      Object.assign(S.boot.mailbox, clean);
    });
  }
  function testBlock() {
    var t = S.testResult;
    var res = '';
    if (t === 'running') res = '<div class="row"><span class="spin"></span><span>Spurlos meldet sich an und schickt eine Testmail an sich selbst …</span></div>';
    else if (t) {
      res = t.steps.map(function (s) {
        return '<div class="result-step"><span class="' + (s.ok ? 'ico-ok' : 'ico-bad') + '">' + (s.ok ? I.ok : I.x) + '</span><div class="stack" style="gap:2px"><b style="font-weight:500">' + esc(s.name) + '</b><span class="small muted">' + esc(s.detail) + '</span></div></div>';
      }).join('') + (t.passed ? '<div class="notice ok">' + I.ok + '<span>Alles funktioniert. Die Testmail liegt gleich in deinem Posteingang.</span></div>' : '<div class="notice bad">' + I.warn + '<span>Bitte prüfe die Angaben beim Postfach und teste noch einmal.</span></div>');
    }
    return '<section class="card"><div class="row wrap between"><h2>Verbindung testen</h2><button class="btn ' + (t && t !== 'running' && t.passed ? '' : 'p') + '" data-act="run-test"' + (t === 'running' ? ' disabled' : '') + '>' + (t ? 'Noch mal testen' : 'Test starten') + '</button></div>' +
      '<p class="small muted" style="margin:0">Spurlos meldet sich am Posteingang und am Postausgang an und schickt eine Testmail an ' + esc(S.boot.mailbox.address || 'dich') + '.</p>' + res + '</section>';
  }
  ACT['run-test'] = function () {
    S.testResult = 'running'; render();
    api('/api/mailbox/test', { body: { send_test: true } }).then(function (d) {
      S.testResult = d;
      if (d.passed) return api('/api/mailbox/save', { body: { verified: true } });
    }).then(render).catch(function (e) { S.testResult = null; render(); fail(e); });
  };

  function kiBlock() {
    var cur = S.draft.ai.provider || 'none';
    var st = S.aiStatus;
    if (!st) { api('/api/ai/status').then(function (d) { S.aiStatus = d; render(); }).catch(function () { S.aiStatus = { apple: {}, ollama: {}, cloud: {} }; }); }
    var apple = st ? st.apple : {};
    var oll = st ? st.ollama : {};
    var cards = [
      { id: 'none', name: 'Ohne KI', text: 'Erkennt Antworten an typischen Formulierungen. Klappt bei Standardantworten gut.', chips: [['Standard', 'planned'], ['Keine Einrichtung', 'planned']] },
      { id: 'apple', name: 'Apple Intelligence', text: 'Läuft direkt auf deinem Mac, ohne Internet und ohne Kosten. Braucht macOS 26, einen Mac mit M-Chip und eingeschaltete Apple Intelligence.',
        chips: [['Kostenlos', 'done'], ['Offline', 'done'], [st ? (apple.ok ? 'Auf diesem Mac verfügbar' : 'Nicht verfügbar') : 'Prüfe …', apple.ok ? 'done' : 'todo']],
        extra: st && !apple.ok ? '<span class="tiny muted">' + esc(apple.text || '') + '</span>' : '' },
      { id: 'ollama', name: 'Lokales Modell (Ollama)', text: 'Ein freies KI-Modell auf deinem Mac. Der Download ist mehrere Gigabyte groß, und es braucht viel Arbeitsspeicher.',
        chips: [['Kostenlos', 'done'], ['Offline', 'done'], [st ? (oll.ok ? 'Ollama läuft' : 'Ollama nicht gefunden') : 'Prüfe …', oll.ok ? 'done' : 'todo']],
        extra: cur === 'ollama' && oll.ok ? '<div class="field"><label for="om">Modell</label><select id="om" class="input" data-ai="ollama_model"><option value="">Automatisch</option>' + (oll.models || []).map(function (x) { return '<option' + (S.draft.ai.ollama_model === x ? ' selected' : '') + '>' + esc(x) + '</option>'; }).join('') + '</select></div>' : (st && !oll.ok ? '<span class="tiny muted">Ollama gibt es kostenlos auf ollama.com.</span>' : '') },
      { id: 'cloud', name: 'Cloud-KI (Claude, ChatGPT)', text: 'Versteht ungewöhnliche Antworten am besten. Braucht einen API-Schlüssel und kostet pro Nutzung.',
        chips: [['Kostenpflichtig', 'todo'], ['Online', 'planned']], warn: 'Antworten mit deinen persönlichen Daten gehen an den KI-Anbieter.',
        extra: cur === 'cloud' ? '<div class="form-grid" style="grid-template-columns:1fr"><div class="field"><label for="cv">Anbieter</label><select id="cv" class="input" data-ai="cloud_vendor"><option value="anthropic"' + (S.draft.ai.cloud_vendor !== 'openai' ? ' selected' : '') + '>Anthropic (Claude)</option><option value="openai"' + (S.draft.ai.cloud_vendor === 'openai' ? ' selected' : '') + '>OpenAI (ChatGPT)</option></select></div>' +
          '<div class="field"><label for="ck">API-Schlüssel</label><input id="ck" class="input mono" type="password" data-ai="api_key" placeholder="' + (S.boot.ai.has_key ? 'gespeichert – nur zum Ändern eintragen' : 'sk-…') + '"></div>' +
          '<div class="field"><label for="cm">Modell (optional)</label><input id="cm" class="input mono" data-ai="cloud_model" value="' + esc(S.draft.ai.cloud_model || '') + '" placeholder="Standard des Anbieters"></div>' +
          '<button class="btn sm" data-act="ai-save">Speichern</button></div>' : '' }
    ];
    var html = cards.map(function (c) {
      var on = c.id === cur;
      return '<div class="ki-card ' + (on ? 'on' : '') + '"><div class="row between" style="align-items:flex-start"><b style="font-size:15px">' + esc(c.name) + '</b>' + (on ? '<span class="pill nodot" style="background:var(--accent);color:#fff">' + I.ok + ' Aktiv</span>' : '') + '</div>' +
        '<span class="small" style="color:var(--ink-2);line-height:1.5">' + esc(c.text) + '</span><div class="row wrap" style="gap:6px">' + c.chips.map(function (x) { return '<span class="mini g-' + x[1] + '">' + esc(x[0]) + '</span>'; }).join('') + '</div>' +
        (c.warn ? '<div class="notice warn">' + I.warn + '<span>' + esc(c.warn) + '</span></div>' : '') + (c.extra || '') +
        '<button class="btn sm ' + (on ? 'p' : '') + '" style="margin-top:auto;align-self:flex-start" role="radio" aria-checked="' + on + '" data-act="ai-pick" data-id="' + c.id + '">' + (on ? 'Ausgewählt' : c.id === 'cloud' ? 'Auswählen und einrichten' : 'Auswählen') + '</button></div>';
    }).join('');
    return '<section class="card" style="gap:18px"><div class="stack" style="gap:8px"><div class="row"><h2 style="font-size:19px">KI-Assistent</h2><span class="tag">Optional</span></div>' +
      '<div class="row wrap" style="gap:6px;font-size:15px"><span>Für eine bessere Erkennung kannst du eine KI einbinden.</span><span class="tipw"><button class="tipbtn" aria-label="Was bringt eine KI?" aria-describedby="tip-ki"><span aria-hidden="true">?</span></button>' +
      '<span role="tooltip" id="tip-ki" class="tip"><strong>Was bringt eine KI?</strong>Ohne KI erkennt Spurlos Antworten an typischen Formulierungen wie „keine Daten gespeichert“. Das klappt bei Standardantworten gut. Eine KI versteht auch ungewöhnliche Mails und Rückfragen und macht genauere Vorschläge. Du bestätigst trotzdem jeden Vorschlag selbst.</span></span></div></div>' +
      '<div class="ki-cards" role="radiogroup" aria-label="KI auswählen">' + html + '</div>' +
      '<div class="row wrap between" style="padding:14px 16px;border-radius:10px;background:var(--soft);border:1px solid var(--line-3)"><div class="stack" style="gap:2px"><b style="font-weight:500">Mit einer Beispielantwort testen</b><span class="mono tiny muted">' + esc(S.ui.aiTest || 'Noch nicht getestet') + '</span></div><button class="btn sm" data-act="ai-test">Test starten</button></div>' +
      '<div class="row small muted" style="align-items:flex-start">' + I.lock + '<span>Die KI sieht nur den Text einer Antwort. Mit Apple Intelligence oder einem lokalen Modell verlässt nichts deinen Mac. Egal welche Einstellung: Spurlos verschickt nichts ohne deine Bestätigung.</span></div></section>';
  }
  ACT['ai-pick'] = function (el) {
    S.draft.ai.provider = el.dataset.id;
    api('/api/settings/ai', { body: { provider: el.dataset.id } }).then(function (d) { S.boot.ai.provider = d.ai.provider; render(); }).catch(fail);
  };
  ACT['ai-save'] = function () {
    var a = S.draft.ai;
    api('/api/settings/ai', { body: { cloud_vendor: a.cloud_vendor, cloud_model: a.cloud_model, ollama_model: a.ollama_model, api_key: a.api_key || undefined } })
      .then(function () { if (a.api_key) S.boot.ai.has_key = true; a.api_key = ''; toast('Gespeichert'); render(); }).catch(fail);
  };
  ACT['ai-test'] = function (el) {
    var a = S.draft.ai;
    busy(el, true);
    var save = a.provider === 'ollama' ? api('/api/settings/ai', { body: { ollama_model: a.ollama_model } }) : Promise.resolve();
    save.then(function () { return api('/api/ai/test', { body: {} }); }).then(function (d) {
      S.ui.aiTest = 'Erkannt: „' + d.category + '“' + (d.ai ? ' · KI stimmt ' + (d.ai === 'no_data' ? 'zu' : 'nicht zu') : '') + (d.note && !d.ai ? ' · ' + d.note : '') + ' · ' + String(d.seconds).replace('.', ',') + ' s';
      render();
    }).catch(fail).then(function () { busy(el, false); });
  };

  // ------------------------------------------------------------------ Einrichtung
  var STEPS = [['Deine Daten', 'Name, Adressen, Nummern'], ['Postfach', 'Woher die Anfragen kommen'], ['Verbinden & testen', 'Testmail an dich selbst'],
    ['KI-Assistent', 'Optional'], ['Start', 'Firmen wählen, loslegen']];
  function renderSetup(r) {
    var step = +(r.page === 'einrichtung' && r.arg ? r.arg : S.boot.setup_step || 1);
    if (step < 1 || step > 5) step = 1;
    var side = '<aside class="onb-side"><div class="stack" style="gap:40px"><div class="row">' + LOGO + '<b style="color:#fff;font-size:19px">Spurlos</b></div>' +
      '<div class="stack" style="gap:8px"><span class="label" style="color:var(--side-ink)">Einrichtung</span><p style="margin:0;font-size:15px;line-height:1.5;color:#E6E9EE">In fünf Schritten startklar. Danach schreibt Spurlos die Datenhändler für dich an.</p></div>' +
      '<ol class="steps">' + STEPS.map(function (s, i) {
        var n = i + 1; var cls = n === step ? 'now' : n < step ? 'done' : '';
        return '<li class="' + cls + '"><span class="n">' + (n < step ? '✓' : '0' + n) + '</span><div><b>' + s[0] + '</b><span class="tiny">' + s[1] + '</span></div></li>';
      }).join('') + '</ol></div>' +
      '<div class="row small" style="align-items:flex-start;line-height:1.5">' + I.lock + '<span>Alles bleibt auf deinem Mac. Spurlos hat keinen eigenen Server und kein Benutzerkonto.</span></div>' +
      (S.boot.setup_done ? '<a class="btn sm" href="#/uebersicht" style="background:transparent;color:#E6E9EE;border-color:#2B3240">Zurück zur Übersicht</a>' : '') + '</aside>';
    var content = '';
    var nav = function (back, next, label) {
      return '<div class="row wrap between">' + (back ? '<a class="btn" href="#/einrichtung/' + back + '">Zurück</a>' : '<span></span>') +
        '<button class="btn p" data-act="setup-next" data-step="' + step + '">' + (label || 'Weiter') + '</button></div>';
    };
    if (step === 1) {
      content = '<div class="stack" style="gap:10px"><span class="eyebrow" style="color:var(--accent)">Schritt 1 von 5 · Deine Daten</span><h1>Nach welchen Angaben sollen die Firmen suchen?</h1>' +
        '<p class="lead">Je vollständiger, desto besser finden dich die Firmen in ihren Datenbanken. Diese Angaben bleiben auf deinem Mac und stehen nur in deinen Anfragen.</p></div>' + profileForm() + nav(0, 2, 'Weiter: Postfach');
    } else if (step === 2) {
      content = '<div class="stack" style="gap:10px"><span class="eyebrow" style="color:var(--accent)">Schritt 2 von 5 · Postfach</span><h1>Über welches Postfach soll Spurlos schreiben?</h1>' +
        '<p class="lead">Aus diesem Postfach gehen deine Anfragen raus, und hier kommen die Antworten der Firmen an. Am besten nimmst du eine eigene Adresse nur für dieses Projekt.</p></div>' + mailboxForm() + nav(1, 3, 'Weiter: Verbindung testen');
    } else if (step === 3) {
      content = '<div class="stack" style="gap:10px"><span class="eyebrow" style="color:var(--accent)">Schritt 3 von 5 · Verbinden & testen</span><h1>Klappt die Verbindung?</h1>' +
        '<p class="lead">Spurlos prüft, ob es sich anmelden und Mails verschicken kann.</p></div>' + testBlock() +
        '<div class="row wrap between"><a class="btn" href="#/einrichtung/2">Zurück</a><button class="btn p" data-act="setup-next" data-step="3"' + (S.testResult && S.testResult.passed ? '' : (S.boot.mailbox.verified ? '' : ' disabled')) + '>Weiter: KI-Assistent</button></div>';
    } else if (step === 4) {
      content = '<div class="stack" style="gap:10px"><span class="eyebrow" style="color:var(--accent)">Schritt 4 von 5 · KI-Assistent (optional)</span><h1>Soll eine KI beim Einordnen helfen?</h1>' +
        '<p class="lead">Spurlos funktioniert auch ohne KI. Du kannst das später jederzeit in den Einstellungen ändern.</p></div>' + kiBlock() + nav(3, 5, 'Weiter: Start');
    } else {
      content = renderStartStep() ;
    }
    return '<div class="onb">' + side + '<main class="onb-main"><div class="onb-inner">' + content + '</div></main></div>';
  }
  function renderStartStep() {
    var d = S.brokers;
    if (!d) { api('/api/brokers').then(function (x) { S.brokers = x; render(); }).catch(fail); }
    var rows = '';
    var totalSel = 0, totalMail = 0;
    if (d) {
      rows = S.boot.group_order.map(function (g) {
        var inGroup = d.brokers.filter(function (b) { return b.grp === g && b.relevant && b.active; });
        if (!inGroup.length) return '';
        var on = !!S.boot.groups[g];
        var mailN = inGroup.filter(function (b) { return b.contact === 'email'; }).length;
        if (on) { totalSel += inGroup.length; totalMail += mailN; }
        return '<div class="group-row"><button class="switch" role="switch" aria-checked="' + on + '" aria-label="' + esc(groupLabel(g)) + '" data-act="toggle-group" data-g="' + g + '"></button><div class="grow stack" style="gap:2px"><b>' + esc(groupLabel(g)) + '</b><span class="small muted">' + esc(S.boot.group_meta[g].sub) + '</span></div><span class="mono small muted" style="text-align:right">' + inGroup.length + ' Firmen<br>' + mailN + ' per E-Mail</span></div>';
      }).join('');
    }
    var s = S.draft.sending;
    return '<div class="stack" style="gap:10px"><span class="eyebrow" style="color:var(--accent)">Schritt 5 von 5 · Start</span><h1>Welche Firmen soll Spurlos anschreiben?</h1>' +
      '<p class="lead">Die Liste richtet sich nach deinen Ländern (' + esc(S.boot.countries.map(function (c) { return S.boot.all_countries[c]; }).join(', ')) + '). Einzelne Firmen kannst du später in der Händlerliste ab- oder zuschalten.</p></div>' +
      '<section class="card">' + (d ? rows : '<div class="empty"><span class="spin"></span></div>') + (d ? '<div class="notice ok">' + I.info + '<span><b>' + totalSel + ' Firmen ausgewählt, ' + totalMail + ' davon per E-Mail.</b> Firmen ohne Mailadresse landen unter „Kontakt fehlt“ oder „Formular offen“, dort kannst du sie nachtragen.</span></div>' : '') + '</section>' +
      '<section class="card"><h2>Versand</h2><div class="form-grid">' +
      '<div class="field"><label for="pd">Anfragen pro Tag</label><input id="pd" class="input mono" type="number" min="1" max="50" data-send="per_day" value="' + esc(s.per_day) + '"><span class="hint">In Etappen, damit nichts im Spam landet.</span></div>' +
      '<div class="field"><label for="st">Versand ab</label><input id="st" class="input mono" type="time" data-send="send_time" value="' + esc(s.send_time) + '"></div></div>' +
      '<label class="check"><input type="checkbox" id="fbn" ' + (s.first_batch_now ? 'checked' : '') + ' data-send="first_batch_now"> Erste Etappe sofort senden</label></section>' +
      '<section class="card"><div class="row wrap between"><div class="stack" style="gap:2px"><h2>So sieht deine Anfrage aus</h2><span class="small muted">Mit deinen Daten. Firmen in Deutschland und Österreich bekommen sie auf Deutsch, Schweizer Firmen nach Schweizer Recht, alle anderen auf Englisch.</span></div><div class="row wrap"><button class="btn sm" data-act="sample" data-lang="de">Deutsch</button>' + (S.boot.countries.indexOf('ch') >= 0 ? '<button class="btn sm" data-act="sample" data-lang="ch">Schweiz</button>' : '') + '<button class="btn sm" data-act="sample" data-lang="en">Englisch</button></div></div></section>' +
      '<div class="notice warn">' + I.warn + '<span>Lass Spurlos geöffnet, solange es arbeiten soll. Es verschickt die Etappen und ruft das Postfach nur ab, während das Programm läuft. Was liegen bleibt, holt es beim nächsten Start nach.</span></div>' +
      '<div class="row wrap between"><a class="btn" href="#/einrichtung/4">Zurück</a><button class="btn p" data-act="start">Anfragen starten</button></div>';
  }
  document.addEventListener('change', function (e) { if (e.target.id === 'fbn' && S.draft) S.draft.sending.first_batch_now = e.target.checked; });
  ACT.sample = function (el) {
    var save = saveProfile().catch(function () { return null; });
    save.then(function () { return api('/api/sample?lang=' + el.dataset.lang); }).then(function (d) {
      textModal('Beispiel: ' + { de: 'Anfrage auf Deutsch', ch: 'Anfrage an Schweizer Firmen', en: 'Anfrage auf Englisch' }[el.dataset.lang], 'Das Aktenzeichen wird pro Firma vergeben.', d.subject, d.body);
    }).catch(fail);
  };
  ACT['setup-next'] = function (el) {
    var step = +el.dataset.step;
    var job;
    if (step === 1) job = saveProfile();
    else if (step === 2) job = saveMailbox(false).then(function () { S.testResult = null; });
    else job = Promise.resolve();
    job.then(function () {
      var next = step + 1;
      return api('/api/setup', { body: { step: next } }).then(function () {
        S.boot.setup_step = next; go('#/einrichtung/' + next);
        // Nach dem Postfach-Schritt startet der Verbindungstest sofort, ohne zweiten Klick
        if (next === 3) ACT['run-test']();
      });
    }).catch(fail);
  };
  ACT.start = function (el) {
    busy(el, true);
    var s = S.draft.sending;
    api('/api/settings/sending', { body: { per_day: s.per_day, send_time: s.send_time, first_batch_now: s.first_batch_now } })
      .then(function () { return api('/api/start', { body: {} }); })
      .then(function (d) {
        S.boot.setup_done = true; S.boot.started = true;
        toast((d.created.email || 0) + ' Anfragen geplant. Die erste Etappe geht ' + (s.first_batch_now ? 'jetzt' : 'zur Versandzeit') + ' raus.');
        go('#/uebersicht');
        return refreshData();
      }).then(render).catch(function (e) { busy(el, false); fail(e); });
  };

  // ------------------------------------------------------------------ Einstellungen
  var TABS = [['daten', 'Meine Daten'], ['postfach', 'Postfach'], ['ki', 'KI-Assistent'], ['fristen', 'Fristen & Versand'], ['vorlagen', 'Vorlagen'], ['sicherung', 'Daten & Sicherung'], ['ueber', 'Über Spurlos']];
  function renderSettings() {
    var tab = S.ui.setTab;
    var nav = '<nav class="subnav" aria-label="Bereiche">' + TABS.map(function (t) {
      return '<button class="' + (tab === t[0] ? 'on' : '') + '" data-act="set-tab" data-t="' + t[0] + '"><span>' + t[1] + '</span>' + (t[0] === 'ki' ? '<span class="tag ki">KI</span>' : '') + '</button>';
    }).join('') + '</nav>';
    var body = '';
    if (tab === 'daten') {
      body = '<div class="stack" style="gap:16px"><div class="stack" style="gap:6px"><h2 style="margin:0;font-size:19px">Meine Daten</h2><p class="small muted" style="margin:0">Nach diesen Angaben sollen die Firmen suchen. Änderungen gelten für alle Anfragen, die noch nicht verschickt sind.</p></div>' +
        profileForm() + '<div><button class="btn p" data-act="save-profile">Speichern</button></div></div>';
    } else if (tab === 'postfach') {
      body = '<div class="stack" style="gap:16px"><h2 style="margin:0;font-size:19px">Postfach</h2>' + mailboxForm() +
        '<div class="row"><button class="btn p" data-act="save-mailbox">Speichern</button></div>' + testBlock() + '</div>';
    } else if (tab === 'ki') {
      body = kiBlock();
    } else if (tab === 'fristen') {
      var s = S.draft.sending;
      body = '<section class="card"><div class="stack" style="gap:4px"><h2 style="font-size:19px">Fristen & Versand</h2><span class="small muted">Wie schnell Spurlos schreibt und wann es nachhakt.</span></div><div class="form-grid">' +
        numField('per_day', 'Anfragen pro Tag', 'In Etappen, damit nichts im Spam landet.') +
        '<div class="field"><label for="f-send_time">Versand ab</label><input id="f-send_time" class="input mono" type="time" data-send="send_time" value="' + esc(s.send_time) + '"></div>' +
        numField('reminder_days', 'Erinnerung nach (Tagen)', 'Firmen haben einen Monat Zeit für die Antwort.') +
        numField('complaint_days', 'Beschwerde-Text nach weiteren (Tagen)', 'Zählt ab der Erinnerung.') +
        numField('poll_minutes', 'Postfach abrufen alle (Minuten)', '') + '</div>' +
        '<label class="check"><input type="checkbox" data-send="auto_remind"' + (s.auto_remind ? ' checked' : '') + '> Erinnerungen automatisch verschicken</label>' +
        '<label class="check"><input type="checkbox" data-send="notifications"' + (s.notifications ? ' checked' : '') + '> Mitteilungen auf dem Mac bei neuen Antworten</label>' +
        '<div><button class="btn p" data-act="save-sending">Speichern</button></div></section>';
    } else if (tab === 'vorlagen') {
      body = '<section class="card"><div class="stack" style="gap:4px"><h2 style="font-size:19px">Vorlagen</h2><span class="small muted">Die Texte, die Spurlos verschickt, mit deinen Daten.</span></div><ul class="list">' +
        S.boot.templates.map(function (t) {
          return '<li><div class="grow stack" style="gap:2px"><b style="font-weight:500">' + esc(t.label) + '</b><span class="small muted">' + esc(t.sub) + '</span></div><span class="mono small">' + esc(t.langs) + '</span>' +
            '<button class="btn sm" data-act="tpl" data-id="' + t.id + '" data-lang="de">Deutsch</button>' + (t.langs.indexOf('CH') >= 0 ? '<button class="btn sm" data-act="tpl" data-id="' + t.id + '" data-lang="ch">Schweiz</button>' : '') + (t.langs.indexOf('EN') >= 0 ? '<button class="btn sm" data-act="tpl" data-id="' + t.id + '" data-lang="en">Englisch</button>' : '') + '</li>';
        }).join('') + '</ul><p class="small muted" style="margin:0;padding-top:12px;border-top:1px solid var(--line-3)">Grundlage: Musterschreiben von datenanfragen.de (CC0), der Verbraucherzentralen und des Landesdatenschutzbeauftragten Baden-Württemberg.</p></section>';
    } else if (tab === 'sicherung') {
      body = '<section class="card"><div class="stack" style="gap:4px"><h2 style="font-size:19px">Daten & Sicherung</h2><span class="small muted">Alles liegt nur auf diesem Mac. Kein Server, kein Konto.</span></div><ul class="list">' +
        '<li><div class="grow stack" style="gap:2px"><b style="font-weight:500">Speicherort</b><span class="small muted">Angaben, Anfragen, Verläufe</span></div><span class="mono small" style="word-break:break-all">' + esc(S.boot.data_dir) + '</span></li>' +
        '<li><div class="grow stack" style="gap:2px"><b style="font-weight:500">Sicherung exportieren</b><span class="small muted">Eine Datei mit allen Anfragen und Antworten. Passwörter sind nicht enthalten.</span></div><a class="btn sm" href="/api/export" data-act="export">Exportieren</a></li>' +
        '<li><div class="grow stack" style="gap:2px"><b style="font-weight:500">Einrichtung erneut öffnen</b><span class="small muted">Deine Daten bleiben erhalten.</span></div><a class="btn sm" href="#/einrichtung/1">Öffnen</a></li>' +
        '<li><div class="grow stack" style="gap:2px"><b style="font-weight:500">Alle Daten löschen</b><span class="small muted">Entfernt alles von diesem Mac. Die Firmen behalten deine Anfragen.</span></div><button class="btn sm danger" data-act="reset">Löschen</button></li></ul></section>';
    } else {
      body = '<section class="card"><div class="row">' + LOGO + '<div class="stack" style="gap:2px"><h2 style="font-size:19px">Spurlos</h2><span class="mono small muted">Version ' + esc(S.boot.version) + '</span></div></div>' +
        '<p class="small" style="margin:0;line-height:1.55;color:var(--ink-2)">Holt deine Daten bei Datenhändlern zurück. Läuft nur auf deinem Mac, ohne Server und ohne Konto. Spurlos hilft dir, deine Rechte wahrzunehmen, ersetzt aber keine Rechtsberatung.</p></section>' +
        '<section class="card"><h3>Quellen</h3><ul class="small" style="margin:0;padding-left:18px;line-height:1.7;color:var(--ink-2)"><li>Firmenkontakte: datenanfragen.de (offene Datenbank, CC0)</li><li>EU-Datenhändler: öffentliche Liste von Incogni</li><li>USA: Datenhändler-Register von Kalifornien (CPPA)</li><li>Musterbriefe: datenanfragen.de, Verbraucherzentralen, LfDI Baden-Württemberg</li><li>Schrift: IBM Plex (SIL Open Font License)</li></ul></section>';
    }
    return head('Alles wird nur auf diesem Mac gespeichert', 'Einstellungen') + '<div class="row wrap" style="align-items:flex-start;gap:28px">' + nav + '<div style="flex:4 1 520px;min-width:0" class="stack">' + body + '</div></div>';
  }
  function numField(k, label, hint) {
    return '<div class="field"><label for="f-' + k + '">' + label + '</label><input id="f-' + k + '" class="input mono" type="number" min="1" data-send="' + k + '" value="' + esc(S.draft.sending[k]) + '">' + (hint ? '<span class="hint">' + hint + '</span>' : '') + '</div>';
  }
  ACT['set-tab'] = function (el) { S.ui.setTab = el.dataset.t; history.replaceState(null, '', '#/einstellungen/' + el.dataset.t); render(); };
  ACT['save-profile'] = function (el) { busy(el, true); saveProfile().then(function () { toast('Gespeichert'); return refreshData(); }).then(render).catch(function (e) { busy(el, false); fail(e); }); };
  ACT['save-mailbox'] = function (el) { busy(el, true); saveMailbox(false).then(function () { S.testResult = null; toast('Gespeichert. Bitte einmal testen.'); render(); }).catch(function (e) { busy(el, false); fail(e); }); };
  ACT['save-sending'] = function (el) {
    var s = S.draft.sending;
    document.querySelectorAll('[data-send]').forEach(function (n) { if (n.type === 'checkbox') s[n.dataset.send] = n.checked; });
    api('/api/settings/sending', { body: s }).then(function (d) { S.boot.sending = d.sending; toast('Gespeichert'); }).catch(fail);
  };
  ACT.tpl = function (el) {
    api('/api/sample?kind=' + el.dataset.id + '&lang=' + el.dataset.lang).then(function (d) { textModal('Vorlage', 'Mit deinen Daten. Aktenzeichen und Datum werden pro Firma eingesetzt.', d.subject, d.body); }).catch(fail);
  };
  ACT['export'] = function (el) {
    busy(el, true);
    fetch('/api/export', { headers: { 'X-Spurlos': '1' }, credentials: 'same-origin' }).then(function (r) {
      if (!r.ok) throw new Error('Export fehlgeschlagen (' + r.status + ')');
      return r.blob();
    }).then(function (blob) {
      var a = document.createElement('a');
      var d = new Date();
      a.href = URL.createObjectURL(blob);
      // Uhrzeit im Namen: im Programmfenster scheitert das Speichern still, wenn die Datei schon existiert
      a.download = 'spurlos-sicherung-' + d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + '-' + pad(d.getHours()) + pad(d.getMinutes()) + '.json';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
      toast(window.pywebview ? 'Wähle im Dialog, wo die Sicherung liegen soll.' : 'Sicherung gespeichert (Ordner „Downloads“)');
    }).catch(fail).then(function () { busy(el, false); });
  };
  ACT.reset = function () {
    var v = prompt('Wirklich alles löschen? Tippe LÖSCHEN ein.');
    if (v !== 'LÖSCHEN') return;
    api('/api/reset', { body: { confirm: v } }).then(function () { S.draft = null; return load(); }).then(function () { go('#/einrichtung/1'); }).catch(fail);
  };

  // ------------------------------------------------------------------ Start
  render();
  function boot(attempt) {
    load().then(function () {
      var r = route();
      if (r.page === 'einstellungen' && r.arg) S.ui.setTab = r.arg;
      if (r.page === 'anfragen' && r.q.f) S.ui.reqFilter = r.q.f;
      return refreshData();
    }).then(render).catch(function (e) {
      // Netzwerkfehler (z. B. weil eine Rückfrage des Macs den Start aufgehalten hat): von selbst neu versuchen.
      var retry = e instanceof TypeError && attempt < 20;
      $app.innerHTML = '<div class="empty"><b>Spurlos konnte nicht starten.</b><span>' + esc(e.message) + '</span>' +
        (retry ? '<span class="small muted">Spurlos versucht es gleich noch einmal …</span>' : '') +
        '<button class="btn" data-act="reload">Erneut versuchen</button></div>';
      if (retry) setTimeout(function () { boot(attempt + 1); }, 3000);
    });
  }
  ACT.reload = function () {
    // Im Programmfenster: über die App neu laden, damit der Zugangs-Link wieder gesetzt wird
    if (window.pywebview && window.pywebview.api && window.pywebview.api.restart) window.pywebview.api.restart();
    else location.reload();
  };
  // Fenster war im Hintergrund (Timer gedrosselt): beim Zurückholen sofort auffrischen
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && S.boot && S.boot.setup_done) refreshData().then(render).catch(function () {});
  });
  boot(0);
  setInterval(function () {
    if (!S.boot || !S.boot.setup_done) return;
    var a = document.activeElement;
    if (a && /INPUT|TEXTAREA|SELECT/.test(a.tagName)) return;
    if ($modal.innerHTML) return;
    refreshData().then(render).catch(function () { /* still */ });
  }, 60000);
})();
