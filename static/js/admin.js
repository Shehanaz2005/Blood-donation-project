/* Blood Connect — administrator dashboard charts.
 *
 * Chart.js is loaded only on the admin dashboard. Data is injected by Flask
 * as JSON inside <script id="adminChartData">, so no API round-trip is needed.
 */
(function () {
  "use strict";

  var dataNode = document.getElementById("adminChartData");
  if (!dataNode || !window.Chart) return;

  var data;
  try {
    data = JSON.parse(dataNode.textContent || "{}");
  } catch (error) {
    return;
  }

  var RED = "#c8102e";
  var RED_DARK = "#9d0b23";
  var RED_SOFT = "#f3c6ce";
  var INK = "#1b2430";
  var MUTED = "#7a8797";
  var LINE = "#e8ebef";
  var FONT = "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif";

  var palette = [
    "#c8102e",
    "#e04a5f",
    "#f08a97",
    "#9d0b23",
    "#ffb3bd",
    "#6b7280",
    "#b9c0c9",
    "#2f3a47",
  ];

  var statusColours = {
    Pending: "#e0a800",
    Accepted: "#2f80ed",
    Rejected: "#c8102e",
    Completed: "#1e9e6a",
    Cancelled: "#7a8797",
    Expired: "#2f3a47",
  };

  window.Chart.defaults.font.family = FONT;
  window.Chart.defaults.color = MUTED;
  window.Chart.defaults.borderColor = LINE;

  function makeGradient(context) {
    var gradient = context.createLinearGradient(0, 0, 0, 260);
    gradient.addColorStop(0, "rgba(200, 16, 46, 0.22)");
    gradient.addColorStop(1, "rgba(200, 16, 46, 0.01)");
    return gradient;
  }

  function baseScales(showY) {
    return {
      x: {
        grid: { display: false },
        border: { display: false },
        ticks: { font: { size: 11 } },
      },
      y: {
        beginAtZero: true,
        display: showY !== false,
        ticks: { precision: 0, font: { size: 11 } },
        grid: { color: LINE, drawTicks: false },
        border: { display: false },
      },
    };
  }

  /* ------------------------------------------------------------------
   * Account growth — line
   * ------------------------------------------------------------------ */
  var growthCanvas = document.getElementById("growthChart");
  if (growthCanvas && data.monthly) {
    new window.Chart(growthCanvas, {
      type: "line",
      data: {
        labels: data.monthly.labels || [],
        datasets: [
          {
            label: "New accounts",
            data: data.monthly.values || [],
            borderColor: RED,
            backgroundColor: function (context) {
              var chart = context.chart;
              var area = chart.chartArea;
              if (!area) return "rgba(200, 16, 46, 0.08)";
              return makeGradient(chart.ctx);
            },
            borderWidth: 2.5,
            pointBackgroundColor: "#ffffff",
            pointBorderColor: RED,
            pointBorderWidth: 2,
            pointRadius: 4,
            pointHoverRadius: 6,
            tension: 0.35,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: INK,
            padding: 12,
            cornerRadius: 10,
            displayColors: false,
            callbacks: {
              label: function (item) {
                return item.parsed.y + " new account" + (item.parsed.y === 1 ? "" : "s");
              },
            },
          },
        },
        scales: baseScales(true),
      },
    });
  }

  /* ------------------------------------------------------------------
   * Donors by blood group — doughnut
   * ------------------------------------------------------------------ */
  var groupCanvas = document.getElementById("groupChart");
  if (groupCanvas && data.bloodGroups) {
    new window.Chart(groupCanvas, {
      type: "doughnut",
      data: {
        labels: data.bloodGroups.labels || [],
        datasets: [
          {
            data: data.bloodGroups.values || [],
            backgroundColor: palette,
            borderColor: "#ffffff",
            borderWidth: 3,
            hoverOffset: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "66%",
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              boxWidth: 10,
              boxHeight: 10,
              usePointStyle: true,
              pointStyle: "circle",
              padding: 14,
              font: { size: 11 },
            },
          },
          tooltip: {
            backgroundColor: INK,
            padding: 12,
            cornerRadius: 10,
            callbacks: {
              label: function (item) {
                var value = item.parsed;
                return " " + item.label + ": " + value + " donor" + (value === 1 ? "" : "s");
              },
            },
          },
        },
      },
    });
  }

  /* ------------------------------------------------------------------
   * Request pipeline — bar
   * ------------------------------------------------------------------ */
  var statusCanvas = document.getElementById("statusChart");
  if (statusCanvas && data.statuses) {
    var labels = data.statuses.labels || [];
    var values = data.statuses.values || [];
    new window.Chart(statusCanvas, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Requests",
            data: values,
            backgroundColor: labels.map(function (label) {
              return statusColours[label] || RED_SOFT;
            }),
            hoverBackgroundColor: labels.map(function (label) {
              return statusColours[label] || RED_DARK;
            }),
            borderRadius: 6,
            borderSkipped: false,
            maxBarThickness: 46,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: INK,
            padding: 12,
            cornerRadius: 10,
            displayColors: false,
            callbacks: {
              label: function (item) {
                return item.parsed.y + " request" + (item.parsed.y === 1 ? "" : "s");
              },
            },
          },
        },
        scales: baseScales(true),
      },
    });
  }
})();
