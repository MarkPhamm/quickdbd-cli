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
    vp.innerHTML = Q.renderInner(S.vm, S.pos, S.mode, { docMarks: true });
    applyFocus();
    drawMinimap();
  }

  function renderEdges() {
    var g = vp.querySelector(".edges");
    if (g) g.innerHTML = Q.renderEdges(S.vm, S.pos, S.mode);
    applyFocus();
  }

  function applyView() {
    var v = S.view;
    vp.setAttribute("transform", "translate(" + v.x + "," + v.y + ") scale(" + v.k + ")");
    zoomval.textContent = Math.round(v.k * 100) + "%";
    drawViewportRect();
  }

  function stageSize() {
    var r = svg.getBoundingClientRect();
    return [r.width || 800, r.height || 600];
  }

  function fit() {
    var b = Q.bounds(S.vm, S.pos, S.mode), sz = stageSize(), pad = 40;
    var k = Math.min((sz[0] - 2 * pad) / (b[2] - b[0]), (sz[1] - 2 * pad) / (b[3] - b[1]), 1.5);
    k = Math.max(k, 0.05);
    S.view = { k: k, x: (sz[0] - (b[2] - b[0]) * k) / 2 - b[0] * k, y: (sz[1] - (b[3] - b[1]) * k) / 2 - b[1] * k };
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
  vp.addEventListener("mouseleave", function () { clearHover(); hideTip(); });

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
    drag = { sx: ev.clientX, sy: ev.clientY, moved: false, table: tEl ? tEl.getAttribute("data-id") : null, el: tEl };
    if (drag.table && S.serve) {
      drag.start = S.pos[drag.table].slice();
    } else {
      drag.view = { x: S.view.x, y: S.view.y };
      svg.classList.add("panning");
    }
    svg.setPointerCapture(ev.pointerId);
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
      if (!raf) raf = requestAnimationFrame(function () { raf = null; renderEdges(); });
    } else if (drag.view) {
      S.view.x = drag.view.x + dx;
      S.view.y = drag.view.y + dy;
      applyView();
    }
  });
  svg.addEventListener("pointerup", function () {
    if (!drag) return;
    svg.classList.remove("panning");
    var d = drag;
    drag = null;
    if (!d.moved) {
      select(d.table && S.focus !== d.table ? d.table : null);
      return;
    }
    if (d.start) {
      drawMinimap();
      var name = byId[d.table].name, body = {};
      body[name] = S.pos[d.table];
      if (window.qdbdServe) window.qdbdServe.saveLayout(body);
    }
  });
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
  document.getElementById("zfit").onclick = fit;
  document.querySelectorAll("#modes button").forEach(function (b) {
    b.onclick = function () {
      S.mode = b.getAttribute("data-mode");
      document.querySelectorAll("#modes button").forEach(function (o) { o.classList.toggle("on", o === b); });
      render();
    };
  });

  /* ------------------------------------------------------------- selection: focus + details */
  function select(id, opts) {
    S.focus = id && byId[id] ? id : null;
    applyFocus();
    if (S.focus) showDetails(S.focus);
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
        return '<div class="ti" data-id="' + Q.esc(t.id) + '">' + Q.esc(t.name) +
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
  }
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
    if (window.qdbdOnState) window.qdbdOnState();
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
    out.push("<h2>" + Q.esc(t.name) + "</h2>");
    var meta = [];
    if (t.aliases.length) meta.push("as " + Q.esc(t.aliases.join(", ")));
    if (t.file) meta.push(Q.esc(t.file) + ":" + t.line);
    if (meta.length) out.push('<div class="meta">' + meta.join(" &middot; ") + "</div>");
    if (t.doc) out.push('<div class="doc">' + Q.esc(t.doc) + "</div>");
    out.push("<h3>Columns (" + t.cols.length + ")</h3><table>");
    t.cols.forEach(function (c) {
      var tags = [];
      if (c.pk) tags.push('<span class="tag pk">PK</span>');
      if (c.fk) tags.push('<span class="tag fk">FK</span>');
      c.badges.forEach(function (b) { tags.push('<span class="tag">' + Q.esc(b.t) + "</span>"); });
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
  function closeDetails() {
    details.classList.remove("open");
    document.getElementById("stage").classList.remove("has-details");
  }
  dbody.addEventListener("click", function (ev) {
    var a = ev.target.closest("a[data-go]");
    if (a) select(a.getAttribute("data-go"), { center: true });
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
      if (p) parts.push('<rect x="' + p[0] + '" y="' + p[1] + '" width="' + geo[t.id].w + '" height="' + geo[t.id].h + '" fill="#2b5797" opacity=".55"/>');
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
  mini.addEventListener("pointerdown", function (ev) { miniDrag = true; mini.setPointerCapture(ev.pointerId); miniPan(ev); });
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
    return Q.renderSvg(S.vm, S.pos, { mode: S.mode, only: only, fontCss: document.getElementById("qdbd-font").textContent });
  }
  document.getElementById("xsvg").onclick = function () {
    download((data.title || "diagram") + ".svg", new Blob([exportSvg()], { type: "image/svg+xml" }));
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
      if (S.focus && byId[S.focus]) showDetails(S.focus);
      else select(null);
    },
    state: S,
  };

  index();
  if (S.serve) document.body.classList.add("serve");
  computeView();
  render();
  drawTree();
  if (S.model.zoom) {
    var k = S.model.zoom / 100, p = S.model.position || [0, 0];
    S.view = { k: k, x: -p[0] * k, y: -p[1] * k };
    applyView();
    if (!S.model.position) fit();
  } else {
    fit();
  }
  window.addEventListener("resize", drawViewportRect);
})();
