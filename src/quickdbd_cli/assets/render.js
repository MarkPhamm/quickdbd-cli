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
    added: "#2e7d32",
    changed: "#d48806",
  };
  var FONT = "Inter, 'Helvetica Neue', Helvetica, Arial, sans-serif";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function n(v) { return Math.round(v * 100) / 100; }

  /* Relative luminance above 0.45: only pale colours. Every built-in header, diff and tag colour is below it. */
  function isLight(hex) {
    var m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex || "");
    if (!m) return false;
    var h = m[1].length === 3 ? m[1].replace(/./g, "$&$&") : m[1];
    var lum = [0, 2, 4].map(function (i) {
      var c = parseInt(h.substr(i, 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * lum[0] + 0.7152 * lum[1] + 0.0722 * lum[2] > 0.45;
  }

  function relatedColumns(model) {
    var set = {};
    model.rels.forEach(function (r) {
      set[r.a.t + "\u0000" + r.a.c] = true;
      set[r.b.t + "\u0000" + r.b.c] = true;
    });
    return set;
  }

  /* Visible columns of each table for a collapse mode: "full" | "keys" | "header". Tagged columns count as keys. */
  function geometry(model, mode) {
    var st = model.style, rel = mode === "keys" ? relatedColumns(model) : null, out = {};
    model.tables.forEach(function (t) {
      var cols = [];
      if (mode !== "header") {
        t.cols.forEach(function (c) {
          if (mode === "full" || c.pk || c.fk || c.color || rel[t.id + "\u0000" + c.id]) cols.push(c);
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
    return '<g class="ki" stroke="' + C.key + '" stroke-width="1.5" fill="none">' +
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
    var state = t.diff && t.diff.state, hcol = state === "added" ? C.added : state === "changed" ? C.changed : t.color || C.header;
    out.push('<path class="th" d="M0 2a2 2 0 0 1 2-2h' + (w - 4) + "a2 2 0 0 1 2 2v" + (st.headerH - 2) + "h-" + w + 'z" fill="' + hcol + '"/>');
    if (state) {
      out.push('<text x="' + (w - st.padX) + '" y="' + n(st.headerH / 2 + 4) + '" text-anchor="end" fill="#fff" font-family="' + FONT +
        '" font-size="10" font-weight="bold">' + (state === "added" ? "NEW" : "CHANGED") + "</text>");
    }
    var light = isLight(hcol); // a pale DBML headercolor or tag colour: dark text on it
    out.push('<text class="tn" x="' + st.padX + '" y="' + n(st.headerH / 2 + st.headerSize * 0.36) + '" fill="' + (light ? C.text : C.headerText) +
      '" font-family="' + FONT + '" font-size="' + st.headerSize + '">' + esc(t.name) + "</text>");
    if (docMarks && t.doc) {
      out.push(docMark(st.padX, st.headerH / 2 + st.headerSize * 0.36 + 3, t.nameW, light ? "rgba(0,0,0,.45)" : "rgba(255,255,255,.7)"));
    }
    g.cols.forEach(function (c, i) {
      var y = st.headerH + i * st.rowH, cy = y + st.rowH / 2, base = n(cy + st.rowSize * 0.36);
      var weight = c.pk || c.fk ? ' font-weight="bold"' : "";
      var color = c.color || (c.pk ? C.pk : c.fk ? C.fk : C.text), rn = c.pk ? "rn rpk" : c.fk ? "rn rfk" : "rn";
      out.push('<g class="r" data-c="' + esc(c.id) + '">');
      // a tagged column: tinted row and a bar in the tag colour (a diff bar, drawn next, covers the bar)
      if (c.color) {
        out.push('<rect y="' + y + '" width="' + w + '" height="' + st.rowH + '" fill="' + c.color + '" fill-opacity=".1"/>');
        out.push('<rect y="' + (y + 3) + '" width="3" height="' + (st.rowH - 6) + '" fill="' + c.color + '"/>');
      }
      out.push('<rect class="rb" y="' + y + '" width="' + w + '" height="' + st.rowH + '" fill="' + C.body + '" fill-opacity="0"/>');
      var cstate = t.diff && t.diff.cols && t.diff.cols[c.id];
      if (cstate) out.push('<rect y="' + (y + 3) + '" width="3" height="' + (st.rowH - 6) + '" fill="' + C[cstate] + '"/>');
      out.push('<text class="' + rn + '" x="' + st.padX + '" y="' + base + '" fill="' + color + '"' + (c.color ? ' style="fill:' + c.color + '"' : "") +
        ' font-family="' + FONT + '" font-size="' + st.rowSize + '"' + weight + ">" + esc(c.name) + "</text>");
      if (docMarks && c.doc) out.push(docMark(st.padX, cy + st.rowSize * 0.36 + 2.5, c.nameW, color));
      if (c.tags && c.tags.indexOf("removed") >= 0) {
        out.push('<line x1="' + st.padX + '" y1="' + n(cy) + '" x2="' + n(st.padX + c.nameW) + '" y2="' + n(cy) + '" stroke="' + color + '" stroke-width="1.2"/>');
      }
      var bx = st.padX + c.nameW + 6;
      c.badges.forEach(function (b) {
        var bh = st.badgeSize + 5;
        out.push('<rect class="bb" x="' + n(bx) + '" y="' + n(cy - bh / 2) + '" width="' + n(b.w) + '" height="' + bh + '" rx="3" fill="' + C.badgeBg + '"/>');
        out.push('<text class="bt" x="' + n(bx + st.badgePad) + '" y="' + n(cy + st.badgeSize * 0.36) + '" fill="' + C.badgeText +
          '" font-family="' + FONT + '" font-size="' + st.badgeSize + '">' + esc(b.t) + "</text>");
        bx += b.w + st.badgeGap;
      });
      if (c.pk) out.push(keyIcon(w - st.padX - c.typeW - st.keyW, cy));
      out.push('<text class="rt" x="' + (w - st.padX) + '" y="' + base + '" text-anchor="end" fill="' + C.type + '" font-family="' + FONT +
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
      s.push('<circle class="mc" cx="' + n(x + dir * o) + '" cy="' + n(y) + '" r="3.5" fill="' + C.bg + '" stroke="' + C.edge + '" stroke-width="1.2"/>');
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

  /* ------------------------------------------------------------------ regions: one shaded area per group */
  var REGION_COLORS = ["#4c78a8", "#59a14f", "#e15759", "#b07aa1", "#f28e2b", "#76b7b2", "#9c755f", "#edc948"];
  var REGION_PAD = 28, REGION_LABEL = 30;
  function regions(model, pos, mode) {
    var geo = geometry(model, mode), groups = {}, names = [];
    model.tables.forEach(function (t) {
      var g = t.group || "", p = pos[t.id];
      if (!g || !p) return;
      if (!groups[g]) { groups[g] = [Infinity, Infinity, -Infinity, -Infinity]; names.push(g); }
      var b = groups[g], tg = geo[t.id];
      b[0] = Math.min(b[0], p[0]); b[1] = Math.min(b[1], p[1]);
      b[2] = Math.max(b[2], p[0] + tg.w); b[3] = Math.max(b[3], p[1] + tg.h);
    });
    var all = {};
    model.tables.forEach(function (t) { if (t.group) all[t.group] = true; });
    var order = Object.keys(all).sort();
    return names.sort().map(function (g) {
      var b = groups[g];
      return {
        name: g,
        color: REGION_COLORS[order.indexOf(g) % REGION_COLORS.length],
        x: b[0] - REGION_PAD, y: b[1] - REGION_PAD - REGION_LABEL,
        w: b[2] - b[0] + 2 * REGION_PAD, h: b[3] - b[1] + 2 * REGION_PAD + REGION_LABEL,
      };
    });
  }
  function renderRegions(model, pos, mode) {
    return regions(model, pos, mode).map(function (r) {
      return '<g class="rg" data-g="' + esc(r.name) + '"><rect x="' + n(r.x) + '" y="' + n(r.y) + '" width="' + n(r.w) + '" height="' + n(r.h) +
        '" rx="14" fill="' + r.color + '" fill-opacity="0.07" stroke="' + r.color + '" stroke-opacity="0.45" stroke-width="1.5"/>' +
        '<text x="' + n(r.x + 16) + '" y="' + n(r.y + 22) + '" fill="' + r.color + '" font-family="' + FONT +
        '" font-size="16" font-weight="bold">' + esc(r.name) + "</text></g>";
    }).join("");
  }

  function renderEdges(model, pos, mode, geo) {
    geo = geo || geometry(model, mode);
    return model.rels.map(function (r) { return renderEdge(model, geo, pos, r); }).join("");
  }

  /* opts.docMarks: underline tables/columns that have doc comments (viewer only, not exports). */
  function renderInner(model, pos, mode, opts) {
    var geo = geometry(model, mode), marks = !!(opts && opts.docMarks);
    var rg = opts && opts.regions ? '<g class="regions">' + renderRegions(model, pos, mode) + "</g>" : "";
    var tables = model.tables.map(function (t) { return pos[t.id] ? renderTable(model, t, geo[t.id], pos[t.id], marks) : ""; }).join("");
    return rg + '<g class="edges">' + renderEdges(model, pos, mode, geo) + '</g><g class="tables">' + tables + "</g>";
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
    if (opts.regions) {
      regions(m, pos, mode).forEach(function (r) {
        b = [Math.min(b[0], r.x), Math.min(b[1], r.y), Math.max(b[2], r.x + r.w), Math.max(b[3], r.y + r.h)];
      });
    }
    var x0 = b[0] - pad - edgePad, y0 = b[1] - pad, w = b[2] - b[0] + 2 * (pad + edgePad), h = b[3] - b[1] + 2 * pad;
    var style = opts.fontCss ? "<style>" + opts.fontCss + "</style>" : "";
    return '<svg xmlns="http://www.w3.org/2000/svg" width="' + n(w) + '" height="' + n(h) + '" viewBox="' + n(x0) + " " + n(y0) + " " + n(w) + " " + n(h) + '">' +
      style + '<rect class="bgr" x="' + n(x0) + '" y="' + n(y0) + '" width="' + n(w) + '" height="' + n(h) + '" fill="' + C.bg + '"/>' +
      renderInner(m, pos, mode, { regions: opts.regions }) + "</svg>";
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

  /* ------------------------------------------------------------------ draw.io export
   * mxGraph XML using draw.io's own Entity Relation table shapes, so tables stay editable
   * (rows can be added, lines re-attached) and crow's-foot arrows are draw.io's ER arrows. */
  var DRAWIO_ARROW = { one: "ERmandOne", many: "ERmany", zeroOne: "ERzeroToOne", zeroMany: "ERzeroToMany" };
  function renderDrawio(model, pos, opts) {
    opts = opts || {};
    var mode = opts.mode || "full", m = subset(model, opts.only), geo = geometry(m, mode);
    var KEYW = 44, ROWH = 26, HEADH = 32, cells = [], rowId = {}, n = 2;
    function id() { return "q" + n++; }
    function cell(attrs, geom) {
      var a = Object.keys(attrs).map(function (k) { return k + '="' + esc(attrs[k]) + '"'; }).join(" ");
      return "<mxCell " + a + ">" + geom + "</mxCell>";
    }
    function g(x, y, w, h) {
      return '<mxGeometry x="' + n2(x) + '" y="' + n2(y) + '" width="' + n2(w) + '" height="' + n2(h) + '" as="geometry"/>';
    }
    function n2(v) { return Math.round(v); }
    var b = bounds(m, pos, mode);
    if (opts.regions) {
      regions(m, pos, mode).forEach(function (r) {
        cells.push(cell({
          id: id(), value: r.name, vertex: "1", parent: "1",
          style: "rounded=1;arcSize=4;whiteSpace=wrap;html=0;fillColor=" + r.color + ";opacity=12;strokeColor=" + r.color +
            ";verticalAlign=top;align=left;spacingLeft=12;spacingTop=4;fontStyle=1;fontSize=16;fontColor=" + r.color + ";",
        }, g(r.x - b[0] + 40, r.y - b[1] + 40, r.w + KEYW, r.h)));
      });
    }
    m.tables.forEach(function (t) {
      var p = pos[t.id];
      if (!p) return;
      var tg = geo[t.id], w = tg.w + KEYW, tid = id();
      rowId[t.id] = { _table: tid };
      cells.push(cell({
        id: tid, value: t.name, vertex: "1", parent: "1",
        style: "shape=table;startSize=" + HEADH + ";container=1;collapsible=1;childLayout=tableLayout;fixedRows=1;rowLines=0;" +
          "fontStyle=1;align=left;spacingLeft=10;resizeLast=1;html=0;whiteSpace=wrap;fillColor=" + (t.color || C.header) +
          ";fontColor=" + (isLight(t.color) ? C.text : "#ffffff") + ";" +
          "strokeColor=#dfe3e8;swimlaneFillColor=#ffffff;fontSize=14;",
      }, g(p[0] - b[0] + 40, p[1] - b[1] + 40, w, HEADH + Math.max(tg.cols.length, 0) * ROWH)));
      tg.cols.forEach(function (c, i) {
        var rid = id(), key = c.pk && c.fk ? "PK,FK" : c.pk ? "PK" : c.fk ? "FK" : "";
        rowId[t.id][c.id] = rid;
        cells.push(cell({
          id: rid, value: "", vertex: "1", parent: tid,
          style: "shape=tableRow;horizontal=0;startSize=0;swimlaneHead=0;swimlaneBody=0;fillColor=none;collapsible=0;" +
            "dropTarget=0;points=[[0,0.5],[1,0.5]];portConstraint=eastwest;top=0;left=0;right=0;bottom=0;",
        }, g(0, HEADH + i * ROWH, w, ROWH)));
        var base = "shape=partialRectangle;connectable=0;fillColor=none;top=0;left=0;bottom=0;right=0;overflow=hidden;html=0;";
        var flags = c.badges.map(function (x) { return x.t; }).join(" ");
        var fs = (c.pk ? 5 : c.fk ? 1 : 0) | (c.tags && c.tags.indexOf("removed") >= 0 ? 8 : 0); // bold, underline, strike
        cells.push(cell({ id: id(), value: key, vertex: "1", parent: rid, style: base + "fontStyle=1;fontColor=#2b5797;align=center;fontSize=11;" },
          g(0, 0, KEYW, ROWH)));
        cells.push(cell({
          id: id(), value: c.name + (flags ? "  [" + flags + "]" : "") + (c.type ? " : " + c.type : ""), vertex: "1", parent: rid,
          style: base + "align=left;spacingLeft=6;fontSize=12;" + (fs ? "fontStyle=" + fs + ";" : "") + (c.color ? "fontColor=" + c.color + ";" : ""),
        }, g(KEYW, 0, w - KEYW, ROWH)));
      });
    });
    m.rels.forEach(function (r) {
      var ra = rowId[r.a.t], rb = rowId[r.b.t];
      if (!ra || !rb) return;
      var src = ra[r.a.c] || ra._table, dst = rb[r.b.c] || rb._table;
      cells.push(cell({
        id: id(), value: "", edge: "1", parent: "1", source: src, target: dst,
        style: "edgeStyle=entityRelationEdgeStyle;fontSize=12;html=0;endFill=0;startFill=0;strokeColor=#9aa0a6;" +
          "startArrow=" + DRAWIO_ARROW[r.a.card] + ";endArrow=" + DRAWIO_ARROW[r.b.card] + ";",
      }, '<mxGeometry relative="1" as="geometry"/>'));
    });
    return '<mxfile host="qdbd" type="device"><diagram id="erd" name="' + esc(opts.title || "ERD") + '">' +
      '<mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" ' +
      'page="0" pageScale="1" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>' +
      cells.join("") + "</root></mxGraphModel></diagram></mxfile>";
  }

  /* ------------------------------------------------------------------ selectors (dbt-style, over relationships)
   * Space-separated atoms are unioned; a comma inside an atom intersects (a,b); a leading ! excludes.
   * Atom: [N]+  method:pattern  +[N]
   *   method: name (default; also matches aliases), group, file, col, tag
   *   pattern: glob with * and ?
   *   +x   x plus the tables it references (parents), any depth; 2+x limits to 2 hops
   *   x+   x plus the tables referencing it (children); x+1 limits to 1 hop
   */
  function globRe(p) {
    // Runs of * collapse to one, so a pattern like ******x can't backtrack for seconds.
    var src = p.replace(/\*+/g, "*").replace(/[.^$|()[\]{}\\+]/g, "\\$&");
    return new RegExp("^" + src.replace(/\*/g, ".*").replace(/\?/g, ".") + "$", "i");
  }
  function edges(model) {
    var up = {}, down = {};
    model.rels.forEach(function (r) {
      var aMany = r.a.card === "many" || r.a.card === "zeroMany", bMany = r.b.card === "many" || r.b.card === "zeroMany";
      var aIsChild = aMany || !bMany, child = aIsChild ? r.a.t : r.b.t, parent = aIsChild ? r.b.t : r.a.t;
      if (child === parent) return;
      (up[child] = up[child] || []).push(parent);
      (down[parent] = down[parent] || []).push(child);
    });
    return { up: up, down: down };
  }
  function walk(start, adj, depth, into) {
    var frontier = start, d = 0;
    while (frontier.length && d < depth) {
      var next = [];
      frontier.forEach(function (id) {
        (adj[id] || []).forEach(function (o) { if (!into[o]) { into[o] = true; next.push(o); } });
      });
      frontier = next;
      d++;
    }
  }
  function atomSet(model, atom, g) {
    var m = /^(\d*\+)?(.*?)(\+\d*)?$/.exec(atom), up = m[1], body = m[2], down = m[3];
    var method = "name", pat = body, i = body.indexOf(":");
    if (i > 0) { method = body.slice(0, i).toLowerCase(); pat = body.slice(i + 1); }
    var re = globRe(pat || "*"), out = {}, base = [];
    model.tables.forEach(function (t) {
      var ok;
      if (method === "name") ok = re.test(t.name) || t.aliases.some(function (a) { return re.test(a); });
      else if (method === "group") ok = re.test(t.group || "") || (t.group || "").toLowerCase().indexOf(pat.toLowerCase() + "/") === 0;
      else if (method === "file") ok = re.test(t.file || "") || re.test((t.file || "").split("/").pop());
      else if (method === "col" || method === "column") ok = t.cols.some(function (c) { return re.test(c.name); });
      else if (method === "tag") {
        var has = function (x) { return re.test(x); };
        ok = (t.tags || []).some(has) || t.cols.some(function (c) { return (c.tags || []).some(has); });
      }
      else if (method === "diff" || method === "state") {
        var ds = t.diff && t.diff.state, want = pat.toLowerCase();
        ok = !!ds && (want === "modified" || want === "*" || want === ds || (want === "new" && ds === "added"));
      }
      else throw new Error("unknown selector method '" + method + "' (use name, group, file, col, tag, diff)");
      if (ok) { out[t.id] = true; base.push(t.id); }
    });
    function hops(op, before) {
      var n = before ? op.slice(0, -1) : op.slice(1);
      return n ? parseInt(n, 10) : Infinity;
    }
    // Separate visited sets, so the down-walk isn't cut short by tables the up-walk reached (cycles).
    [[up, g.up, true], [down, g.down, false]].forEach(function (w) {
      if (!w[0]) return;
      var seen = {};
      base.forEach(function (id) { seen[id] = true; });
      walk(base, w[1], hops(w[0], w[2]), seen);
      Object.keys(seen).forEach(function (id) { out[id] = true; });
    });
    return out;
  }
  /* Returns the ids matching `expr`, in model order, or null when expr is blank (= everything). */
  function select(model, expr) {
    var tokens = String(expr || "").trim().split(/\s+/).filter(Boolean);
    if (!tokens.length) return null;
    var g = edges(model), inc = null, exc = {};
    tokens.forEach(function (tok) {
      var neg = tok.charAt(0) === "!";
      if (neg) tok = tok.slice(1);
      var parts = tok.split(",").filter(Boolean), set = null;
      parts.forEach(function (p) {
        var s = atomSet(model, p, g);
        if (set === null) set = s;
        else { var k = {}; Object.keys(set).forEach(function (id) { if (s[id]) k[id] = true; }); set = k; }
      });
      set = set || {};
      if (neg) Object.keys(set).forEach(function (id) { exc[id] = true; });
      else { inc = inc || {}; Object.keys(set).forEach(function (id) { inc[id] = true; }); }
    });
    return model.tables.filter(function (t) { return (inc === null || inc[t.id]) && !exc[t.id]; }).map(function (t) { return t.id; });
  }

  /* ------------------------------------------------------------------ path finder
   * Shortest chain of relationships between two tables (relationships are walked in either
   * direction). Each step says which columns join. */
  var VIRTUAL = "qdbdvirtualfield";
  function findPath(model, from, to) {
    if (from === to) return [];
    var adj = {};
    model.rels.forEach(function (r, i) {
      (adj[r.a.t] = adj[r.a.t] || []).push({ to: r.b.t, i: i, fwd: true, cols: r.a.c !== VIRTUAL });
      (adj[r.b.t] = adj[r.b.t] || []).push({ to: r.a.t, i: i, fwd: false, cols: r.a.c !== VIRTUAL });
    });
    // Between the same two tables, a relationship with join columns beats a table-level one.
    Object.keys(adj).forEach(function (k) {
      adj[k] = adj[k].filter(function (e) { return e.cols; }).concat(adj[k].filter(function (e) { return !e.cols; }));
    });
    var prev = {}, queue = [from], seen = {};
    seen[from] = true;
    while (queue.length) {
      var cur = queue.shift();
      if (cur === to) break;
      (adj[cur] || []).forEach(function (e) {
        if (seen[e.to]) return;
        seen[e.to] = true;
        prev[e.to] = { from: cur, e: e };
        queue.push(e.to);
      });
    }
    if (!seen[to]) return null;
    var steps = [], at = to;
    while (at !== from) {
      var pv = prev[at], r = model.rels[pv.e.i];
      var here = pv.e.fwd ? r.a : r.b, there = pv.e.fwd ? r.b : r.a; // here = side of pv.from
      steps.unshift({
        rel: pv.e.i, from: { t: pv.from, c: here.c, card: here.card }, to: { t: at, c: there.c, card: there.card },
        pairs: stepPairs(model, pv.e.i, pv.from),
      });
      at = pv.from;
    }
    return steps;
  }

  /* Every [fromCol, toCol] the step joins on: all columns of a composite key (rels sharing "k"), [] when
   * table-level. */
  function stepPairs(model, i, fromT) {
    var r = model.rels[i];
    if (r.a.c === VIRTUAL || r.b.c === VIRTUAL) return [];
    var group = r.k === undefined ? [r] : model.rels.filter(function (x) {
      return x.k === r.k && ((x.a.t === r.a.t && x.b.t === r.b.t) || (x.a.t === r.b.t && x.b.t === r.a.t));
    });
    return group.map(function (x) { return x.a.t === fromT ? [x.a.c, x.b.c] : [x.b.c, x.a.c]; });
  }

  var SQL_RESERVED = ("all and any as asc between by case check column constraint create cross default delete desc distinct " +
    "drop else end exists foreign from full grant group having in index inner insert intersect into is join key left like " +
    "limit not null offset on or order outer primary references right select set table then to union unique update user " +
    "using values view when where with").split(" ");
  function sqlPart(name) {
    var plain = /^[A-Za-z_][A-Za-z0-9_]*$/.test(name) && SQL_RESERVED.indexOf(name.toLowerCase()) < 0;
    return plain ? name : '"' + name.replace(/"/g, '""') + '"';
  }
  /* A dotted name (DBML schema.table, a dbt source) is a qualified name: each part is quoted on its own. */
  function sqlIdent(name) {
    var parts = name.split(".");
    return parts.length > 1 && parts.every(Boolean) ? parts.map(sqlPart).join(".") : sqlPart(name);
  }

  /* SQL FROM/JOIN clause following a path. */
  function pathSql(model, from, steps) {
    var byId = {};
    model.tables.forEach(function (t) { byId[t.id] = t; });
    function col(t, c) {
      var x = byId[t].cols.filter(function (k) { return k.id === c; })[0];
      return x ? sqlPart(x.name) : null;
    }
    var lines = ["FROM " + sqlIdent(byId[from].name)];
    steps.forEach(function (s) {
      var a = sqlIdent(byId[s.from.t].name), b = sqlIdent(byId[s.to.t].name);
      var pairs = s.pairs || (s.from.c === VIRTUAL ? [] : [[s.from.c, s.to.c]]);
      var on = pairs.map(function (p) { return b + "." + col(s.to.t, p[1]) + " = " + a + "." + col(s.from.t, p[0]); });
      if (on.length) lines.push("JOIN " + b + " ON " + on.join(" AND "));
      else lines.push("JOIN " + b + " ON ...  -- table-level relationship: join columns not specified");
    });
    return lines.join("\n");
  }

  root.qdbd = {
    findPath: findPath,
    stepPairs: stepPairs,
    pathSql: pathSql,
    renderDrawio: renderDrawio,
    regions: regions,
    select: select,
    subset: subset,
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
  root.qdbdSelect = select;
  root.qdbdRenderDrawio = renderDrawio;
  root.qdbdFindPath = findPath;
  root.qdbdPathSql = pathSql;
  root.qdbdNeighbourhood = neighbourhood;
})(typeof window !== "undefined" ? window : globalThis);
