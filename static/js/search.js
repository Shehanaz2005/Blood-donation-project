/* Blood Connect — donor directory live search.
 *
 * The page is fully rendered on the server; this script upgrades the filter
 * form to fetch JSON from /api/v1/donors and re-render the same card markup
 * without a full reload. All values from the API are escaped before use.
 */
(function () {
  "use strict";

  var form = document.getElementById("donorSearchForm");
  if (!form) return;

  var resultsHost = document.getElementById("donorResults");
  var paginationHost = document.getElementById("donorPagination");
  var errorBox = document.getElementById("searchError");
  var retryButton = document.getElementById("retrySearch");
  var countLabel = document.getElementById("resultCount");
  var hintLabel = document.getElementById("resultHint");
  var chipsHost = document.querySelector(".results-toolbar__chips");
  var clearLink = document.getElementById("clearFilters");

  var apiUrl = form.getAttribute("data-api-url") || "/api/v1/donors";
  var formAction = form.getAttribute("action") || window.location.pathname;
  var viewerRole = form.getAttribute("data-viewer-role") || "anonymous";

  var currentPage = 1;
  var currentController = null;

  var DEFAULTS = {
    blood_group: "",
    city: "",
    compatible: "0",
    available: "1",
    verified: "1",
    eligible: "1",
    sort: "recommended",
  };

  /* ------------------------------------------------------------------
   * Helpers
   * ------------------------------------------------------------------ */
  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatShortDate(iso) {
    if (!iso) return "";
    var parts = String(iso).split("-");
    if (parts.length !== 3) return escapeHtml(iso);
    var date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    if (isNaN(date.getTime())) return escapeHtml(iso);
    var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return date.getDate() + " " + months[date.getMonth()];
  }

  function plural(count, singular, pluralWord) {
    return count === 1 ? singular : pluralWord || singular + "s";
  }

  function setHidden(element, hidden) {
    if (!element) return;
    if (hidden) {
      element.setAttribute("hidden", "hidden");
    } else {
      element.removeAttribute("hidden");
    }
  }

  function buildParams(page) {
    var params = new URLSearchParams();
    var checkboxNames = {};
    form.querySelectorAll('input[type="checkbox"][name]').forEach(function (box) {
      checkboxNames[box.name] = true;
    });

    form.querySelectorAll("input[name], select[name]").forEach(function (field) {
      var name = field.name;
      if (!name || field.disabled) return;

      if (field.type === "checkbox") {
        params.set(name, field.checked ? "1" : "0");
        return;
      }
      if (field.type === "hidden" && checkboxNames[name]) return;
      if (field.type === "submit" || field.type === "button" || field.type === "reset") return;

      var value = (field.value || "").trim();
      if (value !== "") params.set(name, value);
    });

    if (page && page > 1) {
      params.set("page", String(page));
    }
    return params;
  }

  function urlForPage(page) {
    var query = buildParams(page).toString();
    return query ? formAction + "?" + query : formAction;
  }

  function applyParamsToForm(params) {
    form.querySelectorAll("input[name], select[name]").forEach(function (field) {
      var name = field.name;
      if (!name || field.type === "submit" || field.type === "button") return;

      var fallback = Object.prototype.hasOwnProperty.call(DEFAULTS, name) ? DEFAULTS[name] : "";
      var value = params.has(name) ? params.get(name) : fallback;

      if (field.type === "checkbox") {
        field.checked = value === "1" || value === "true" || value === "on";
      } else if (field.tagName === "SELECT") {
        field.value = value || "";
      } else if (field.type !== "hidden") {
        field.value = value || "";
      }
    });
  }

  /* ------------------------------------------------------------------
   * Card rendering — mirrors templates/macros/ui.html
   * ------------------------------------------------------------------ */
  function badgeMarkup(donor) {
    var html = "";
    if (donor.is_verified) {
      html +=
        '<span class="mini-badge mini-badge--verified"><i class="fa-solid fa-circle-check"></i> Verified</span>';
    } else {
      html +=
        '<span class="mini-badge mini-badge--muted"><i class="fa-solid fa-clock"></i> Awaiting verification</span>';
    }

    if (donor.is_available && donor.is_eligible) {
      html +=
        '<span class="mini-badge mini-badge--available"><i class="fa-solid fa-circle"></i> Available now</span>';
    } else if (donor.is_in_cooldown) {
      html +=
        '<span class="mini-badge mini-badge--muted"><i class="fa-solid fa-hourglass-half"></i> Eligible ' +
        escapeHtml(formatShortDate(donor.next_eligible_date)) +
        "</span>";
    } else {
      html +=
        '<span class="mini-badge mini-badge--muted"><i class="fa-solid fa-circle"></i> Unavailable</span>';
    }
    return html;
  }

  function actionMarkup(donor) {
    var html =
      '<a class="btn btn-outline-red w-100" href="' +
      escapeHtml(donor.url || "#") +
      '">View profile</a>';

    if (donor.request_url) {
      html +=
        '<a class="btn btn-red w-100" href="' +
        escapeHtml(donor.request_url) +
        '"><i class="fa-solid fa-droplet" aria-hidden="true"></i> Request blood</a>';
    } else if (viewerRole === "receiver") {
      html +=
        '<button class="btn btn-light-soft w-100" type="button" disabled title="This donor is not currently accepting requests">Not accepting requests</button>';
    } else if (viewerRole === "anonymous") {
      html +=
        '<a class="btn btn-red w-100" href="' +
        escapeHtml(donor.login_url || "/auth/login") +
        '">Sign in to contact</a>';
    }
    return html;
  }

  function donorCard(donor) {
    var bio = donor.bio
      ? '<p class="donor-card__bio">' + escapeHtml(donor.bio) + "</p>"
      : "";

    return (
      '<div class="col-md-6 col-xl-4">' +
      '<article class="donor-card">' +
      '<div class="donor-card__head">' +
      '<span class="avatar avatar--lg">' +
      escapeHtml(donor.initials || "D") +
      "</span>" +
      '<div class="donor-card__identity">' +
      "<h3>" +
      escapeHtml(donor.name || "Donor") +
      "</h3>" +
      '<p><i class="fa-solid fa-location-dot" aria-hidden="true"></i> ' +
      escapeHtml(donor.city || "—") +
      "</p>" +
      "</div>" +
      '<span class="blood-badge blood-badge--lg">' +
      escapeHtml(donor.blood_group || "?") +
      "</span>" +
      "</div>" +
      '<div class="donor-card__badges">' +
      badgeMarkup(donor) +
      "</div>" +
      bio +
      '<dl class="donor-card__meta">' +
      "<div><dt>Donations</dt><dd>" +
      escapeHtml(donor.total_donations || 0) +
      "</dd></div>" +
      "<div><dt>Level</dt><dd>" +
      escapeHtml(donor.donor_level || "New donor") +
      "</dd></div>" +
      "<div><dt>Member since</dt><dd>" +
      escapeHtml(donor.member_since || "—") +
      "</dd></div>" +
      "</dl>" +
      '<div class="donor-card__actions">' +
      actionMarkup(donor) +
      "</div>" +
      "</article>" +
      "</div>"
    );
  }

  function emptyMarkup() {
    return (
      '<div class="col-12">' +
      '<div class="empty-state">' +
      '<span class="empty-state__icon"><i class="fa-solid fa-magnifying-glass" aria-hidden="true"></i></span>' +
      "<h3>No donors match these filters</h3>" +
      "<p>Try a wider city, enable compatible groups, or clear the verified/eligible filters. New donors join every week.</p>" +
      '<a class="btn btn-red" href="' +
      escapeHtml(formAction) +
      '">Reset search</a>' +
      "</div>" +
      "</div>"
    );
  }

  function skeletonMarkup(count) {
    var html = "";
    for (var index = 0; index < count; index += 1) {
      html +=
        '<div class="col-md-6 col-xl-4"><div class="skeleton-card" aria-hidden="true">' +
        '<div class="skeleton-line skeleton-line--circle"></div>' +
        '<div class="skeleton-line"></div>' +
        '<div class="skeleton-line skeleton-line--short"></div>' +
        '<div class="skeleton-line mt-4"></div>' +
        '<div class="skeleton-line"></div>' +
        "</div></div>";
    }
    return html;
  }

  /* ------------------------------------------------------------------
   * Toolbar, pagination and errors
   * ------------------------------------------------------------------ */
  function renderToolbar(meta) {
    var total = meta.total || 0;
    if (countLabel) {
      countLabel.textContent = String(total);
      var parent = countLabel.parentNode;
      if (parent && parent.childNodes.length > 1) {
        var textNode = null;
        parent.childNodes.forEach(function (node) {
          if (node.nodeType === 3 && node.textContent.indexOf("donor") !== -1) {
            textNode = node;
          }
        });
        if (textNode) {
          textNode.textContent = " " + plural(total, "donor") + " found";
        }
      }
    }

    var filters = meta.filters || {};
    if (hintLabel) {
      var hint = filters.blood_group
        ? "Group " + filters.blood_group + (filters.compatible ? " + compatible" : "")
        : "All blood groups";
      if (filters.city) hint += " in " + filters.city;
      hintLabel.textContent = hint;
    }

    if (chipsHost) {
      var chips = [];
      if (filters.blood_group) {
        chips.push('<span class="filter-chip">Group ' + escapeHtml(filters.blood_group) + "</span>");
      }
      if (filters.city) {
        chips.push(
          '<span class="filter-chip"><i class="fa-solid fa-location-dot"></i> ' +
            escapeHtml(filters.city) +
            "</span>"
        );
      }
      if (filters.compatible) chips.push('<span class="filter-chip">Compatible</span>');
      if (filters.verified) chips.push('<span class="filter-chip">Verified</span>');
      chipsHost.innerHTML = chips.join("");
    }
  }

  function pageList(current, total) {
    var pages = [];
    var add = function (value) {
      if (pages.indexOf(value) === -1) pages.push(value);
    };
    add(1);
    for (var page = current - 1; page <= current + 1; page += 1) {
      if (page > 1 && page < total) add(page);
    }
    if (total > 1) add(total);

    var output = [];
    for (var index = 0; index < pages.length; index += 1) {
      if (index > 0 && pages[index] - pages[index - 1] > 1) output.push("ellipsis");
      output.push(pages[index]);
    }
    return output;
  }

  function renderPagination(meta) {
    if (!paginationHost) return;
    if (!meta.pages || meta.pages <= 1) {
      paginationHost.innerHTML = "";
      return;
    }

    var html =
      '<nav class="mt-4" aria-label="Pagination"><ul class="pagination app-pagination justify-content-center flex-wrap">';

    html +=
      '<li class="page-item ' +
      (meta.has_prev ? "" : "disabled") +
      '">' +
      (meta.has_prev
        ? '<a class="page-link" href="' +
          escapeHtml(urlForPage(meta.page - 1)) +
          '" data-page="' +
          (meta.page - 1) +
          '" aria-label="Previous page"><i class="fa-solid fa-chevron-left"></i></a>'
        : '<span class="page-link" aria-hidden="true"><i class="fa-solid fa-chevron-left"></i></span>') +
      "</li>";

    pageList(meta.page, meta.pages).forEach(function (item) {
      if (item === "ellipsis") {
        html += '<li class="page-item disabled"><span class="page-link">…</span></li>';
        return;
      }
      html +=
        '<li class="page-item ' +
        (item === meta.page ? "active" : "") +
        '">' +
        '<a class="page-link" href="' +
        escapeHtml(urlForPage(item)) +
        '" data-page="' +
        item +
        '"' +
        (item === meta.page ? ' aria-current="page"' : "") +
        ">" +
        item +
        "</a></li>";
    });

    html +=
      '<li class="page-item ' +
      (meta.has_next ? "" : "disabled") +
      '">' +
      (meta.has_next
        ? '<a class="page-link" href="' +
          escapeHtml(urlForPage(meta.page + 1)) +
          '" data-page="' +
          (meta.page + 1) +
          '" aria-label="Next page"><i class="fa-solid fa-chevron-right"></i></a>'
        : '<span class="page-link" aria-hidden="true"><i class="fa-solid fa-chevron-right"></i></span>') +
      "</li></ul>";

    if (meta.total) {
      var start = (meta.page - 1) * meta.per_page + 1;
      var end = Math.min(meta.page * meta.per_page, meta.total);
      html +=
        '<p class="pagination-summary text-center">Showing ' +
        start +
        "–" +
        end +
        " of " +
        meta.total +
        "</p>";
    }

    html += "</nav>";
    paginationHost.innerHTML = html;
  }

  function showError() {
    setHidden(errorBox, false);
    if (paginationHost) paginationHost.innerHTML = "";
  }

  function hideError() {
    setHidden(errorBox, true);
  }

  /* ------------------------------------------------------------------
   * Fetch + render
   * ------------------------------------------------------------------ */
  function fetchDonors(page, options) {
    options = options || {};
    var params = buildParams(page);

    if (currentController) currentController.abort();
    currentController = window.AbortController ? new AbortController() : null;

    hideError();
    if (resultsHost) resultsHost.innerHTML = skeletonMarkup(6);
    if (paginationHost) paginationHost.innerHTML = "";

    var requestOptions = {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    };
    if (currentController) requestOptions.signal = currentController.signal;

    fetch(apiUrl + "?" + params.toString(), requestOptions)
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (payload) {
        if (!payload || payload.ok !== true) throw new Error("Invalid response");

        var data = payload.data || [];
        var meta = payload.meta || {};
        currentPage = meta.page || page || 1;

        if (resultsHost) {
          resultsHost.innerHTML = data.length
            ? data.map(donorCard).join("")
            : emptyMarkup();
        }
        renderToolbar(meta);
        renderPagination(meta);

        var query = params.toString();
        var nextUrl = query ? formAction + "?" + query : formAction;
        if (options.push !== false && window.history && history.pushState) {
          history.pushState({ donorSearch: true, page: currentPage }, "", nextUrl);
        }

        if (options.scroll && resultsHost) {
          resultsHost.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      })
      .catch(function (error) {
        if (error && error.name === "AbortError") return;
        if (resultsHost) resultsHost.innerHTML = "";
        showError();
      })
      .finally(function () {
        currentController = null;
      });
  }

  /* ------------------------------------------------------------------
   * Events
   * ------------------------------------------------------------------ */
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    fetchDonors(1, { push: true });
  });

  if (paginationHost) {
    paginationHost.addEventListener("click", function (event) {
      var link = event.target.closest("a[data-page]");
      if (!link) return;
      event.preventDefault();
      var page = Number(link.getAttribute("data-page")) || 1;
      fetchDonors(page, { push: true, scroll: true });
    });
  }

  if (retryButton) {
    retryButton.addEventListener("click", function () {
      fetchDonors(currentPage, { push: false });
    });
  }

  if (clearLink) {
    clearLink.addEventListener("click", function (event) {
      event.preventDefault();
      applyParamsToForm(new URLSearchParams());
      fetchDonors(1, { push: true });
    });
  }

  window.addEventListener("popstate", function () {
    var params = new URLSearchParams(window.location.search);
    applyParamsToForm(params);
    var page = Number(params.get("page")) || 1;
    fetchDonors(page, { push: false });
  });
})();
