/* qdbd interactive viewer: pan/zoom, search, minimap, focus, collapse, FK hover, export.
 * In serve mode (data.serve) tables can also be dragged; positions are POSTed to the server. */
(function () {
  "use strict";
  var Q = window.qdbd;
  var data = JSON.parse(document.getElementById("qdbd-data").textContent);
  var S = {
    model: data.model,
    pos: data.positions,
    mode: "full",
    focus: null,
    view: { x: 0, y: 0, k: 1 },
    serve: !!data.serve,
    filter: "",
    vm: data.model, // view model: the tables/relationships left after the filter
    shown: {},
    regions: !!data.model.regions,
    path: null, // {to: id, steps: [...]} from the selected table
    edge: null, // the clicked (locked) relationship line: "a|ac|b|bc", like the .e data attributes
    hover: null, // {t: table id} or {e: line key} under the mouse: lights lines without dimming anything
  };
  var svg = document.getElementById("canvas");
  var vp = document.getElementById("vp");
  var zoomval = document.getElementById("zoomval");
  var byId = {};

  function index() {
    byId = {};
    S.model.tables.forEach(function (t) { byId[t.id] = t; });
  }

  /* ------------------------------------------------------------- render */
  function render() {
    vp.innerHTML = Q.renderInner(S.vm, S.pos, S.mode, { docMarks: true, regions: S.regions }) +
      '<g class="fx"></g><g class="hit"></g>';
    vp.appendChild(vp.querySelector(".tables")); // lit overlay and line hit targets sit under the tables
    relByKey = {};
    S.vm.rels.forEach(function (r, i) { relByKey[[r.a.t, r.a.c, r.b.t, r.b.c].join("|")] = i; });
    buildHits();
    applyFocus();
    drawMinimap();
  }

  function renderEdges() {
    var g = vp.querySelector(".edges");
    if (g) g.innerHTML = Q.renderEdges(S.vm, S.pos, S.mode);
    buildHits();
    applyFocus();
  }

  /* ------------------------------------------------------------- lit relationships
   * A lit line gets the --lit colour, flowing dashes and cardinality labels (drawn in .fx), and its rows are
   * highlighted. Lines light up under a hovered table or line, for the selected table, and for the clicked line. */
  var relByKey = {};
  function edgeKey(e) {
    return [e.getAttribute("data-a"), e.getAttribute("data-ac"), e.getAttribute("data-b"), e.getAttribute("data-bc")].join("|");
  }
  /* Wide transparent copies of every line, so a 1px curve can be hovered and clicked. */
  function buildHits() {
    var hit = vp.querySelector(".hit");
    if (!hit) return;
    hit.innerHTML = [].map.call(vp.querySelectorAll(".e"), function (e) {
      return '<path data-k="' + Q.esc(edgeKey(e)) + '" d="' + e.querySelector(".ep").getAttribute("d") + '"/>';
    }).join("");
  }
  function light() {
    var fx = vp.querySelector(".fx");
    if (!fx) return;
    if (S.edge && relByKey[S.edge] === undefined) S.edge = null; // the clicked line was filtered away or edited out
    if (!S.edge) closeCard();
    vp.querySelectorAll(".lit, .t.on").forEach(function (el) { el.classList.remove("lit", "on"); });
    svg.classList.toggle("efocus", !!S.edge);
    var focused = svg.classList.contains("focus"), h = S.hover || {}, geo = null, parts = [];
    vp.querySelectorAll(".e").forEach(function (e) {
      var k = edgeKey(e), a = e.getAttribute("data-a"), b = e.getAttribute("data-b"), d = e.querySelector(".ep").getAttribute("d");
      var dk = ' data-k="' + Q.esc(k) + '"';
      if (e.classList.contains("ph")) { parts.push('<path class="flow amber"' + dk + ' d="' + d + '"/>'); return; }
      if (!(k === S.edge || h.e === k || h.t === a || h.t === b || e.classList.contains("hl") ||
          (focused && !S.path && !e.classList.contains("dim")))) return;
      var r = S.vm.rels[relByKey[k]];
      if (!r) return;
      e.classList.add("lit");
      [[r.a.t, r.a.c], [r.b.t, r.b.c]].forEach(function (end) {
        var t = vp.querySelector('.t[data-id="' + cssEsc(end[0]) + '"]');
        if (!t) return;
        if (k === S.edge) t.classList.add("on");
        var row = t.querySelector('.r[data-c="' + cssEsc(end[1]) + '"]');
        if (row) row.classList.add("lit");
      });
      parts.push('<path class="flow"' + dk + ' d="' + d + '"/>');
      (Q.edgeLabels(S.vm, S.pos, S.mode, r, geo = geo || Q.geometry(S.vm, S.mode)) || []).forEach(function (l) {
        parts.push('<text class="lbl"' + dk + ' x="' + l.x + '" y="' + l.y + '" text-anchor="' + l.anchor + '">' + Q.esc(l.text) + "</text>");
      });
    });
    fx.innerHTML = parts.join("");
  }
  var lightRaf = null;
  function scheduleLight() {
    if (!lightRaf) lightRaf = requestAnimationFrame(function () { lightRaf = null; light(); });
  }
  vp.addEventListener("mouseover", function (ev) {
    var hp = ev.target.closest && ev.target.closest(".hit path"), t = ev.target.closest && ev.target.closest(".t");
    var next = hp ? { e: hp.getAttribute("data-k") } : t ? { t: t.getAttribute("data-id") } : null;
    if (JSON.stringify(next) !== JSON.stringify(S.hover)) { S.hover = next; scheduleLight(); }
  });
  /* A click on a line locks it: everything else dims. A second click on it, Esc or a click elsewhere clears it. */
  function lockEdge(k, x, y) {
    select(null);
    S.edge = k;
    light();
    openCard(k, x, y);
  }

  /* The relationship card: both ends with their cardinality, a plain-English sentence and the JOIN. */
  var rcard = document.getElementById("rcard"), cardInfo = null;
  function openCard(k, x, y) {
    var r = S.vm.rels[relByKey[k]], c = Q.relCard(S.vm, relByKey[k]);
    cardInfo = { sql: c.sql, tables: [r.a.t, r.b.t] };
    rcard.innerHTML = '<div class="rt">' + Q.esc(c.from) + "<b>" + Q.esc(c.cardFrom) + " &mdash; " + Q.esc(c.cardTo) + "</b>" + Q.esc(c.to) +
      '</div><div class="rk">' + Q.esc(c.sentence) + "</div><pre>" + Q.esc(c.sql) +
      '</pre><div class="acts"><a id="rcopy">Copy JOIN</a><a id="rboth">Show both tables</a></div>';
    rcard.classList.remove("open");
    void rcard.offsetWidth; // restart the open animation
    rcard.classList.add("open");
    var st = document.getElementById("stage").getBoundingClientRect();
    rcard.style.left = Math.max(8, Math.min(x - st.left + 12, st.width - rcard.offsetWidth - 8)) + "px";
    rcard.style.top = Math.max(8, Math.min(y - st.top + 12, st.height - rcard.offsetHeight - 8)) + "px";
  }
  function closeCard() { rcard.classList.remove("open"); }
  rcard.addEventListener("click", function (ev) {
    if (ev.target.id === "rcopy" && cardInfo) copyText(cardInfo.sql, "JOIN copied", rcard.querySelector("pre"));
    else if (ev.target.id === "rboth" && cardInfo) {
      var names = cardInfo.tables.filter(function (t, i, all) { return all.indexOf(t) === i; }).map(function (t) { return byId[t].name; });
      closeCard();
      applyFilter(names.map(function (n) { return n.replace(/[\s,+!]/g, "?"); }).join(" "));
    }
  });
  document.addEventListener("pointerdown", function (ev) {
    if (!rcard.contains(ev.target) && !(ev.target.closest && ev.target.closest(".hit path"))) closeCard();
  });

  /* The clipboard is blocked in some frames (the VS Code preview): select the text instead and say how to copy it. */
  function copyText(text, done, pre) {
    function fallback() {
      var sel = window.getSelection(), range = document.createRange();
      range.selectNodeContents(pre);
      sel.removeAllRanges();
      sel.addRange(range);
      showToast("Press Ctrl/Cmd+C");
    }
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(function () { showToast(done); }, fallback);
    else fallback();
  }

  // Zoomed out on a big diagram, table text is unreadable but repainting it made every zoom step take ~150 ms
  // at 1000 tables, so it is hidden there. Smaller diagrams always show it.
  var LOD_TABLES = 300, LOD_ZOOM = 0.3;
  function applyView() {
    var v = S.view;
    vp.setAttribute("transform", "translate(" + v.x + "," + v.y + ") scale(" + v.k + ")");
    svg.classList.toggle("lod", v.k < LOD_ZOOM && S.vm.tables.length > LOD_TABLES);
    zoomval.textContent = Math.round(v.k * 100) + "%";
    drawViewportRect();
    scheduleHash();
  }

  function stageSize() {
    var r = svg.getBoundingClientRect();
    return [r.width || 800, r.height || 600];
  }

  function fit(only) {
    var b = Q.bounds(only ? Q.subset(S.vm, only) : S.vm, S.pos, S.mode), sz = stageSize(), pad = 40;
    if (S.regions && !only) b = [b[0] - 30, b[1] - 60, b[2] + 30, b[3] + 30]; // room for region borders and labels
    if (only) sz = [sz[0] - (details.classList.contains("open") ? 400 : 0), sz[1]]; // keep clear of the details panel
    // Keep clear of the floating search box / toolbar at the top and, on narrow screens, the toolbar at the bottom.
    var top = 70, bottom = sz[0] < 900 ? 70 : pad, availH = sz[1] - top - bottom;
    var k = Math.min((sz[0] - 2 * pad) / (b[2] - b[0]), availH / (b[3] - b[1]), 1.5);
    k = Math.max(k, 0.03); // same floor as manual zoom, so wide diagrams still fit a phone screen
    S.view = { k: k, x: (sz[0] - (b[2] - b[0]) * k) / 2 - b[0] * k, y: top + (availH - (b[3] - b[1]) * k) / 2 - b[1] * k };
    applyView();
  }

  function zoomAt(factor, cx, cy) {
    var v = S.view, k = Math.min(4, Math.max(0.03, v.k * factor));
    S.view = { k: k, x: cx - (cx - v.x) * (k / v.k), y: cy - (cy - v.y) * (k / v.k) };
    applyView();
  }

  function centerOn(id) {
    var t = byId[id], p = S.pos[id];
    if (!t || !p) return;
    var g = Q.geometry(S.vm, S.mode)[id], sz = stageSize();
    if (!g) return;
    var k = Math.max(S.view.k, 0.9);
    S.view = { k: k, x: sz[0] / 2 - (p[0] + g.w / 2) * k, y: sz[1] / 2 - (p[1] + g.h / 2) * k };
    applyView();
    var el = vp.querySelector('.t[data-id="' + cssEsc(id) + '"]');
    if (el) {
      el.classList.add("flash");
      setTimeout(function () { el.classList.remove("flash"); }, 1200);
    }
  }

  function cssEsc(s) { return window.CSS && CSS.escape ? CSS.escape(s) : s.replace(/"/g, '\\"'); }

  /* ------------------------------------------------------------- focus + hover */
  function neighbours(id) {
    var set = {};
    set[id] = true;
    S.vm.rels.forEach(function (r) {
      if (r.a.t === id) set[r.b.t] = true;
      if (r.b.t === id) set[r.a.t] = true;
    });
    return set;
  }

  function applyFocus() {
    applyFocusClasses();
    light();
  }
  function applyFocusClasses() {
    vp.querySelectorAll(".ph").forEach(function (el) { el.classList.remove("ph"); });
    if (S.path && S.focus && S.path.steps) {
      var on = {}, edges = [];
      on[S.focus] = true;
      S.path.steps.forEach(function (st) { on[st.to.t] = true; edges.push(st); });
      svg.classList.add("focus");
      vp.querySelectorAll(".t").forEach(function (el) {
        var id = el.getAttribute("data-id");
        el.classList.toggle("dim", !on[id]);
        el.classList.toggle("ph", !!on[id]);
      });
      vp.querySelectorAll(".e").forEach(function (el) {
        var a = el.getAttribute("data-a"), ac = el.getAttribute("data-ac"), b = el.getAttribute("data-b"), bc = el.getAttribute("data-bc");
        var hit = edges.some(function (st) {
          return (st.from.t === a && st.from.c === ac && st.to.t === b && st.to.c === bc) ||
            (st.from.t === b && st.from.c === bc && st.to.t === a && st.to.c === ac);
        });
        el.classList.toggle("dim", !hit);
        el.classList.toggle("ph", hit);
      });
      return;
    }
    if (!S.focus || !byId[S.focus]) {
      S.focus = null;
      svg.classList.remove("focus");
      return;
    }
    var set = neighbours(S.focus);
    svg.classList.add("focus");
    vp.querySelectorAll(".t").forEach(function (el) { el.classList.toggle("dim", !set[el.getAttribute("data-id")]); });
    vp.querySelectorAll(".e").forEach(function (el) {
      var a = el.getAttribute("data-a"), b = el.getAttribute("data-b");
      el.classList.toggle("dim", !(a === S.focus || b === S.focus));
    });
  }

  function clearHover() {
    vp.querySelectorAll(".hl").forEach(function (el) { el.classList.remove("hl"); });
  }

  vp.addEventListener("mouseover", function (ev) {
    var row = ev.target.closest && ev.target.closest(".r");
    clearHover();
    if (!row) return;
    var tid = row.closest(".t").getAttribute("data-id"), cid = row.getAttribute("data-c");
    vp.querySelectorAll(".e").forEach(function (e) {
      var a = e.getAttribute("data-a"), ac = e.getAttribute("data-ac"), b = e.getAttribute("data-b"), bc = e.getAttribute("data-bc");
      var other = null;
      if (a === tid && ac === cid) other = [b, bc];
      else if (b === tid && bc === cid) other = [a, ac];
      if (!other) return;
      e.classList.add("hl");
      row.classList.add("hl");
      var t = vp.querySelector('.t[data-id="' + cssEsc(other[0]) + '"] .r[data-c="' + cssEsc(other[1]) + '"]');
      if (t) t.classList.add("hl");
    });
  });
  vp.addEventListener("mouseleave", function () { clearHover(); hideTip(); S.hover = null; scheduleLight(); });

  /* ------------------------------------------------------------- doc-comment tooltips */
  var tip = document.getElementById("tip");
  function hideTip() { tip.classList.remove("open"); }
  function showTip(ev, title, sub, doc) {
    tip.innerHTML = "";
    var h = document.createElement("div");
    h.className = "tt";
    h.textContent = title;
    if (sub) {
      var s = document.createElement("span");
      s.textContent = sub;
      h.appendChild(s);
    }
    var d = document.createElement("div");
    d.className = "td";
    d.textContent = doc;
    tip.appendChild(h);
    tip.appendChild(d);
    tip.classList.add("open");
    moveTip(ev);
  }
  function moveTip(ev) {
    var r = svg.getBoundingClientRect(), x = ev.clientX - r.left + 14, y = ev.clientY - r.top + 14;
    var w = tip.offsetWidth, h = tip.offsetHeight;
    if (x + w > r.width - 8) x = ev.clientX - r.left - w - 14;
    if (y + h > r.height - 8) y = ev.clientY - r.top - h - 14;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  }
  vp.addEventListener("mousemove", function (ev) {
    if (drag && drag.moved) { hideTip(); return; }
    var tEl = ev.target.closest && ev.target.closest(".t");
    if (!tEl) { hideTip(); return; }
    var t = byId[tEl.getAttribute("data-id")], row = ev.target.closest(".r");
    if (row) {
      var cid = row.getAttribute("data-c"), c = t.cols.filter(function (x) { return x.id === cid; })[0];
      if (c && c.doc) showTip(ev, t.name + "." + c.name, c.type, c.doc);
      else hideTip();
    } else if (t.doc && ev.target.closest(".th, text")) {
      showTip(ev, t.name, t.aliases.length ? "as " + t.aliases.join(", ") : "", t.doc);
    } else hideTip();
  });

  /* ------------------------------------------------------------- pointer: pan, click, drag */
  var drag = null;
  svg.addEventListener("pointerdown", function (ev) {
    if (ev.button !== 0) return;
    var tEl = ev.target.closest && ev.target.closest(".t");
    var hp = !tEl && ev.target.closest && ev.target.closest(".hit path");
    drag = { sx: ev.clientX, sy: ev.clientY, moved: false, table: tEl ? tEl.getAttribute("data-id") : null, el: tEl,
      edge: hp ? hp.getAttribute("data-k") : null };
    if (drag.table) { // tables are draggable everywhere; only `qdbd serve` saves the new position
      drag.start = S.pos[drag.table].slice();
      dragPrep(drag);
      tEl.parentNode.appendChild(tEl); // bring the grabbed table to the front
    } else {
      drag.view = { x: S.view.x, y: S.view.y };
    }
    svg.classList.add("panning");
    try { svg.setPointerCapture(ev.pointerId); } catch (e) { /* synthetic events (the qdbd.dev tour) have no pointer to capture */ }
  });
  var raf = null;
  svg.addEventListener("pointermove", function (ev) {
    if (!drag) return;
    var dx = ev.clientX - drag.sx, dy = ev.clientY - drag.sy;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    if (!drag.moved) return;
    if (drag.start) {
      var p = [Math.round(drag.start[0] + dx / S.view.k), Math.round(drag.start[1] + dy / S.view.k)];
      S.pos[drag.table] = p;
      drag.el.setAttribute("transform", "translate(" + p[0] + "," + p[1] + ")");
      if (!raf) raf = requestAnimationFrame(function () { raf = null; if (drag) dragEdges(drag); });
    } else if (drag.view) {
      S.view.x = drag.view.x + dx;
      S.view.y = drag.view.y + dy;
      applyView();
    }
  });
  svg.addEventListener("pointerup", function (ev) {
    if (!drag) return;
    svg.classList.remove("panning");
    var d = drag;
    drag = null;
    if (!d.moved) {
      if (d.edge) { if (d.edge === S.edge) select(null); else lockEdge(d.edge, ev.clientX, ev.clientY); return; }
      // Clicking the selected table toggles it off, unless it was selected quietly: then show its details.
      if (d.table && d.table === S.focus && !details.classList.contains("open")) showDetails(d.table);
      else select(d.table && S.focus !== d.table ? d.table : null);
      return;
    }
    if (d.start) {
      if (S.regions) render(); // regions are sized from table positions
      else renderEdges();
      drawMinimap();
      var name = byId[d.table].name, body = {};
      body[name] = S.pos[d.table];
      if (window.qdbdServe) window.qdbdServe.saveLayout(body);
    }
  });
  /* While a table is dragged only its own lines are redrawn (a full redraw per frame was slow at 200+ tables). */
  function dragPrep(d) {
    var on = function (k) { var p = k.split("|"); return p[0] === d.table || p[2] === d.table; };
    d.geo = Q.geometry(S.vm, S.mode);
    d.rels = S.vm.rels.filter(function (r) { return r.a.t === d.table || r.b.t === d.table; });
    d.els = {};
    d.hits = {};
    vp.querySelectorAll(".edges .e").forEach(function (e) { var k = edgeKey(e); if (on(k)) d.els[k] = e; });
    vp.querySelectorAll(".hit path").forEach(function (h) { var k = h.getAttribute("data-k"); if (on(k)) d.hits[k] = h; });
  }
  function dragEdges(d) {
    var tmp = document.createElementNS("http://www.w3.org/2000/svg", "g"), fx = vp.querySelector(".fx");
    tmp.innerHTML = Q.renderEdges({ style: S.vm.style, tables: S.vm.tables, rels: d.rels }, S.pos, S.mode, d.geo);
    [].slice.call(tmp.children).forEach(function (e) {
      var k = edgeKey(e), old = d.els[k], path = e.querySelector(".ep").getAttribute("d");
      if (!old) return;
      e.setAttribute("class", old.getAttribute("class")); // keep dim / lit / ph
      old.replaceWith(e);
      d.els[k] = e;
      if (d.hits[k]) d.hits[k].setAttribute("d", path);
      var items = fx ? fx.querySelectorAll('[data-k="' + cssEsc(k) + '"]') : [], labels = null, li = 0;
      [].forEach.call(items, function (it) {
        if (it.tagName === "path") { it.setAttribute("d", path); return; }
        labels = labels || Q.edgeLabels(S.vm, S.pos, S.mode, S.vm.rels[relByKey[k]], d.geo) || [];
        var l = labels[li++];
        if (l) { it.setAttribute("x", l.x); it.setAttribute("y", l.y); it.setAttribute("text-anchor", l.anchor); }
      });
    });
  }
  svg.addEventListener("wheel", function (ev) {
    ev.preventDefault();
    var r = svg.getBoundingClientRect();
    var factor = Math.exp(-ev.deltaY * (ev.ctrlKey ? 0.01 : 0.0015));
    zoomAt(factor, ev.clientX - r.left, ev.clientY - r.top);
  }, { passive: false });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && document.activeElement !== input) select(null);
  });

  /* ------------------------------------------------------------- toolbar */
  function center() { var s = stageSize(); return [s[0] / 2, s[1] / 2]; }
  document.getElementById("zin").onclick = function () { var c = center(); zoomAt(1.25, c[0], c[1]); };
  document.getElementById("zout").onclick = function () { var c = center(); zoomAt(0.8, c[0], c[1]); };
  document.getElementById("zfit").onclick = function () { fit(); };
  document.querySelectorAll("#modes button").forEach(function (b) {
    b.onclick = function () {
      setMode(b.getAttribute("data-mode"));
    };
  });

  var regionBtn = document.getElementById("xregions");
  function groupCount() {
    var g = {};
    S.model.tables.forEach(function (t) { if (t.group) g[t.group] = true; });
    return Object.keys(g).length;
  }
  function setRegions(on) {
    S.regions = !!on && groupCount() > 0;
    regionBtn.classList.toggle("on", S.regions);
    regionBtn.style.display = groupCount() > 1 ? "" : "none";
    render();
    scheduleHash();
  }
  regionBtn.onclick = function () { setRegions(!S.regions); };

  /* Theme: auto (follow the OS) -> dark -> light. A viewer preference, so localStorage, not the URL hash.
   * The <head> script applies it before paint; exports always use render.js's light colours. */
  var themeBtn = document.getElementById("xtheme"), darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
  function themePref() {
    try { var t = localStorage.getItem("qdbd-theme"); return t === "light" || t === "dark" ? t : "auto"; } catch (e) { return "auto"; }
  }
  function applyTheme() {
    if (data.embed) return; // the editor sets the theme (qdbd.theme message)
    var pref = themePref(), t = pref === "auto" ? (darkQuery.matches ? "dark" : "light") : pref;
    document.documentElement.setAttribute("data-theme", t);
    themeBtn.title = "Theme: " + pref;
  }
  themeBtn.onclick = function () {
    var next = { auto: "dark", dark: "light", light: "auto" }[themePref()];
    try { if (next === "auto") localStorage.removeItem("qdbd-theme"); else localStorage.setItem("qdbd-theme", next); } catch (e) { /* private mode */ }
    applyTheme();
    showToast("Theme: " + next);
  };
  if (darkQuery.addEventListener) darkQuery.addEventListener("change", applyTheme);
  applyTheme();

  function setMode(mode) {
    S.mode = ["full", "keys", "header"].indexOf(mode) >= 0 ? mode : "full";
    document.querySelectorAll("#modes button").forEach(function (o) { o.classList.toggle("on", o.getAttribute("data-mode") === S.mode); });
    render();
    scheduleHash();
  }

  /* ------------------------------------------------------------- selection: focus + details */
  /* opts.center: pan to it. opts.quiet: don't open the details panel (only refresh it if it's already open). */
  function select(id, opts) {
    if ((id || null) !== S.focus) S.path = null;
    S.edge = null; // a table (or nothing) replaces the clicked line
    S.focus = id && byId[id] ? id : null;
    scheduleHash();
    applyFocus();
    if (S.focus && (!(opts && opts.quiet) || details.classList.contains("open"))) showDetails(S.focus);
    else closeDetails();
    markTree();
    if (S.focus && opts && opts.center) centerOn(S.focus);
  }

  /* ------------------------------------------------------------- explorer: search + table tree */
  var input = document.getElementById("q"), tree = document.getElementById("tree");
  var explorer = document.getElementById("explorer"), shut = {}, visible = [], sel = -1;
  function matches(t, q) {
    if (!q) return true;
    return t.name.toLowerCase().indexOf(q) >= 0 || t.aliases.some(function (a) { return a.toLowerCase().indexOf(q) >= 0; }) ||
      (t.group || "").toLowerCase().indexOf(q) >= 0;
  }
  function drawTree() {
    var q = input.value.trim().toLowerCase(), groups = {}, names = [];
    S.vm.tables.forEach(function (t) {
      if (!matches(t, q)) return;
      var g = t.group || "";
      if (!groups[g]) { groups[g] = []; names.push(g); }
      groups[g].push(t);
    });
    names.sort();
    var flat = names.length <= 1 && (names[0] || "") === "";
    tree.classList.toggle("flat", flat);
    visible = [];
    var html = names.map(function (g) {
      var items = groups[g].slice().sort(function (a, b) { return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1; });
      var open = q || !shut[g];
      var rows = items.map(function (t) {
        if (open) visible.push(t.id);
        return '<div class="ti" data-id="' + Q.esc(t.id) + '">' +
          (t.color ? '<i class="tdot" style="background:' + Q.esc(t.color) + '" title="' + Q.esc(t.tags.join(", ")) + '"></i>' : "") + Q.esc(t.name) +
          (t.aliases.length ? "<small>as " + Q.esc(t.aliases.join(", ")) + "</small>" : "") + "</div>";
      }).join("");
      if (flat) return rows;
      return '<div class="grp' + (open ? "" : " shut") + '" data-g="' + Q.esc(g) + '"><div class="gh"><span class="gname">' +
        Q.esc(g || "(root)") + "</span><span>" + items.length + '</span></div><div class="gl">' + rows + "</div></div>";
    }).join("");
    tree.innerHTML = html || '<div class="empty">No tables match</div>';
    sel = q && visible.length ? bestMatch(q) : -1;
    markTree();
  }
  /* Enter goes to an exact name match first, then a prefix match, then the first row. */
  function bestMatch(q) {
    var best = 0, score = -1;
    visible.forEach(function (id, i) {
      var n = byId[id].name.toLowerCase(), sc = n === q ? 3 : n.indexOf(q) === 0 ? 2 : 1;
      if (sc > score) { score = sc; best = i; }
    });
    return best;
  }
  function markTree() {
    tree.querySelectorAll(".ti").forEach(function (el) {
      var id = el.getAttribute("data-id");
      el.classList.toggle("cur", id === S.focus);
      el.classList.toggle("sel", sel >= 0 && visible[sel] === id);
    });
  }
  tree.addEventListener("click", function (ev) {
    var gh = ev.target.closest(".gh");
    if (gh) {
      var g = gh.parentNode.getAttribute("data-g");
      shut[g] = !shut[g];
      drawTree();
      return;
    }
    var ti = ev.target.closest(".ti");
    if (ti) select(ti.getAttribute("data-id"), { center: true });
  });
  input.addEventListener("input", function () { explorer.classList.remove("collapsed"); drawTree(); });
  input.addEventListener("keydown", function (ev) {
    if ((ev.key === "ArrowDown" || ev.key === "ArrowUp") && visible.length) {
      sel = Math.max(0, Math.min(visible.length - 1, sel + (ev.key === "ArrowDown" ? 1 : -1)));
      markTree();
      var el = tree.querySelector(".ti.sel");
      if (el) el.scrollIntoView({ block: "nearest" });
      ev.preventDefault();
    } else if (ev.key === "Enter" && visible.length) {
      select(visible[sel >= 0 ? sel : 0], { center: true });
    } else if (ev.key === "Escape") {
      input.value = "";
      drawTree();
      input.blur();
    }
  });
  document.getElementById("extoggle").onclick = function () { explorer.classList.toggle("collapsed"); };
  document.addEventListener("keydown", function (ev) {
    if ((ev.key === "/" || (ev.key === "f" && (ev.metaKey || ev.ctrlKey))) && document.activeElement.tagName !== "TEXTAREA" &&
        !(document.activeElement.closest && document.activeElement.closest(".CodeMirror"))) {
      ev.preventDefault();
      explorer.classList.remove("collapsed");
      input.focus();
    }
  });

  /* ------------------------------------------------------------- filter (dbt-style selectors) */
  var finput = document.getElementById("filter"), fstat = document.getElementById("fstat"), ftimer = null;
  function computeView() {
    var ids = null, err = null;
    try { ids = Q.select(S.model, S.filter); } catch (e) { err = e.message; }
    S.vm = ids ? Q.subset(S.model, ids) : S.model;
    S.shown = {};
    S.vm.tables.forEach(function (t) { S.shown[t.id] = true; });
    finput.classList.toggle("bad", !!err);
    fstat.classList.toggle("bad", !!err);
    if (err) fstat.textContent = err;
    else if (ids) fstat.innerHTML = "Showing " + ids.length + " of " + S.model.tables.length + ' tables<a id="fclear">clear</a>';
    else fstat.textContent = "";
    drawTags();
  }
  /* Tag legend: one chip per tag (header colour + count); a click filters to tag:NAME, a second click clears. */
  var tagbar = document.getElementById("tagbar");
  function drawTags() {
    var tags = S.model.tags || [];
    tagbar.style.display = tags.length ? "" : "none";
    tagbar.innerHTML = tags.map(function (g) {
      var on = S.filter.toLowerCase() === "tag:" + g.name;
      return '<button class="tchip' + (on ? " on" : "") + '" data-tag="' + Q.esc(g.name) + '" title="Show only tag:' + Q.esc(g.name) +
        '"><i style="background:' + Q.esc(g.color) + '"></i>' + Q.esc(g.name) + "<small>" + g.count + "</small></button>";
    }).join("");
  }
  tagbar.addEventListener("click", function (ev) {
    var b = ev.target.closest(".tchip");
    if (!b) return;
    var expr = "tag:" + b.getAttribute("data-tag");
    applyFilter(S.filter.toLowerCase() === expr ? "" : expr);
  });
  function applyFilter(expr, keepView) {
    S.filter = (expr || "").trim();
    if (finput.value.trim() !== S.filter) finput.value = S.filter;
    computeView();
    if (S.focus && !S.shown[S.focus]) S.focus = null;
    render();
    drawTree();
    if (S.focus) showDetails(S.focus);
    else closeDetails();
    if (!keepView) fit();
    scheduleHash();
  }
  finput.addEventListener("input", function () {
    clearTimeout(ftimer);
    ftimer = setTimeout(function () { applyFilter(finput.value); }, 350);
  });
  finput.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") { clearTimeout(ftimer); applyFilter(finput.value); }
    else if (ev.key === "Escape") { clearTimeout(ftimer); applyFilter(""); finput.blur(); }
  });
  fstat.addEventListener("click", function (ev) { if (ev.target.id === "fclear") applyFilter(""); });

  /* ------------------------------------------------------------- details panel (dbt-docs style, for relationships) */
  var details = document.getElementById("details"), dbody = document.getElementById("dbody");
  var CARD = { one: "1", many: "N", zeroOne: "0..1", zeroMany: "0..N" };
  function colName(t, cid) {
    var c = t.cols.filter(function (x) { return x.id === cid; })[0];
    return c ? c.name : cid;
  }
  function colLabel(t, cid) {
    return cid && cid !== "qdbdvirtualfield" ? Q.esc(colName(t, cid)) : "<em>table</em>";
  }
  function link(tid, cid) {
    var t = byId[tid];
    if (!t) return Q.esc(tid);
    if (!S.shown[tid]) {
      return '<span class="hidden" title="Hidden by the filter">' + Q.esc(t.name) + "</span>" +
        (cid && cid !== "qdbdvirtualfield" ? "." + Q.esc(colName(t, cid)) : "");
    }
    return '<a data-go="' + Q.esc(tid) + '">' + Q.esc(t.name) + "</a>" +
      (cid && cid !== "qdbdvirtualfield" ? "." + Q.esc(colName(t, cid)) : "");
  }
  /* mine: {t, c, card} of this table; other: the far end. */
  function refItem(t, mine, other) {
    return "<li>" + colLabel(t, mine.c) + " &rarr; " + link(other.t, other.c) +
      '<span class="card">' + CARD[mine.card] + ":" + CARD[other.card] + "</span></li>";
  }
  function backItem(t, mine, other) {
    return "<li>" + link(other.t, other.c) + " &rarr; " + colLabel(t, mine.c) +
      '<span class="card">' + CARD[other.card] + ":" + CARD[mine.card] + "</span></li>";
  }
  function showDetails(id) {
    var t = byId[id], out = [], refs = [], back = [];
    S.model.rels.forEach(function (r) {
      // "References": this table holds the many/FK side; "Referenced by": the other side points here.
      var aMany = r.a.card === "many" || r.a.card === "zeroMany", bMany = r.b.card === "many" || r.b.card === "zeroMany";
      var aIsChild = aMany || !bMany;
      var child = aIsChild ? r.a : r.b, parent = aIsChild ? r.b : r.a;
      if (child.t === id) refs.push(refItem(t, child, parent));
      if (parent.t === id) back.push(backItem(t, parent, child));
    });
    out.push("<h2>" + Q.esc(t.name) + (t.diff ? '<span class="state ' + t.diff.state + '">' +
      (t.diff.state === "added" ? "NEW" : "CHANGED") + "</span>" : "") + "</h2>");
    var meta = [];
    if (t.aliases.length) meta.push("as " + Q.esc(t.aliases.join(", ")));
    if (t.file) {
      var where = Q.esc(t.file) + ":" + t.line;
      meta.push(data.embed ? '<a class="reveal" title="Open in the editor">' + where + "</a>" : where);
    }
    if (meta.length) out.push('<div class="meta">' + meta.join(" &middot; ") + "</div>");
    if (t.tags) {
      out.push('<div class="ttags">' + t.tags.map(function (g) {
        var c = (S.model.tags || []).filter(function (x) { return x.name === g; })[0];
        return '<a class="ttag" data-tag="' + Q.esc(g) + '" style="background:' + Q.esc(c ? c.color : "#2b5797") + '">' + Q.esc(g) + "</a>";
      }).join("") + "</div>");
    }
    if (t.doc) out.push('<div class="doc">' + Q.esc(t.doc) + "</div>");
    out.push('<div class="pathbox"><input id="pathto" list="pathlist" placeholder="Path to another table…" autocomplete="off" value="' +
      (S.path && byId[S.path.to] ? Q.esc(byId[S.path.to].name) : "") + '"></div><datalist id="pathlist">' +
      S.vm.tables.filter(function (x) { return x.id !== id; }).map(function (x) { return '<option value="' + Q.esc(x.name) + '">'; }).join("") +
      '</datalist><div class="pathres" id="pathres">' + pathHtml(id) + "</div>");
    if (t.diff && t.diff.state === "changed") {
      var base = (S.model.diff && S.model.diff.base) || "base", ch = [];
      t.cols.forEach(function (c) {
        var cs = t.diff.cols[c.id];
        if (cs === "added") ch.push('<div class="chg"><span class="add">+ ' + Q.esc(c.name) + "</span></div>");
        else if (cs === "changed") {
          ch.push('<div class="chg"><span class="mod">~ ' + Q.esc(c.name) + "</span>: " +
            Q.esc((t.diff.changes[c.name] || []).join("; ")) + "</div>");
        }
      });
      (t.diff.removedCols || []).forEach(function (n) { ch.push('<div class="chg"><span class="del">- ' + Q.esc(n) + "</span></div>"); });
      out.push("<h3>Changes since " + Q.esc(base) + "</h3>" + ch.join(""));
    }
    out.push("<h3>Columns (" + t.cols.length + ")</h3><table>");
    t.cols.forEach(function (c) {
      var tags = [];
      if (c.pk) tags.push('<span class="tag pk">PK</span>');
      if (c.fk) tags.push('<span class="tag fk">FK</span>');
      c.badges.forEach(function (b) { tags.push('<span class="tag">' + Q.esc(b.t) + "</span>"); });
      (c.tags || []).forEach(function (g) {
        var tc = (S.model.tags || []).filter(function (x) { return x.name === g; })[0];
        tags.push('<a class="ttag" data-tag="' + Q.esc(g) + '" style="background:' + Q.esc(tc ? tc.color : "#2b5797") + '">' + Q.esc(g) + "</a>");
      });
      out.push('<tr><td class="cn">' + Q.esc(c.name) + " " + tags.join("") + (c.doc ? '<div class="cd">' + Q.esc(c.doc) + "</div>" : "") +
        '</td><td class="ct">' + Q.esc(c.type) + "</td></tr>");
    });
    out.push("</table>");
    out.push("<h3>References (" + refs.length + ")</h3>" + (refs.length ? "<ul>" + refs.join("") + "</ul>" : '<div class="none">None</div>'));
    out.push("<h3>Referenced by (" + back.length + ")</h3>" + (back.length ? "<ul>" + back.join("") + "</ul>" : '<div class="none">None</div>'));
    dbody.innerHTML = out.join("");
    details.classList.add("open");
    document.getElementById("stage").classList.add("has-details");
  }
  /* ------------------------------------------------------------- path finder */
  function pathHtml(id) {
    if (!S.path) return "";
    var to = byId[S.path.to];
    if (!S.path.steps) return '<div class="none">No relationship path from ' + Q.esc(byId[id].name) + " to " + Q.esc(to.name) + " (with the current filter).</div>";
    var items = S.path.steps.map(function (st) {
      var pairs = st.pairs && st.pairs.length > 1 ? st.pairs : [[st.from.c, st.to.c]]; // composite keys: every column
      return "<li>" + pairs.map(function (p) { return link(st.from.t, p[0]) + " &rarr; " + link(st.to.t, p[1]); }).join(", ") +
        '<span class="card">' + CARD[st.from.card] + ":" + CARD[st.to.card] + "</span></li>";
    }).join("");
    return "<h3>Path to " + Q.esc(to.name) + " (" + S.path.steps.length + " join" + (S.path.steps.length === 1 ? "" : "s") + ")</h3><ol>" + items +
      "</ol><pre>" + Q.esc(Q.pathSql(S.vm, id, S.path.steps)) + '</pre><div class="acts"><a id="pathsql">Copy SQL</a><a id="pathonly">Show only this path</a><a id="pathclear">Clear</a></div>';
  }
  function findPathTo(name) {
    var target = null;
    S.vm.tables.forEach(function (t) { if (t.name.toLowerCase() === String(name).trim().toLowerCase()) target = t.id; });
    if (!S.focus || !target || target === S.focus) return false;
    S.path = { to: target, steps: Q.findPath(S.vm, S.focus, target) };
    showDetails(S.focus);
    applyFocus();
    if (S.path.steps && !applyingHash) fit([S.focus].concat(S.path.steps.map(function (st) { return st.to.t; })));
    scheduleHash();
    return true;
  }
  dbody.addEventListener("keydown", function (ev) {
    if (ev.target.id === "pathto" && ev.key === "Enter") findPathTo(ev.target.value);
    if (ev.target.id === "pathto" && ev.key === "Escape") ev.stopPropagation();
  });
  dbody.addEventListener("change", function (ev) { if (ev.target.id === "pathto") findPathTo(ev.target.value); });
  dbody.addEventListener("click", function (ev) {
    if (ev.target.id === "pathclear") { S.path = null; showDetails(S.focus); applyFocus(); scheduleHash(); }
    else if (ev.target.id === "pathonly" && S.path && S.path.steps) {
      var names = [byId[S.focus].name].concat(S.path.steps.map(function (st) { return byId[st.to.t].name; }));
      // Selector syntax treats spaces, commas, + and a leading ! specially; match those characters with "?".
      applyFilter(names.map(function (n) { return n.replace(/[\s,+!]/g, "?"); }).join(" "));
    } else if (ev.target.id === "pathsql" && S.path && S.path.steps) {
      copyText(Q.pathSql(S.vm, S.focus, S.path.steps), "SQL copied", dbody.querySelector("#pathres pre"));
    }
  });

  function closeDetails() {
    details.classList.remove("open");
    document.getElementById("stage").classList.remove("has-details");
  }
  dbody.addEventListener("click", function (ev) {
    var a = ev.target.closest("a[data-go]");
    if (a) select(a.getAttribute("data-go"), { center: true });
    var tg = ev.target.closest("a.ttag");
    if (tg) applyFilter("tag:" + tg.getAttribute("data-tag"));
  });
  document.getElementById("dclose").onclick = function () { select(null); };

  /* ------------------------------------------------------------- minimap */
  var mini = document.getElementById("mini"), miniB = null;
  function drawMinimap() {
    miniB = Q.bounds(S.vm, S.pos, S.mode);
    var pad = 40, b = miniB;
    mini.setAttribute("viewBox", (b[0] - pad) + " " + (b[1] - pad) + " " + (b[2] - b[0] + 2 * pad) + " " + (b[3] - b[1] + 2 * pad));
    var geo = Q.geometry(S.vm, S.mode), parts = [];
    S.vm.tables.forEach(function (t) {
      var p = S.pos[t.id];
      if (p) parts.push('<rect x="' + p[0] + '" y="' + p[1] + '" width="' + geo[t.id].w + '" height="' + geo[t.id].h + '" fill="' + (t.color || "#2b5797") + '" opacity=".55"/>');
    });
    parts.push('<rect class="vpr" id="vpr"/>');
    mini.innerHTML = parts.join("");
    drawViewportRect();
  }
  function drawViewportRect() {
    var r = document.getElementById("vpr");
    if (!r) return;
    var sz = stageSize(), v = S.view;
    r.setAttribute("x", -v.x / v.k);
    r.setAttribute("y", -v.y / v.k);
    r.setAttribute("width", sz[0] / v.k);
    r.setAttribute("height", sz[1] / v.k);
  }
  function miniPan(ev) {
    var pt = mini.createSVGPoint();
    pt.x = ev.clientX;
    pt.y = ev.clientY;
    var m = pt.matrixTransform(mini.getScreenCTM().inverse()), sz = stageSize();
    S.view.x = sz[0] / 2 - m.x * S.view.k;
    S.view.y = sz[1] / 2 - m.y * S.view.k;
    applyView();
  }
  var miniDrag = false;
  mini.addEventListener("pointerdown", function (ev) {
    miniDrag = true;
    try { mini.setPointerCapture(ev.pointerId); } catch (e) { /* synthetic event */ }
    miniPan(ev);
  });
  mini.addEventListener("pointermove", function (ev) { if (miniDrag) miniPan(ev); });
  mini.addEventListener("pointerup", function () { miniDrag = false; });

  /* ------------------------------------------------------------- export */
  function download(name, blob) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  function exportSvg() {
    var only = S.focus ? Object.keys(neighbours(S.focus)) : null;
    return Q.renderSvg(S.vm, S.pos, { mode: S.mode, only: only, regions: S.regions, fontCss: document.getElementById("qdbd-font").textContent });
  }
  document.getElementById("xsvg").onclick = function () {
    download((data.title || "diagram") + ".svg", new Blob([exportSvg()], { type: "image/svg+xml" }));
  };
  document.getElementById("xdrawio").onclick = function () {
    var only = S.focus ? Object.keys(neighbours(S.focus)) : null;
    var xml = Q.renderDrawio(S.vm, S.pos, { mode: S.mode, only: only, title: data.title || "ERD", regions: S.regions });
    download((data.title || "diagram") + ".drawio", new Blob([xml], { type: "application/xml" }));
  };
  document.getElementById("xpng").onclick = function () {
    var text = exportSvg();
    var m = /width="([\d.]+)" height="([\d.]+)"/.exec(text);
    var w = +m[1], h = +m[2], scale = Math.min(2, 16000 / Math.max(w, h));
    var img = new Image();
    img.onload = function () {
      var c = document.createElement("canvas");
      c.width = Math.round(w * scale);
      c.height = Math.round(h * scale);
      var ctx = c.getContext("2d");
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0, w, h);
      c.toBlob(function (b) { download((data.title || "diagram") + ".png", b); }, "image/png");
    };
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(text);
  };

  /* ------------------------------------------------------------- embed: the VS Code preview (qdbd serve --embed)
   * The page sits in an iframe inside a webview. It posts qdbd.ready / qdbd.reveal {file, line} to the parent and
   * takes qdbd.focus {table} and qdbd.theme {theme}. Downloads and the clipboard don't work there, so the
   * extension's commands replace the export, link and theme buttons. */
  if (data.embed) {
    ["xsvg", "xpng", "xdrawio", "xlink", "xtheme"].forEach(function (id) { document.getElementById(id).style.display = "none"; });
    window.qdbdServe = {
      saveLayout: function (body) {
        fetch("layout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      },
    };
    var reveal = function (id) {
      var t = byId[id];
      if (t && t.file) window.parent.postMessage({ type: "qdbd.reveal", file: t.file, line: t.line }, "*");
    };
    svg.addEventListener("dblclick", function (ev) {
      var g = ev.target.closest(".t");
      if (g) reveal(g.getAttribute("data-id"));
    });
    dbody.addEventListener("click", function (ev) { if (ev.target.closest("a.reveal")) reveal(S.focus); });
    window.addEventListener("message", function (ev) {
      var m = ev.data;
      if (ev.source !== window.parent || !m) return;
      if (m.type === "qdbd.focus") {
        var t = S.model.tables.filter(function (x) { return x.name === m.table; })[0];
        // Follows the editor's cursor: highlight and pan, but don't cover the diagram with the details panel.
        if (t && t.id !== S.focus && S.shown[t.id]) select(t.id, { center: true, quiet: true });
      } else if (m.type === "qdbd.theme") {
        document.documentElement.setAttribute("data-theme", m.theme === "dark" ? "dark" : "light");
      }
    });
    window.parent.postMessage({ type: "qdbd.ready" }, "*");
  }

  /* ------------------------------------------------------------- public API (serve mode) */
  window.qdbdViewer = {
    setData: function (model, positions) {
      S.model = model;
      S.pos = positions;
      index();
      computeView();
      render();
      applyView();
      drawTree();
      drawDiffBar(); // serve --diff-base: the counts change as you edit
      if (S.focus && byId[S.focus]) showDetails(S.focus);
      else select(null);
    },
    state: S,
  };

  index();
  if (S.serve) document.body.classList.add("serve");
  if (stageSize()[0] < 900) explorer.classList.add("collapsed"); // small screens / embedded frames
  regionBtn.classList.toggle("on", S.regions);
  regionBtn.style.display = groupCount() > 1 ? "" : "none";
  computeView();
  render();
  drawTree();
  /* ------------------------------------------------------------- diff banner (build --diff-base) */
  function drawDiffBar() {
    var bar = document.getElementById("diffbar"), d = S.model.diff;
    if (!d) { bar.classList.remove("open"); return; }
    var removed = d.removed || [];
    bar.innerHTML = "Changes since <code>" + Q.esc(d.base) + "</code>: " +
      '<b class="add">' + d.added + " new</b> &middot; " + '<b class="chg">' + d.changed + " changed</b> &middot; " +
      '<b class="del" title="' + Q.esc(removed.join(", ") || "none") + '">' + removed.length + " removed</b>" +
      " &middot; relationships +" + d.relsAdded.length + " / -" + d.relsRemoved.length +
      (d.added + d.changed ? '<a id="diffonly">Show changes</a>' : "");
    bar.classList.add("open");
  }
  document.getElementById("diffbar").addEventListener("click", function (ev) {
    if (ev.target.id === "diffonly") applyFilter("diff:modified+1 +diff:modified");
  });
  drawDiffBar();

  /* ------------------------------------------------------------- shareable links
   * The URL hash holds the view: #f=<filter>&t=<table>&m=<mode>&z=<zoom>&c=<x>,<y> (centre, diagram coords).
   * It is kept up to date with history.replaceState, so copying the address bar shares exactly this view. */
  var hashTimer = null, applyingHash = false;
  function scheduleHash() {
    if (applyingHash) return;
    clearTimeout(hashTimer);
    hashTimer = setTimeout(writeHash, 250);
  }
  function currentHash() {
    var p = new URLSearchParams(), v = S.view, sz = stageSize();
    if (S.filter) p.set("f", S.filter);
    if (S.focus && byId[S.focus]) p.set("t", byId[S.focus].name);
    if (S.path && byId[S.path.to]) p.set("p", byId[S.path.to].name);
    if (S.mode !== "full") p.set("m", S.mode);
    if (S.regions !== !!S.model.regions) p.set("r", S.regions ? "1" : "0");
    p.set("z", String(Math.round(v.k * 1000) / 1000));
    p.set("c", Math.round((sz[0] / 2 - v.x) / v.k) + "," + Math.round((sz[1] / 2 - v.y) / v.k));
    return "#" + p.toString();
  }
  function writeHash() {
    var h = currentHash();
    if (location.hash !== h) {
      try { history.replaceState(null, "", h); } catch (e) { /* sandboxed iframe */ }
    }
  }
  function readHash() {
    var raw = location.hash.replace(/^#/, "");
    if (!raw) return false;
    var p = new URLSearchParams(raw);
    applyingHash = true;
    try {
      if (p.has("m")) setMode(p.get("m"));
      if (p.has("r")) setRegions(p.get("r") === "1");
      if ((p.get("f") || "") !== S.filter) applyFilter(p.get("f") || "", true); // else already rendered
      var name = p.get("t"), id = null;
      if (name) S.model.tables.forEach(function (t) { if (t.name === name) id = t.id; });
      select(id && S.shown[id] ? id : null);
      if (p.get("p") && S.focus) findPathTo(p.get("p"));
      var z = parseFloat(p.get("z")), c = (p.get("c") || "").split(",").map(Number);
      if (z > 0 && c.length === 2 && !isNaN(c[0]) && !isNaN(c[1])) {
        var sz = stageSize();
        S.view = { k: Math.min(4, Math.max(0.03, z)), x: sz[0] / 2 - c[0] * z, y: sz[1] / 2 - c[1] * z };
        applyView();
      } else if (id) centerOn(id);
      else fit();
    } finally {
      applyingHash = false;
    }
    return true;
  }
  window.addEventListener("hashchange", function () { if (location.hash !== currentHash()) readHash(); });

  var toast = document.getElementById("toast"), toastTimer = null;
  function showToast(text) {
    toast.textContent = text;
    toast.classList.add("open");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("open"); }, 1800);
  }
  document.getElementById("xlink").onclick = function () {
    writeHash();
    var url = location.href;
    function fallback() { window.prompt("Copy this link:", url); }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(url).then(function () { showToast("Link copied: this exact view"); }, fallback);
    } else fallback();
  };

  if (!readHash()) {
    if (S.model.zoom) {
      var k = S.model.zoom / 100, p0 = S.model.position || [0, 0];
      S.view = { k: k, x: -p0[0] * k, y: -p0[1] * k };
      applyView();
      if (!S.model.position) fit();
    } else {
      fit();
    }
  }
  window.addEventListener("resize", drawViewportRect);
})();
