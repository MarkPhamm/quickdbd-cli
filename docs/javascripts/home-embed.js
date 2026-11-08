/* Home page dbt yml demo: the real viewer in an iframe (assets/tour/dbt-docs.html, same origin), scaled to the
 * section. The still screenshot stays on phones and touch screens, and until the section is near. Hovering hands
 * control to the visitor. The viewer's own hash (#t=orders) opens the table the section is about. */
(function () {
  "use strict";

  window.qhome.add(function (root) {
    var embed = root.querySelector(".qh-embed");
    if (!embed || window.matchMedia("(max-width: 960px), (hover: none)").matches) return;
    var stage = embed.querySelector(".qh-tour__stage"), stateEl = embed.querySelector(".qh-tour__state");
    var ifr = null;

    function fit() {
      if (ifr) ifr.style.transform = "scale(" + stage.clientWidth / 1440 + ")";
    }
    function yours(on) {
      embed.classList.toggle("mine", on);
      if (stateEl) stateEl.textContent = on ? "Your turn" : "Live";
    }

    window.qhome.onView(embed, function () {
      ifr = document.createElement("iframe");
      ifr.title = embed.getAttribute("data-title") || "qdbd viewer demo";
      ifr.tabIndex = -1;
      ifr.addEventListener("load", function () {
        try {
          var W = ifr.contentWindow, D = ifr.contentDocument;
          if (!D.getElementById("qdbd-data") || !W.qdbdViewer) throw new Error("not a qdbd page");
          D.documentElement.setAttribute("data-theme", "light"); // the home page is light; the viewer would follow a dark OS
          embed.classList.add("live");
        } catch (e) {
          ifr.remove();
          ifr = null;
        }
      });
      ifr.src = embed.getAttribute("data-src");
      stage.insertBefore(ifr, stage.firstChild);
      fit();
    }, "300px 0px 300px 0px");

    window.addEventListener("resize", fit);
    embed.addEventListener("mouseenter", function () { yours(true); });
    embed.addEventListener("mouseleave", function () { yours(false); });
  });
})();
