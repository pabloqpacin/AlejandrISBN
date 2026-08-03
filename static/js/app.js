const isbnInput = document.getElementById("isbn-input");
const lookupForm = document.getElementById("lookup-form");
const lookupBtn = document.getElementById("lookup-btn");
const manualBtn = document.getElementById("manual-btn");
const formStatus = document.getElementById("form-status");
const searchInput = document.getElementById("search-input");
const clearSearchBtn = document.getElementById("clear-search");
const viewChips = document.getElementById("view-chips");
const exportMenu = document.querySelector(".export-menu:not(.import-menu)");
const importMenu = document.querySelector(".import-menu");
const importFile = document.getElementById("import-file");
const enrichDialog = document.getElementById("enrich-dialog");
const enrichBody = document.getElementById("enrich-body");
const enrichClose = document.getElementById("enrich-close");
let enrichAbortController = null;
let enrichSearchActive = false;
const batchBar = document.getElementById("batch-bar");
const batchCount = document.getElementById("batch-count");
const selectAllVisible = document.getElementById("select-all-visible");
const batchDialog = document.getElementById("batch-dialog");
const batchBody = document.getElementById("batch-body");
const batchClose = document.getElementById("batch-close");
let importAccept = ".json,application/json";
const bookTbody = document.getElementById("book-tbody");
const listMeta = document.getElementById("list-meta");
const emptyState = document.getElementById("empty-state");
const sortButtons = document.querySelectorAll(".sort-btn");
const groupToggles = document.querySelectorAll(".group-toggle");

const reviewDialog = document.getElementById("review-dialog");
const reviewBody = document.getElementById("review-body");
const reviewClose = document.getElementById("review-close");

const detailDialog = document.getElementById("detail-dialog");
const detailBody = document.getElementById("detail-body");
const detailClose = document.getElementById("detail-close");

const SORT_LABELS = {
  favourite: "favorito",
  title: "título",
  authors: "autor",
  publication_year: "año",
  isbn: "ISBN",
  legal_deposit: "depósito legal",
  genre: "género",
  room: "habitación",
  furniture: "mueble",
  location: "ubicación",
  publisher: "editorial",
  collection: "colección",
  notes: "notas",
};

const GROUP_LABELS = {
  favourite: "favorito",
  authors: "autor",
  genre: "género",
  room: "habitación",
  furniture: "mueble",
  location: "ubicación",
  publisher: "editorial",
  collection: "colección",
};

const COL_COUNT = 15;
const selectedIds = new Set();

const MEDIA_TABS = {
  overview: { label: "Resumen", mediaType: null },
  all: { label: "Todos", mediaType: null },
  book: { label: "Libros", mediaType: "book" },
  magazine: { label: "Revistas", mediaType: "magazine" },
  cd: { label: "CDs", mediaType: "cd" },
  dvd: { label: "DVDs", mediaType: "dvd" },
  vhs: { label: "VHS", mediaType: "vhs" },
  cassette: { label: "Cassettes", mediaType: "cassette" },
};
const PRINT_TYPES = new Set(["book", "magazine"]);
const MEDIA_LABELS = {
  book: "Libros",
  magazine: "Revistas",
  cd: "CDs",
  dvd: "DVDs",
  vhs: "VHS",
  cassette: "Cassettes",
};
const TAB_STATE_KEY = "alejandrisbn-tab";

const overviewPanel = document.getElementById("overview-panel");
const inventoryPanel = document.getElementById("inventory-panel");
const catalogNav = document.getElementById("catalog-nav");
const overviewTotal = document.getElementById("overview-total");
const overviewByType = document.getElementById("overview-by-type");
const overviewByRoom = document.getElementById("overview-by-room");
const heroLede = document.getElementById("hero-lede");
const manualOnlyActions = document.getElementById("manual-only-actions");
const addManualMediaBtn = document.getElementById("add-manual-media-btn");
const inventoryTitle = document.getElementById("inventory-title");

let activeTab = "overview";
let books = [];
let searchTimer = null;
let pendingIsbn = "";
let sortKey = "title";
let sortDir = "asc";
const VIEW_STATE_KEY = "alejandrisbn-view";

/** @type {string[]} ordered group-by fields — all active at once (nested) */
let groupByFields = [];
/** @type {{ field: string, key: string, label: string }[]} facet filters — AND */
let facetFilters = [];
/** @type {Set<string>} collapsed group ids (`field\\0key`); expanded by default */
let collapsedGroups = new Set();
/** @type {string[]} committed search terms — OR across inventory fields */
let searchTerms = [];
let suggestions = { authors: [], genre: [], room: [], furniture: [], location: [], collection: [], translators: [] };
let suggestionsLoadedAt = 0;

function groupCollapseId(field, key) {
  return `${field}\0${key}`;
}

function isGroupCollapsed(field, key) {
  return collapsedGroups.has(groupCollapseId(field, key));
}

function toggleGroupCollapsed(field, key) {
  const id = groupCollapseId(field, key);
  if (collapsedGroups.has(id)) collapsedGroups.delete(id);
  else collapsedGroups.add(id);
  saveViewState();
  renderList();
}

function loadViewState() {
  try {
    const raw = sessionStorage.getItem(VIEW_STATE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (Array.isArray(saved.groupByFields)) {
      groupByFields = saved.groupByFields.filter((field) => GROUP_LABELS[field]);
    }
    if (Array.isArray(saved.facetFilters)) {
      facetFilters = saved.facetFilters.filter(
        (facet) =>
          facet &&
          GROUP_LABELS[facet.field] &&
          typeof facet.key === "string" &&
          typeof facet.label === "string",
      );
    }
    if (Array.isArray(saved.collapsedGroups)) {
      collapsedGroups = new Set(
        saved.collapsedGroups.filter((id) => typeof id === "string" && id.includes("\0")),
      );
    }
    if (Array.isArray(saved.searchTerms)) {
      searchTerms = saved.searchTerms
        .map((term) => String(term || "").trim())
        .filter(Boolean)
        .slice(0, 12);
    }
    if (saved.sortKey && SORT_LABELS[saved.sortKey]) {
      sortKey = saved.sortKey;
    }
    if (saved.sortDir === "asc" || saved.sortDir === "desc") {
      sortDir = saved.sortDir;
    }
  } catch {
    /* ignore corrupt state */
  }
}

function saveViewState() {
  try {
    sessionStorage.setItem(
      VIEW_STATE_KEY,
      JSON.stringify({
        groupByFields,
        facetFilters,
        collapsedGroups: [...collapsedGroups],
        searchTerms,
        sortKey,
        sortDir,
      }),
    );
  } catch {
    /* ignore quota / private mode */
  }
}

function normalizeSearchTerm(value) {
  return String(value || "").trim();
}

function activeSearchTerms() {
  const terms = [...searchTerms];
  const draft = normalizeSearchTerm(searchInput?.value);
  if (draft && !terms.some((term) => term.toLowerCase() === draft.toLowerCase())) {
    terms.push(draft);
  }
  return terms;
}

function hasActiveSearch() {
  return searchTerms.length > 0 || Boolean(normalizeSearchTerm(searchInput?.value));
}

function updateClearSearchVisibility() {
  clearSearchBtn?.classList.toggle("hidden", !hasActiveSearch());
}

function commitSearchTerms(raw) {
  const parts = String(raw || "")
    .split(/[,;]+/)
    .map(normalizeSearchTerm)
    .filter(Boolean);
  if (!parts.length) return false;
  let changed = false;
  for (const part of parts) {
    if (!searchTerms.some((term) => term.toLowerCase() === part.toLowerCase())) {
      searchTerms = [...searchTerms, part];
      changed = true;
    }
  }
  if (!changed) {
    searchInput.value = "";
    updateClearSearchVisibility();
    return false;
  }
  searchInput.value = "";
  saveViewState();
  updateClearSearchVisibility();
  loadBooks();
  return true;
}

function removeSearchTerm(term) {
  const target = String(term || "").toLowerCase();
  searchTerms = searchTerms.filter((item) => item.toLowerCase() !== target);
  saveViewState();
  updateClearSearchVisibility();
  loadBooks();
}

function clearSearch(reload = true) {
  searchTerms = [];
  if (searchInput) searchInput.value = "";
  saveViewState();
  updateClearSearchVisibility();
  if (reload) loadBooks();
}

function setStatus(message, isError = false) {
  formStatus.textContent = message;
  formStatus.classList.toggle("error", isError);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function coverHtml(book, className = "cover") {
  if (book.cover_url) {
    return `<img class="${className}" src="${escapeHtml(book.cover_url)}" alt="" loading="lazy" onerror="this.outerHTML='<div class=\\'${className} placeholder\\' aria-hidden=\\'true\\'>§</div>'" />`;
  }
  return `<div class="${className} placeholder" aria-hidden="true">§</div>`;
}

function detailMessage(text) {
  return Array.isArray(text)
    ? text.map((item) => item.msg || item).join(", ")
    : text || "Error";
}

/** Ctrl/Cmd+Enter submits the form from any field (including textareas). */
function wireCtrlEnterSubmit(form) {
  if (!form) return;
  form.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || !(event.ctrlKey || event.metaKey)) return;
    event.preventDefault();
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    }
  });
}

function truncate(text, max = 36) {
  const value = String(text || "").trim();
  if (!value) return "—";
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

/** Fields stored as ``;``-separated labels (multi-value). */
const MULTI_LABEL_FIELDS = new Set(["authors", "genre", "translators"]);

function splitLabels(value) {
  return String(value ?? "")
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean);
}

function joinLabels(labels) {
  const seen = new Set();
  const unique = [];
  for (const raw of labels) {
    const part = String(raw || "").trim();
    if (!part) continue;
    const key = part.toLocaleLowerCase("es");
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(part);
  }
  return unique.join("; ");
}

function normalizeLabelField(value) {
  return joinLabels(splitLabels(value));
}

function labelsHtml(value, empty = "—") {
  const labels = splitLabels(value);
  if (!labels.length) return empty;
  return `<span class="field-labels">${labels
    .map((label) => `<span class="field-label">${escapeHtml(label)}</span>`)
    .join("")}</span>`;
}

function collectionDisplay(book) {
  const name = String(book.collection || "").trim();
  const volume = String(book.volume || "").trim();
  if (!name && !volume) return "";
  if (!name) return volume;
  if (!volume) return name;
  return `${name} · ${volume}`;
}

/** Advanced bibliographic fields — editor only, not shown in inventory table. */
function originFieldsHtml(book = {}) {
  return `
    <details class="origin-panel">
      <summary>Origen / traducción</summary>
      <div class="origin-panel-body">
        <label class="field">
          <span>Título original</span>
          <input name="original_title" type="text" value="${escapeHtml(book.original_title || "")}" placeholder="Título en la lengua original…" />
        </label>
        <div class="review-grid">
          <label class="field">
            <span>Año original</span>
            <input name="original_year" type="number" min="1" max="2100" value="${escapeHtml(book.original_year ?? "")}" placeholder="Primera publicación" />
          </label>
          <label class="field">
            <span>Traductor(es)</span>
            <input name="translators" type="text" value="${escapeHtml(book.translators || "")}" placeholder="Apellido, Nombre; …" />
          </label>
        </div>
        <p class="origin-hint">El año de arriba es el de <em>esta</em> edición; el original es la primera aparición de la obra.</p>
      </div>
    </details>
  `;
}

function readOriginFields(data) {
  const yearRaw = String(data.get("original_year") || "").trim();
  const payload = {
    original_title: String(data.get("original_title") || "").trim(),
    translators: normalizeLabelField(data.get("translators")),
  };
  if (yearRaw) {
    const year = Number(yearRaw);
    if (!Number.isNaN(year)) payload.original_year = year;
  } else {
    payload.original_year = null;
  }
  return payload;
}

function isLocalId(isbn) {
  return /^LOCAL-[A-Z0-9]{8,32}$/i.test(String(isbn || "").trim());
}


function loadActiveTab() {
  try {
    const saved = sessionStorage.getItem(TAB_STATE_KEY);
    if (saved && MEDIA_TABS[saved]) activeTab = saved;
  } catch {
    /* ignore */
  }
}

function saveActiveTab() {
  try {
    sessionStorage.setItem(TAB_STATE_KEY, activeTab);
  } catch {
    /* ignore */
  }
}

function currentMediaType() {
  return MEDIA_TABS[activeTab]?.mediaType || null;
}

function isPrintTab() {
  if (activeTab === "all" || activeTab === "overview") return true;
  return PRINT_TYPES.has(currentMediaType() || "");
}

function defaultMediaTypeForCreate() {
  const mt = currentMediaType();
  if (mt) return mt;
  return "book";
}

function updateHeroForTab() {
  const mt = currentMediaType();
  const print = !mt || PRINT_TYPES.has(mt);
  lookupForm?.classList.toggle("hidden", activeTab === "overview" ? false : !print);
  if (activeTab === "overview") {
    lookupForm?.classList.remove("hidden");
    manualOnlyActions?.classList.add("hidden");
    if (heroLede) {
      heroLede.textContent = "Inventario lean de biblioteca y multimedia. Elige una categoría o añade desde aquí.";
    }
    return;
  }
  lookupForm?.classList.toggle("hidden", !print);
  manualOnlyActions?.classList.toggle("hidden", print);
  if (heroLede) {
    if (print) {
      heroLede.textContent = mt === "magazine"
        ? "Revistas: busca por ISBN o añade sin ISBN."
        : "Libros: busca por ISBN o añade sin ISBN.";
      if (activeTab === "all") {
        heroLede.textContent = "Todo el inventario. ISBN solo para libros y revistas.";
      }
    } else {
      const label = MEDIA_LABELS[mt] || mt;
      heroLede.textContent = `${label}: alta manual (sin lookup online todavía).`;
    }
  }
}

function updatePrintColumns() {
  const show = isPrintTab();
  document.querySelectorAll(".col-print").forEach((el) => {
    el.classList.toggle("hidden", !show);
    if (el.tagName === "TH" || el.tagName === "TD") {
      el.hidden = !show;
    }
  });
  const authorsBtn = document.getElementById("sort-authors-label");
  const publisherBtn = document.getElementById("sort-publisher-label");
  if (authorsBtn) {
    authorsBtn.textContent = PRINT_TYPES.has(currentMediaType() || "book") || activeTab === "all" || activeTab === "overview"
      ? "Autor"
      : "Artista / créditos";
  }
  if (publisherBtn) {
    publisherBtn.textContent = PRINT_TYPES.has(currentMediaType() || "book") || activeTab === "all" || activeTab === "overview"
      ? "Editorial"
      : "Sello / estudio";
  }
}

function setActiveTab(tab, { skipLoad = false } = {}) {
  if (!MEDIA_TABS[tab]) tab = "overview";
  activeTab = tab;
  saveActiveTab();
  catalogNav?.querySelectorAll(".catalog-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === activeTab);
  });
  const showOverview = activeTab === "overview";
  overviewPanel?.classList.toggle("hidden", !showOverview);
  if (overviewPanel) overviewPanel.hidden = !showOverview;
  inventoryPanel?.classList.toggle("hidden", showOverview);
  if (inventoryPanel) inventoryPanel.hidden = showOverview;
  if (inventoryTitle) {
    inventoryTitle.textContent = MEDIA_TABS[activeTab]?.label || "Inventario";
  }
  updateHeroForTab();
  updatePrintColumns();
  if (skipLoad) return;
  if (showOverview) {
    loadOverview();
  } else {
    loadBooks();
  }
}

async function loadOverview() {
  try {
    const res = await fetch("/api/stats");
    if (!res.ok) {
      setStatus("Error al cargar el resumen.", true);
      return;
    }
    const stats = await res.json();
    if (overviewTotal) {
      overviewTotal.textContent = `${stats.total} ítem(s) en total`;
    }
    if (overviewByType) {
      const order = ["book", "magazine", "cd", "dvd", "vhs", "cassette"];
      overviewByType.innerHTML = order
        .map((type) => {
          const count = stats.by_media_type?.[type] || 0;
          return `<li><button type="button" class="overview-link" data-goto-tab="${type}"><span>${escapeHtml(MEDIA_LABELS[type] || type)}</span><strong>${count}</strong></button></li>`;
        })
        .join("");
    }
    if (overviewByRoom) {
      const rows = stats.by_room || [];
      if (!rows.length) {
        overviewByRoom.innerHTML = `<li class="overview-empty">Sin habitaciones aún</li>`;
      } else {
        overviewByRoom.innerHTML = rows
          .map((row) => {
            const room = String(row.value || "");
            const isEmpty = room === "(sin habitación)";
            const furniture = Array.isArray(row.furniture) ? row.furniture : [];
            const furnitureHtml = furniture
              .map((item) => {
                const furn = String(item.value || "");
                const furnEmpty = furn === "(sin mueble)";
                return `<button type="button" class="overview-sublink" data-goto-room="${escapeHtml(isEmpty ? "" : room)}" data-goto-furniture="${escapeHtml(furnEmpty ? "" : furn)}" data-room-label="${escapeHtml(room)}" data-furniture-label="${escapeHtml(furn)}"><span>${escapeHtml(furn)}</span><strong>${item.count}</strong></button>`;
              })
              .join("");
            return `<li class="overview-room">
              <button type="button" class="overview-link" data-goto-room="${escapeHtml(isEmpty ? "" : room)}" data-room-label="${escapeHtml(room)}"><span>${escapeHtml(room)}</span><strong>${row.count}</strong></button>
              <div class="overview-furniture">${furnitureHtml}</div>
            </li>`;
          })
          .join("");
      }
    }
  } catch {
    setStatus("Error de red al cargar el resumen.", true);
  }
}

function hasRealIsbn(book) {
  const isbn = String(book?.isbn || "").trim();
  return Boolean(isbn) && !isLocalId(isbn);
}

function placementDisplay(book) {
  const room = String(book?.room || "").trim();
  const furniture = String(book?.furniture || "").trim();
  if (room && furniture) return `${room} · ${furniture}`;
  return room || furniture || String(book?.location || "").trim();
}

function placementFieldsHtml(book = {}, { autofocusRoom = false } = {}) {
  return `
    <div class="review-grid">
      <label class="field">
        <span>Habitación</span>
        <input name="room" type="text" value="${escapeHtml(book.room || "")}" placeholder="Salón, dormitorio, trastero…" ${autofocusRoom ? "autofocus" : ""} />
      </label>
      <label class="field">
        <span>Mueble</span>
        <input name="furniture" type="text" value="${escapeHtml(book.furniture || "")}" placeholder="Estantería norte, caja 1…" />
      </label>
    </div>`;
}

function readPlacementFields(data) {
  return {
    room: String(data.get("room") || "").trim(),
    furniture: String(data.get("furniture") || "").trim(),
  };
}

function isbnCellHtml(book) {
  if (!hasRealIsbn(book)) {
    return `<span class="no-isbn">—</span>`;
  }
  return `<code>${escapeHtml(book.isbn)}</code>`;
}

function legalDepositCellHtml(book) {
  const value = String(book.legal_deposit || "").trim();
  if (!value) return "—";
  return `<span class="legal-deposit">${escapeHtml(value)}</span>`;
}

function compareValues(a, b) {
  const emptyA = a === null || a === undefined || a === "";
  const emptyB = b === null || b === undefined || b === "";
  if (emptyA && emptyB) return 0;
  if (emptyA) return 1;
  if (emptyB) return -1;
  if (typeof a === "boolean" && typeof b === "boolean") return Number(a) - Number(b);
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), "es", { sensitivity: "base", numeric: true });
}

function sortedBooks(list = books) {
  const copy = [...list];
  copy.sort((left, right) => {
    let result;
    if (sortKey === "collection") {
      result = compareValues(left.collection || "", right.collection || "");
      if (result === 0) {
        result = compareValues(left.volume || "", right.volume || "");
      }
    } else {
      const leftVal = MULTI_LABEL_FIELDS.has(sortKey)
        ? splitLabels(left[sortKey])[0] || ""
        : left[sortKey];
      const rightVal = MULTI_LABEL_FIELDS.has(sortKey)
        ? splitLabels(right[sortKey])[0] || ""
        : right[sortKey];
      result = compareValues(leftVal, rightVal);
    }
    return sortDir === "asc" ? result : -result;
  });
  return copy;
}

function groupKey(value, field) {
  if (field === "favourite") {
    return value ? "1" : "0";
  }
  if (field === "publication_year") {
    return value == null || value === "" ? "" : String(value);
  }
  return String(value ?? "").trim();
}

function groupLabel(value, field) {
  if (field === "favourite") {
    return value ? "Favoritos" : "Otros";
  }
  if (field === "publication_year") {
    return value == null || value === "" ? "Sin año" : String(value);
  }
  const text = String(value ?? "").trim();
  return text || "Sin clasificar";
}

/** One entry per group a book belongs to (multi-label fields expand). */
function bookGroupEntries(book, field) {
  if (MULTI_LABEL_FIELDS.has(field)) {
    const labels = splitLabels(book[field]);
    if (!labels.length) return [{ key: "", label: "Sin clasificar" }];
    return labels.map((label) => ({ key: label, label }));
  }
  const key = groupKey(book[field], field);
  return [{ key, label: groupLabel(book[field], field) }];
}

function bookMatchesFacets(book) {
  return facetFilters.every((facet) => {
    if (MULTI_LABEL_FIELDS.has(facet.field)) {
      const labels = splitLabels(book[facet.field]);
      if (!labels.length) return facet.key === "";
      return labels.some((label) => label === facet.key);
    }
    return groupKey(book[facet.field], facet.field) === facet.key;
  });
}

function visibleBooks() {
  return sortedBooks(books.filter(bookMatchesFacets));
}

function toggleGroupBy(field) {
  if (!GROUP_LABELS[field]) return;
  const idx = groupByFields.indexOf(field);
  if (idx >= 0) {
    groupByFields = groupByFields.filter((item) => item !== field);
  } else {
    groupByFields = [...groupByFields, field];
  }
  saveViewState();
  renderList();
}

function toggleFacetFilter(field, key, label) {
  const existing = facetFilters.findIndex((facet) => facet.field === field && facet.key === key);
  if (existing >= 0) {
    facetFilters = facetFilters.filter((_, index) => index !== existing);
  } else {
    // One value per field; replace if same dimension already filtered
    facetFilters = [...facetFilters.filter((facet) => facet.field !== field), { field, key, label }];
  }
  saveViewState();
  renderList();
}

function clearGroupBy(field = null) {
  groupByFields = field ? groupByFields.filter((item) => item !== field) : [];
  saveViewState();
  renderList();
}

function clearFacetFilter(field = null, key = null) {
  if (!field) {
    facetFilters = [];
  } else if (key == null) {
    facetFilters = facetFilters.filter((facet) => facet.field !== field);
  } else {
    facetFilters = facetFilters.filter((facet) => !(facet.field === field && facet.key === key));
  }
  saveViewState();
  renderList();
}

function updateSortButtons() {
  sortButtons.forEach((btn) => {
    const key = btn.dataset.sort;
    const active = key === sortKey;
    const base = key === "favourite" ? "★" : btn.textContent.replace(/[↑↓]\s*$/, "").trim();
    btn.classList.toggle("active", active);
    if (key === "favourite") {
      btn.textContent = "★";
      btn.setAttribute("aria-sort", active ? (sortDir === "asc" ? "ascending" : "descending") : "none");
      return;
    }
    btn.textContent = active ? `${base} ${sortDir === "asc" ? "↑" : "↓"}` : base;
  });
}

function updateGroupToggles() {
  groupToggles.forEach((btn) => {
    const active = groupByFields.includes(btn.dataset.group);
    btn.classList.toggle("is-on", active);
    btn.setAttribute("aria-pressed", active ? "true" : "false");
    const th = btn.closest("th");
    th?.classList.toggle("is-grouped", active);
  });
}

function updateViewChips() {
  if (!viewChips) return;
  const hasGroups = groupByFields.length > 0;
  const hasFacets = facetFilters.length > 0;
  const hasSearch = searchTerms.length > 0;
  if (!hasGroups && !hasFacets && !hasSearch) {
    viewChips.hidden = true;
    viewChips.innerHTML = "";
    return;
  }

  const searchChips = searchTerms
    .map(
      (term) => `
        <span class="view-chip view-chip-search">
          <strong>${escapeHtml(term)}</strong>
          <button
            type="button"
            class="chip-clear"
            data-clear-search-term="${escapeHtml(term)}"
            aria-label="Quitar término ${escapeHtml(term)}"
          >×</button>
        </span>
      `,
    )
    .join("");

  const searchCluster = hasSearch
    ? `<div class="view-chip-cluster" role="group" aria-label="Búsqueda">
        <span class="view-chip-legend">Buscar</span>
        ${searchChips}
      </div>`
    : "";

  const groupChips = groupByFields
    .map((field, index) => {
      const label = GROUP_LABELS[field] || field;
      const order =
        groupByFields.length > 1
          ? `<span class="chip-ord" aria-hidden="true">${index + 1}</span>`
          : "";
      return `
        <span class="view-chip view-chip-group">
          ${order}<strong>${escapeHtml(label)}</strong>
          <button type="button" class="chip-clear" data-clear-group="${escapeHtml(field)}" aria-label="Quitar agrupación por ${escapeHtml(label)}">×</button>
        </span>
      `;
    })
    .join("");

  const groupCluster = hasGroups
    ? `<div class="view-chip-cluster" role="group" aria-label="Agrupación">
        <span class="view-chip-legend">Agrupado</span>
        ${groupChips}
      </div>`
    : "";

  const facetChips = facetFilters
    .map(
      (facet) => `
        <span class="view-chip view-chip-filter">
          <span class="chip-dim">${escapeHtml(GROUP_LABELS[facet.field] || facet.field)}</span>
          <strong>${escapeHtml(facet.label)}</strong>
          <button
            type="button"
            class="chip-clear"
            data-clear-facet
            data-field="${escapeHtml(facet.field)}"
            data-key="${escapeHtml(facet.key)}"
            aria-label="Quitar filtro ${escapeHtml(facet.label)}"
          >×</button>
        </span>
      `,
    )
    .join("");

  const facetCluster = hasFacets
    ? `<div class="view-chip-cluster" role="group" aria-label="Filtros">
        <span class="view-chip-legend">Filtros</span>
        ${facetChips}
      </div>`
    : "";

  const clearAll =
    hasGroups || hasFacets || hasSearch
      ? `<button type="button" class="view-chip view-chip-clear-all" data-clear-view>Limpiar vista</button>`
      : "";

  viewChips.hidden = false;
  viewChips.innerHTML = `${searchCluster}${groupCluster}${facetCluster}${clearAll}`;
}

function findItem(id) {
  return books.find((book) => book.id === id);
}

function findBook(id) {
  return findItem(id);
}

function bookRowHtml(book) {
  const fav = Boolean(book.favourite);
  const id = book.id;
  const checked = selectedIds.has(id) ? "checked" : "";
  const printCols = isPrintTab()
    ? `<td class="col-isbn col-print">${isbnCellHtml(book)}</td>
    <td class="col-dl col-print">${legalDepositCellHtml(book)}</td>`
    : `<td class="col-isbn col-print hidden" hidden>—</td>
    <td class="col-dl col-print hidden" hidden>—</td>`;
  return `
    <td class="col-select">
      <input
        type="checkbox"
        class="row-select"
        data-select-id="${escapeHtml(id)}"
        ${checked}
        aria-label="Seleccionar ${escapeHtml(book.title || id)}"
      />
    </td>
    <td class="col-fav">
      <button
        type="button"
        class="fav-btn${fav ? " is-on" : ""}"
        data-fav-toggle="${escapeHtml(id)}"
        title="${fav ? "Quitar de favoritos" : "Marcar favorito"}"
        aria-pressed="${fav ? "true" : "false"}"
        aria-label="${fav ? "Quitar de favoritos" : "Marcar favorito"}"
      >★</button>
    </td>
    <td class="col-cover">${coverHtml(book, "cover thumb")}</td>
    <td class="col-title">
      <button type="button" class="linkish" data-open="${escapeHtml(id)}">
        ${escapeHtml(book.title)}
      </button>
    </td>
    <td class="col-authors">${labelsHtml(book.authors)}</td>
    <td class="col-year">${escapeHtml(book.publication_year ?? "—")}</td>
    ${printCols}
    <td class="col-genre">${labelsHtml(book.genre)}</td>
    <td class="col-room">${escapeHtml(book.room || "—")}</td>
    <td class="col-furniture">${escapeHtml(book.furniture || "—")}</td>
    <td title="${escapeHtml(book.publisher || "")}">${escapeHtml(truncate(book.publisher, 22))}</td>
    <td class="col-collection" title="${escapeHtml(collectionDisplay(book))}">${escapeHtml(truncate(collectionDisplay(book) || "—", 28))}</td>
    <td title="${escapeHtml(book.notes || "")}">${escapeHtml(truncate(book.notes, 24))}</td>
    <td class="col-actions">
      <button type="button" class="btn ghost compact" data-open="${escapeHtml(id)}">Ver</button>
      <button type="button" class="btn danger compact" data-delete="${escapeHtml(id)}" title="Eliminar">✕</button>
    </td>
  `;
}

function appendGroupHeader({ field, key, label, count, depth, filtered, collapsed }) {
  const tr = document.createElement("tr");
  tr.className = `group-row depth-${Math.min(depth, 4)}${filtered ? " is-filtered" : ""}${
    collapsed ? " is-collapsed" : ""
  }`;
  tr.innerHTML = `
    <td colspan="${COL_COUNT}">
      <div class="group-heading">
        <button
          type="button"
          class="group-collapse-btn"
          data-collapse-field="${escapeHtml(field)}"
          data-collapse-key="${escapeHtml(key)}"
          aria-expanded="${collapsed ? "false" : "true"}"
          title="${collapsed ? "Expandir grupo" : "Plegar grupo"}"
          aria-label="${collapsed ? "Expandir" : "Plegar"} ${escapeHtml(label)}"
        >${collapsed ? "▸" : "▾"}</button>
        <button
          type="button"
          class="group-filter-btn"
          data-facet-field="${escapeHtml(field)}"
          data-facet-key="${escapeHtml(key)}"
          data-facet-label="${escapeHtml(label)}"
          aria-pressed="${filtered ? "true" : "false"}"
          title="${filtered ? "Quitar filtro" : "Filtrar por este grupo (se combina con los demás)"}"
        >
          <span class="group-label">${escapeHtml(label)}</span>
          <span class="group-count">${count}</span>
          <span class="group-filter-hint">${filtered ? "filtro activo" : "filtrar"}</span>
        </button>
      </div>
    </td>
  `;
  bookTbody.appendChild(tr);
}

function appendBookRow(book) {
  const tr = document.createElement("tr");
  tr.innerHTML = bookRowHtml(book);
  bookTbody.appendChild(tr);
}

function partitionByField(rows, field) {
  const groups = new Map();
  rows.forEach((book) => {
    bookGroupEntries(book, field).forEach(({ key, label }) => {
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          label,
          items: [],
        });
      }
      groups.get(key).items.push(book);
    });
  });

  let entries = [...groups.values()];
  if (field === "favourite") {
    const order = ["1", "0"];
    entries.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
  } else {
    entries.sort((a, b) =>
      a.label.localeCompare(b.label, "es", { sensitivity: "base", numeric: true }),
    );
  }
  return entries;
}

function renderGrouped(rows, fields, depth = 0) {
  if (!fields.length) {
    rows.forEach(appendBookRow);
    return;
  }

  const [field, ...rest] = fields;
  partitionByField(rows, field).forEach((group) => {
    const filtered = facetFilters.some(
      (facet) => facet.field === field && facet.key === group.key,
    );
    const collapsed = isGroupCollapsed(field, group.key);
    appendGroupHeader({
      field,
      key: group.key,
      label: group.label,
      count: group.items.length,
      depth,
      filtered,
      collapsed,
    });
    if (!collapsed) {
      renderGrouped(group.items, rest, depth + 1);
    }
  });
}

function renderList() {
  const rows = visibleBooks();
  bookTbody.innerHTML = "";
  emptyState.classList.toggle("hidden", rows.length > 0);

  updateClearSearchVisibility();

  const terms = activeSearchTerms();
  const sortHint = `orden: ${SORT_LABELS[sortKey]} ${sortDir === "asc" ? "A→Z" : "Z→A"}`;
  const filterHint = facetFilters.length
    ? ` · ${facetFilters.length} filtro${facetFilters.length === 1 ? "" : "s"}`
    : "";
  const groupHint = groupByFields.length
    ? ` · agrupado: ${groupByFields.map((field) => GROUP_LABELS[field] || field).join(" → ")}`
    : "";
  const searchHint = terms.length
    ? ` · buscar: ${terms.map((term) => `“${term}”`).join(" | ")}`
    : "";
  listMeta.textContent = terms.length
    ? `${rows.length} resultado${rows.length === 1 ? "" : "s"}${searchHint} · ${sortHint}${filterHint}${groupHint}`
    : `${rows.length} ítem${rows.length === 1 ? "" : "s"} · ${sortHint}${filterHint}${groupHint}`;

  if (!rows.length) {
    const label = MEDIA_TABS[activeTab]?.label || "categoría";
    emptyState.textContent =
      activeTab === "all"
        ? "Aún no hay ítems. Añade el primero desde el formulario."
        : `Aún no hay ítems en ${label}.`;
  }

  updateSortButtons();
  updateGroupToggles();
  updateViewChips();

  const activeGroups = groupByFields.filter((field) => GROUP_LABELS[field]);
  if (activeGroups.length) {
    renderGrouped(rows, activeGroups);
    updateBatchBar();
    return;
  }

  rows.forEach(appendBookRow);
  updateBatchBar();
}

function selectedList() {
  return [...selectedIds];
}

function pruneSelection() {
  const known = new Set(books.map((book) => book.id));
  for (const isbn of [...selectedIds]) {
    if (!known.has(isbn)) selectedIds.delete(isbn);
  }
}

function updateBatchBar() {
  const n = selectedIds.size;
  if (batchCount) {
    batchCount.textContent = n === 1 ? "1 seleccionado" : `${n} seleccionados`;
  }
  if (batchBar) {
    batchBar.hidden = n === 0;
    batchBar.classList.toggle("hidden", n === 0);
  }
  if (selectAllVisible) {
    const visible = visibleBooks();
    const selectedVisible = visible.filter((book) => selectedIds.has(book.id)).length;
    selectAllVisible.checked = visible.length > 0 && selectedVisible === visible.length;
    selectAllVisible.indeterminate =
      selectedVisible > 0 && selectedVisible < visible.length;
  }
}

function setRowSelected(isbn, on) {
  if (!isbn) return;
  if (on) selectedIds.add(isbn);
  else selectedIds.delete(isbn);
}

function selectVisibleRows(on) {
  visibleBooks().forEach((book) => setRowSelected(book.id, on));
  bookTbody.querySelectorAll(".row-select").forEach((cb) => {
    cb.checked = on;
  });
  updateBatchBar();
}

async function batchDeleteSelected() {
  const isbns = selectedList();
  if (!isbns.length || !batchDialog || !batchBody) return;

  batchBody.innerHTML = `
    <h3 class="enrich-title">Eliminar selección</h3>
    <p class="enrich-meta">
      Vas a borrar <strong>${isbns.length}</strong> registro(s) del inventario.
      Esta acción no se puede deshacer.
    </p>
    <div class="enrich-actions">
      <button type="button" class="btn ghost" data-batch-close>Cancelar</button>
      <button type="button" class="btn danger" id="batch-delete-confirm">Eliminar</button>
    </div>`;
  batchDialog.showModal();
  batchBody.querySelector("[data-batch-close]")?.addEventListener("click", () => batchDialog.close());
  batchBody.querySelector("#batch-delete-confirm")?.addEventListener("click", async () => {
    const btn = batchBody.querySelector("#batch-delete-confirm");
    if (btn) btn.disabled = true;
    setStatus(`Eliminando ${isbns.length}…`);
    try {
      const res = await fetch("/api/items/batch/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: isbns }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setStatus(data.detail || "No se pudo eliminar la selección.", true);
        return;
      }
      isbns.forEach((isbn) => selectedIds.delete(isbn));
      batchDialog.close();
      setStatus(`Eliminados: ${data.deleted}.`);
      await loadBooks();
    } catch {
      setStatus("Error de red al eliminar.", true);
    } finally {
      if (btn) btn.disabled = false;
    }
  });
}

function openBatchFieldDialog() {
  const isbns = selectedList();
  if (!isbns.length || !batchDialog || !batchBody) return;
  batchBody.innerHTML = `
    <h3 class="enrich-title">Actualizar campo</h3>
    <p class="enrich-meta">${isbns.length} registro(s) seleccionados. Se aplicará el mismo valor a todos.</p>
    <form id="batch-field-form" class="batch-field-form">
      <label class="field">
        <span>Campo</span>
        <select name="field" required>
          <option value="room" selected>Habitación</option>
          <option value="furniture">Mueble</option>
          <option value="genre">Género</option>
          <option value="collection">Colección</option>
          <option value="volume">Volumen</option>
          <option value="notes">Notas</option>
          <option value="legal_deposit">Depósito legal</option>
          <option value="publisher">Editorial</option>
          <option value="authors">Autores</option>
        </select>
      </label>
      <label class="field">
        <span>Valor</span>
        <input name="value" type="text" placeholder="p. ej. A1" required />
      </label>
      <div class="enrich-actions">
        <button type="button" class="btn ghost" data-batch-close>Cancelar</button>
        <button type="submit" class="btn primary">Aplicar</button>
      </div>
    </form>`;
  batchDialog.showModal();
  batchBody.querySelector("[data-batch-close]")?.addEventListener("click", () => batchDialog.close());
  batchBody.querySelector("#batch-field-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const field = form.field.value;
    const value = form.value.value;
    const applyBtn = form.querySelector('button[type="submit"]');
    if (applyBtn) applyBtn.disabled = true;
    setStatus(`Actualizando ${isbns.length}…`);
    try {
      const res = await fetch("/api/items/batch/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: isbns, fields: { [field]: value } }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setStatus(data.detail || "No se pudo actualizar.", true);
        return;
      }
      batchDialog.close();
      setStatus(`Actualizados: ${data.updated} (${(data.fields || []).join(", ")}).`);
      await loadBooks();
    } catch {
      setStatus("Error de red al actualizar.", true);
    } finally {
      if (applyBtn) applyBtn.disabled = false;
    }
  });
}

function batchEnrichSelected() {
  const ids = selectedList().filter((id) => {
    const item = findItem(id);
    return item && hasRealIsbn(item);
  });
  if (!ids.length) {
    setStatus("La selección no tiene ítems con ISBN (libros/revistas).", true);
    return;
  }
  runEnrichPreview(ids);
}

async function toggleFavourite(isbn) {
  const book = findBook(isbn);
  if (!book) return;
  const next = !book.favourite;
  const res = await fetch(`/api/items/${encodeURIComponent(isbn)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ favourite: next }),
  });
  if (!res.ok) {
    setStatus("No se pudo actualizar el favorito.", true);
    return;
  }
  const updated = await res.json();
  const idx = books.findIndex((item) => item.id === isbn);
  if (idx >= 0) books[idx] = updated;
  renderList();
}

async function deleteBook(isbn, title) {
  if (!confirm(`¿Eliminar “${title}” del inventario?`)) return false;
  const res = await fetch(`/api/items/${encodeURIComponent(isbn)}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    setStatus("No se pudo eliminar el libro.", true);
    return false;
  }
  setStatus("Libro eliminado.");
  suggestionsLoadedAt = 0;
  await loadBooks();
  return true;
}

async function loadSuggestions(force = false) {
  const stale = Date.now() - suggestionsLoadedAt > 30_000;
  if (!force && suggestionsLoadedAt && !stale) return suggestions;
  try {
    const res = await fetch("/api/suggestions");
    if (!res.ok) return suggestions;
    suggestions = await res.json();
    suggestionsLoadedAt = Date.now();
  } catch {
    /* keep previous cache */
  }
  return suggestions;
}

function filterSuggestions(items, query, { exclude = [] } = {}) {
  const q = String(query || "").trim().toLowerCase();
  const excluded = new Set(exclude.map((item) => String(item).toLowerCase()));
  return items
    .filter((item) => {
      const value = item.value.toLowerCase();
      if (excluded.has(value)) return false;
      return !q || value.includes(q);
    })
    .slice(0, 12);
}

function attachSuggest(input, items, { showCount = false, multiLabel = false } = {}) {
  if (!input) return;
  const wrap = document.createElement("div");
  wrap.className = "suggest-field";
  input.parentNode.insertBefore(wrap, input);
  wrap.appendChild(input);
  input.setAttribute("autocomplete", "off");
  input.setAttribute("spellcheck", "false");

  const list = document.createElement("ul");
  list.className = "suggest-list";
  list.hidden = true;
  list.setAttribute("role", "listbox");
  wrap.appendChild(list);

  let activeIndex = -1;
  let visible = [];

  function close() {
    list.hidden = true;
    list.innerHTML = "";
    activeIndex = -1;
    visible = [];
  }

  function segmentState() {
    if (!multiLabel) {
      return { prefix: "", query: input.value, used: [] };
    }
    const raw = input.value;
    const lastSep = raw.lastIndexOf(";");
    if (lastSep < 0) {
      return { prefix: "", query: raw, used: [] };
    }
    const prefix = raw.slice(0, lastSep);
    const query = raw.slice(lastSep + 1);
    return {
      prefix,
      query,
      used: splitLabels(prefix),
    };
  }

  function render() {
    const { query, used } = segmentState();
    visible = filterSuggestions(items, query, { exclude: used });
    if (!visible.length) {
      close();
      return;
    }
    list.innerHTML = visible
      .map(
        (item, index) => `
        <li role="presentation">
          <button
            type="button"
            class="suggest-option${index === activeIndex ? " is-active" : ""}"
            role="option"
            data-index="${index}"
            data-value="${escapeHtml(item.value)}"
          >
            <span class="suggest-option-value">${escapeHtml(item.value)}</span>
            ${
              showCount
                ? `<span class="suggest-option-count">${item.count}</span>`
                : ""
            }
          </button>
        </li>
      `,
      )
      .join("");
    list.hidden = false;
  }

  function pick(index) {
    const item = visible[index];
    if (!item) return;
    if (multiLabel) {
      const { used } = segmentState();
      input.value = joinLabels([...used, item.value]);
    } else {
      input.value = item.value;
    }
    close();
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus();
  }

  input.addEventListener("focus", render);
  input.addEventListener("input", () => {
    activeIndex = -1;
    render();
  });

  input.addEventListener("keydown", (event) => {
    if (list.hidden && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      render();
    }
    if (list.hidden) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      activeIndex = (activeIndex + 1) % visible.length;
      render();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      activeIndex = (activeIndex - 1 + visible.length) % visible.length;
      render();
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      pick(activeIndex);
    } else if (event.key === "Escape") {
      close();
    }
  });

  list.addEventListener("mousedown", (event) => {
    const option = event.target.closest("[data-value]");
    if (!option) return;
    event.preventDefault();
    pick(Number(option.dataset.index));
  });

  input.addEventListener("blur", () => {
    window.setTimeout(close, 120);
  });
}

async function wireFieldSuggestions(root) {
  const data = await loadSuggestions();
  attachSuggest(root.querySelector('input[name="authors"]'), data.authors || [], {
    showCount: true,
    multiLabel: true,
  });
  attachSuggest(root.querySelector('input[name="genre"]'), data.genre || [], {
    showCount: true,
    multiLabel: true,
  });
  attachSuggest(root.querySelector('input[name="room"]'), data.room || [], {
    showCount: true,
  });
  attachSuggest(root.querySelector('input[name="furniture"]'), data.furniture || [], {
    showCount: true,
  });
  attachSuggest(root.querySelector('input[name="collection"]'), data.collection || [], {
    showCount: true,
  });
  attachSuggest(root.querySelector('input[name="translators"]'), data.translators || [], {
    showCount: true,
    multiLabel: true,
  });
}

function openReview(isbn, meta) {
  pendingIsbn = isbn;
  reviewBody.innerHTML = `
    <div class="review-layout">
      ${coverHtml(meta, "detail-cover")}
      <div>
        <p class="review-kicker">Match encontrado · ${escapeHtml(meta.source || "catálogo")}</p>
        <h3 class="review-title">${escapeHtml(meta.title)}</h3>
        <p class="authors">${escapeHtml(meta.authors || "Autor desconocido")}</p>
        <p class="review-isbn">ISBN ${escapeHtml(isbn)}</p>

        <form id="review-form" class="review-form">
          <label class="field">
            <span>Título</span>
            <input name="title" type="text" value="${escapeHtml(meta.title || "")}" required />
          </label>
          <label class="field">
            <span>Autor(es)</span>
            <input name="authors" type="text" value="${escapeHtml(meta.authors || "")}" placeholder="Apellido, Nombre; Otro autor…" />
          </label>
          <div class="review-grid">
            <label class="field">
              <span>Año</span>
              <input name="publication_year" type="number" min="1000" max="2100" value="${escapeHtml(meta.publication_year ?? "")}" />
            </label>
            <label class="field">
              <span>Editorial</span>
              <input name="publisher" type="text" value="${escapeHtml(meta.publisher || "")}" />
            </label>
          </div>
          <label class="field">
            <span>Género(s)</span>
            <input name="genre" type="text" value="${escapeHtml(meta.genre || "")}" placeholder="Novela; Ensayo; Poesía…" />
          </label>
          ${placementFieldsHtml({}, { autofocusRoom: true })}
          <label class="field">
            <span>Colección</span>
            <input name="collection" type="text" placeholder="Opcional — serie, colección editorial…" />
          </label>
          <label class="field">
            <span>Volumen / nº</span>
            <input name="volume" type="text" placeholder="8, II, tomo 3…" />
          </label>
          <label class="field">
            <span>Notas</span>
            <input name="notes" type="text" placeholder="Donación, estado, préstamo…" />
          </label>
          <label class="field">
            <span>Descripción</span>
            <textarea name="description" rows="3">${escapeHtml(meta.description || "")}</textarea>
          </label>
          ${originFieldsHtml(meta)}
          <label class="checkbox-row">
            <input name="favourite" type="checkbox" />
            <span>Marcar como favorito</span>
          </label>
          <input type="hidden" name="cover_url" value="${escapeHtml(meta.cover_url || "")}" />

          <div class="detail-actions">
            <button type="submit" class="btn primary" id="save-review-btn">Guardar en inventario</button>
            <button type="button" class="btn ghost" id="cancel-review-btn">Cancelar</button>
          </div>
          <p id="review-status" class="status" role="status"></p>
        </form>
      </div>
    </div>
  `;

  const form = reviewBody.querySelector("#review-form");
  const saveBtn = reviewBody.querySelector("#save-review-btn");
  const reviewStatus = reviewBody.querySelector("#review-status");

  reviewBody.querySelector("#cancel-review-btn")?.addEventListener("click", () => {
    reviewDialog.close();
    setStatus("Alta cancelada.");
  });

  wireCtrlEnterSubmit(form);

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const yearRaw = String(data.get("publication_year") || "").trim();
    const payload = {
      media_type: activeTab === "magazine" ? "magazine" : "book",
      isbn: pendingIsbn,
      title: String(data.get("title") || "").trim(),
      authors: normalizeLabelField(data.get("authors")),
      genre: normalizeLabelField(data.get("genre")),
      publisher: String(data.get("publisher") || "").trim(),
      ...readPlacementFields(data),
      collection: String(data.get("collection") || "").trim(),
      volume: String(data.get("volume") || "").trim(),
      notes: String(data.get("notes") || "").trim(),
      description: String(data.get("description") || "").trim(),
      cover_url: String(data.get("cover_url") || "").trim(),
      favourite: data.get("favourite") === "on",
      ...readOriginFields(data),
    };
    if (yearRaw) payload.publication_year = Number(yearRaw);

    saveBtn.disabled = true;
    reviewStatus.textContent = "Guardando…";
    reviewStatus.classList.remove("error");

    try {
      const res = await fetch("/api/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        reviewStatus.textContent = detailMessage(body.detail) || "No se pudo guardar.";
        reviewStatus.classList.add("error");
        return;
      }
      reviewDialog.close();
      isbnInput.value = "";
      setStatus(`Añadido: ${body.title}${placementDisplay(body) ? ` · ${placementDisplay(body)}` : ""}`);
      clearSearch(false);
      sortKey = "title";
      sortDir = "asc";
      suggestionsLoadedAt = 0;
      await loadBooks();
    } catch {
      reviewStatus.textContent = "Error de red al guardar.";
      reviewStatus.classList.add("error");
    } finally {
      saveBtn.disabled = false;
    }
  });

  reviewDialog.showModal();
  wireFieldSuggestions(reviewBody).then(() => {
    reviewBody.querySelector('input[name="room"]')?.focus();
  });
}

function openManual() {
  pendingIsbn = "";
  const mediaType = defaultMediaTypeForCreate();
  const print = PRINT_TYPES.has(mediaType);
  const typeOptions = Object.entries(MEDIA_LABELS)
    .map(([value, label]) => `<option value="${value}"${value === mediaType ? " selected" : ""}>${label}</option>`)
    .join("");
  const authorsLabel = print ? "Autor(es)" : "Artista / créditos";
  const publisherLabel = print ? "Editorial" : "Sello / estudio";
  reviewBody.innerHTML = `
    <div class="review-layout">
      <div class="detail-cover placeholder" aria-hidden="true">§</div>
      <div>
        <p class="review-kicker">Alta manual</p>
        <h3 class="review-title">${escapeHtml(MEDIA_LABELS[mediaType] || "Ítem")}</h3>
        <p class="authors">Título obligatorio.${print ? " ISBN opcional vía búsqueda en la pantalla principal." : ""}</p>

        <form id="review-form" class="review-form">
          <label class="field">
            <span>Tipo</span>
            <select name="media_type">${typeOptions}</select>
          </label>
          <label class="field">
            <span>Título</span>
            <input name="title" type="text" required autofocus placeholder="Nombre del ítem" />
          </label>
          <label class="field">
            <span>${authorsLabel}</span>
            <input name="authors" type="text" placeholder="${print ? "Apellido, Nombre; Otro autor…" : "Artista, banda, director…"}" />
          </label>
          <label class="field${print ? "" : " hidden"}" ${print ? "" : "hidden"}>
            <span>Depósito legal</span>
            <input name="legal_deposit" type="text" placeholder="B. 7528-1969" ${print ? "" : "disabled"} />
          </label>
          <div class="review-grid">
            <label class="field">
              <span>Año</span>
              <input name="publication_year" type="number" min="1000" max="2100" />
            </label>
            <label class="field">
              <span>${publisherLabel}</span>
              <input name="publisher" type="text" />
            </label>
          </div>
          <label class="field">
            <span>Género(s)</span>
            <input name="genre" type="text" placeholder="Teatro; Revista; Manual…" />
          </label>
          ${placementFieldsHtml()}
          <label class="field">
            <span>Colección</span>
            <input name="collection" type="text" placeholder="Opcional — serie, colección editorial…" />
          </label>
          <label class="field">
            <span>Volumen / nº</span>
            <input name="volume" type="text" placeholder="8, II, tomo 3…" />
          </label>
          <label class="field">
            <span>Notas</span>
            <input name="notes" type="text" placeholder="Estado, préstamo…" />
          </label>
          <label class="field">
            <span>Descripción</span>
            <textarea name="description" rows="3"></textarea>
          </label>
          ${originFieldsHtml()}
          <label class="checkbox-row">
            <input name="favourite" type="checkbox" />
            <span>Marcar como favorito</span>
          </label>

          <div class="detail-actions">
            <button type="submit" class="btn primary" id="save-review-btn">Guardar en inventario</button>
            <button type="button" class="btn ghost" id="cancel-review-btn">Cancelar</button>
          </div>
          <p id="review-status" class="status" role="status"></p>
        </form>
      </div>
    </div>
  `;

  const form = reviewBody.querySelector("#review-form");
  const saveBtn = reviewBody.querySelector("#save-review-btn");
  const reviewStatus = reviewBody.querySelector("#review-status");

  reviewBody.querySelector("#cancel-review-btn")?.addEventListener("click", () => {
    reviewDialog.close();
    setStatus("Alta cancelada.");
  });

  wireCtrlEnterSubmit(form);

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const yearRaw = String(data.get("publication_year") || "").trim();
    const payload = {
      media_type: String(data.get("media_type") || defaultMediaTypeForCreate()).trim(),
      title: String(data.get("title") || "").trim(),
      authors: normalizeLabelField(data.get("authors")),
      legal_deposit: String(data.get("legal_deposit") || "").trim(),
      genre: normalizeLabelField(data.get("genre")),
      publisher: String(data.get("publisher") || "").trim(),
      ...readPlacementFields(data),
      collection: String(data.get("collection") || "").trim(),
      volume: String(data.get("volume") || "").trim(),
      notes: String(data.get("notes") || "").trim(),
      description: String(data.get("description") || "").trim(),
      favourite: data.get("favourite") === "on",
      ...readOriginFields(data),
    };
    if (yearRaw) payload.publication_year = Number(yearRaw);
    if (!PRINT_TYPES.has(payload.media_type)) {
      payload.legal_deposit = "";
      delete payload.translators;
      delete payload.original_title;
      delete payload.original_year;
    }

    saveBtn.disabled = true;
    reviewStatus.textContent = "Guardando…";
    reviewStatus.classList.remove("error");

    try {
      const res = await fetch("/api/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        reviewStatus.textContent = detailMessage(body.detail) || "No se pudo guardar.";
        reviewStatus.classList.add("error");
        return;
      }
      reviewDialog.close();
      setStatus(`Añadido: ${body.title}${placementDisplay(body) ? ` · ${placementDisplay(body)}` : ""}`);
      if (body.media_type && MEDIA_TABS[body.media_type]) {
        setActiveTab(body.media_type);
      } else {
        clearSearch(false);
        sortKey = "title";
        sortDir = "asc";
        suggestionsLoadedAt = 0;
        await loadBooks();
      }
    } catch {
      reviewStatus.textContent = "Error de red al guardar.";
      reviewStatus.classList.add("error");
    } finally {
      saveBtn.disabled = false;
    }
  });

  reviewDialog.showModal();
  wireFieldSuggestions(reviewBody).then(() => {
    reviewBody.querySelector('input[name="title"]')?.focus();
  });
}

function openDetail(book) {
  detailBody.innerHTML = `
    <div class="detail-layout">
      ${coverHtml(book, "detail-cover")}
      <div>
        <form id="detail-form" class="review-form">
          <label class="field">
            <span>Título</span>
            <input name="title" type="text" value="${escapeHtml(book.title || "")}" required />
          </label>
          <label class="field">
            <span>Autor(es)</span>
            <input name="authors" type="text" value="${escapeHtml(book.authors || "")}" placeholder="Apellido, Nombre; Otro autor…" />
          </label>
          <div class="review-grid">
            <label class="field">
              <span>Año (edición)</span>
              <input name="publication_year" type="number" min="1000" max="2100" value="${escapeHtml(book.publication_year ?? "")}" />
            </label>
            <label class="field">
              <span>Editorial</span>
              <input name="publisher" type="text" value="${escapeHtml(book.publisher || "")}" />
            </label>
          </div>
          <dl class="detail-grid detail-grid-2">
            <div>
              <dt>Tipo</dt>
              <dd>${escapeHtml(MEDIA_LABELS[book.media_type] || book.media_type || "book")}</dd>
            </div>
            <div>
              <dt>ISBN</dt>
              <dd>${
                hasRealIsbn(book)
                  ? escapeHtml(book.isbn)
                  : `<span class="no-isbn">Sin ISBN</span>`
              }</dd>
            </div>
            <div><dt>Fuente</dt><dd>${escapeHtml(book.source || "—")}</dd></div>
          </dl>
          <label class="field">
            <span>Depósito legal</span>
            <input name="legal_deposit" type="text" value="${escapeHtml(book.legal_deposit || "")}" placeholder="B. 7528-1969" />
          </label>
          <label class="field">
            <span>Género(s)</span>
            <input name="genre" type="text" value="${escapeHtml(book.genre || "")}" placeholder="Novela; Ensayo…" />
          </label>
          ${placementFieldsHtml(book)}
          <div class="review-grid">
            <label class="field">
              <span>Colección</span>
              <input name="collection" type="text" value="${escapeHtml(book.collection || "")}" placeholder="Grandes genios…" />
            </label>
            <label class="field">
              <span>Volumen / nº</span>
              <input name="volume" type="text" value="${escapeHtml(book.volume || "")}" placeholder="8, II…" />
            </label>
          </div>
          <label class="field">
            <span>Notas</span>
            <textarea name="notes" rows="2">${escapeHtml(book.notes || "")}</textarea>
          </label>
          ${originFieldsHtml(book)}
          <label class="checkbox-row">
            <input name="favourite" type="checkbox" ${book.favourite ? "checked" : ""} />
            <span>Favorito</span>
          </label>
          ${
            book.description
              ? `<p class="detail-description">${escapeHtml(book.description).slice(0, 420)}${book.description.length > 420 ? "…" : ""}</p>`
              : ""
          }
          <div class="detail-actions">
            <button type="submit" class="btn primary compact" title="Ctrl+Enter">Guardar cambios</button>
            <button type="button" class="btn danger compact" data-delete="${escapeHtml(book.id)}">Eliminar</button>
          </div>
          <p id="detail-status" class="status" role="status"></p>
        </form>
      </div>
    </div>
  `;

  const detailStatus = detailBody.querySelector("#detail-status");
  const detailForm = detailBody.querySelector("#detail-form");
  wireCtrlEnterSubmit(detailForm);
  detailForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const title = String(data.get("title") || "").trim();
    if (!title) {
      detailStatus.textContent = "El título no puede quedar vacío.";
      detailStatus.classList.add("error");
      return;
    }
    const yearRaw = String(data.get("publication_year") || "").trim();
    const payload = {
      title,
      authors: normalizeLabelField(data.get("authors")),
      publisher: String(data.get("publisher") || "").trim(),
      publication_year: yearRaw ? Number(yearRaw) : null,
      legal_deposit: String(data.get("legal_deposit") || "").trim(),
      genre: normalizeLabelField(data.get("genre")),
      ...readPlacementFields(data),
      collection: String(data.get("collection") || "").trim(),
      volume: String(data.get("volume") || "").trim(),
      notes: String(data.get("notes") || "").trim(),
      favourite: data.get("favourite") === "on",
      ...readOriginFields(data),
    };
    if (yearRaw && Number.isNaN(payload.publication_year)) {
      detailStatus.textContent = "El año no es válido.";
      detailStatus.classList.add("error");
      return;
    }
    const res = await fetch(`/api/items/${encodeURIComponent(book.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      detailStatus.textContent = "No se pudieron guardar los cambios.";
      detailStatus.classList.add("error");
      return;
    }
    const updated = await res.json();
    const idx = books.findIndex((item) => item.id === book.id);
    if (idx >= 0) books[idx] = updated;
    Object.assign(book, updated);
    suggestionsLoadedAt = 0;
    renderList();
    detailDialog.close();
    setStatus(`Guardado: ${updated.title}`);
  });

  detailBody.querySelector("[data-delete]")?.addEventListener("click", async () => {
    const ok = await deleteBook(book.id, book.title);
    if (ok) detailDialog.close();
  });

  detailDialog.showModal();
  wireFieldSuggestions(detailBody);
}

async function loadBooks() {
  if (activeTab === "overview") {
    await loadOverview();
    return;
  }
  const params = new URLSearchParams({ limit: "500" });
  for (const term of activeSearchTerms()) {
    params.append("q", term);
  }
  const mediaType = currentMediaType();
  if (mediaType) params.set("media_type", mediaType);
  const res = await fetch(`/api/items?${params}`);
  if (!res.ok) {
    setStatus("Error al cargar el inventario.", true);
    return;
  }
  books = await res.json();
  pruneSelection();
  updatePrintColumns();
  renderList();
}

bookTbody.addEventListener("change", (event) => {
  const cb = event.target.closest(".row-select");
  if (!cb) return;
  setRowSelected(cb.getAttribute("data-select-id"), cb.checked);
  updateBatchBar();
});

bookTbody.addEventListener("click", async (event) => {
  const collapseBtn = event.target.closest("[data-collapse-field]");
  if (collapseBtn) {
    toggleGroupCollapsed(
      collapseBtn.getAttribute("data-collapse-field"),
      collapseBtn.getAttribute("data-collapse-key"),
    );
    return;
  }

  const facetBtn = event.target.closest("[data-facet-field]");
  if (facetBtn) {
    toggleFacetFilter(
      facetBtn.getAttribute("data-facet-field"),
      facetBtn.getAttribute("data-facet-key"),
      facetBtn.getAttribute("data-facet-label"),
    );
    return;
  }

  const favBtn = event.target.closest("[data-fav-toggle]");
  if (favBtn) {
    await toggleFavourite(favBtn.getAttribute("data-fav-toggle"));
    return;
  }

  const target = event.target.closest("[data-open], [data-delete]");
  if (!target) return;
  const isbn = target.getAttribute("data-open") || target.getAttribute("data-delete");
  const book = findBook(isbn);
  if (!book) return;
  if (target.hasAttribute("data-delete")) {
    await deleteBook(book.id, book.title);
    return;
  }
  openDetail(book);
});

sortButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const key = btn.dataset.sort;
    if (sortKey === key) {
      sortDir = sortDir === "asc" ? "desc" : "asc";
    } else {
      sortKey = key;
      sortDir = key === "favourite" ? "desc" : "asc";
    }
    saveViewState();
    renderList();
  });
});

groupToggles.forEach((btn) => {
  btn.addEventListener("click", () => {
    toggleGroupBy(btn.dataset.group);
  });
});

viewChips?.addEventListener("click", (event) => {
  if (event.target.closest("[data-clear-view]")) {
    groupByFields = [];
    facetFilters = [];
    collapsedGroups = new Set();
    clearSearch(false);
    saveViewState();
    loadBooks();
    return;
  }
  const clearSearchTerm = event.target.closest("[data-clear-search-term]");
  if (clearSearchTerm) {
    removeSearchTerm(clearSearchTerm.getAttribute("data-clear-search-term"));
    return;
  }
  const clearGroup = event.target.closest("[data-clear-group]");
  if (clearGroup) {
    clearGroupBy(clearGroup.getAttribute("data-clear-group"));
    return;
  }
  const clearFacet = event.target.closest("[data-clear-facet]");
  if (clearFacet) {
    clearFacetFilter(
      clearFacet.getAttribute("data-field"),
      clearFacet.getAttribute("data-key"),
    );
  }
});

lookupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const isbn = isbnInput.value.trim();
  if (!isbn) return;

  lookupBtn.disabled = true;
  setStatus("Consultando catálogos online…");

  try {
    const existingRes = await fetch(`/api/items?${new URLSearchParams({ q: isbn, limit: "50" })}`);
    if (existingRes.ok) {
      const matches = await existingRes.json();
      const book = matches.find((item) => String(item.isbn || "").toUpperCase() === isbn.replace(/[^0-9Xx]/g, "").toUpperCase());
      if (book) {
        setStatus(`Ya está en inventario: ${book.title}`, true);
        openDetail(book);
        return;
      }
    }

    const res = await fetch(`/api/lookup/${encodeURIComponent(isbn)}`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setStatus(detailMessage(data.detail) || "No se encontró ese ISBN.", true);
      return;
    }

    setStatus(`Match: ${data.title}. Revisa y completa antes de guardar.`);
    openReview(isbn.replace(/[^0-9Xx]/g, "").toUpperCase(), data);
  } catch {
    setStatus("Error de red al buscar el ISBN.", true);
  } finally {
    lookupBtn.disabled = false;
  }
});

manualBtn?.addEventListener("click", () => {
  setStatus("Alta manual: rellena título y el resto a mano.");
  openManual();
});

addManualMediaBtn?.addEventListener("click", () => {
  setStatus("Alta manual: rellena título y el resto a mano.");
  openManual();
});

catalogNav?.addEventListener("click", (event) => {
  const tabBtn = event.target.closest("[data-tab]");
  if (!tabBtn) return;
  setActiveTab(tabBtn.getAttribute("data-tab"));
});

overviewPanel?.addEventListener("click", (event) => {
  const typeBtn = event.target.closest("[data-goto-tab]");
  if (typeBtn) {
    setActiveTab(typeBtn.getAttribute("data-goto-tab"));
    return;
  }
  const furnBtn = event.target.closest("[data-goto-furniture]");
  const roomBtn = event.target.closest("[data-goto-room]");
  if (!furnBtn && !roomBtn) return;
  const btn = furnBtn || roomBtn;
  const roomRaw = btn.getAttribute("data-goto-room") ?? "";
  const roomLabel = btn.getAttribute("data-room-label") || roomRaw || "(sin habitación)";
  const filters = [
    {
      field: "room",
      key: groupKey(roomRaw, "room"),
      label: roomLabel,
    },
  ];
  if (furnBtn) {
    const furnRaw = furnBtn.getAttribute("data-goto-furniture") ?? "";
    const furnLabel = furnBtn.getAttribute("data-furniture-label") || furnRaw || "(sin mueble)";
    filters.push({
      field: "furniture",
      key: groupKey(furnRaw, "furniture"),
      label: furnLabel,
    });
  }
  facetFilters = filters;
  saveViewState();
  setActiveTab("all");
});

searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  updateClearSearchVisibility();
  searchTimer = setTimeout(() => {
    loadBooks();
  }, 250);
});

searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    clearTimeout(searchTimer);
    commitSearchTerms(searchInput.value);
  } else if (event.key === "Backspace" && !searchInput.value && searchTerms.length) {
    removeSearchTerm(searchTerms[searchTerms.length - 1]);
  }
});

clearSearchBtn.addEventListener("click", () => {
  clearSearch();
});

async function exportInventory(format) {
  const optionButtons = exportMenu.querySelectorAll(".export-option");
  optionButtons.forEach((btn) => {
    btn.disabled = true;
  });
  try {
    const res = await fetch(`/api/export/items?format=${encodeURIComponent(format)}`);
    if (!res.ok) {
      setStatus("No se pudo exportar el inventario.", true);
      return;
    }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match?.[1] || `alejandrisbn-items.${format}`;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setStatus(`Exportado (${format.toUpperCase()}): ${filename}`);
  } catch {
    setStatus("Error de red al exportar.", true);
  } finally {
    optionButtons.forEach((btn) => {
      btn.disabled = false;
    });
  }
}

exportMenu?.querySelectorAll("[data-export]").forEach((btn) => {
  btn.addEventListener("click", (event) => {
    event.preventDefault();
    exportInventory(btn.getAttribute("data-export"));
  });
});

async function importInventoryFile(file) {
  if (!file) return;
  const optionButtons = importMenu?.querySelectorAll(".export-option") || [];
  optionButtons.forEach((btn) => {
    btn.disabled = true;
  });
  setStatus(`Importando ${file.name}…`);
  try {
    const body = new FormData();
    body.append("file", file, file.name);
    const res = await fetch("/api/import/items", { method: "POST", body });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map((d) => d.msg || d).join("; ")
        : data.detail;
      setStatus(detail || "No se pudo importar el archivo.", true);
      return;
    }
    const fmt = (data.format || "").toUpperCase();
    setStatus(
      `Importado${fmt ? ` (${fmt})` : ""}: ${data.inserted} nuevos, ${data.skipped} ya existían (${data.parsed} en el archivo).`
    );
    await loadBooks();
    if (data.inserted > 0) {
      offerEnrichAfterImport(data.inserted_ids || []);
    }
  } catch {
    setStatus("Error de red al importar.", true);
  } finally {
    optionButtons.forEach((btn) => {
      btn.disabled = false;
    });
    importFile.value = "";
  }
}

importMenu?.querySelectorAll("[data-import]").forEach((btn) => {
  btn.addEventListener("click", (event) => {
    event.preventDefault();
    const format = btn.getAttribute("data-import");
    if (format === "csv") {
      importAccept = ".csv,text/csv";
    } else {
      importAccept = ".json,application/json";
    }
    importFile.accept = importAccept;
    importFile.click();
  });
});

importFile?.addEventListener("change", () => {
  const file = importFile.files?.[0];
  if (file) importInventoryFile(file);
});

const ENRICH_FIELD_LABELS = {
  title: "Título",
  authors: "Autores",
  publication_year: "Año",
  genre: "Género",
  publisher: "Editorial",
  cover_url: "Portada",
  description: "Descripción",
  original_title: "Título original",
  translators: "Traductores",
  original_year: "Año original",
};

function cancelEnrichSearch() {
  if (enrichAbortController) {
    enrichAbortController.abort();
    enrichAbortController = null;
  }
}

function setEnrichProgress({ current, total, label, found, failed }) {
  if (!enrichBody) return;
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  enrichBody.innerHTML = `
    <h3 class="enrich-title">Completar online</h3>
    <p class="enrich-loading" id="enrich-progress-label">
      ${escapeHtml(label || "Preparando…")}
    </p>
    <div class="enrich-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}">
      <div class="enrich-progress-bar" style="width:${pct}%"></div>
    </div>
    <p class="enrich-progress-meta">
      ${total ? `${current} / ${total}` : "…"}
      ${typeof found === "number" ? ` · ${found} con sugerencias` : ""}
      ${typeof failed === "number" && failed > 0 ? ` · ${failed} sin datos` : ""}
    </p>
    <p class="enrich-meta">
      Cerrar este diálogo <strong>detiene</strong> la búsqueda.
    </p>`;
}

function truncateText(value, max = 120) {
  const text = String(value ?? "");
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

function offerEnrichAfterImport(ids) {
  if (!enrichDialog || !enrichBody) return;
  const realIds = (Array.isArray(ids) ? ids : []).filter(Boolean);
  if (!realIds.length) return;

  enrichBody.innerHTML = `
    <h3 class="enrich-title">Importación lista</h3>
    <p class="enrich-meta">
      Se añadieron ${realIds.length} registro(s).
      ¿Buscar online datos faltantes (autor, año, portada…) para los que tengan ISBN
      y revisar sugerencias antes de aplicarlas?
      Solo se proponen valores para <strong>campos vacíos</strong> (no corrige datos ya rellenados).
      ${realIds.length > 20 ? " Puede tardar un rato." : ""}
    </p>
    <div class="enrich-actions">
      <button type="button" class="btn ghost" data-enrich-close>Ahora no</button>
      <button type="button" class="btn primary" id="enrich-start-btn">Buscar online</button>
    </div>`;
  enrichDialog.showModal();
  enrichBody.querySelector("[data-enrich-close]")?.addEventListener("click", () => enrichDialog.close());
  enrichBody.querySelector("#enrich-start-btn")?.addEventListener("click", () => {
    runEnrichPreview(realIds);
  });
}

function renderEnrichResults(suggestions, scanned, failed) {
  const actionable = (suggestions || []).filter((s) => (s.fields || []).length > 0);
  if (!actionable.length) {
    enrichBody.innerHTML = `
      <h3 class="enrich-title">Completar online</h3>
      <p>No hay sugerencias nuevas (revisados ${scanned || 0}; fallos ${failed || 0}).</p>
      <div class="enrich-actions">
        <button type="button" class="btn ghost" data-enrich-close>Cerrar</button>
      </div>`;
    setStatus("Sin sugerencias de enriquecimiento.");
    enrichBody.querySelector("[data-enrich-close]")?.addEventListener("click", () => enrichDialog.close());
    return;
  }

  enrichBody.innerHTML = `
    <h3 class="enrich-title">Completar online</h3>
    <p class="enrich-meta">
      ${actionable.length} libro(s) con campos vacíos sugeridos
      (revisados ${scanned}; fallos ${failed || 0}).
      Solo se rellenan <strong>campos vacíos</strong>; no se corrigen valores ya presentes.
      Desmarca lo que no quieras aplicar.
    </p>
    <div class="enrich-list" id="enrich-list"></div>
    <div class="enrich-actions">
      <button type="button" class="btn ghost" data-enrich-close>Cancelar</button>
      <button type="button" class="btn primary" id="enrich-apply-btn">Aplicar seleccionados</button>
    </div>`;

  const list = enrichBody.querySelector("#enrich-list");
  for (const item of actionable) {
    const card = document.createElement("article");
    card.className = "enrich-card";
    card.dataset.id = item.id || "";
    card.dataset.isbn = item.isbn || "";
    const fieldsHtml = item.fields
      .map((field, idx) => {
        const label = ENRICH_FIELD_LABELS[field.name] || field.name;
        const cur = truncateText(field.current || "—");
        const sug = truncateText(field.suggested);
        return `
          <label class="enrich-field">
            <input type="checkbox" checked data-field="${escapeHtml(field.name)}" data-idx="${idx}" />
            <span class="enrich-field-copy">
              <strong>${escapeHtml(label)}</strong>
              <span class="enrich-from">${escapeHtml(cur)}</span>
              <span class="enrich-arrow">→</span>
              <span class="enrich-to">${escapeHtml(sug)}</span>
            </span>
          </label>`;
      })
      .join("");
    card.innerHTML = `
      <header class="enrich-card-head">
        <div>
          <strong>${escapeHtml(truncateText(item.title || item.isbn, 80))}</strong>
          <div class="enrich-isbn">${escapeHtml(item.isbn)}${item.lookup_source ? ` · ${escapeHtml(item.lookup_source)}` : ""}</div>
        </div>
        <label class="enrich-book-toggle">
          <input type="checkbox" checked data-book-toggle />
          Incluir
        </label>
      </header>
      <div class="enrich-fields">${fieldsHtml}</div>`;
    card._fieldMap = Object.fromEntries(item.fields.map((f) => [f.name, f.suggested]));
    list.appendChild(card);

    const bookToggle = card.querySelector("[data-book-toggle]");
    bookToggle?.addEventListener("change", () => {
      card.querySelectorAll("input[data-field]").forEach((cb) => {
        cb.checked = bookToggle.checked;
        cb.disabled = !bookToggle.checked;
      });
    });
  }

  enrichBody.querySelector("[data-enrich-close]")?.addEventListener("click", () => enrichDialog.close());
  enrichBody.querySelector("#enrich-apply-btn")?.addEventListener("click", () => applyEnrichFromDialog());
  setStatus(`Sugerencias listas: ${actionable.length} libro(s).`);
}

async function runEnrichPreview(ids) {
  if (!enrichDialog || !enrichBody) return;
  if (!Array.isArray(ids) || !ids.length) {
    setStatus("Selecciona al menos un libro/revista con ISBN.", true);
    return;
  }
  const batchEnrichBtn = document.getElementById("batch-enrich");
  batchEnrichBtn && (batchEnrichBtn.disabled = true);
  cancelEnrichSearch();
  enrichAbortController = new AbortController();
  const { signal } = enrichAbortController;
  enrichSearchActive = true;
  setStatus("Consultando catálogos online…");
  enrichDialog.showModal();
  setEnrichProgress({ current: 0, total: 0, label: "Preparando lista…", found: 0, failed: 0 });

  try {
    const items = ids
      .map((id) => {
        const found = findItem(id);
        return {
          id,
          isbn: found?.isbn || "",
          title: found?.title || "",
        };
      })
      .filter((item) => item.id);

    if (!items.length) {
      enrichSearchActive = false;
      renderEnrichResults([], 0, 0);
      return;
    }

    const suggestions = [];
    let failed = 0;
    let found = 0;
    const total = items.length;

    for (let i = 0; i < total; i += 1) {
      if (signal.aborted) break;

      const item = items[i];
      const label = `Consultando catálogos… ${truncateText(item.title || item.isbn || item.id, 48)}`;
      setEnrichProgress({
        current: i,
        total,
        label,
        found,
        failed,
      });
      setStatus(`Completar online: ${i + 1}/${total}`);

      try {
        const res = await fetch("/api/enrich/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ids: [item.id],
            fill_empty_only: true,
          }),
          signal,
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          failed += 1;
          suggestions.push({
            id: item.id,
            isbn: item.isbn,
            title: item.title || "",
            lookup_source: "",
            fields: [],
            error: data.detail || "Error de consulta",
          });
        } else {
          for (const suggestion of data.suggestions || []) {
            suggestions.push(suggestion);
            if (suggestion.error) failed += 1;
            else if ((suggestion.fields || []).length) found += 1;
          }
        }
      } catch (err) {
        if (err?.name === "AbortError" || signal.aborted) break;
        throw err;
      }

      if (signal.aborted) break;

      setEnrichProgress({
        current: i + 1,
        total,
        label: `Listo: ${truncateText(item.title || item.isbn || item.id, 48)}`,
        found,
        failed,
      });
    }

    if (signal.aborted) {
      setStatus("Búsqueda online cancelada.");
      return;
    }

    enrichSearchActive = false;
    renderEnrichResults(suggestions, total, failed);
  } catch {
    if (!signal.aborted) {
      enrichBody.innerHTML = `<p class="status error">Error de red al consultar catálogos.</p>`;
      setStatus("Error de red al completar online.", true);
    }
  } finally {
    enrichSearchActive = false;
    enrichAbortController = null;
    batchEnrichBtn && (batchEnrichBtn.disabled = false);
  }
}

async function applyEnrichFromDialog() {
  const list = enrichBody?.querySelector("#enrich-list");
  if (!list) return;
  const updates = [];
  list.querySelectorAll(".enrich-card").forEach((card) => {
    const id = card.dataset.id;
    const isbn = card.dataset.isbn;
    const bookOn = card.querySelector("[data-book-toggle]")?.checked;
    if (!bookOn || (!id && !isbn)) return;
    const fields = {};
    card.querySelectorAll("input[data-field]:checked").forEach((cb) => {
      const name = cb.getAttribute("data-field");
      if (name && card._fieldMap && name in card._fieldMap) {
        fields[name] = card._fieldMap[name];
      }
    });
    if (Object.keys(fields).length) updates.push({ id, isbn, fields });
  });

  if (!updates.length) {
    setStatus("No hay campos seleccionados.", true);
    return;
  }

  const applyBtn = enrichBody.querySelector("#enrich-apply-btn");
  if (applyBtn) applyBtn.disabled = true;
  setStatus(`Aplicando ${updates.length} actualización(es)…`);

  try {
    const res = await fetch("/api/enrich/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ updates, fill_empty_only: true }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setStatus(data.detail || "No se pudieron aplicar los cambios.", true);
      return;
    }
    enrichDialog.close();
    setStatus(
      `Completado: ${data.updated} libro(s) actualizados` +
        (data.skipped ? `, ${data.skipped} omitidos` : "") +
        (data.errors?.length ? `, ${data.errors.length} error(es)` : "") +
        ".",
    );
    await loadBooks();
  } catch {
    setStatus("Error de red al aplicar enriquecimiento.", true);
  } finally {
    if (applyBtn) applyBtn.disabled = false;
  }
}

enrichClose?.addEventListener("click", () => enrichDialog?.close());

enrichDialog?.addEventListener("close", () => {
  if (enrichSearchActive) {
    cancelEnrichSearch();
    setStatus("Búsqueda online cancelada.");
  }
});

function closeOnBackdrop(dialog) {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}

selectAllVisible?.addEventListener("change", () => {
  selectVisibleRows(Boolean(selectAllVisible.checked));
});

document.getElementById("batch-delete")?.addEventListener("click", () => {
  batchDeleteSelected();
});

document.getElementById("batch-location")?.addEventListener("click", () => {
  openBatchFieldDialog();
});

document.getElementById("batch-enrich")?.addEventListener("click", () => {
  batchEnrichSelected();
});

reviewClose.addEventListener("click", () => reviewDialog.close());
detailClose.addEventListener("click", () => detailDialog.close());
batchClose?.addEventListener("click", () => batchDialog?.close());
closeOnBackdrop(reviewDialog);
closeOnBackdrop(detailDialog);
if (enrichDialog) closeOnBackdrop(enrichDialog);
if (batchDialog) closeOnBackdrop(batchDialog);

const themeToggle = document.getElementById("theme-toggle");
const THEME_KEY = "alejandrisbn-theme";

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function applyTheme(theme) {
  const next = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch {
    /* ignore */
  }
  if (themeToggle) {
    themeToggle.setAttribute(
      "aria-label",
      next === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro",
    );
    themeToggle.title = next === "dark" ? "Modo claro" : "Modo oscuro";
  }
}

themeToggle?.addEventListener("click", () => {
  applyTheme(currentTheme() === "dark" ? "light" : "dark");
});

applyTheme(currentTheme());
loadViewState();
loadActiveTab();
updateGroupToggles();
updateClearSearchVisibility();
setActiveTab(activeTab);
