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
    vp.innerHTML = Q.renderInner(S.model, S.pos, S.mode);
    applyFocus();
    drawMinimap();
  }

  function renderEdges() {
    var g = vp.querySelector(".edges");
    if (g) g.innerHTML = Q.renderEdges(S.model, S.pos, S.mode);
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
    var b = Q.bounds(S.model, S.pos, S.mode), sz = stageSize(), pad = 40;
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
    var g = Q.geometry(S.model, S.mode)[id], sz = stageSize();
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
    S.model.rels.forEach(function (r) {
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
  vp.addEventListener("mouseleave", clearHover);

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
      S.focus = d.table && S.focus !== d.table ? d.table : null;
      applyFocus();
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
    if (ev.key === "Escape") { S.focus = null; applyFocus(); }
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

  /* ------------------------------------------------------------- search */
  var input = document.getElementById("q"), results = document.getElementById("results"), sel = 0, hits = [];
  function search() {
    var q = input.value.trim().toLowerCase();
    hits = !q ? [] : S.model.tables.filter(function (t) {
      return t.name.toLowerCase().indexOf(q) >= 0 || t.aliases.some(function (a) { return a.toLowerCase().indexOf(q) >= 0; });
    }).slice(0, 50);
    sel = 0;
    results.innerHTML = hits.map(function (t, i) {
      return '<div data-i="' + i + '"' + (i === 0 ? ' class="sel"' : "") + ">" + Q.esc(t.name) +
        (t.aliases.length ? "<small>as " + Q.esc(t.aliases.join(", ")) + "</small>" : "") + "</div>";
    }).join("");
    results.classList.toggle("open", hits.length > 0);
  }
  function pick(i) {
    var t = hits[i];
    if (!t) return;
    results.classList.remove("open");
    input.blur();
    centerOn(t.id);
  }
  input.addEventListener("input", search);
  input.addEventListener("keydown", function (ev) {
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      sel = Math.max(0, Math.min(hits.length - 1, sel + (ev.key === "ArrowDown" ? 1 : -1)));
      results.querySelectorAll("div").forEach(function (d, i) { d.classList.toggle("sel", i === sel); });
      ev.preventDefault();
    } else if (ev.key === "Enter") pick(sel);
    else if (ev.key === "Escape") { input.value = ""; search(); input.blur(); }
  });
  results.addEventListener("mousedown", function (ev) {
    var d = ev.target.closest("div[data-i]");
    if (d) pick(+d.getAttribute("data-i"));
  });
  document.addEventListener("keydown", function (ev) {
    if ((ev.key === "/" || (ev.key === "f" && (ev.metaKey || ev.ctrlKey))) && document.activeElement.tagName !== "TEXTAREA" &&
        !(document.activeElement.closest && document.activeElement.closest(".CodeMirror"))) {
      ev.preventDefault();
      input.focus();
    }
  });

  /* ------------------------------------------------------------- minimap */
  var mini = document.getElementById("mini"), miniB = null;
  function drawMinimap() {
    miniB = Q.bounds(S.model, S.pos, S.mode);
    var pad = 40, b = miniB;
    mini.setAttribute("viewBox", (b[0] - pad) + " " + (b[1] - pad) + " " + (b[2] - b[0] + 2 * pad) + " " + (b[3] - b[1] + 2 * pad));
    var geo = Q.geometry(S.model, S.mode), parts = [];
    S.model.tables.forEach(function (t) {
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
    return Q.renderSvg(S.model, S.pos, { mode: S.mode, only: only, fontCss: data.fontCss });
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
      render();
      applyView();
    },
    state: S,
  };

  index();
  if (S.serve) document.body.classList.add("serve");
  render();
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
