let comparisonChart;

const numberFormatter = new Intl.NumberFormat("en-US");
const compactNumberFormatter = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("refreshButton").addEventListener("click", runRefresh);
  document.getElementById("refreshNewsButton").addEventListener("click", runNewsRefresh);
  await loadDashboard();
});

async function loadDashboard() {
  const [summary, history, leaders, correlation, status, benchmarks, news] = await Promise.all([
    fetchJson("/api/summary"),
    fetchJson("/api/history"),
    fetchJson("/api/leaders"),
    fetchJson("/api/correlation"),
    fetchJson("/api/pipeline/status"),
    fetchJson("/api/benchmarks"),
    fetchJson("/api/news?limit=10"),
  ]);

  renderMetricCards(summary.cards || []);
  renderComparisonChart(history.series || [], benchmarks.series || []);
  renderBenchmarks(benchmarks.benchmarks || []);
  renderNews(news.items || []);
  renderAssetTable(summary.assets || []);
  renderLeaders(leaders);
  renderCorrelation(correlation);
  renderStatus(summary, status, benchmarks, news);
}

async function runRefresh() {
  const button = document.getElementById("refreshButton");
  button.disabled = true;
  button.textContent = "Refreshing...";
  try {
    const result = await fetchJson("/api/pipeline/run", { method: "POST" });
    await loadDashboard();
    button.textContent = result.status === "success" ? "Refresh Complete" : "Refresh Market Data";
  } catch (error) {
    button.textContent = "Refresh Failed";
    console.error(error);
  } finally {
    window.setTimeout(() => {
      button.disabled = false;
      button.textContent = "Refresh Market Data";
    }, 1600);
  }
}

async function runNewsRefresh() {
  const button = document.getElementById("refreshNewsButton");
  button.disabled = true;
  button.textContent = "Refreshing...";
  try {
    const news = await fetchJson("/api/news?limit=10");
    renderNews(news.items || []);
    renderNewsSource(news);
    button.textContent = news.warning
      ? news.is_live === false
        ? "Using Cached News"
        : "Used Backup Feed"
      : "Refresh Complete";
  } catch (error) {
    button.textContent = "Refresh Failed";
    console.error(error);
  } finally {
    window.setTimeout(() => {
      button.disabled = false;
      button.textContent = "Refresh News";
    }, 1400);
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
          <p>${escapeHtml(card.label)}</p>
          <div class="metric-value">${formatValue(card.value, card.format)}</div>
          <div class="metric-delta ${deltaClass}">
            ${formatSignedPercent(card.delta)} ${escapeHtml(card.delta_label || "")}
          </div>
        </article>
      `;
    })
    .join("");
}

function renderComparisonChart(cryptoSeries, benchmarkSeries) {
  const ctx = document.getElementById("comparisonChart");
  const allSeries = [
    ...cryptoSeries.map((series) => ({ ...series, kind: "crypto" })),
    ...benchmarkSeries.map((series) => ({ ...series, kind: "benchmark" })),
  ];
  const labels = [...new Set(allSeries.flatMap((series) => series.points.map((point) => point.date)))].sort();
  const palette = ["#0f766e", "#d97706", "#1d4ed8", "#be123c", "#6d28d9", "#5b5bd6", "#8b5e34"];

  if (comparisonChart) {
    comparisonChart.destroy();
  }

  comparisonChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: allSeries.map((series, index) => {
        const normalizedMap = buildNormalizedPointMap(series.points);
        return {
          label: series.symbol,
          data: labels.map((date) => normalizedMap.get(date) ?? null),
          borderColor: palette[index % palette.length],
          backgroundColor: palette[index % palette.length],
          borderWidth: series.kind === "benchmark" ? 2.8 : 2.4,
          borderDash: series.kind === "benchmark" ? [8, 6] : undefined,
          pointRadius: 0,
          pointHoverRadius: 4,
          spanGaps: true,
          tension: 0.28,
        };
      }),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          labels: {
            color: "#6e655c",
          },
        },
        tooltip: {
          backgroundColor: "#1f1a16",
          titleColor: "#fffdf9",
          bodyColor: "#f3ece2",
          callbacks: {
            label(context) {
              return `${context.dataset.label}: ${Number(context.raw).toFixed(2)}`;
            },
          },
        },
      },
      scales: {
        x: axisOptions((value) => labels[value]),
        y: axisOptions((value) => Number(value).toFixed(0)),
      },
    },
  });
}

function renderBenchmarks(benchmarks) {
  const container = document.getElementById("benchmarkCards");
  if (!benchmarks.length) {
    container.innerHTML = `<div class="empty-state">Benchmark data is currently unavailable.</div>`;
    return;
  }

  container.innerHTML = benchmarks
    .map((benchmark) => {
      const dailyClass = Number(benchmark.change_1d) >= 0 ? "positive" : "negative";
      const monthlyClass = Number(benchmark.change_30d) >= 0 ? "positive" : "negative";
      return `
        <article class="benchmark-card">
          <div class="benchmark-head">
            <div>
              <div class="leader-label">${escapeHtml(benchmark.name)}</div>
              <div class="benchmark-symbol">${escapeHtml(benchmark.symbol)}</div>
            </div>
            <div class="${dailyClass}">${formatSignedPercent(benchmark.change_1d)}</div>
          </div>
          <div class="benchmark-price">${formatIndexValue(benchmark.price)}</div>
          <div class="benchmark-stats">
            <span>30d <strong class="${monthlyClass}">${formatSignedPercent(benchmark.change_30d)}</strong></span>
            <span>Range ${formatIndexValue(benchmark.range_30d_low)} - ${formatIndexValue(benchmark.range_30d_high)}</span>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderNews(items) {
  const container = document.getElementById("newsFeed");
  if (!items.length) {
    container.innerHTML = `<div class="empty-state">No crypto headlines are available right now.</div>`;
    return;
  }

  container.innerHTML = items
    .slice(0, 10)
    .map((item) => {
      return `
        <a class="news-item" href="${escapeAttribute(item.link || "#")}" target="_blank" rel="noreferrer">
          <div class="news-meta">
            <span>${escapeHtml(item.source || "CoinDesk")}</span>
            <span>${formatDateTime(item.published_at)}</span>
          </div>
          <div class="news-title">${escapeHtml(item.title || "Untitled story")}</div>
          <div class="news-summary">${escapeHtml(truncate(item.summary || "", 150))}</div>
        </a>
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
              <span>${escapeHtml(asset.name)}</span>
              <span class="asset-symbol">${escapeHtml(asset.symbol)}</span>
            </div>
          </td>
          <td>${formatCurrency(asset.price)}</td>
          <td class="${change24Class}">${formatPercent(asset.change_24h)}</td>
          <td class="${change7Class}">${formatPercent(asset.change_7d)}</td>
          <td class="${change30Class}">${formatPercent(asset.return_30d)}</td>
          <td>${formatCompactCurrency(asset.market_cap)}</td>
        </tr>
      `;
    })
    .join("");
}

function renderLeaders(leaders) {
  const gainers = document.getElementById("gainersList");
  const laggards = document.getElementById("laggardsList");
  gainers.innerHTML = (leaders.gainers || []).length
    ? (leaders.gainers || []).map(renderLeaderRow).join("")
    : `<div class="empty-state">No gainers available.</div>`;
  laggards.innerHTML = (leaders.laggards || []).length
    ? (leaders.laggards || []).map(renderLeaderRow).join("")
    : `<div class="empty-state">No laggards available.</div>`;
}

function renderLeaderRow(asset) {
  const deltaClass = Number(asset.change_24h) >= 0 ? "positive" : "negative";
  return `
    <div class="leader-row">
      <div>
        <div class="leader-label">${escapeHtml(asset.name)} (${escapeHtml(asset.symbol)})</div>
        <div class="leader-meta">${formatCompactCurrency(asset.market_cap)} market cap</div>
      </div>
      <div class="${deltaClass}">${formatPercent(asset.change_24h)}</div>
    </div>
  `;
}

function renderCorrelation(correlation) {
  const container = document.getElementById("correlationHeatmap");
  const labels = correlation.labels || [];
  if (!labels.length) {
    container.innerHTML = `<div class="empty-state">Correlation data is currently unavailable.</div>`;
    return;
  }
  const columns = `84px repeat(${labels.length}, minmax(0, 1fr))`;
  const rows = [];

  rows.push(`
    <div class="heatmap-row" style="grid-template-columns:${columns}">
      <div class="heatmap-label">Pair</div>
      ${labels.map((label) => `<div class="heatmap-label">${escapeHtml(label)}</div>`).join("")}
    </div>
  `);

  labels.forEach((rowLabel, rowIndex) => {
    rows.push(`
      <div class="heatmap-row" style="grid-template-columns:${columns}">
        <div class="heatmap-label">${escapeHtml(rowLabel)}</div>
        ${labels
          .map((_, colIndex) => {
            const value = correlation.matrix[rowIndex]?.[colIndex] ?? 0;
            return `<div class="heatmap-cell" style="background:${correlationColor(value)}">${Number(value).toFixed(2)}</div>`;
          })
          .join("")}
      </div>
    `);
  });

  container.innerHTML = rows.join("");
}

function renderStatus(summary, status, benchmarks, news) {
  const summaryTime = summary.last_updated || status.last_finished_at;
  document.getElementById("lastUpdated").textContent = summaryTime
    ? `Market data updated ${formatDateTime(summaryTime)}`
    : "No pipeline run recorded yet.";

  document.getElementById("pipelineSource").textContent = buildSourceLabel("Crypto", status.source, null);
  document.getElementById("benchmarkSource").textContent = buildSourceLabel("Benchmarks", benchmarks.source, benchmarks.warning);
  renderNewsSource(news);
}

function renderNewsSource(news) {
  document.getElementById("newsSource").textContent = buildSourceLabel("News", news.source, news.warning);
}

function buildNormalizedPointMap(points) {
  const sortedPoints = [...points].sort((left, right) => left.date.localeCompare(right.date));
  const firstPoint = sortedPoints.find((point) => Number.isFinite(Number(point.price)));
  const base = firstPoint ? Number(firstPoint.price) : null;
  const normalized = new Map();

  if (!base) {
    return normalized;
  }

  sortedPoints.forEach((point) => {
    normalized.set(point.date, (Number(point.price) / base) * 100);
  });
  return normalized;
}

function formatValue(value, format) {
  if (format === "currency_compact") {
    return formatCompactCurrency(value);
  }
  if (format === "percent") {
    return formatPercent(value);
  }
  return escapeHtml(String(value ?? "-"));
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

function formatIndexValue(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return numberFormatter.format(Number(Number(value).toFixed(2)));
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(2)}%`;
}

function formatSignedPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  const prefix = Number(value) >= 0 ? "+" : "";
  return `${prefix}${Number(value).toFixed(2)}%`;
}

function formatDateTime(value) {
  if (!value) {
    return "Unavailable";
  }
  return new Date(value).toLocaleString();
}

function buildSourceLabel(prefix, source, warning) {
  if (!source) {
    return `${prefix}: unavailable`;
  }
  return warning ? `${prefix}: ${source} (degraded)` : `${prefix}: ${source}`;
}

function truncate(value, maxLength) {
  return value.length <= maxLength ? value : `${value.slice(0, maxLength - 3)}...`;
}

function correlationColor(value) {
  const clamped = Math.max(-1, Math.min(1, Number(value)));
  if (clamped >= 0) {
    return `rgba(15, 138, 75, ${0.18 + clamped * 0.5})`;
  }
  return `rgba(193, 73, 61, ${0.18 + Math.abs(clamped) * 0.5})`;
}

function axisOptions(tickFormatter) {
  return {
    ticks: {
      color: "#6e655c",
      callback: tickFormatter,
      maxTicksLimit: 6,
    },
    grid: {
      color: "rgba(217, 201, 177, 0.6)",
    },
  };
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(String(value));
}
