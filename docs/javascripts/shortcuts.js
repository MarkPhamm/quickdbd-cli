// ⌘K / Ctrl+K opens search, like modelith.sh
document.addEventListener("keydown", function (e) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    var toggle = document.getElementById("__search");
    if (!toggle) return;
    toggle.checked = true;
    toggle.dispatchEvent(new Event("change"));
    setTimeout(function () {
      var input = document.querySelector(".md-search__input");
      if (input) input.focus();
    }, 30);
  }
});
