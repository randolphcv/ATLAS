const state = {
  health: null,
  summary: null,
  assets: [],
  events: [],
  backups: [],
  activeSection: "overview",
  selectedAssetId: null,
};

const byId = (id) => document.getElementById(id);

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  const number = value / Math.pow(1024, index);
  return `${number >= 10 || index === 0 ? number.toFixed(0) : number.toFixed(1)} ${units[index]}`;
}

function formatDate(value, includeTime = true) {
  if (!value) return "No observations yet";
  const date = new Date(value);
  const options = includeTime
    ? { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }
    : { year: "numeric", month: "short", day: "numeric" };
  return new Intl.DateTimeFormat(undefined, options).format(date);
}

function timeAgo(value) {
  if (!value) return "—";
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const ranges = [
    ["year", 31536000],
    ["month", 2592000],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, divisor] of ranges) {
    if (Math.abs(seconds) >= divisor) return formatter.format(Math.round(seconds / divisor), unit);
  }
  return "just now";
}

function signalLabel(asset) {
  if (asset.probe_error) return "Probe attention";
  if (asset.kind === "video") return asset.codec ? `Video · ${asset.codec}` : "Video";
  if (asset.kind === "audio") return asset.codec ? `Audio · ${asset.codec}` : "Audio";
  return "File";
}

function glyphLabel(asset) {
  if (asset.kind === "video") return "VID";
  if (asset.kind === "audio") return "AUD";
  if (asset.probe_error) return "ERR";
  return "OBJ";
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Accept": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Preserve the status-based message.
    }
    throw new Error(message);
  }
  return response.json();
}

function showError(error) {
  const banner = byId("error-banner");
  banner.textContent = `Beacon could not complete that check: ${error.message}`;
  banner.hidden = false;
}

function clearError() {
  byId("error-banner").hidden = true;
}

function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 5000);
}

function setSection(name) {
  state.activeSection = name;
  document.querySelectorAll("[data-section]").forEach((section) => {
    const active = section.dataset.section === name;
    section.hidden = !active;
    section.classList.toggle("is-active", active);
  });
  document.querySelectorAll("[data-section-target]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.sectionTarget === name);
  });
  if (window.location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
}

function renderSummary() {
  const summary = state.summary;
  const health = state.health;
  byId("metric-assets").textContent = summary.assets.toLocaleString();
  byId("metric-locations").textContent = summary.locations.toLocaleString();
  byId("metric-duplicates").textContent = summary.duplicate_groups.toLocaleString();
  byId("metric-size").textContent = formatBytes(summary.total_bytes);
  byId("hero-last-seen").textContent = timeAgo(summary.last_activity_at);
  byId("app-version").textContent = health.version;

  const healthy = health.database.state === "healthy";
  byId("hero-integrity").textContent = healthy ? "Verified healthy" : "Needs attention";
  byId("hero-integrity").style.color = healthy ? "var(--jade)" : "var(--ember)";
  byId("hero-state-label").textContent = healthy ? "All signals nominal" : "Attention requested";
  const score = healthy ? (state.backups.length ? "100%" : "75%") : "50%";
  byId("readiness-score").textContent = score;
  const pill = byId("readiness-pill");
  pill.textContent = healthy ? "Healthy" : "Attention";
  pill.className = `status-pill ${healthy ? "status-pill--jade" : "status-pill--ember"}`;
  const backupLine = byId("backup-readiness");
  backupLine.innerHTML = state.backups.length
    ? '<span class="checkmark">✓</span> Verified backup available'
    : '<span class="pending-mark">·</span> Backup not yet observed';
}

function compactAssetElement(asset) {
  const row = document.createElement("div");
  row.className = "compact-asset";

  const glyph = document.createElement("span");
  glyph.className = "asset-glyph";
  glyph.textContent = glyphLabel(asset);

  const name = document.createElement("div");
  name.className = "compact-name";
  const strong = document.createElement("strong");
  strong.textContent = asset.filename;
  const small = document.createElement("small");
  small.textContent = asset.atlas_uri;
  name.append(strong, small);

  const meta = document.createElement("span");
  meta.className = "compact-meta";
  meta.textContent = `${signalLabel(asset)} · ${formatBytes(asset.size_bytes)}`;

  const time = document.createElement("time");
  time.className = "compact-time";
  time.dateTime = asset.last_seen_at;
  time.textContent = timeAgo(asset.last_seen_at);
  row.append(glyph, name, meta, time);
  return row;
}

function renderRecentAssets() {
  const container = byId("recent-assets");
  container.replaceChildren();
  const items = state.assets.slice(0, 4);
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "The catalog is quiet. Synthetic assets will appear here.";
    container.append(empty);
    return;
  }
  items.forEach((asset) => container.append(compactAssetElement(asset)));
}

function eventElement(event, compact = true) {
  if (compact) {
    const row = document.createElement("div");
    row.className = "activity-item";
    const dot = document.createElement("span");
    dot.className = `status-dot ${event.state === "failed" ? "" : "status-dot--jade"}`;
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = event.message;
    const detail = document.createElement("small");
    detail.textContent = event.location_path || event.asset_id || "System event";
    copy.append(title, detail);
    const time = document.createElement("time");
    time.dateTime = event.created_at;
    time.textContent = timeAgo(event.created_at);
    row.append(dot, copy, time);
    return row;
  }

  const row = document.createElement("div");
  row.className = "ledger-row";
  const statePill = document.createElement("span");
  statePill.className = `status-pill ${event.state === "failed" ? "status-pill--ember" : "status-pill--jade"}`;
  statePill.textContent = event.state;
  const operation = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = event.message;
  const kind = document.createElement("small");
  kind.textContent = event.kind;
  operation.append(title, kind);
  const object = document.createElement("span");
  object.className = "ledger-object";
  object.textContent = event.location_path || event.asset_id || "Beacon";
  const time = document.createElement("time");
  time.className = "ledger-time";
  time.dateTime = event.created_at;
  time.textContent = formatDate(event.created_at);
  row.append(statePill, operation, object, time);
  return row;
}

function renderEvents() {
  const recent = byId("recent-activity");
  const ledger = byId("operation-list");
  recent.replaceChildren();
  ledger.replaceChildren();
  if (!state.events.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No operations recorded yet.";
    recent.append(empty);
    ledger.append(empty.cloneNode(true));
    return;
  }
  state.events.slice(0, 4).forEach((event) => recent.append(eventElement(event, true)));
  state.events.forEach((event) => ledger.append(eventElement(event, false)));
}

function renderLibrary() {
  const body = byId("asset-table-body");
  body.replaceChildren();
  byId("library-loading").hidden = true;
  byId("library-count").textContent = state.summary.assets.toLocaleString();
  if (!state.assets.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "empty-state";
    cell.textContent = "No assets match this view.";
    row.append(cell);
    body.append(row);
    return;
  }

  state.assets.forEach((asset) => {
    const row = document.createElement("tr");
    row.dataset.assetId = asset.id;
    row.classList.toggle("is-selected", asset.id === state.selectedAssetId);

    const objectCell = document.createElement("td");
    const button = document.createElement("button");
    button.className = "asset-link";
    button.dataset.assetId = asset.id;
    const title = document.createElement("strong");
    title.textContent = asset.filename;
    const uri = document.createElement("small");
    uri.textContent = asset.atlas_uri;
    button.append(title, uri);
    objectCell.append(button);

    const signalCell = document.createElement("td");
    const signal = document.createElement("span");
    signal.className = "signal-label";
    signal.textContent = signalLabel(asset);
    signalCell.append(signal);

    const locationCell = document.createElement("td");
    locationCell.textContent = asset.location_count;

    const timeCell = document.createElement("td");
    timeCell.textContent = timeAgo(asset.last_seen_at);
    row.append(objectCell, signalCell, locationCell, timeCell);
    body.append(row);
  });
}

function fact(label, value) {
  const wrapper = document.createElement("div");
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = label;
  dd.textContent = value;
  wrapper.append(dt, dd);
  return wrapper;
}

function renderSystem() {
  const database = state.health.database;
  const healthy = database.state === "healthy";
  const pill = byId("system-health-pill");
  pill.textContent = healthy ? "Verified" : database.state;
  pill.className = `status-pill ${healthy ? "status-pill--jade" : "status-pill--ember"}`;

  const facts = byId("system-facts");
  facts.replaceChildren(
    fact("Integrity check", database.integrity),
    fact("Foreign-key errors", String(database.foreign_key_errors)),
    fact("Schema version", String(database.schema_version)),
    fact("Journal mode", database.journal_mode || "—"),
    fact("Database size", formatBytes(database.size_bytes)),
    fact("Network boundary", "127.0.0.1"),
  );

  const list = byId("backup-list");
  list.replaceChildren();
  if (!state.backups.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No verified local backups yet.";
    list.append(empty);
  } else {
    state.backups.forEach((backup) => {
      const row = document.createElement("div");
      row.className = "backup-item";
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = backup.name;
      const date = document.createElement("small");
      date.textContent = formatDate(backup.modified_at);
      copy.append(title, date);
      const size = document.createElement("span");
      size.className = "backup-size";
      size.textContent = formatBytes(backup.size_bytes);
      row.append(copy, size);
      list.append(row);
    });
  }
}

async function loadAssetDetail(assetId) {
  state.selectedAssetId = assetId;
  renderLibrary();
  const panel = byId("asset-detail");
  panel.innerHTML = '<div class="loading-state">Reading identity…</div>';
  try {
    const asset = await request(`/api/assets/${encodeURIComponent(assetId)}`);
    panel.replaceChildren();
    const content = document.createElement("div");
    content.className = "detail-content";
    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = "Permanent identity";
    const title = document.createElement("h2");
    title.textContent = asset.filename;
    const uri = document.createElement("p");
    uri.className = "detail-uri";
    uri.textContent = asset.atlas_uri;

    const facts = document.createElement("div");
    facts.className = "detail-section";
    const factsTitle = document.createElement("h3");
    factsTitle.textContent = "Technical signal";
    const grid = document.createElement("div");
    grid.className = "detail-grid";
    [
      ["Type", signalLabel(asset)],
      ["Size", formatBytes(asset.size_bytes)],
      ["Duration", asset.duration_seconds ? `${asset.duration_seconds}s` : "—"],
      ["Dimensions", asset.dimensions || "—"],
    ].forEach(([label, value]) => {
      const item = document.createElement("div");
      item.className = "detail-fact";
      const span = document.createElement("span");
      span.textContent = label;
      const strong = document.createElement("strong");
      strong.textContent = value;
      item.append(span, strong);
      grid.append(item);
    });
    facts.append(factsTitle, grid);

    const locations = document.createElement("div");
    locations.className = "detail-section";
    const locationsTitle = document.createElement("h3");
    locationsTitle.textContent = `Observed locations · ${asset.locations.length}`;
    locations.append(locationsTitle);
    asset.locations.forEach((location) => {
      const path = document.createElement("p");
      path.className = "path-item";
      path.textContent = location.path;
      locations.append(path);
    });

    const proof = document.createElement("div");
    proof.className = "detail-section";
    const proofTitle = document.createElement("h3");
    proofTitle.textContent = "Content proof / SHA-256";
    const checksum = document.createElement("p");
    checksum.className = "checksum";
    checksum.textContent = asset.sha256;
    proof.append(proofTitle, checksum);
    content.append(eyebrow, title, uri, facts, locations, proof);
    panel.append(content);
  } catch (error) {
    showError(error);
  }
}

function openBackupDialog() {
  byId("backup-dialog").showModal();
}

async function createVerifiedBackup(event) {
  event.preventDefault();
  const button = byId("confirm-backup-button");
  button.disabled = true;
  button.textContent = "Verifying…";
  try {
    const backup = await request("/api/backups", {
      method: "POST",
      headers: { "X-ATLAS-Action": "create-backup" },
    });
    byId("backup-dialog").close();
    showToast(`Verified backup created · ${formatBytes(backup.size_bytes)}`);
    await refreshData();
  } catch (error) {
    byId("backup-dialog").close();
    showError(error);
  } finally {
    button.disabled = false;
    button.textContent = "Create backup";
  }
}

async function loadAssets(query = "") {
  const result = await request(`/api/assets?q=${encodeURIComponent(query)}&limit=100`);
  state.assets = result.items;
  renderRecentAssets();
  renderLibrary();
}

async function refreshData() {
  clearError();
  const button = byId("refresh-button");
  button.disabled = true;
  try {
    const [health, summary, events, backups] = await Promise.all([
      request("/api/health"),
      request("/api/summary"),
      request("/api/events?limit=50"),
      request("/api/backups"),
    ]);
    state.health = health;
    state.summary = summary;
    state.events = events.items;
    state.backups = backups.items;
    await loadAssets(byId("asset-search-input").value || "");
    renderSummary();
    renderEvents();
    renderSystem();
  } catch (error) {
    showError(error);
  } finally {
    button.disabled = false;
  }
}

function bindInteractions() {
  document.querySelectorAll("[data-section-target]").forEach((button) => {
    button.addEventListener("click", () => setSection(button.dataset.sectionTarget));
  });
  document.querySelectorAll("[data-section-jump]").forEach((button) => {
    button.addEventListener("click", () => setSection(button.dataset.sectionJump));
  });
  byId("refresh-button").addEventListener("click", refreshData);
  byId("asset-search").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await loadAssets(byId("asset-search-input").value);
    } catch (error) {
      showError(error);
    }
  });
  byId("asset-table-body").addEventListener("click", (event) => {
    const button = event.target.closest("[data-asset-id]");
    if (button) loadAssetDetail(button.dataset.assetId);
  });
  byId("overview-backup-button").addEventListener("click", openBackupDialog);
  byId("system-backup-button").addEventListener("click", openBackupDialog);
  byId("confirm-backup-button").addEventListener("click", createVerifiedBackup);
}

document.addEventListener("DOMContentLoaded", async () => {
  byId("current-date").textContent = new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date());
  bindInteractions();
  const requestedSection = window.location.hash.slice(1);
  if (["overview", "library", "operations", "system"].includes(requestedSection)) {
    setSection(requestedSection);
  }
  await refreshData();
});
