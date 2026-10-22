/* qdbd serve: editor pane (one tab per file), autosave, live reload, problems panel. */
(function () {
  "use strict";
  var AUTOSAVE_MS = 1000;
  var files = {}; // path -> {path, text (disk), mtime, doc, dirty, timer, sentText}
  var order = [];
  var active = null;
  var cm = null, textarea = null;
  var diagnostics = [];
  var tabs = document.getElementById("tabs");
  var problems = document.getElementById("problems");
  var banner = document.getElementById("banner");

  if (window.CodeMirror && CodeMirror.defineSimpleMode) {
    CodeMirror.defineSimpleMode("qdbd", {
      start: [
        { regex: /#.*/, token: "comment" },
        { regex: /"(?:[^"])*"/, token: "string" },
        { regex: /^\s*\[(tables|settings|layout)\]\s*$/i, token: "header" },
        { regex: /^-+\s*$/, token: "qdbd-op" },
        { regex: /(>-<|>0-|-0<|0-0|-<|>-|-0|0-)(?=\s)/, token: "qdbd-op" },
        { regex: /\b(PK|FK|NULL|NULLABLE|UNIQUE|INDEX|IDENTITY|AUTOINCREMENT|as|rel)\b/i, token: "qdbd-kw" },
        { regex: /default=\S*/i, token: "qdbd-kw" },
        { regex: /^[^\s#-][^#]*$/, token: null, sol: true },
      ],
    });
    CodeMirror.defineSimpleMode("dbml", {
      start: [
        { regex: /\/\/.*/, token: "comment" },
        { regex: /\/\*/, token: "comment", next: "comment" },
        { regex: /'''/, token: "string", next: "note" },
        { regex: /'(?:[^'\\]|\\.)*'?/, token: "string" },
        { regex: /"(?:[^"\\]|\\.)*"?/, token: "variable-2" },
        { regex: /`[^`]*`?/, token: "string-2" },
        { regex: /#[0-9a-fA-F]{3,6}\b/, token: "number" },
        { regex: /\b(Table|TablePartial|TableGroup|Ref|Enum|Project|Note|indexes|checks|records|Dep|as)\b/i, token: "qdbd-kw" },
        { regex: /\b(pk|primary key|not null|null|unique|increment|default|note|ref|headercolor|delete|update)\b/i, token: "keyword" },
        { regex: /\?(<>|<|>|-)\??|(<>|<|>|-)\?|<>|[<>~]/, token: "qdbd-op" },
        { regex: /-?\d+(\.\d+)?/, token: "number" },
      ],
      comment: [{ regex: /.*?\*\//, token: "comment", next: "start" }, { regex: /.*/, token: "comment" }],
      note: [{ regex: /.*?'''/, token: "string", next: "start" }, { regex: /.*/, token: "string" }],
    });
  }

  function modeOf(f) { return f.syntax === "dbml" || /\.dbml$/i.test(f.path) ? "dbml" : "qdbd"; }

  function editorValue() { return cm ? cm.getValue() : textarea.value; }

  function makeEditor() {
    var host = document.getElementById("editor");
    if (window.CodeMirror) {
      cm = CodeMirror(host, { lineNumbers: true, mode: "qdbd", indentWithTabs: false, tabSize: 2, extraKeys: { Tab: false } });
      cm.on("change", function (_, ch) { if (ch.origin !== "setValue") onEdit(); });
    } else {
      textarea = document.createElement("textarea");
      textarea.spellcheck = false;
      host.appendChild(textarea);
      textarea.addEventListener("input", onEdit);
    }
  }

  function setEditorText(f) {
    if (cm) {
      if (!f.doc) f.doc = CodeMirror.Doc(f.text, modeOf(f));
      cm.swapDoc(f.doc);
    } else {
      textarea.value = f.buffer != null ? f.buffer : f.text;
    }
  }

  function currentText(f) {
    if (cm) return f.doc ? f.doc.getValue() : f.text;
    return f === files[active] ? textarea.value : (f.buffer != null ? f.buffer : f.text);
  }

  function replaceText(f, text) {
    if (cm && f.doc) {
      var cur = f.doc.getCursor(), scroll = f === files[active] ? cm.getScrollInfo() : null;
      f.doc.setValue(text);
      f.doc.setCursor(cur);
      if (scroll) cm.scrollTo(scroll.left, scroll.top);
    } else {
      f.buffer = text;
      if (f === files[active]) textarea.value = text;
    }
  }

  function drawTabs() {
    tabs.innerHTML = "";
    order.forEach(function (p) {
      var f = files[p], b = document.createElement("button");
      b.innerHTML = p.split("/").pop() + (f.dirty ? ' <span class="dirty">●</span>' : "");
      b.title = p;
      b.className = p === active ? "on" : "";
      b.onclick = function () { activate(p); };
      tabs.appendChild(b);
    });
  }

  function activate(p) {
    if (!cm && active && files[active]) files[active].buffer = textarea.value;
    active = p;
    setEditorText(files[p]);
    drawTabs();
    markLines();
    showBanner();
  }

  function onEdit() {
    var f = files[active];
    if (!f) return;
    if (!cm) f.buffer = textarea.value;
    f.dirty = currentText(f) !== f.text;
    drawTabs();
    clearTimeout(f.timer);
    f.timer = setTimeout(function () { save(f); }, AUTOSAVE_MS);
  }

  function save(f) {
    if (!f.dirty || f.conflict) return;
    var text = currentText(f);
    fetch("/file", { method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: f.path, text: text, mtime: f.mtime }) })
      .then(function (r) { return r.json().then(function (j) { return [r.status, j]; }); })
      .then(function (res) {
        var code = res[0], j = res[1];
        if (code === 200) {
          f.text = text;
          f.mtime = j.mtime;
          f.dirty = currentText(f) !== f.text;
          if (f.dirty) onEditFor(f);
        } else if (code === 409) {
          f.conflict = { text: j.text, mtime: j.mtime };
          showBanner();
        }
        drawTabs();
      });
  }

  function onEditFor(f) {
    clearTimeout(f.timer);
    f.timer = setTimeout(function () { save(f); }, AUTOSAVE_MS);
  }

  function showBanner() {
    var f = files[active];
    banner.classList.toggle("open", !!(f && f.conflict));
  }
  document.getElementById("keepmine").onclick = function () {
    var f = files[active];
    if (!f || !f.conflict) return;
    f.mtime = f.conflict.mtime;
    f.text = f.conflict.text;
    f.conflict = null;
    f.dirty = true;
    showBanner();
    save(f);
  };
  document.getElementById("reload").onclick = function () {
    var f = files[active];
    if (!f || !f.conflict) return;
    f.text = f.conflict.text;
    f.mtime = f.conflict.mtime;
    f.conflict = null;
    f.dirty = false;
    replaceText(f, f.text);
    showBanner();
    drawTabs();
  };

  /* ------------------------------------------------------------- problems */
  var marked = [];
  function markLines() {
    if (!cm) return;
    marked.forEach(function (m) { m.doc.removeLineClass(m.line, "background", "lineerr"); });
    marked = [];
    var f = files[active];
    if (!f || !f.doc) return;
    diagnostics.forEach(function (d) {
      if (d.path === active && d.severity === "error") {
        f.doc.addLineClass(d.line - 1, "background", "lineerr");
        marked.push({ doc: f.doc, line: d.line - 1 });
      }
    });
  }

  function drawProblems() {
    var errors = diagnostics.filter(function (d) { return d.severity === "error"; });
    problems.classList.toggle("bad", errors.length > 0);
    if (!diagnostics.length) {
      problems.textContent = "No errors found. Good job!";
      return;
    }
    problems.innerHTML = "";
    if (errors.length) {
      var note = document.createElement("div");
      note.textContent = "Showing the last valid diagram until these are fixed:";
      note.style.color = "#aaa";
      problems.appendChild(note);
    }
    diagnostics.forEach(function (d) {
      var el = document.createElement("div");
      el.className = d.severity === "error" ? "err" : "warn";
      el.textContent = d.text;
      el.onclick = function () {
        if (files[d.path]) {
          activate(d.path);
          if (cm) { cm.focus(); cm.setCursor({ line: d.line - 1, ch: 0 }); }
        }
      };
      problems.appendChild(el);
    });
  }

  /* ------------------------------------------------------------- sync with server */
  var lastVersion = -1;
  function refresh(first) {
    return fetch("/state").then(function (r) { return r.json(); }).then(function (st) {
      if (st.version === lastVersion) return;
      lastVersion = st.version;
      var seen = {};
      st.files.forEach(function (sf) {
        seen[sf.path] = true;
        var f = files[sf.path];
        if (!f) {
          files[sf.path] = { path: sf.path, text: sf.text, mtime: sf.mtime, syntax: sf.syntax, dirty: false };
          order.push(sf.path);
          return;
        }
        if (sf.mtime === f.mtime) return;
        if (f.dirty) {
          if (sf.text !== currentText(f)) f.conflict = { text: sf.text, mtime: sf.mtime };
          else { f.text = sf.text; f.mtime = sf.mtime; f.dirty = false; }
        } else {
          f.text = sf.text;
          f.mtime = sf.mtime;
          if (currentText(f) !== sf.text) replaceText(f, sf.text);
        }
      });
      order = order.filter(function (p) { return seen[p]; });
      diagnostics = st.diagnostics;
      if (first) activate(order[0]);
      drawTabs();
      showBanner();
      drawProblems();
      markLines();
      if (!first) window.qdbdViewer.setData(st.model, st.positions);
    });
  }

  window.qdbdServe = {
    saveLayout: function (body) {
      fetch("/layout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    },
  };

  makeEditor();
  refresh(true).then(function () {
    var es = new EventSource("/events");
    es.onmessage = function () { refresh(false); };
  });
})();
