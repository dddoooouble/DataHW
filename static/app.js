let historyChart;
let scatterChart;

const formatter = new Intl.NumberFormat("en-US");
const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("refreshButton").addEventListener("click", runRefresh);
  await loadDashboard();
});

async function loadDashboard() {
  const [summary, history, leaders, correlation, status] = await Promise.all([
    fetchJson("/api/summary"),
    fetchJson("/api/history"),
    fetchJson("/api/leaders"),
    fetchJson("/api/correlation"),
    fetchJson("/api/pipeline/status"),
  ]);

  renderMetricCards(summary.cards || []);
  renderAssetTable(summary.assets || []);
  renderHistoryChart(history.series || []);
  renderScatterChart(summary.assets || []);
  renderLeaders(leaders);
  renderCorrelation(correlation);
  renderStatus(summary, status);
}

async function runRefresh() {
  const button = document.getElementById("refreshButton");
  button.disabled = true;
  button.textContent = "Refreshing...";
  try {
    const result = await fetchJson("/api/pipeline/run", { method: "POST" });
    await loadDashboard();
    button.textContent = result.status === "success" ? "Refresh Complete" : "Run Refresh";
  } catch (error) {
    button.textContent = "Refresh Failed";
    console.error(error);
  } finally {
    window.setTimeout(() => {
      button.disabled = false;
      button.textContent = "Run Refresh";
    }, 1600);
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  return response.json();
}

function renderMetricCards(cards) {
  const container = document.getElementById("metricCards");
  container.innerHTML = cards
    .map((card) => {
      const deltaClass = Number(card.delta) >= 0 ? "positive" : "negative";
      return `
        <article class="panel metric-card">
          <p>${card.label}</p>
          <div class="metric-value">${formatValue(card.value, card.format)}</div>
          <div class="metric-delta ${deltaClass}">
            ${formatDelta(card.delta)} ${card.delta_label}
          </div>
        </article>
      `;
    })
    .join("");
}

function renderAssetTable(assets) {
  const body = document.getElementById("assetTableBody");
  body.innerHTML = assets
    .map((asset) => {
      const change24Class = Number(asset.change_24h) >= 0 ? "positive" : "negative";
      const change7Class = Number(asset.change_7d) >= 0 ? "positive" : "negative";
      const change30Class = Number(asset.return_30d) >= 0 ? "positive" : "negative";
      return `
        <tr>
          <td>${asset.market_cap_rank ?? "-"}</td>
          <td>
            <div class="asset-name">
              <span>${asset.name}</span>
              <span class="asset-symbol">${asset.symbol}</span>
            </div>
          </td>
          <td>${formatCurrency(asset.price)}</td>
          <td class="${change24Class}">${formatPercent(asset.change_24h)}</td>
          <td class="${change7Class}">${formatPercent(asset.change_7d)}</td>
          <td class="${change30Class}">${formatPercent(asset.return_30d)}</td>
          <td>${formatPercent(asset.volatility_30d)}</td>
          <td>${formatCompactCurrency(asset.market_cap)}</td>
        </tr>
      `;
    })
    .join("");
}

function renderHistoryChart(series) {
  const ctx = document.getElementById("historyChart");
  const palette = ["#52b4ff", "#ffd36e", "#3fe1a7", "#ff6a78", "#b88cff"];
  if (historyChart) {
    historyChart.destroy();
  }
  historyChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: series[0]?.points.map((point) => point.date) || [],
      datasets: series.map((assetSeries, index) => ({
        label: assetSeries.symbol,
        data: assetSeries.points.map((point) => point.price),
        borderColor: palette[index % palette.length],
        backgroundColor: palette[index % palette.length],
        tension: 0.3,
        pointRadius: 0,
        borderWidth: 2.4,
      })),
    },
    options: chartOptions({
      plugins: {
        legend: {
          labels: {
            color: "#edf4ff",
          },
        },
      },
      scales: {
        x: axisOptions(),
        y: axisOptions((value) => formatCurrency(value)),
      },
    }),
  });
}

function renderScatterChart(assets) {
  const ctx = document.getElementById("scatterChart");
  if (scatterChart) {
    scatterChart.destroy();
  }
  scatterChart = new Chart(ctx, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Assets",
          data: assets.map((asset) => ({
            x: asset.market_cap,
            y: asset.change_24h,
            label: asset.symbol,
          })),
          pointRadius: 8,
          pointHoverRadius: 10,
          pointBackgroundColor: "#52b4ff",
          pointBorderColor: "#ffd36e",
          pointBorderWidth: 1.5,
        },
      ],
    },
    options: chartOptions({
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(context) {
              return `${context.raw.label}: ${formatCompactCurrency(context.raw.x)} market cap, ${formatPercent(context.raw.y)} 24h`;
            },
          },
        },
      },
      scales: {
        x: axisOptions((value) => formatCompactCurrency(value)),
        y: axisOptions((value) => formatPercent(value)),
      },
    }),
  });
}

function renderLeaders(leaders) {
  const gainers = document.getElementById("gainersList");
  const laggards = document.getElementById("laggardsList");
  gainers.innerHTML = (leaders.gainers || []).map(renderLeaderRow).join("");
  laggards.innerHTML = (leaders.laggards || []).map(renderLeaderRow).join("");
}

function renderLeaderRow(asset) {
  const deltaClass = Number(asset.change_24h) >= 0 ? "positive" : "negative";
  return `
    <div class="leader-row">
      <div>
        <div class="leader-label">${asset.name} (${asset.symbol})</div>
        <div class="leader-meta">${formatCompactCurrency(asset.market_cap)} cap</div>
      </div>
      <div class="${deltaClass}">${formatPercent(asset.change_24h)}</div>
    </div>
  `;
}

function renderCorrelation(correlation) {
  const container = document.getElementById("correlationHeatmap");
  const labels = correlation.labels || [];
  const rows = [];
  rows.push(`
    <div class="heatmap-row">
      <div class="heatmap-label">Pair</div>
      ${labels.map((label) => `<div class="heatmap-label">${label}</div>`).join("")}
    </div>
  `);
  labels.forEach((rowLabel, rowIndex) => {
    rows.push(`
      <div class="heatmap-row">
        <div class="heatmap-label">${rowLabel}</div>
        ${labels
          .map((_, colIndex) => {
            const value = correlation.matrix[rowIndex]?.[colIndex] ?? 0;
            return `<div class="heatmap-cell" style="background:${correlationColor(value)}">${value.toFixed(2)}</div>`;
          })
          .join("")}
      </div>
    `);
  });
  container.innerHTML = rows.join("");
}

function renderStatus(summary, status) {
  const summaryTime = summary.last_updated || status.last_finished_at;
  document.getElementById("lastUpdated").textContent = summaryTime
    ? `Last refreshed: ${new Date(summaryTime).toLocaleString()}`
    : "No pipeline run recorded yet.";
  document.getElementById("pipelineSource").textContent = status.source
    ? `Source: ${status.source}`
    : "Source unavailable";
}

function formatValue(value, format) {
  if (format === "currency_compact") {
    return formatCompactCurrency(value);
  }
  if (format === "percent") {
    return formatPercent(value);
  }
  return value;
}

function formatCurrency(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  if (Number(value) >= 1000) {
    return currencyFormatter.format(Number(value));
  }
  return `$${Number(value).toFixed(Number(value) < 10 ? 3 : 2)}`;
}

function formatCompactCurrency(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  const absolute = Math.abs(Number(value));
  if (absolute >= 1_000_000_000_000) {
    return `$${(value / 1_000_000_000_000).toFixed(2)}T`;
  }
  if (absolute >= 1_000_000_000) {
    return `$${(value / 1_000_000_000).toFixed(2)}B`;
  }
  if (absolute >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(2)}M`;
  }
  return currencyFormatter.format(Number(value));
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(2)}%`;
}

function formatDelta(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  const prefix = Number(value) >= 0 ? "+" : "";
  return `${prefix}${Number(value).toFixed(2)}%`;
}

function correlationColor(value) {
  const clamped = Math.max(-1, Math.min(1, value));
  if (clamped >= 0) {
    const intensity = Math.floor(110 + clamped * 100);
    return `rgba(63, 225, 167, ${0.16 + clamped * 0.54})`;
  }
  return `rgba(255, 106, 120, ${0.18 + Math.abs(clamped) * 0.5})`;
}

function chartOptions(overrides) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      tooltip: {
        backgroundColor: "#09182d",
        titleColor: "#edf4ff",
        bodyColor: "#c7d9f4",
      },
    },
    scales: {},
    ...overrides,
  };
}

function axisOptions(tickFormatter) {
  return {
    ticks: {
      color: "#8fa8c9",
      callback: tickFormatter,
      maxTicksLimit: 6,
    },
    grid: {
      color: "rgba(143, 168, 201, 0.12)",
    },
  };
}
