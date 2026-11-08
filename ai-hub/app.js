(function () {
  "use strict";
  var I18N = window.I18N, DATA = window.AI_HUB_DATA;
  var LANGS = ["en", "uz", "ru"];
  var CATS = ["all", "model", "tool", "repo", "learn", "site"];
  var PRICES = ["free", "freemium", "paid", "open"];
  // Category <-> URL hash, so a link like ".../#repos" opens that section.
  var HASH = { all: "", model: "models", tool: "tools", repo: "repos", learn: "learning", site: "websites" };

  function store(k, v) {
    try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; }
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  // Lower-case and drop apostrophe variants so "o'zbek", "oʻzbek" and "ozbek" all match.
  function norm(s) { return String(s).toLowerCase().replace(/[ʻʼ'’`‘]/g, ""); }
  function host(u) { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (e) { return u; } }

  // Search text covers every language, so a Russian query finds items while the UI is in English.
  DATA.forEach(function (it) {
    var parts = [it.name, it.by, host(it.url), it.d.en, it.d.uz, it.d.ru];
    LANGS.forEach(function (l) {
      parts.push(I18N[l].cats[it.type], I18N[l].price[it.price]);
      it.tags.forEach(function (t) { parts.push(I18N[l].tags[t] || t); });
    });
    it._hay = norm(parts.join(" "));
  });
  DATA.sort(function (a, b) { return a.name.localeCompare(b.name); });

  var saved = store("aixona-lang");
  var nav = (navigator.language || "en").slice(0, 2);
  var state = {
    lang: LANGS.indexOf(saved) >= 0 ? saved : LANGS.indexOf(nav) >= 0 ? nav : "en",
    cat: "all", price: "all", q: ""
  };

  var $ = function (id) { return document.getElementById(id); };
  var q = $("q"), tabs = $("tabs"), priceEl = $("price"), grid = $("grid"), count = $("count"), empty = $("empty");

  function catFromHash() {
    var h = location.hash.replace("#", "");
    for (var k in HASH) if (HASH[k] && HASH[k] === h) return k;
    return "all";
  }

  function matches(it, ignoreCat) {
    if (!ignoreCat && state.cat !== "all" && it.type !== state.cat) return false;
    if (state.price !== "all" && it.price !== state.price) return false;
    if (state.q) {
      var words = norm(state.q).split(/\s+/).filter(Boolean);
      for (var i = 0; i < words.length; i++) if (it._hay.indexOf(words[i]) < 0) return false;
    }
    return true;
  }

  function renderChrome() {
    var T = I18N[state.lang];
    document.documentElement.lang = T.htmlLang;
    document.querySelectorAll("[data-i18n]").forEach(function (el) { el.innerHTML = T[el.getAttribute("data-i18n")]; });
    q.placeholder = T.searchPh;
    document.querySelectorAll(".lang button").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-lang") === state.lang));
    });
    priceEl.setAttribute("aria-label", T.priceAll);
    priceEl.innerHTML = ["all"].concat(PRICES).map(function (p) {
      return '<button type="button" class="chip" data-price="' + p + '" aria-pressed="' + (state.price === p) + '">' +
        esc(p === "all" ? T.priceAll : T.price[p]) + "</button>";
    }).join("");
  }

  function render() {
    var T = I18N[state.lang];
    tabs.innerHTML = CATS.map(function (c) {
      var n = DATA.filter(function (it) { return (c === "all" || it.type === c) && matches(it, true); }).length;
      return '<a class="tab" href="#' + HASH[c] + '" data-cat="' + c + '"' +
        (state.cat === c ? ' aria-current="page"' : "") + ">" + esc(T.cats[c]) + '<span class="n">' + n + "</span></a>";
    }).join("");

    var list = DATA.filter(function (it) { return matches(it); });
    count.textContent = T.count(list.length);
    empty.hidden = list.length > 0;
    if (!list.length) empty.textContent = T.empty(state.q.trim());

    grid.innerHTML = list.map(function (it) {
      return '<article class="card">' +
        '<div class="card-top"><span class="type" data-t="' + it.type + '">' + esc(T.cats[it.type]) + "</span>" +
        '<span class="price" data-p="' + it.price + '">' + esc(T.price[it.price]) + "</span></div>" +
        "<h3>" + esc(it.name) + "</h3>" +
        '<p class="by">' + esc(it.by) + "</p>" +
        '<p class="desc">' + esc(it.d[state.lang] || it.d.en) + "</p>" +
        '<div class="tags">' + it.tags.map(function (t) {
          return '<button type="button" class="tag" data-tag="' + esc(t) + '">' + esc(T.tags[t] || t) + "</button>";
        }).join("") + "</div>" +
        '<a class="visit" href="' + esc(it.url) + '" target="_blank" rel="noopener noreferrer">' +
        '<span class="label">' + esc(T.visit) + " ↗</span>" + '<span class="host">' + esc(host(it.url)) + "</span></a>" +
        "</article>";
    }).join("");
  }

  // Events
  document.querySelector(".lang").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-lang]");
    if (!b) return;
    state.lang = b.getAttribute("data-lang");
    store("aixona-lang", state.lang);
    renderChrome(); render();
  });
  q.addEventListener("input", function () { state.q = q.value; render(); });
  priceEl.addEventListener("click", function (e) {
    var b = e.target.closest("[data-price]");
    if (!b) return;
    state.price = b.getAttribute("data-price");
    renderChrome(); render();
  });
  tabs.addEventListener("click", function (e) {
    var a = e.target.closest("[data-cat]");
    if (!a) return;
    e.preventDefault();
    state.cat = a.getAttribute("data-cat");
    var h = HASH[state.cat];
    if (history.replaceState) history.replaceState(null, "", h ? "#" + h : location.pathname + location.search);
    else location.hash = h;
    render();
  });
  grid.addEventListener("click", function (e) {
    var t = e.target.closest("[data-tag]");
    if (!t) return;
    q.value = I18N[state.lang].tags[t.getAttribute("data-tag")] || t.getAttribute("data-tag");
    state.q = q.value; render();
    q.focus();
  });
  window.addEventListener("hashchange", function () { state.cat = catFromHash(); render(); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement !== q && !/input|textarea/i.test(document.activeElement.tagName)) {
      e.preventDefault(); q.focus();
    } else if (e.key === "Escape" && document.activeElement === q) {
      q.value = ""; state.q = ""; render();
    }
  });

  state.cat = catFromHash();
  renderChrome();
  render();
})();
