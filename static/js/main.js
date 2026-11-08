/* Blood Connect — shared front-end behaviour.
 *
 * Progressive enhancement only: every feature here has a server-rendered
 * fallback, so the site keeps working if JavaScript is unavailable.
 */
(function () {
  "use strict";

  var doc = document;

  function csrfToken() {
    var meta = doc.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  /* ------------------------------------------------------------------
   * Sticky navbar shadow + back-to-top button
   * ------------------------------------------------------------------ */
  function initScrollEffects() {
    var navbar = doc.getElementById("siteNavbar");
    var backToTop = doc.getElementById("backToTop");

    function onScroll() {
      var y = window.scrollY || doc.documentElement.scrollTop || 0;
      if (navbar) {
        navbar.classList.toggle("is-scrolled", y > 8);
      }
      if (backToTop) {
        backToTop.classList.toggle("is-visible", y > 480);
      }
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    if (backToTop) {
      backToTop.addEventListener("click", function () {
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }
  }

  /* ------------------------------------------------------------------
   * Bootstrap tooltips
   * ------------------------------------------------------------------ */
  function initTooltips() {
    if (!window.bootstrap || !window.bootstrap.Tooltip) return;
    doc.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
      window.bootstrap.Tooltip.getOrCreateInstance(el);
    });
  }

  /* ------------------------------------------------------------------
   * Show / hide password fields
   * ------------------------------------------------------------------ */
  function initPasswordToggles() {
    doc.querySelectorAll("[data-password-toggle]").forEach(function (button) {
      var wrapper = button.closest(".password-wrap");
      var input = wrapper ? wrapper.querySelector("input") : null;
      if (!input) return;

      button.addEventListener("click", function () {
        var showing = input.getAttribute("type") === "text";
        input.setAttribute("type", showing ? "password" : "text");
        button.setAttribute("aria-label", showing ? "Show password" : "Hide password");
        button.classList.toggle("is-active", !showing);
        var icon = button.querySelector("i");
        if (icon) {
          icon.classList.toggle("fa-eye", showing);
          icon.classList.toggle("fa-eye-slash", !showing);
        }
        input.focus({ preventScroll: true });
      });
    });
  }

  /* ------------------------------------------------------------------
   * Bootstrap-style client validation
   * ------------------------------------------------------------------ */
  function initValidation() {
    doc.querySelectorAll("form.needs-validation").forEach(function (form) {
      form.addEventListener(
        "submit",
        function (event) {
          if (!form.checkValidity()) {
            event.preventDefault();
            event.stopPropagation();
            var firstInvalid = form.querySelector(":invalid");
            if (firstInvalid && typeof firstInvalid.focus === "function") {
              firstInvalid.focus({ preventScroll: false });
            }
          } else {
            var submitter = event.submitter;
            if (submitter && submitter.tagName === "BUTTON") {
              submitter.dataset.originalText = submitter.innerHTML;
              submitter.disabled = true;
              submitter.innerHTML =
                '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Working…';
            }
          }
          form.classList.add("was-validated");
        },
        false
      );
    });
  }

  /* ------------------------------------------------------------------
   * Sensible date limits
   * ------------------------------------------------------------------ */
  function isoDate(date) {
    var year = date.getFullYear();
    var month = String(date.getMonth() + 1).padStart(2, "0");
    var day = String(date.getDate()).padStart(2, "0");
    return year + "-" + month + "-" + day;
  }

  function initDateLimits() {
    var today = new Date();
    var maxBirth = new Date(today.getFullYear() - 18, today.getMonth(), today.getDate());
    var minBirth = new Date(today.getFullYear() - 65, today.getMonth(), today.getDate());

    doc.querySelectorAll('input[type="date"]').forEach(function (input) {
      var name = input.getAttribute("name") || "";
      if (name === "needed_by") {
        input.min = isoDate(today);
      } else if (name === "last_donation_date") {
        input.max = isoDate(today);
      } else if (name === "date_of_birth") {
        input.max = isoDate(maxBirth);
        input.min = isoDate(minBirth);
      }
    });
  }

  /* ------------------------------------------------------------------
   * Destructive-action confirmation
   * ------------------------------------------------------------------ */
  function initConfirmations() {
    doc.addEventListener("submit", function (event) {
      var form = event.target;
      if (!form || form.tagName !== "FORM") return;

      var submitter = event.submitter;
      var message =
        (submitter && submitter.getAttribute("data-confirm")) ||
        form.getAttribute("data-confirm");

      if (message && !window.confirm(message)) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    });
  }

  /* ------------------------------------------------------------------
   * Donor availability switch (AJAX, falls back to a normal POST)
   * ------------------------------------------------------------------ */
  function initAvailabilityToggle() {
    var form = doc.querySelector("[data-availability-form]");
    if (!form) return;

    var checkbox = form.querySelector('input[name="available"]');
    var label = form.querySelector("[data-availability-label]");
    var card = form.closest(".availability-card");
    if (!checkbox) return;

    var endpoint = form.getAttribute("data-url") || form.getAttribute("action");
    var inFlight = false;

    function paint(available) {
      checkbox.checked = available;
      if (label) label.textContent = available ? "Available" : "Unavailable";
      if (card) {
        card.classList.toggle("is-on", available);
        card.classList.toggle("is-off", !available);
      }
    }

    function showMessage(text, tone) {
      var host = card ? card.parentNode : form.parentNode;
      var existing = doc.getElementById("availabilityFeedback");
      if (existing) existing.remove();
      if (!text) return;
      var box = doc.createElement("div");
      box.id = "availabilityFeedback";
      box.className = "alert alert-" + (tone || "info") + " app-alert mt-3";
      box.setAttribute("role", "status");
      box.textContent = text;
      host.insertBefore(box, card ? card.nextSibling : form.nextSibling);
    }

    checkbox.addEventListener("change", function () {
      if (inFlight) {
        checkbox.checked = !checkbox.checked;
        return;
      }
      if (!endpoint || !window.fetch) {
        form.submit();
        return;
      }

      var desired = checkbox.checked;
      inFlight = true;
      checkbox.disabled = true;

      fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({ available: desired }),
      })
        .then(function (response) {
          return response.json().then(function (payload) {
            return { ok: response.ok, payload: payload };
          });
        })
        .then(function (result) {
          var payload = result.payload || {};
          if (!result.ok || payload.ok === false) {
            paint(!desired);
            showMessage(
              (payload.error && payload.error.message) ||
                payload.message ||
                "We could not update your availability. Please try again.",
              "danger"
            );
            return;
          }
          paint(Boolean(payload.is_available));
          showMessage(
            payload.message ||
              (payload.is_available
                ? "You are now visible as available to receivers."
                : "You are now marked as unavailable."),
            payload.is_available ? "success" : "info"
          );
          if (window.setTimeout) {
            window.setTimeout(function () {
              var box = doc.getElementById("availabilityFeedback");
              if (box) box.remove();
            }, 6000);
          }
        })
        .catch(function () {
          paint(!desired);
          showMessage("Network error — your availability was not changed.", "danger");
        })
        .finally(function () {
          inFlight = false;
          checkbox.disabled = false;
        });
    });
  }

  /* ------------------------------------------------------------------
   * Auto-dismiss flash messages
   * ------------------------------------------------------------------ */
  function initFlashAlerts() {
    if (!window.bootstrap || !window.bootstrap.Alert) return;
    doc.querySelectorAll(".flash-stack .app-alert").forEach(function (alert) {
      window.setTimeout(function () {
        window.bootstrap.Alert.getOrCreateInstance(alert).close();
      }, 7000);
    });
  }

  /* ------------------------------------------------------------------
   * Close the mobile menu after choosing a link
   * ------------------------------------------------------------------ */
  function initMobileNav() {
    var collapse = doc.getElementById("mainNav");
    if (!collapse || !window.bootstrap || !window.bootstrap.Collapse) return;
    collapse.querySelectorAll(".nav-link, .dropdown-item").forEach(function (link) {
      link.addEventListener("click", function () {
        if (window.innerWidth < 992 && collapse.classList.contains("show")) {
          window.bootstrap.Collapse.getOrCreateInstance(collapse).hide();
        }
      });
    });
  }

  /* ------------------------------------------------------------------
   * Smooth in-page anchors (respecting reduced motion)
   * ------------------------------------------------------------------ */
  function initSmoothAnchors() {
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    doc.querySelectorAll('a[href^="#"]').forEach(function (link) {
      var targetId = link.getAttribute("href");
      if (!targetId || targetId === "#") return;
      link.addEventListener("click", function (event) {
        var target = doc.querySelector(targetId);
        if (!target) return;
        event.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        if (history.replaceState) history.replaceState(null, "", targetId);
      });
    });
  }

  function init() {
    initScrollEffects();
    initTooltips();
    initPasswordToggles();
    initValidation();
    initDateLimits();
    initConfirmations();
    initAvailabilityToggle();
    initFlashAlerts();
    initMobileNav();
    initSmoothAnchors();
  }

  if (doc.readyState === "loading") {
    doc.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
