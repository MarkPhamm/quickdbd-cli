/* Home page motion (overrides/home.html). Loaded on every docs page; does nothing without the home page's .qh root.
 * Material's instant navigation swaps the page without a reload, so init runs on every document$ emission and
 * marks the root it handled. home-tour.js and home-mini.js use the helpers on window.qhome. */
(function () {
  "use strict";
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");

  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  /* fn(el) once el scrolls into view. */
  function onView(el, fn, margin) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { io.unobserve(e.target); fn(e.target); } });
    }, { rootMargin: margin || "0px 0px -12% 0px" });
    io.observe(el);
  }

  /* setInterval that stops once the home page is gone (instant navigation keeps the window alive). */
  function every(root, ms, fn) {
    var id = setInterval(function () { if (!root.isConnected) clearInterval(id); else fn(); }, ms);
  }

  /* Re-types an element's text with a cursor, keeping its <b>/<i>/<span> colouring. play() resolves true when it
   * finished, false when another play() or show() cut it short. onLine(i) runs as line i (0-based) is completed. */
  function typer(node) {
    var segs = [].map.call(node.childNodes, function (c) {
      return c.nodeType === 3 ? { text: c.textContent } : { tag: c.tagName, cls: c.className, text: c.textContent };
    });
    var full = node.innerHTML, token = 0;
    function hold() { node.innerHTML = full; node.style.minHeight = node.offsetHeight + "px"; }
    return {
      show: function () { token++; node.innerHTML = full; },
      clear: function () { if (reduce.matches) return; hold(); node.innerHTML = ""; },
      play: async function (onLine, speed) {
        var my = ++token, line = 0, lines = full.split("\n").length;
        hold();
        if (reduce.matches) { for (var L = 0; L < lines; L++) if (onLine) onLine(L); return true; }
        node.innerHTML = "";
        var caret = document.createElement("q-caret");
        node.appendChild(caret);
        for (var s = 0; s < segs.length; s++) {
          var box = segs[s].tag ? document.createElement(segs[s].tag) : document.createTextNode("");
          if (segs[s].tag && segs[s].cls) box.className = segs[s].cls;
          node.insertBefore(box, caret);
          for (var k = 0; k < segs[s].text.length; k++) {
            if (my !== token) return false;
            var ch = segs[s].text[k];
            box.textContent += ch;
            if (ch === "\n") { if (onLine) onLine(line); line++; await wait(110); } else await wait(speed || 17);
          }
        }
        if (onLine) onLine(line);
        setTimeout(function () { if (my === token) caret.remove(); }, 1600);
        return true;
      },
    };
  }

  /* Headings rise word by word. Only real spaces split, so &nbsp; keeps "200+ tables" together. */
  function splitWords(h) {
    var i = 0;
    (function walk(n) {
      [].slice.call(n.childNodes).forEach(function (c) {
        if (c.nodeType === 3) {
          var frag = document.createDocumentFragment();
          c.textContent.split(/( +|\n+)/).forEach(function (w) {
            if (!w) return;
            if (!w.trim()) { frag.appendChild(document.createTextNode(w)); return; }
            var q = document.createElement("q-w");
            q.style.setProperty("--i", i++);
            q.textContent = w;
            frag.appendChild(q);
          });
          c.replaceWith(frag);
        } else if (c.nodeType === 1 && c.tagName !== "CODE") walk(c);
      });
    })(h);
    h.classList.add("qh-words");
  }

  /* Reveal in order: hide everything first, then set the stagger, so the hiding itself isn't delayed. */
  function reveal(items, step) {
    items.forEach(function (el) { el.classList.add("qh-rv"); });
    void document.body.offsetWidth;
    items.forEach(function (el, k) {
      el.style.setProperty("--d", (step ? k * step : 0) + "s");
      onView(el, function () { el.classList.add("qh-in"); });
    });
  }

  function init() {
    var root = document.querySelector(".qh");
    if (!root || root.dataset.qh) return;
    root.dataset.qh = "1";
    var h1 = root.querySelector(".qh-hero h1");
    if (h1) splitWords(h1);
    root.querySelectorAll(".qh-section > h2, .qh-final > h2").forEach(function (h) {
      splitWords(h);
      onView(h, function () { h.classList.add("qh-in"); });
    });
    reveal([].slice.call(root.querySelectorAll(".qh-section > .qh-sub, .qh-section > .qh-more, .qh-final > :not(h2)")));
    root.querySelectorAll(".qh-steps3, .qh-steps4, .qh-gallery, .qh-faq").forEach(function (g) {
      reveal([].slice.call(g.children).filter(function (c) { return c.tagName !== "H2"; }), 0.08);
    });
    root.querySelectorAll(".qh-col, .qh-box, .qh-card, .qh-steps4 > li, .qh-tabs, .qh-comment, .qh-tour__chapters li").forEach(function (c) {
      c.classList.add("qh-glow");
      c.addEventListener("pointermove", function (e) {
        var r = c.getBoundingClientRect();
        c.style.setProperty("--mx", e.clientX - r.left + "px");
        c.style.setProperty("--my", e.clientY - r.top + "px");
      });
    });
    window.qhome.sections.forEach(function (fn) { fn(root); });
  }

  /* Compare cards: rise, rows and marks pop in, then the side cards step back and the qdbd card lifts. */
  function compare(root) {
    var cmp = root.querySelector(".qh-compare");
    if (!cmp || reduce.matches) return;
    cmp.classList.add("qh-anim");
    void cmp.offsetWidth;
    [].forEach.call(cmp.children, function (col, i) {
      col.style.setProperty("--d", i * 0.12 + "s");
      col.querySelectorAll("li").forEach(function (li, j) { li.style.setProperty("--d", 0.3 + i * 0.12 + j * 0.1 + "s"); });
    });
    onView(cmp, function () {
      cmp.classList.add("qh-in");
      setTimeout(function () { cmp.classList.add("qh-settled"); }, 1700);
    });
  }

  /* Flow diagram: curved wires from each input to qdbd and on to each output, drawn in order; then a pulse runs from
   * one input through qdbd ("check · layout · render") to every output. Hovering a box lights its path. */
  var NS = "http://www.w3.org/2000/svg";
  function svgEl(tag, a) {
    var e = document.createElementNS(NS, tag);
    for (var k in a) e.setAttribute(k, a[k]);
    return e;
  }
  function flow(root) {
    var f = root.querySelector(".qh-flow");
    if (!f) return;
    var cols = f.querySelectorAll(".qh-flow__col");
    cols[0].classList.add("qh-flow__ins");
    cols[2].classList.add("qh-flow__outs");
    var ins = [].slice.call(cols[0].children), core = cols[1].querySelector(".qh-box"), outs = [].slice.call(cols[2].children);
    var small = core.querySelector("small"), words = small.textContent.split(" · ");
    small.textContent = "";
    words = words.map(function (w, i) {
      if (i) small.appendChild(document.createTextNode(" · "));
      var s = document.createElement("span");
      s.textContent = w;
      return small.appendChild(s);
    });
    f.classList.add("wired");
    if (!reduce.matches) f.classList.add("qh-anim");
    void f.offsetWidth;
    ins.forEach(function (b, i) { b.style.setProperty("--d", i * 0.1 + "s"); });
    outs.forEach(function (b, i) { b.style.setProperty("--d", 1.5 + i * 0.1 + "s"); });
    core.style.setProperty("--d", ".7s");

    var svg = svgEl("svg", { "class": "qh-flow__wires", "aria-hidden": "true" }), wires = { in: [], out: [] };
    f.insertBefore(svg, f.firstChild);
    /* Layout boxes from offsets, which ignore the build-in transforms. */
    function box(b) {
      var x = b.offsetLeft + b.offsetParent.offsetLeft, y = b.offsetTop + b.offsetParent.offsetTop;
      return { left: x, right: x + b.offsetWidth, mid: y + b.offsetHeight / 2 };
    }
    function draw() {
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      wires = { in: [], out: [] };
      if (getComputedStyle(svg).display === "none") return;
      var c = box(core);
      function wire(kind, x1, y1, x2, y2) {
        var dx = (x2 - x1) * 0.55, d = "M" + x1 + " " + y1 + " C" + (x1 + dx) + " " + y1 + " " + (x2 - dx) + " " + y2 + " " + x2 + " " + y2;
        var g = svgEl("g", {}), base = svgEl("path", { d: d, "class": "base" });
        g.appendChild(base);
        g.appendChild(svgEl("path", { d: d, "class": "flow" }));
        g.appendChild(svgEl("circle", { cx: x1, cy: y1, r: 3, "class": "dot" }));
        g.appendChild(svgEl("circle", { cx: x2, cy: y2, r: 3, "class": "dot" }));
        svg.appendChild(g);
        wires[kind].push({ g: g, base: base, d: d, len: base.getTotalLength() });
      }
      ins.forEach(function (b, i) { var r = box(b); wire("in", r.right, r.mid, c.left, c.mid + (i - (ins.length - 1) / 2) * 14); });
      outs.forEach(function (b, i) { var r = box(b); wire("out", c.right, c.mid + (i - (outs.length - 1) / 2) * 12, r.left, r.mid); });
    }
    draw();
    new ResizeObserver(function () { if (f.isConnected) draw(); }).observe(f);

    function drawIn(list, delay) {
      list.forEach(function (w, i) {
        w.base.animate([{ strokeDasharray: w.len, strokeDashoffset: w.len }, { strokeDasharray: w.len, strokeDashoffset: 0 }],
          { duration: 520, delay: delay + i * 90, easing: "cubic-bezier(.6,0,.3,1)", fill: "backwards" });
        w.g.querySelectorAll(".dot").forEach(function (dot) {
          dot.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 200, delay: delay + i * 90 + 380, fill: "backwards" });
        });
      });
    }
    function comet(w, ms) {
      var p = svgEl("path", { d: w.d, "class": "comet", "stroke-dasharray": "22 " + (w.len + 44) });
      svg.appendChild(p);
      p.animate([{ strokeDashoffset: 22 }, { strokeDashoffset: -w.len }], { duration: ms, easing: "cubic-bezier(.45,0,.55,1)" })
        .onfinish = function () { p.remove(); };
    }
    function ping(b) {
      b.classList.add("ping");
      setTimeout(function () { b.classList.remove("ping"); }, 650);
    }
    var turn = 0, hovering = false;
    async function pulse() {
      if (hovering || !wires.in.length) return;
      var i = turn++ % ins.length;
      ping(ins[i]);
      comet(wires.in[i], 700);
      await wait(650);
      ping(core);
      for (var k = 0; k < words.length; k++) {
        words[k].classList.add("on");
        await wait(160);
        words[k].classList.remove("on");
      }
      wires.out.forEach(function (w, j) { setTimeout(function () { comet(w, 650); }, j * 70); });
      await wait(560);
      outs.forEach(function (b, j) { setTimeout(function () { ping(b); }, j * 70); });
    }
    function light(on) { wires.in.concat(wires.out).forEach(function (w) { w.g.classList.toggle("lit", on.indexOf(w) >= 0); }); }
    function hover(b, which) {
      b.addEventListener("mouseenter", function () { hovering = true; light(which()); });
      b.addEventListener("mouseleave", function () { hovering = false; light([]); });
    }
    ins.forEach(function (b, i) { hover(b, function () { return [wires.in[i]].concat(wires.out); }); });
    outs.forEach(function (b, i) { hover(b, function () { return wires.in.concat([wires.out[i]]); }); });
    hover(core, function () { return wires.in.concat(wires.out); });

    onView(f, async function () {
      f.classList.add("qh-in");
      if (reduce.matches) return;
      drawIn(wires.in, 350);
      drawIn(wires.out, 1250);
      await wait(2600);
      pulse();
      every(root, 3800, pulse);
    });
  }

  /* Quick start: a track fills from step 1 to 4; each number pops as it arrives, then its command types itself. */
  function quick(root) {
    var steps = root.querySelector(".qh-steps4");
    if (!steps) return;
    var lis = [].slice.call(steps.children), track = document.createElement("div");
    track.className = "qh-steps4__track";
    track.appendChild(document.createElement("i"));
    steps.appendChild(track);
    function place() {
      var a = lis[0].querySelector("span"), z = lis[lis.length - 1].querySelector("span");
      var ax = lis[0].offsetLeft + a.offsetLeft + a.offsetWidth / 2, zx = lis[lis.length - 1].offsetLeft + z.offsetLeft + z.offsetWidth / 2;
      track.style.left = ax + "px";
      track.style.width = zx - ax + "px";
      track.style.top = lis[0].offsetTop + a.offsetTop + a.offsetHeight / 2 - 1 + "px";
    }
    place();
    window.addEventListener("resize", function () { if (steps.isConnected) place(); });
    if (reduce.matches) return;
    var codes = lis.map(function (li) { var c = li.querySelector(":scope > code"); return c && typer(c); });
    steps.classList.add("qh-anim");
    codes.forEach(function (t) { if (t) t.clear(); });
    onView(steps, async function () {
      await wait(450);
      steps.classList.add("go");
      for (var k = 0; k < lis.length; k++) {
        lis[k].querySelector("span").classList.add("on");
        if (codes[k]) codes[k].play(null, 28);
        await wait(600);
      }
    }, "0px 0px -20% 0px");
  }

  /* PR review: the points arrive in order, the comment slides up onto the screenshot and its rows flash in. */
  function pr(root) {
    var stage = root.querySelector(".qh-pr__stage"), list = root.querySelector(".qh-pr .qh-list");
    if (list) reveal([].slice.call(list.children), 0.12);
    if (!stage || reduce.matches) return;
    stage.classList.add("qh-anim");
    stage.querySelectorAll(".qh-comment tr + tr").forEach(function (tr, k) { tr.style.setProperty("--d", 0.35 + k * 0.15 + "s"); });
    onView(stage, function () { stage.classList.add("qh-in"); }, "0px 0px -25% 0px");
  }

  /* Closing: the install command types itself. */
  function closing(root) {
    var code = root.querySelector(".qh-final .qh-install code");
    if (!code || reduce.matches) return;
    var t = typer(code);
    t.clear();
    onView(code, function () { setTimeout(function () { t.play(null, 45); }, 400); });
  }

  window.qhome = { reduce: reduce, wait: wait, onView: onView, every: every, typer: typer, sections: [compare, flow, quick, pr, closing] };
  /* Section scripts register here; run after this file's helpers exist. */
  window.qhome.add = function (fn) { window.qhome.sections.push(fn); };
  function start() {
    if (window.document$) window.document$.subscribe(init);
    else init();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
