/* Home page live demo: a scripted cursor drives the real viewer (assets/tour/adventureworks.html, same origin) with
 * real events. Four chapters loop; hovering the frame hands control to the visitor. Phones and touch screens keep the
 * still screenshot; with reduced motion the page loads ready to use and a chapter card jumps to its end state.
 * The elements it drives are pinned by tests/test_viewer_contract.py. */
(function () {
  "use strict";
  var DUR = [7, 8, 7, 11]; // seconds per chapter, for the progress bars

  window.qhome.add(function (root) {
    var section = root.querySelector(".qh-tour");
    if (!section || window.matchMedia("(max-width: 760px), (hover: none)").matches) return;
    var frame = section.querySelector(".qh-tour__frame"), stage = frame.querySelector(".qh-tour__stage");
    var overlay = frame.querySelector(".qh-tour__overlay"), cursor = frame.querySelector(".qh-cursor");
    var toastEl = frame.querySelector(".qh-tour__toast"), stateEl = frame.querySelector(".qh-tour__state");
    var chapters = [].slice.call(section.querySelectorAll(".qh-tour__chapters li"));
    var reduce = window.qhome.reduce.matches, ifr = null, W = null, D = null;
    var scale = 1, cx = 0, cy = 0, token = 0, instant = false, resumeT = null;

    function Stop() {}
    function sleep(ms, my) {
      return new Promise(function (res, rej) {
        setTimeout(function () { my === token && frame.isConnected ? res() : rej(new Stop()); }, instant ? 0 : ms);
      });
    }
    function q(sel) { return D.querySelector(sel); }
    function fitScale() {
      scale = stage.clientWidth / 1440;
      if (ifr) ifr.style.transform = "scale(" + scale + ")";
    }
    function moveTo(x, y, my) {
      var t = instant ? 0 : Math.min(1100, 350 + Math.hypot(x - cx, y - cy) * 0.9);
      cursor.style.transitionDuration = t + "ms";
      cursor.style.transform = "translate(" + x * scale + "px," + y * scale + "px)";
      cx = x;
      cy = y;
      return sleep(t + 80, my);
    }
    function moveToEl(el, my, dx) {
      var r = el.getBoundingClientRect();
      return moveTo(r.left + (dx == null ? r.width / 2 : dx), r.top + r.height / 2, my);
    }
    function ripple() {
      if (instant) return;
      var e = document.createElement("div");
      e.className = "qh-ripple";
      e.style.left = cx * scale + "px";
      e.style.top = cy * scale + "px";
      overlay.appendChild(e);
      setTimeout(function () { e.remove(); }, 600);
    }
    function toast(msg) {
      toastEl.textContent = msg;
      toastEl.classList.add("open");
      setTimeout(function () { toastEl.classList.remove("open"); }, 1500);
    }
    function pointer(el, type, x, y) {
      el.dispatchEvent(new W.PointerEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, pointerId: 1, isPrimary: true }));
    }
    function key(el, k) { el.dispatchEvent(new W.KeyboardEvent("keydown", { key: k, bubbles: true })); }
    async function type(input, text, my) {
      input.value = "";
      for (var i = 0; i < text.length; i++) {
        input.value += text[i];
        input.dispatchEvent(new W.Event("input", { bubbles: true }));
        await sleep(65 + Math.random() * 50, my);
      }
    }
    function reset() {
      var qi = q("#q"), f = q("#filter");
      qi.value = "";
      qi.dispatchEvent(new W.Event("input", { bubbles: true }));
      if (f.value) { f.value = ""; key(f, "Enter"); }
      key(D, "Escape");
      q("#zfit").click();
    }
    /* A visible point on a relationship line, in iframe coordinates. */
    function linePoint(k) {
      var p = q('.hit path[data-k="' + k + '"]');
      if (!p) return null;
      var m = p.getPointAtLength(p.getTotalLength() * 0.5), ctm = p.getScreenCTM();
      return { el: p, x: m.x * ctm.a + ctm.e, y: m.y * ctm.d + ctm.f };
    }
    async function pick(name, my) {
      var qi = q("#q");
      await moveToEl(qi, my, 40);
      ripple();
      await type(qi, name, my);
      await sleep(350, my);
      var ti = q('.ti[data-id="' + name + '"]');
      await moveToEl(ti, my, 60);
      ripple();
      ti.click();
    }

    var steps = [
      async function (my) { // search
        var qi = q("#q");
        await moveToEl(qi, my, 40);
        ripple();
        await sleep(250, my);
        await type(qi, "SalesOrderH", my);
        await sleep(350, my);
        var ti = q('.ti[data-id="SalesOrderHeader"]');
        await moveToEl(ti, my, 60);
        ripple();
        ti.click();
        await sleep(2600, my);
      },
      async function (my) { // a line, its card, Copy JOIN
        if (W.qdbdViewer.state.focus !== "SalesOrderHeader") {
          reset();
          var qi = q("#q");
          qi.value = "SalesOrderHeader";
          qi.dispatchEvent(new W.Event("input", { bubbles: true }));
          q('.ti[data-id="SalesOrderHeader"]').click();
          await sleep(900, my);
        }
        await sleep(300, my);
        var h = linePoint("SalesOrderHeader|CustomerID|Customer|CustomerID");
        await moveTo(h.x, h.y, my);
        ripple();
        pointer(h.el, "pointerdown", h.x, h.y);
        pointer(h.el, "pointerup", h.x, h.y);
        await sleep(1300, my);
        var copy = q("#rcopy");
        await moveToEl(copy, my);
        ripple();
        copy.textContent = "Copied"; // shown, not clicked: the frame has no clipboard access
        toast("JOIN copied");
        await sleep(2000, my);
      },
      async function (my) { // selectors
        reset();
        await sleep(700, my);
        var f = q("#filter");
        await moveToEl(f, my, 60);
        ripple();
        await sleep(200, my);
        await type(f, "+SalesOrderDetail", my);
        key(f, "Enter");
        await sleep(2800, my);
      },
      async function (my) { // join path
        reset();
        await sleep(600, my);
        await pick("SalesOrderDetail", my);
        await sleep(900, my);
        var pin = q("#pathto");
        await moveToEl(pin, my, 50);
        ripple();
        await type(pin, "Person", my);
        key(pin, "Enter");
        await sleep(1600, my);
        var sql = q("#pathsql");
        if (sql) { await moveToEl(sql, my); ripple(); toast("SQL copied"); }
        await sleep(2400, my);
      },
    ];

    function mark(i) {
      chapters.forEach(function (c, j) {
        c.classList.toggle("on", j === i);
        c.classList.toggle("done", j < i);
        c.style.setProperty("--dur", DUR[j] + "s");
      });
      var bar = chapters[i].querySelector("i");
      bar.style.animation = "none";
      void bar.offsetWidth;
      bar.style.animation = "";
    }
    async function play(from) {
      var my = ++token;
      try {
        for (var i = from; ; i = (i + 1) % steps.length) {
          mark(i);
          if (i === 0) { reset(); await sleep(800, my); }
          await steps[i](my);
        }
      } catch (e) {
        if (!(e instanceof Stop)) throw e;
      }
    }
    /* Reduced motion: no cursor travel, no waiting; just the chapter's end state. */
    async function jump(i) {
      var my = ++token;
      instant = true;
      try {
        if (i !== 1) reset();
        await steps[i](my);
      } catch (e) {
        if (!(e instanceof Stop)) throw e;
      } finally {
        instant = false;
      }
    }
    function yours() {
      clearTimeout(resumeT);
      token++;
      frame.classList.add("mine");
      stateEl.textContent = "Your turn";
    }

    function live() {
      section.classList.add("live");
      fitScale();
      window.addEventListener("resize", function () { if (frame.isConnected) fitScale(); });
      chapters.forEach(function (c, j) {
        c.addEventListener("click", function () {
          if (reduce) { jump(j); return; }
          if (j !== 1) reset();
          play(j);
        });
      });
      if (reduce) { yours(); return; }
      frame.addEventListener("mouseenter", yours);
      frame.addEventListener("mouseleave", function () {
        frame.classList.remove("mine");
        stateEl.textContent = "Playing";
        resumeT = setTimeout(function () { play(0); }, 1500);
      });
      var io = new IntersectionObserver(function (es) {
        if (es[0].isIntersecting) { io.disconnect(); setTimeout(function () { if (!frame.classList.contains("mine")) play(0); }, 600); }
      }, { threshold: 0.4 });
      io.observe(frame);
    }

    // load the page only when the section comes near, and keep the still screenshot if it isn't a qdbd page
    window.qhome.onView(frame, function () {
      ifr = document.createElement("iframe");
      ifr.title = "qdbd viewer demo";
      ifr.tabIndex = -1;
      ifr.addEventListener("load", function () {
        try {
          W = ifr.contentWindow;
          D = ifr.contentDocument;
          if (!D.getElementById("qdbd-data") || !W.qdbdViewer) throw new Error("not a qdbd page");
        } catch (e) {
          ifr.remove();
          ifr = null;
          return;
        }
        live();
      });
      ifr.src = frame.getAttribute("data-src");
      stage.insertBefore(ifr, overlay);
      fitScale();
    }, "300px 0px 300px 0px");
  });
})();
