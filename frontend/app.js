const API_BASE = "/api/v1";

let forecastChartInstance = null;
let twinChartInstance = null;

function formatINR(value, decimals = 0) {
  const num = Number(value || 0);
  return (
    "₹" +
    num.toLocaleString("en-IN", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })
  );
}

// Detect embedded shell mode (?embed=true or /shell)
if (new URLSearchParams(window.location.search).get("embed") === "true" || window.location.pathname === "/shell") {
  const header = document.getElementById("main-header");
  if (header) header.classList.add("hidden");
  const studio = document.getElementById("integration-studio");
  if (studio) studio.classList.add("hidden");
}

function showBanner(message, isError = false) {
  const banner = document.getElementById("status-banner");
  banner.textContent = message;
  banner.className = `rounded-xl border px-4 py-3 text-sm ${
    isError
      ? "bg-rose-500/10 border-rose-500/40 text-rose-200"
      : "bg-emerald-500/10 border-emerald-500/40 text-emerald-200"
  }`;
  banner.classList.remove("hidden");
  setTimeout(() => banner.classList.add("hidden"), 6000);
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(errText || `HTTP ${res.status}`);
  }
  return res.json();
}

function populateSkuSelects(inventory) {
  const fSel = document.getElementById("forecast-sku-select");
  const tSel = document.getElementById("twin-sku-select");
  const prevF = fSel.value;
  const prevT = tSel.value;

  const opts = inventory
    .map((i) => `<option value="${i.sku}">${i.name} (${i.days_remaining}d left)</option>`)
    .join("");
  fSel.innerHTML = opts;
  tSel.innerHTML = opts;

  if (prevF) fSel.value = prevF;
  if (prevT) tSel.value = prevT;
}

async function loadDashboardSummary() {
  const data = await fetchJson(`${API_BASE}/dashboard/summary`);

  // External feeds
  const w = data.weather;
  document.getElementById("weather-pill").textContent =
    `${w.location}: ${w.temperature_c}°C · ${w.humidity_pct}% RH (${w.source})`;

  const nextHol = data.upcoming_holidays[0];
  document.getElementById("holiday-pill").textContent = nextHol
    ? `Next Festival/Holiday: ${nextHol.name} (${nextHol.date})`
    : "No upcoming holidays";

  document.getElementById("dataset-pill").textContent =
    `Feed: ${data.data_source_info.transactions_ingested.toLocaleString()} real baskets`;

  // KPIs (INR ₹)
  const k = data.kpis;
  document.getElementById("kpi-risk").textContent = formatINR(k.inventory_value_at_risk_usd);
  document.getElementById("kpi-critical-skus").textContent = `${k.critical_expiry_skus} critical`;
  document.getElementById("kpi-profit").textContent = formatINR(k.projected_7d_profit_usd);
  document.getElementById("kpi-waste").textContent = `${k.projected_waste_kg} kg`;
  document.getElementById("kpi-reduction").textContent = `-${k.waste_reduction_pct}% vs naive`;
  document.getElementById("kpi-records").textContent =
    `Tracked sales observations: ${k.sales_records_count.toLocaleString("en-IN")}`;

  populateSkuSelects(data.inventory);

  // Suppliers
  document.getElementById("suppliers-strip").innerHTML = data.suppliers
    .map(
      (s) => `
      <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
        <div class="flex justify-between items-center">
          <span class="font-semibold text-white">${s.supplier_name}</span>
          <span class="text-emerald-400">${Math.round(s.reliability_score * 100)}%</span>
        </div>
        <p class="text-slate-400 mt-1">${s.category} · Lead ${s.lead_time_days}d</p>
        <p class="text-sky-300 mt-0.5">${s.cold_chain_status}</p>
      </div>`
    )
    .join("");

  // Inventory table
  document.getElementById("inventory-table-body").innerHTML = data.inventory
    .map((item) => {
      const badgeClass =
        item.days_remaining <= 1
          ? "bg-rose-500/15 text-rose-300"
          : item.days_remaining <= 2
          ? "bg-amber-500/15 text-amber-300"
          : "bg-emerald-500/15 text-emerald-300";
      return `
      <tr>
        <td class="py-2 pr-2 font-medium text-white">${item.name}</td>
        <td class="py-2 px-2 text-slate-400">${item.category}</td>
        <td class="py-2 px-2">${item.current_stock_kg} kg</td>
        <td class="py-2 px-2"><span class="rounded-full px-2 py-0.5 ${badgeClass}">${item.days_remaining}d / ${item.shelf_life_days}d</span></td>
        <td class="py-2 px-2 text-slate-400">${item.supplier_name}</td>
        <td class="py-2 px-2 text-sky-300">${item.basket_frequency.toLocaleString()}</td>
        <td class="py-2 pl-2 text-right font-semibold ${item.value_at_risk_usd > 0 ? "text-rose-400" : "text-slate-400"}">${formatINR(item.value_at_risk_usd, 2)}</td>
      </tr>`;
    })
    .join("");
}

async function loadForecast() {
  const sku = document.getElementById("forecast-sku-select").value || "SKU-WHOLE-MILK";
  const data = await fetchJson(`${API_BASE}/forecast?sku=${encodeURIComponent(sku)}&horizon_days=7`);

  const champMetric = data.metrics.find((m) => m.model_name === data.champion_model) || data.metrics[0];
  document.getElementById("kpi-champion").textContent = data.champion_model;
  document.getElementById("kpi-mae").textContent = `MAE ${champMetric.mae}`;

  document.getElementById("model-metrics-strip").innerHTML = data.metrics
    .map(
      (m) => `
      <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-3 flex items-center justify-between">
        <div>
          <p class="font-semibold text-white">${m.model_name} ${m.model_name === data.champion_model ? "★" : ""}</p>
          <p class="text-slate-400">R² = ${m.r2_score}</p>
        </div>
        <div class="text-right">
          <p class="text-sky-300">MAE: ${m.mae}</p>
          <p class="text-slate-400">RMSE: ${m.rmse}</p>
        </div>
      </div>`
    )
    .join("");

  const labels = data.series.map((p) => p.date);
  const actuals = data.series.map((p) => p.actual_demand);
  const xgb = data.series.map((p) => p.xgboost_pred);
  const rf = data.series.map((p) => p.random_forest_pred);

  if (forecastChartInstance) forecastChartInstance.destroy();
  forecastChartInstance = new Chart(document.getElementById("forecastChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Actual Sales", data: actuals, borderColor: "#e2e8f0", borderWidth: 2, tension: 0.25 },
        { label: "XGBoost Forecast", data: xgb, borderColor: "#10b981", borderWidth: 2.5, tension: 0.3 },
        { label: "Random Forest", data: rf, borderColor: "#38bdf8", borderDash: [5, 4], borderWidth: 2, tension: 0.3 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#cbd5e1", boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: "#94a3b8", maxTicksLimit: 8 }, grid: { color: "rgba(51,65,85,0.35)" } },
        y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(51,65,85,0.35)" } },
      },
    },
  });
}

async function loadMLOpsStatus() {
  const data = await fetchJson(`${API_BASE}/mlops/status`);
  document.getElementById("mlops-version").textContent = data.champion_version;
  document.getElementById("mlops-errors").textContent = `${data.champion_mae} / ${data.champion_rmse}`;
  document.getElementById("mlops-psi").textContent = `${data.drift_psi} (thresh ${data.drift_threshold})`;
  document.getElementById("mlops-tol").textContent = `${Math.round((data.auto_rollback_tolerance - 1) * 100)}% MAE gate`;

  const badge = document.getElementById("drift-badge");
  if (data.drift_detected) {
    badge.textContent = "Drift Alert";
    badge.className = "rounded-full px-2.5 py-0.5 text-xs font-medium bg-rose-500/15 text-rose-300";
  } else {
    badge.textContent = "Healthy";
    badge.className = "rounded-full px-2.5 py-0.5 text-xs font-medium bg-emerald-500/15 text-emerald-300";
  }

  document.getElementById("mlops-history").innerHTML = data.history
    .map((h) => {
      const color =
        h.status === "rolled_back"
          ? "text-rose-300"
          : h.is_champion
          ? "text-emerald-300"
          : "text-slate-400";
      return `
      <div class="rounded-lg border border-slate-800 bg-slate-900/50 px-2.5 py-1.5 flex justify-between items-center">
        <span class="font-medium ${color}">${h.version} (${h.status})</span>
        <span class="text-slate-400">MAE ${h.mae}</span>
      </div>`;
    })
    .join("");
}

async function triggerRetrain(simulateNoisyDrift) {
  const res = await fetchJson(`${API_BASE}/mlops/retrain`, {
    method: "POST",
    body: JSON.stringify({ simulate_noisy_drift: simulateNoisyDrift }),
  });
  showBanner(res.message, res.rolled_back);
  await loadMLOpsStatus();
}

async function runDigitalTwin() {
  const sku = document.getElementById("twin-sku-select").value || "SKU-WHOLE-MILK";
  const reorder = Number(document.getElementById("twin-reorder").value);
  const markdown = Number(document.getElementById("twin-markdown").value);

  const data = await fetchJson(`${API_BASE}/digital-twin/simulate`, {
    method: "POST",
    body: JSON.stringify({
      sku,
      horizon_days: 14,
      simulations: 500,
      reorder_qty_kg: reorder,
      markdown_pct: markdown,
    }),
  });

  document.getElementById("twin-kpis").innerHTML = `
    <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-2.5">
      <p class="text-slate-400">Stockout Risk</p>
      <p class="text-base font-bold text-rose-400">${data.stockout_probability_pct}%</p>
    </div>
    <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-2.5">
      <p class="text-slate-400">Spoilage Risk</p>
      <p class="text-base font-bold text-amber-300">${data.spoilage_probability_pct}%</p>
    </div>
    <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-2.5">
      <p class="text-slate-400">Expected Waste</p>
      <p class="text-base font-bold text-violet-300">${data.expected_total_waste_kg} kg (${formatINR(data.expected_waste_cost_usd)})</p>
    </div>`;

  const labels = data.trajectory.map((d) => `Day ${d.day}`);
  if (twinChartInstance) twinChartInstance.destroy();
  twinChartInstance = new Chart(document.getElementById("twinChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "P90 Stock", data: data.trajectory.map((d) => d.p90_stock), borderColor: "#a78bfa", borderDash: [4, 4], borderWidth: 1.5, tension: 0.3 },
        { label: "P50 Median Stock", data: data.trajectory.map((d) => d.p50_stock), borderColor: "#8b5cf6", borderWidth: 2.5, tension: 0.3 },
        { label: "P10 Worst-Case", data: data.trajectory.map((d) => d.p10_stock), borderColor: "#f43f5e", borderWidth: 1.5, tension: 0.3 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#cbd5e1", boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(51,65,85,0.35)" } },
        y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(51,65,85,0.35)" } },
      },
    },
  });
}

async function loadAlerts() {
  const data = await fetchJson(`${API_BASE}/alerts`);
  document.getElementById("alerts-savings").textContent = `Save ${formatINR(data.total_potential_savings_usd)}`;
  document.getElementById("alerts-list").innerHTML = data.alerts
    .map((a) => {
      const badge =
        a.severity === "CRITICAL"
          ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
          : a.severity === "HIGH"
          ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
          : "bg-sky-500/20 text-sky-300 border-sky-500/40";
      return `
      <div class="rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-xs">
        <div class="flex items-center justify-between gap-2">
          <span class="font-semibold text-white">${a.item_name}</span>
          <span class="rounded-full border px-2 py-0.5 text-[10px] font-semibold ${badge}">${a.severity}</span>
        </div>
        <p class="mt-1.5 text-slate-300 leading-relaxed">${a.recommendation}</p>
        <p class="mt-1 text-emerald-400 font-medium">Expected recovery: ${formatINR(a.expected_savings_usd)}</p>
      </div>`;
    })
    .join("");
}

async function runLPOptimization() {
  const maxBudget = Number(document.getElementById("lp-budget").value);
  const maxStorage = Number(document.getElementById("lp-storage").value);
  const data = await fetchJson(`${API_BASE}/optimize/linear-programming`, {
    method: "POST",
    body: JSON.stringify({ max_budget_usd: maxBudget, max_cold_storage_kg: maxStorage }),
  });

  document.getElementById("lp-table-body").innerHTML = data.allocations
    .map(
      (a) => `
      <tr>
        <td class="py-2 pr-2 font-medium text-white">${a.name}</td>
        <td class="py-2 px-2">${a.current_stock_kg} kg</td>
        <td class="py-2 px-2 text-emerald-300 font-semibold">+${a.recommended_order_kg} kg</td>
        <td class="py-2 px-2 text-amber-300">${a.recommended_markdown_pct}%</td>
        <td class="py-2 px-2 text-rose-300">${a.projected_waste_kg} kg</td>
        <td class="py-2 pl-2 text-right font-semibold text-emerald-400">${formatINR(a.projected_profit_usd)}</td>
      </tr>`
    )
    .join("");
}

async function loadAprioriRules() {
  const data = await fetchJson(`${API_BASE}/apriori?top_k=8`);
  document.getElementById("apriori-source").textContent =
    `Analyzed ${data.transactions_analyzed.toLocaleString()} baskets · ${data.dataset_source}`;
  document.getElementById("apriori-table-body").innerHTML = data.rules
    .map(
      (r) => `
      <tr>
        <td class="py-2 pr-2 font-medium text-white">${r.antecedents.join(", ")}</td>
        <td class="py-2 px-2 text-emerald-300">${r.consequents.join(", ")}</td>
        <td class="py-2 px-2">${Math.round(r.confidence * 100)}%</td>
        <td class="py-2 pl-2 text-right font-semibold text-sky-300">${r.lift}x</td>
      </tr>`
    )
    .join("");
}

async function initDashboard() {
  try {
    await loadDashboardSummary();
    await Promise.all([
      loadForecast(),
      loadMLOpsStatus(),
      runDigitalTwin(),
      loadAlerts(),
      runLPOptimization(),
      loadAprioriRules(),
    ]);
  } catch (err) {
    showBanner(`Error loading dashboard: ${err.message}`, true);
  }
}

document.getElementById("forecast-sku-select").addEventListener("change", loadForecast);
document.getElementById("run-twin-btn").addEventListener("click", runDigitalTwin);
document.getElementById("twin-reorder").addEventListener("input", (e) => {
  document.getElementById("twin-reorder-val").textContent = e.target.value;
});
document.getElementById("twin-markdown").addEventListener("input", (e) => {
  document.getElementById("twin-md-val").textContent = e.target.value;
});
document.getElementById("lp-budget").addEventListener("input", (e) => {
  document.getElementById("lp-budget-val").textContent = Number(e.target.value).toLocaleString("en-IN");
});
document.getElementById("lp-storage").addEventListener("input", (e) => {
  document.getElementById("lp-storage-val").textContent = e.target.value;
});
document.getElementById("run-lp-btn").addEventListener("click", runLPOptimization);
document.getElementById("retrain-clean-btn").addEventListener("click", () => triggerRetrain(false));
document.getElementById("retrain-drift-btn").addEventListener("click", () => triggerRetrain(true));
document.getElementById("sync-btn").addEventListener("click", async () => {
  const btn = document.getElementById("sync-btn");
  btn.textContent = "Syncing...";
  try {
    const res = await fetchJson(`${API_BASE}/data/sync`, { method: "POST" });
    showBanner(`Synced ${res.transactions_ingested.toLocaleString("en-IN")} baskets (${res.dataset_source})`);
    await initDashboard();
  } catch (err) {
    showBanner(`Sync failed: ${err.message}`, true);
  } finally {
    btn.textContent = "Sync Real-Time Data";
  }
});

// User Data Import & Site Shell Studio handlers
document.getElementById("load-sample-csv-btn").addEventListener("click", () => {
  document.getElementById("csv-input").value = [
    "sku,name,category,current_stock_kg,unit_cost,selling_price,shelf_life_days,days_remaining,supplier_name",
    "KIRANA-TOMATO,Desi Fresh Tomatoes (kg),Fresh Produce,85,32,58,4,1,Nashik Mandi Hub",
    "KIRANA-DHOKLA,Fresh Khaman Dhokla Batter,Prepared Food,40,95,165,2,1,Local Kitchen Co-op",
    "KIRANA-BANANA,Yelakki Bananas (kg),Seasonal Fruits,70,48,88,5,2,Satara Fruit Farms",
  ].join("\n");
});

document.getElementById("csv-file-input").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    document.getElementById("csv-input").value = ev.target.result;
  };
  reader.readAsText(file);
});

document.getElementById("upload-csv-btn").addEventListener("click", async () => {
  const csvText = document.getElementById("csv-input").value.trim();
  const siteName = document.getElementById("csv-site-name").value.trim() || "My Indian Fresh Mart";
  if (!csvText) {
    showBanner("Please paste CSV data or click 'Load Sample Indian Kirana CSV' first.", true);
    return;
  }
  try {
    const res = await fetchJson(`${API_BASE}/integrate/upload-csv`, {
      method: "POST",
      body: JSON.stringify({ site_name: siteName, csv_text: csvText }),
    });
    showBanner(res.message);
    await initDashboard();
  } catch (err) {
    showBanner(`CSV import failed: ${err.message}`, true);
  }
});

document.getElementById("connect-site-btn").addEventListener("click", async () => {
  const siteName = document.getElementById("connect-site-name").value.trim() || "FreshBazaar India";
  const siteUrl = document.getElementById("connect-site-url").value.trim() || "https://myfreshstore.in";
  const platformType = document.getElementById("connect-platform").value;
  const feedUrl = document.getElementById("connect-feed-url").value.trim();
  try {
    const res = await fetchJson(`${API_BASE}/integrate/connect-site`, {
      method: "POST",
      body: JSON.stringify({
        site_name: siteName,
        site_url: siteUrl,
        platform_type: platformType,
        data_feed_url: feedUrl,
        currency: "INR",
      }),
    });
    document.getElementById("embed-script-code").textContent = res.script_embed_tag;
    document.getElementById("embed-cli-code").textContent = res.shell_cli_command;
    document.getElementById("embed-output").classList.remove("hidden");
    showBanner(`Connected ${res.site_name}! Embed script & CLI shell ready.`);
  } catch (err) {
    showBanner(`Site connection failed: ${err.message}`, true);
  }
});

document.getElementById("preview-shell-btn").addEventListener("click", () => {
  if (window.FreshPulseShell) {
    showBanner("Floating FreshPulse AI Shell widget is already active at the bottom-right!");
    return;
  }
  const s = document.createElement("script");
  s.src = "/embed.js";
  s.dataset.site = document.getElementById("connect-site-name").value || "Partner Store";
  s.dataset.currency = "INR";
  document.body.appendChild(s);
  showBanner("Loaded /embed.js! Click the green 'FreshPulse AI Shell (₹)' button at the bottom-right.");
});

initDashboard();
