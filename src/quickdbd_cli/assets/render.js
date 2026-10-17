/* qdbd renderer: pure functions, model + positions -> SVG markup.
 * Runs in the browser (viewer) and inside V8 from Python (CLI export), so the page,
 * the SVG and the PNG are drawn by the same code. No DOM access here. */
(function (root) {
  "use strict";

  var C = {
    bg: "#f4f5f4",
    header: "#2b5797",
    headerText: "#ffffff",
    body: "#ffffff",
    border: "#dfe3e8",
    text: "#333333",
    pk: "#2b5797",
    fk: "#222222",
    type: "#9a9a9a",
    key: "#b0b0b0",
    badgeBg: "#eef1f5",
    badgeText: "#7a8899",
    edge: "#b8bcc2",
  };
  var FONT = "Inter, 'Helvetica Neue', Helvetica, Arial, sans-serif";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function n(v) { return Math.round(v * 100) / 100; }

  function relatedColumns(model) {
    var set = {};
    model.rels.forEach(function (r) {
      set[r.a.t + "\u0000" + r.a.c] = true;
      set[r.b.t + "\u0000" + r.b.c] = true;
    });
    return set;
  }

  /* Visible columns of each table for a collapse mode: "full" | "keys" | "header". */
  function geometry(model, mode) {
    var st = model.style, rel = mode === "keys" ? relatedColumns(model) : null, out = {};
    model.tables.forEach(function (t) {
      var cols = [];
      if (mode !== "header") {
        t.cols.forEach(function (c) {
          if (mode === "full" || c.pk || c.fk || rel[t.id + "\u0000" + c.id]) cols.push(c);
        });
      }
      var rows = {};
      cols.forEach(function (c, i) { rows[c.id] = i; });
      out[t.id] = {
        cols: cols,
        rows: rows,
        w: t.w,
        h: st.headerH + cols.length * st.rowH + (cols.length ? st.bottomPad : 0),
      };
    });
    return out;
  }

  function keyIcon(x, cy) {
    return '<g stroke="' + C.key + '" stroke-width="1.5" fill="none">' +
      '<circle cx="' + n(x + 3.5) + '" cy="' + n(cy) + '" r="3"/>' +
      '<path d="M' + n(x + 6.5) + " " + n(cy) + "h7m-2 0v3m-2.5-3v2" + '"/></g>';
  }

  /* Dotted underline marking text that has a doc comment (interactive viewer only). */
  function docMark(x, y, w, color) {
    return '<line class="dm" x1="' + n(x) + '" y1="' + n(y) + '" x2="' + n(x + w) + '" y2="' + n(y) +
      '" stroke="' + color + '" stroke-width="1" stroke-dasharray="1.5 2"/>';
  }

  function renderTable(model, t, g, p, docMarks) {
    var st = model.style, w = g.w, h = g.h, out = [];
    out.push('<g class="t" data-id="' + esc(t.id) + '" transform="translate(' + n(p[0]) + "," + n(p[1]) + ')">');
    out.push('<rect class="tb" width="' + w + '" height="' + h + '" rx="2" fill="' + C.body + '" stroke="' + C.border + '"/>');
    out.push('<path class="th" d="M0 2a2 2 0 0 1 2-2h' + (w - 4) + "a2 2 0 0 1 2 2v" + (st.headerH - 2) + "h-" + w + 'z" fill="' + C.header + '"/>');
    out.push('<text x="' + st.padX + '" y="' + n(st.headerH / 2 + st.headerSize * 0.36) + '" fill="' + C.headerText +
      '" font-family="' + FONT + '" font-size="' + st.headerSize + '">' + esc(t.name) + "</text>");
    if (docMarks && t.doc) {
      out.push(docMark(st.padX, st.headerH / 2 + st.headerSize * 0.36 + 3, t.nameW, "rgba(255,255,255,.7)"));
    }
    g.cols.forEach(function (c, i) {
      var y = st.headerH + i * st.rowH, cy = y + st.rowH / 2, base = n(cy + st.rowSize * 0.36);
      var weight = c.pk || c.fk ? ' font-weight="bold"' : "";
      var color = c.pk ? C.pk : c.fk ? C.fk : C.text;
      out.push('<g class="r" data-c="' + esc(c.id) + '">');
      out.push('<rect class="rb" y="' + y + '" width="' + w + '" height="' + st.rowH + '" fill="' + C.body + '" fill-opacity="0"/>');
      out.push('<text x="' + st.padX + '" y="' + base + '" fill="' + color + '" font-family="' + FONT + '" font-size="' +
        st.rowSize + '"' + weight + ">" + esc(c.name) + "</text>");
      if (docMarks && c.doc) out.push(docMark(st.padX, cy + st.rowSize * 0.36 + 2.5, c.nameW, color));
      var bx = st.padX + c.nameW + 6;
      c.badges.forEach(function (b) {
        var bh = st.badgeSize + 5;
        out.push('<rect x="' + n(bx) + '" y="' + n(cy - bh / 2) + '" width="' + n(b.w) + '" height="' + bh + '" rx="3" fill="' + C.badgeBg + '"/>');
        out.push('<text x="' + n(bx + st.badgePad) + '" y="' + n(cy + st.badgeSize * 0.36) + '" fill="' + C.badgeText +
          '" font-family="' + FONT + '" font-size="' + st.badgeSize + '">' + esc(b.t) + "</text>");
        bx += b.w + st.badgeGap;
      });
      if (c.pk) out.push(keyIcon(w - st.padX - c.typeW - st.keyW + 1, cy));
      out.push('<text x="' + (w - st.padX) + '" y="' + base + '" text-anchor="end" fill="' + C.type + '" font-family="' + FONT +
        '" font-size="' + st.rowSize + '">' + esc(c.type) + "</text>");
      out.push("</g>");
    });
    out.push("</g>");
    return out.join("");
  }

  function anchorY(model, g, p, colId) {
    var st = model.style, i = g.rows[colId];
    if (i === undefined) return p[1] + st.headerH / 2;
    return p[1] + st.headerH + i * st.rowH + st.rowH / 2;
  }

  /* Pick sides: facing sides when tables are apart horizontally, both right when stacked. */
  function edgeGeom(model, geo, pos, r) {
    var ga = geo[r.a.t], gb = geo[r.b.t], pa = pos[r.a.t], pb = pos[r.b.t];
    if (!ga || !gb || !pa || !pb) return null;
    var ya = anchorY(model, ga, pa, r.a.c), yb = anchorY(model, gb, pb, r.b.c);
    var da, db;
    var overlap = pa[0] < pb[0] + gb.w + 30 && pb[0] < pa[0] + ga.w + 30;
    if (r.a.t === r.b.t || overlap) { da = 1; db = 1; }
    else if (pa[0] + ga.w / 2 < pb[0] + gb.w / 2) { da = 1; db = -1; }
    else { da = -1; db = 1; }
    var xa = da > 0 ? pa[0] + ga.w : pa[0], xb = db > 0 ? pb[0] + gb.w : pb[0];
    var off;
    if (da === db) off = 40 + Math.min(160, Math.abs(ya - yb) * 0.25) + Math.max(0, (da > 0 ? Math.max(xa, xb) - Math.min(xa, xb) : 0));
    else off = Math.max(40, Math.abs(xb - xa) / 2);
    var offA = off, offB = off;
    if (da === db && da > 0) { offA = off - (Math.max(xa, xb) - xa); offB = off - (Math.max(xa, xb) - xb); offA = Math.max(offA, 40); offB = Math.max(offB, 40); }
    var d = "M" + n(xa) + " " + n(ya) + "C" + n(xa + da * offA) + " " + n(ya) + " " + n(xb + db * offB) + " " + n(yb) + " " + n(xb) + " " + n(yb);
    return { d: d, xa: xa, ya: ya, da: da, xb: xb, yb: yb, db: db };
  }

  function marker(card, x, y, dir) {
    var s = [], st = ' stroke="' + C.edge + '" stroke-width="1.2" fill="none"';
    function bar(o) { s.push('<path d="M' + n(x + dir * o) + " " + n(y - 6) + "v12" + '"' + st + "/>"); }
    function crow() {
      s.push('<path d="M' + n(x + dir * 11) + " " + n(y) + "L" + n(x) + " " + n(y - 6) + "M" + n(x + dir * 11) + " " + n(y) + "L" + n(x) + " " + n(y + 6) + '"' + st + "/>");
    }
    function circle(o) {
      s.push('<circle cx="' + n(x + dir * o) + '" cy="' + n(y) + '" r="3.5" fill="' + C.bg + '" stroke="' + C.edge + '" stroke-width="1.2"/>');
    }
    if (card === "one") { bar(7); }
    else if (card === "many") { crow(); }
    else if (card === "zeroOne") { bar(6); circle(14); }
    else if (card === "zeroMany") { crow(); circle(16); }
    return s.join("");
  }

  function renderEdge(model, geo, pos, r) {
    var e = edgeGeom(model, geo, pos, r);
    if (!e) return "";
    return '<g class="e" data-a="' + esc(r.a.t) + '" data-ac="' + esc(r.a.c) + '" data-b="' + esc(r.b.t) + '" data-bc="' + esc(r.b.c) + '">' +
      '<path class="ep" d="' + e.d + '" stroke="' + C.edge + '" stroke-width="1.2" fill="none"/>' +
      marker(r.a.card, e.xa, e.ya, e.da) + marker(r.b.card, e.xb, e.yb, e.db) + "</g>";
  }

  function subset(model, only) {
    if (!only) return model;
    var keep = {};
    only.forEach(function (id) { keep[id] = true; });
    return {
      style: model.style,
      tables: model.tables.filter(function (t) { return keep[t.id]; }),
      rels: model.rels.filter(function (r) { return keep[r.a.t] && keep[r.b.t]; }),
    };
  }

  function renderEdges(model, pos, mode, geo) {
    geo = geo || geometry(model, mode);
    return model.rels.map(function (r) { return renderEdge(model, geo, pos, r); }).join("");
  }

  /* opts.docMarks: underline tables/columns that have doc comments (viewer only, not exports). */
  function renderInner(model, pos, mode, opts) {
    var geo = geometry(model, mode), marks = !!(opts && opts.docMarks);
    var tables = model.tables.map(function (t) { return pos[t.id] ? renderTable(model, t, geo[t.id], pos[t.id], marks) : ""; }).join("");
    return '<g class="edges">' + renderEdges(model, pos, mode, geo) + '</g><g class="tables">' + tables + "</g>";
  }

  function bounds(model, pos, mode) {
    var geo = geometry(model, mode), b = null;
    model.tables.forEach(function (t) {
      var p = pos[t.id];
      if (!p) return;
      var g = geo[t.id];
      if (!b) b = [p[0], p[1], p[0] + g.w, p[1] + g.h];
      else b = [Math.min(b[0], p[0]), Math.min(b[1], p[1]), Math.max(b[2], p[0] + g.w), Math.max(b[3], p[1] + g.h)];
    });
    return b || [0, 0, 100, 100];
  }

  /* Standalone SVG document. opts: {mode, only: [ids], fontCss, pad} */
  function renderSvg(model, pos, opts) {
    opts = opts || {};
    var mode = opts.mode || "full", m = subset(model, opts.only), pad = opts.pad == null ? 40 : opts.pad;
    var edgePad = 60;
    var b = bounds(m, pos, mode);
    var x0 = b[0] - pad - edgePad, y0 = b[1] - pad, w = b[2] - b[0] + 2 * (pad + edgePad), h = b[3] - b[1] + 2 * pad;
    var style = opts.fontCss ? "<style>" + opts.fontCss + "</style>" : "";
    return '<svg xmlns="http://www.w3.org/2000/svg" width="' + n(w) + '" height="' + n(h) + '" viewBox="' + n(x0) + " " + n(y0) + " " + n(w) + " " + n(h) + '">' +
      style + '<rect x="' + n(x0) + '" y="' + n(y0) + '" width="' + n(w) + '" height="' + n(h) + '" fill="' + C.bg + '"/>' +
      renderInner(m, pos, mode) + "</svg>";
  }

  /* Tables within `depth` relationship hops of `focus`. */
  function neighbourhood(model, focus, depth) {
    var adj = {};
    model.rels.forEach(function (r) {
      (adj[r.a.t] = adj[r.a.t] || []).push(r.b.t);
      (adj[r.b.t] = adj[r.b.t] || []).push(r.a.t);
    });
    var seen = {}, frontier = [focus], out = [focus];
    seen[focus] = true;
    for (var d = 0; d < depth; d++) {
      var next = [];
      frontier.forEach(function (id) {
        (adj[id] || []).forEach(function (o) { if (!seen[o]) { seen[o] = true; next.push(o); out.push(o); } });
      });
      frontier = next;
    }
    return out;
  }

  root.qdbd = {
    colors: C,
    geometry: geometry,
    renderTable: renderTable,
    renderEdges: renderEdges,
    renderInner: renderInner,
    renderSvg: renderSvg,
    bounds: bounds,
    neighbourhood: neighbourhood,
    esc: esc,
  };
  root.qdbdRenderSvg = renderSvg;
  root.qdbdNeighbourhood = neighbourhood;
})(typeof window !== "undefined" ? window : globalThis);
