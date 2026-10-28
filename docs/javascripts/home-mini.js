/* Home page "From text to diagram": the tab underline slides, the code types itself, and the diagram beside it
 * (drawn by qdbd from that same text, hooks/home.py) builds as each line is typed: a table appears with its name,
 * a row with its column, the line once both ends exist; then it lights up like a clicked line in the viewer. */
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg", VIRTUAL = "qdbdvirtualfield";
  function svgEl(tag, a) {
    var e = document.createElementNS(NS, tag);
    for (var k in a) e.setAttribute(k, a[k]);
    return e;
  }
  function div(cls, text) {
    var d = document.createElement("div");
    if (cls) d.className = cls;
    if (text != null) d.textContent = text;
    return d;
  }

  window.qhome.add(function (root) {
    var tabs = root.querySelector(".qh-tabs");
    if (!tabs) return;
    var Q = window.qhome, reduce = Q.reduce.matches;

    var bar = tabs.querySelector(".qh-tabs__bar"), ind = document.createElement("i");
    ind.className = "qh-tabs__ind";
    bar.appendChild(ind);
    bar.classList.add("qh-ind");
    function moveInd() {
      var b = bar.querySelector('[aria-selected="true"]');
      ind.style.width = b.offsetWidth + "px";
      ind.style.transform = "translateX(" + b.offsetLeft + "px)";
    }
    moveInd();
    window.addEventListener("resize", function () { if (bar.isConnected) moveInd(); });
    var typers = {};
    tabs.querySelectorAll(".qh-code").forEach(function (p) { typers[p.id] = Q.typer(p); });

    var mini = root.querySelector(".qh-mini"), dataEl = root.querySelector("#qh-mini-data");
    var svg = mini && mini.querySelector("svg"), card = mini && mini.querySelector(".qh-mini__card");
    var data = dataEl ? JSON.parse(dataEl.textContent) : { steps: {}, rels: [] }, rels = {}, T = {}, edges = [], fx = null;
    data.rels.forEach(function (r) { rels[r.key] = r; });
    function edgeKey(e) {
      return [e.getAttribute("data-a"), e.getAttribute("data-ac"), e.getAttribute("data-b"), e.getAttribute("data-bc")].join("|");
    }
    if (svg) {
      svg.removeAttribute("width");
      svg.removeAttribute("height");
      var bg = svg.querySelector(".bgr");
      if (bg) bg.remove();
      svg.querySelectorAll(".t").forEach(function (t) {
        var inner = svgEl("g", { "class": "ti" });
        while (t.firstChild) inner.appendChild(t.firstChild);
        t.appendChild(inner);
        var tb = inner.querySelector(".tb"), rb = inner.querySelectorAll(".rb"), h = +tb.getAttribute("height");
        var head = rb.length ? +rb[0].getAttribute("y") : h, rowH = rb.length ? +rb[0].getAttribute("height") : 0;
        T[t.getAttribute("data-id")] = { g: t, tb: tb, head: head, rowH: rowH, pad: h - head - rb.length * rowH, rows: 0 };
      });
      var bb = svg.querySelector(".tables").getBBox();
      svg.setAttribute("viewBox", [bb.x - 30, bb.y - 34, bb.width + 60, bb.height + 165].join(" ")); // room below for the card
      fx = svgEl("g", { "class": "fx" });
      svg.insertBefore(fx, svg.querySelector(".tables"));
      edges = [].slice.call(svg.querySelectorAll(".e"));
      if (!reduce) mini.classList.add("qh-anim");
    }

    function reset() {
      if (!svg) return;
      card.classList.remove("open");
      while (fx.firstChild) fx.removeChild(fx.firstChild);
      svg.querySelectorAll(".on, .lit").forEach(function (x) { x.classList.remove("on", "lit"); });
      for (var id in T) {
        T[id].rows = 0;
        T[id].tb.style.height = reduce ? "" : T[id].head + "px";
      }
    }
    function row(id, c) { return T[id] && T[id].g.querySelector('.r[data-c="' + c + '"]'); }
    function ends(e) {
      return [[e.getAttribute("data-a"), e.getAttribute("data-ac")], [e.getAttribute("data-b"), e.getAttribute("data-bc")]];
    }
    function apply(step) {
      var t = T[step[1]];
      if (!t) return;
      if (step[0] === "t") { t.g.classList.add("on"); return; }
      var r = row(step[1], step[2]);
      if (!r) return;
      r.classList.add("on");
      t.rows++;
      if (!reduce) t.tb.style.height = t.head + t.rows * t.rowH + t.pad + "px";
    }
    /* A line draws itself once both of its ends are on the diagram. */
    function drawReady() {
      edges.forEach(function (e) {
        if (e.classList.contains("on")) return;
        var ready = ends(e).every(function (end) {
          var t = T[end[0]];
          return t && t.g.classList.contains("on") && (end[1] === VIRTUAL || (row(end[0], end[1]) || {}).classList.contains("on"));
        });
        if (!ready) return;
        e.classList.add("on");
        if (reduce) return;
        var ep = e.querySelector(".ep"), len = ep.getTotalLength();
        ep.animate([{ strokeDasharray: len, strokeDashoffset: len }, { strokeDasharray: len, strokeDashoffset: 0 }], { duration: 600, easing: "cubic-bezier(.6,0,.3,1)" });
        [].forEach.call(e.querySelectorAll("path:not(.ep)"), function (m) {
          m.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 250, delay: 500, fill: "backwards" });
        });
      });
    }
    /* Light every drawn line like a clicked line in the viewer, and show the first one's card. */
    function lightUp() {
      var first = null;
      edges.forEach(function (e) {
        var rel = rels[edgeKey(e)];
        if (!e.classList.contains("on") || !rel) return;
        e.classList.add("lit");
        ends(e).forEach(function (end) { var r = row(end[0], end[1]); if (r) r.classList.add("lit"); });
        fx.appendChild(svgEl("path", { d: e.querySelector(".ep").getAttribute("d"), "class": "flow" }));
        rel.labels.forEach(function (l) {
          var t = svgEl("text", { x: l.x, y: l.y, "class": "lbl", "text-anchor": l.anchor });
          t.textContent = l.text;
          fx.appendChild(t);
        });
        first = first || { e: e, c: rel.card };
      });
      if (!first) return;
      var c = first.c, title = div(), b = document.createElement("b"), pre = document.createElement("pre");
      title.appendChild(document.createTextNode(c.from));
      b.textContent = c.cardFrom + " — " + c.cardTo;
      title.appendChild(b);
      title.appendChild(document.createTextNode(c.to));
      pre.textContent = c.sql;
      card.textContent = "";
      card.appendChild(title);
      card.appendChild(div("k", c.sentence));
      card.appendChild(pre);
      var ep = first.e.querySelector(".ep"), m = ep.getPointAtLength(ep.getTotalLength() / 2), ctm = svg.getScreenCTM();
      var r = mini.getBoundingClientRect(), tbb = svg.querySelector(".tables").getBBox();
      card.style.left = Math.max(12, Math.min(m.x * ctm.a + ctm.e - r.left - 150, r.width - card.offsetWidth - 12)) + "px";
      card.style.top = (tbb.y + tbb.height + 16) * ctm.d + ctm.f - r.top + "px";
      card.classList.add("open");
    }
    async function build() {
      reset();
      var done = await typers["t-text"].play(function (line) {
        var step = data.steps[line];
        if (step) apply(step);
        drawReady();
      });
      if (done === false || !svg) return;
      await Q.wait(reduce ? 0 : 700);
      lightUp();
    }

    reset();
    typers["t-text"].clear();
    var started = false;
    Q.onView(tabs, function () { started = true; build(); }, "0px 0px -25% 0px");
    if (mini) mini.querySelector(".qh-frame__bar button").addEventListener("click", function () { bar.querySelector('[data-tab="t-text"]').click(); });
    bar.querySelectorAll("button").forEach(function (b) {
      b.addEventListener("click", function () {
        setTimeout(function () { // after home.html's own handler has switched the panels
          moveInd();
          var id = b.getAttribute("data-tab");
          for (var k in typers) if (k !== id) typers[k].show();
          if (id === "t-text") build();
          else if (started) typers[id].play(null, 12);
        }, 0);
      });
    });
  });
})();
