/* Orithena Pulse — lightweight interactivity (no frameworks) */

(function () {
  "use strict";

  // --- Dark mode toggle ---
  var THEME_KEY = "pulse-theme";
  var html = document.documentElement;
  var toggle = document.getElementById("theme-toggle");

  function applyTheme(theme) {
    html.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
  }

  // Restore saved preference, or respect OS preference
  var saved = localStorage.getItem(THEME_KEY);
  if (saved) {
    applyTheme(saved);
  } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    applyTheme("dark");
  }

  if (toggle) {
    toggle.addEventListener("click", function () {
      var current = html.getAttribute("data-theme") || "light";
      applyTheme(current === "dark" ? "light" : "dark");
    });
  }

  // --- Section filtering ---
  // Clicking a section title toggles collapse
  var sectionTitles = document.querySelectorAll(".section-title");
  for (var i = 0; i < sectionTitles.length; i++) {
    sectionTitles[i].style.cursor = "pointer";
    sectionTitles[i].addEventListener("click", function () {
      var list = this.nextElementSibling;
      if (list && list.classList.contains("item-list")) {
        var hidden = list.style.display === "none";
        list.style.display = hidden ? "" : "none";
      }
    });
  }
})();
