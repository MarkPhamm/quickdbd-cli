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

  window.qhome = { reduce: reduce, wait: wait, onView: onView, every: every, typer: typer, sections: [] };
  /* Section scripts register here; run after this file's helpers exist. */
  window.qhome.add = function (fn) { window.qhome.sections.push(fn); };
  function start() {
    if (window.document$) window.document$.subscribe(init);
    else init();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
