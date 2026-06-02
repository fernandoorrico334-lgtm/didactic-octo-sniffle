const scanButton = document.querySelector("#scanButton");
const signalsTable = document.querySelector("#signalsTable");
const warnings = document.querySelector("#warnings");
const categoryTabs = document.querySelector("#categoryTabs");
const minEdgeFilter = document.querySelector("#minEdgeFilter");
const minLiquidityFilter = document.querySelector("#minLiquidityFilter");
const feeBadge = document.querySelector("#feeBadge");
const stakeMemory = new Map();
const signalsById = new Map();
let activeCategory = "all";
let latestSignalsPayload = { signals: [] };
let latestDataMode = "";

const CATEGORY_TABS = [
  { key: "all", label: "TODOS", icon: "sliders" },
  { key: "politica", label: "POLÍTICA", icon: "bank" },
  { key: "economia", label: "ECONOMIA", icon: "chart" },
  { key: "esportes", label: "ESPORTES", icon: "globe" },
  { key: "cripto", label: "CRIPTO", icon: "btc" },
  { key: "clima", label: "CLIMA", icon: "cloud" },
];

function money(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value || 0);
}

function compactNumber(value) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value || 0);
}

function percent(value) {
  return `${((value || 0) * 100).toFixed(2)}%`;
}

function price(value) {
  return `$${Number(value || 0).toFixed(3)}`;
}

function modeLabel(value) {
  return String(value || "").toUpperCase() || "LIVE";
}

function updatedAtLabel(value) {
  if (!value) {
    return "aguardando scan";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function decimalOdds(value) {
  if (!value || value <= 0) {
    return "-";
  }
  return `${(1 / value).toFixed(2)}x`;
}

function setText(id, value) {
  const element = document.querySelector(id);
  if (element) {
    element.textContent = value;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function sideLabel(side) {
  return side === "yes" ? "SIM" : side === "no" ? "NÃO" : String(side || "").toUpperCase();
}

function venueLabel(venue) {
  return String(venue || "").toUpperCase();
}

function numericFilter(input) {
  return Math.max(0, Number(input?.value || 0) || 0);
}

function renderFeeBadge(fees) {
  if (!feeBadge) {
    return;
  }
  const included = Boolean(fees?.included);
  feeBadge.textContent = included ? "Taxas incluídas" : "Taxas configuráveis";
}

function marketCell(signal) {
  const yesLeg = signal.legs.find((leg) => leg.side === "yes");
  const noLeg = signal.legs.find((leg) => leg.side === "no");
  const yesText = yesLeg ? `${venueLabel(yesLeg.venue)} SIM` : "SIM";
  const noText = noLeg ? `${venueLabel(noLeg.venue)} NÃO` : "NÃO";
  return `<strong class="market-title">${escapeHtml(signal.market_title || signal.pair_id || "Mercado")}</strong><span class="price">${escapeHtml(yesText)} contra ${escapeHtml(noText)}</span>`;
}

function legCell(leg) {
  if (!leg) {
    return `<span class="venue">-</span>`;
  }
  const label = `${escapeHtml(venueLabel(leg.venue))} ${escapeHtml(sideLabel(leg.side))}`;
  const headline = leg.url
    ? `<a class="venue" href="${escapeHtml(leg.url)}" target="_blank" rel="noopener noreferrer">${label}</a>`
    : `<span class="venue">${label}</span>`;
  return `${headline}<span class="price">Preço ${price(leg.price)} | Odd ${decimalOdds(leg.price)}</span><span class="price">Liquidez ${escapeHtml(leg.size)}</span>`;
}

function defaultStake(signal) {
  const maxTotal = Number(signal.max_total_stake || 0);
  if (maxTotal > 0) {
    return Math.max(1, Math.min(100, maxTotal)).toFixed(2);
  }
  return "100.00";
}

function calculatorStateForSignal(signal) {
  const remembered = stakeMemory.get(signal.signal_id);
  if (remembered && typeof remembered === "object") {
    return remembered;
  }
  if (remembered) {
    return { source: "total", value: remembered };
  }
  return { source: "total", value: defaultStake(signal) };
}

function calculateStakeSplit(signal, source, rawValue) {
  const value = Math.max(0, Number(rawValue) || 0);
  const yesAsk = Number(signal.yes_ask || 0);
  const noAsk = Number(signal.no_ask || 0);
  const fees = Number(signal.estimated_fees || 0);
  const costPerContract = Number(signal.cost_per_contract || yesAsk + noAsk + fees);
  if (!value || !costPerContract) {
    return { totalStake: 0, contracts: 0, yesStake: 0, noStake: 0, feeCost: 0, payout: 0, profit: 0, roi: 0 };
  }

  let contracts = value / costPerContract;
  if (source === "yes" && yesAsk > 0) {
    contracts = value / yesAsk;
  }
  if (source === "no" && noAsk > 0) {
    contracts = value / noAsk;
  }

  const yesStake = contracts * yesAsk;
  const noStake = contracts * noAsk;
  const feeCost = contracts * fees;
  const totalStake = contracts * costPerContract;
  const payout = contracts;
  const profit = payout - totalStake;
  const roi = profit / totalStake;
  return { totalStake, contracts, yesStake, noStake, feeCost, payout, profit, roi };
}

function formatInputValue(value) {
  return Number(value || 0).toFixed(2);
}

function inputValueForSource(split, source) {
  if (source === "yes") {
    return split.yesStake;
  }
  if (source === "no") {
    return split.noStake;
  }
  return split.totalStake;
}

function calculatorSummary(signal, split) {
  return `<div class="calc-grid">
    <span>Contratos</span><strong>${compactNumber(split.contracts)}</strong>
    <span>Lucro</span><strong class="${split.profit >= 0 ? "edge" : "warn"}">${money(split.profit)}</strong>
    <span>Porcentagem</span><strong class="${split.roi >= 0 ? "edge" : "warn"}">${percent(split.roi)}</strong>
  </div>`;
}

function calculatorCell(signal) {
  const state = calculatorStateForSignal(signal);
  const split = calculateStakeSplit(signal, state.source, state.value);
  const yesLeg = signal.legs.find((leg) => leg.side === "yes");
  const noLeg = signal.legs.find((leg) => leg.side === "no");
  const yesLabel = yesLeg ? `${venueLabel(yesLeg.venue)} ${sideLabel(yesLeg.side)}` : "SIM";
  const noLabel = noLeg ? `${venueLabel(noLeg.venue)} ${sideLabel(noLeg.side)}` : "NÃO";
  return `<div class="calculator" data-signal-id="${escapeHtml(signal.signal_id)}">
    <div class="calc-inputs">
      <label class="calc-label">
        <span>Stake total</span>
        <input class="stake-input" data-source="total" data-signal-id="${escapeHtml(signal.signal_id)}" type="number" min="0" step="1" value="${formatInputValue(split.totalStake)}" />
      </label>
      <label class="calc-label">
        <span>${escapeHtml(yesLabel)}</span>
        <input class="stake-input" data-source="yes" data-signal-id="${escapeHtml(signal.signal_id)}" type="number" min="0" step="1" value="${formatInputValue(split.yesStake)}" />
      </label>
      <label class="calc-label">
        <span>${escapeHtml(noLabel)}</span>
        <input class="stake-input" data-source="no" data-signal-id="${escapeHtml(signal.signal_id)}" type="number" min="0" step="1" value="${formatInputValue(split.noStake)}" />
      </label>
    </div>
    <div class="calc-output">${calculatorSummary(signal, split)}</div>
  </div>`;
}

function updateCalculatorOutput(calculator, signal, source, value, activeInput) {
  const output = calculator?.querySelector(".calc-output");
  if (!output || !signal) {
    return;
  }
  const split = calculateStakeSplit(signal, source, value);
  calculator.querySelectorAll(".stake-input").forEach((input) => {
    if (input === activeInput) {
      return;
    }
    input.value = formatInputValue(inputValueForSource(split, input.dataset.source));
  });
  output.innerHTML = calculatorSummary(signal, split);
}

function categoryCounts(signals) {
  return signals.reduce(
    (counts, signal) => {
      const category = signal.category || "outros";
      counts.all += 1;
      counts[category] = (counts[category] || 0) + 1;
      return counts;
    },
    { all: 0 }
  );
}

function renderCategoryTabs(signals) {
  if (!categoryTabs) {
    return;
  }
  const counts = categoryCounts(signals);
  categoryTabs.innerHTML = CATEGORY_TABS.map((tab) => {
    const selected = activeCategory === tab.key;
    const count = counts[tab.key] || 0;
    return `<button class="category-tab${selected ? " is-active" : ""}" data-category="${tab.key}" type="button" role="tab" aria-selected="${selected}">
      <span class="category-icon category-icon-${tab.icon}" aria-hidden="true"></span>
      <span class="category-label">${tab.label}</span>
      <strong>${count}</strong>
    </button>`;
  }).join("");
}

function filteredSignals(signals) {
  const minEdge = numericFilter(minEdgeFilter) / 100;
  const minLiquidity = numericFilter(minLiquidityFilter);
  return signals.filter((signal) => {
    if (activeCategory !== "all" && signal.category !== activeCategory) {
      return false;
    }
    if (Number(signal.net_edge || 0) < minEdge) {
      return false;
    }
    if (Number(signal.max_total_stake || 0) < minLiquidity) {
      return false;
    }
    return true;
  });
}

function renderSignals(payload, dataMode = "") {
  const signals = payload.signals || [];
  latestSignalsPayload = payload;
  latestDataMode = dataMode;
  signalsById.clear();
  setText("#updatedAt", updatedAtLabel(payload.updated_at));
  setText("#signalCount", signals.length);
  renderCategoryTabs(signals);

  if (!signals.length) {
    const emptyText = dataMode === "live"
      ? "Nenhuma arbitragem válida nos mercados reais escaneados agora."
      : "Nenhum sinal acima da porcentagem mínima.";
    signalsTable.innerHTML = `<tr><td colspan="8" class="empty">${payload.error || emptyText}</td></tr>`;
    if (warnings) {
      warnings.innerHTML = `<li>Revise as regras de resolução antes de qualquer trade real.</li><li>Taxas reais, slippage e tipo de ordem precisam ser configurados antes de operar.</li><li>Os sinais usam modo dry-run; execução de ordens não está ativada.</li>`;
    }
    return;
  }

  const visibleSignals = filteredSignals(signals);

  if (!visibleSignals.length) {
    signalsTable.innerHTML = `<tr><td colspan="8" class="empty">Nenhum sinal passa pelos filtros atuais.</td></tr>`;
    return;
  }

  signalsTable.innerHTML = visibleSignals
    .map((signal) => {
      signalsById.set(signal.signal_id, signal);
      const yesLeg = signal.legs.find((leg) => leg.side === "yes");
      const noLeg = signal.legs.find((leg) => leg.side === "no");
      return `<tr>
        <td>${marketCell(signal)}</td>
        <td>${legCell(yesLeg)}</td>
        <td>${legCell(noLeg)}</td>
        <td><span class="edge">${percent(signal.net_edge)}</span><span class="price">bruto ${percent(signal.gross_edge)}</span></td>
        <td><strong>${compactNumber(signal.max_size)}</strong><span class="price">${money(signal.max_total_stake)} max</span></td>
        <td>${money(signal.estimated_profit)}</td>
        <td class="${signal.confidence < 0.85 ? "warn" : ""}">${percent(signal.confidence)}</td>
        <td>${calculatorCell(signal)}</td>
      </tr>`;
    })
    .join("");

  const allWarnings = [
    "Taxas reais, slippage e tipo de ordem precisam ser configurados antes de operar.",
    ...signals.flatMap((signal) => signal.warnings || []),
  ];
  if (warnings) {
    warnings.innerHTML = (allWarnings.length ? [...new Set(allWarnings)] : ["Sem avisos adicionais nos sinais atuais."])
      .map((item) => `<li>${escapeHtml(item)}</li>`)
      .join("");
  }
}

async function refresh() {
  const [healthResponse, signalsResponse] = await Promise.all([
    fetch("/api/health"),
    fetch("/api/signals"),
  ]);
  const health = await healthResponse.json();
  const signals = await signalsResponse.json();
  setText("#mode", modeLabel(health.data_mode));
  setText("#sourceState", modeLabel(health.data_mode));
  renderFeeBadge(health.fees);
  setText("#polyCount", health.counts.polymarket);
  setText("#kalshiCount", health.counts.kalshi);
  setText("#pairCount", health.counts.pairs);
  renderSignals(signals, health.data_mode);
}

async function scanNow() {
  scanButton.disabled = true;
  scanButton.textContent = "Escaneando";
  try {
    const response = await fetch("/api/scan", { method: "POST" });
    const snapshot = await response.json();
    setText("#polyCount", snapshot.polymarket_count);
    setText("#kalshiCount", snapshot.kalshi_count);
    setText("#pairCount", snapshot.pair_count);
    renderSignals({
      updated_at: snapshot.updated_at,
      status: snapshot.status,
      error: snapshot.error,
      signals: snapshot.signals,
    }, document.querySelector("#sourceState")?.textContent.toLowerCase() || "");
  } finally {
    scanButton.disabled = false;
    scanButton.textContent = "Escanear agora";
  }
}

signalsTable.addEventListener("input", (event) => {
  const input = event.target;
  if (!input.classList || !input.classList.contains("stake-input")) {
    return;
  }
  const signalId = input.dataset.signalId;
  const source = input.dataset.source || "total";
  stakeMemory.set(signalId, { source, value: input.value });
  updateCalculatorOutput(input.closest(".calculator"), signalsById.get(signalId), source, input.value, input);
});

categoryTabs.addEventListener("click", (event) => {
  const button = event.target.closest(".category-tab");
  if (!button) {
    return;
  }
  activeCategory = button.dataset.category || "all";
  renderSignals(latestSignalsPayload, latestDataMode);
});

minEdgeFilter.addEventListener("input", () => renderSignals(latestSignalsPayload, latestDataMode));
minLiquidityFilter.addEventListener("input", () => renderSignals(latestSignalsPayload, latestDataMode));
scanButton.addEventListener("click", scanNow);

refresh();
setInterval(refresh, 15000);
