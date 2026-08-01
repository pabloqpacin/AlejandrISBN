const isbnInput = document.getElementById("isbn-input");
const lookupForm = document.getElementById("lookup-form");
const lookupBtn = document.getElementById("lookup-btn");
const manualBtn = document.getElementById("manual-btn");
const formStatus = document.getElementById("form-status");
const searchInput = document.getElementById("search-input");
const clearSearchBtn = document.getElementById("clear-search");
const viewChips = document.getElementById("view-chips");
const exportMenu = document.querySelector(".export-menu");
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
  location: "ubicación",
  publisher: "editorial",
  notes: "notas",
};

const GROUP_LABELS = {
  favourite: "favorito",
  authors: "autor",
  genre: "género",
  location: "ubicación",
  publisher: "editorial",
};

const COL_COUNT = 12;

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
let suggestions = { authors: [], genre: [], location: [] };
let suggestionsLoadedAt = 0;

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
      JSON.stringify({ groupByFields, facetFilters, sortKey, sortDir }),
    );
  } catch {
    /* ignore quota / private mode */
  }
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

function truncate(text, max = 36) {
  const value = String(text || "").trim();
  if (!value) return "—";
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function isLocalId(isbn) {
  return /^LOCAL-[A-Z0-9]{8,32}$/i.test(String(isbn || "").trim());
}

function isbnCellHtml(book) {
  if (isLocalId(book.isbn)) {
    return `<span class="no-isbn" title="${escapeHtml(book.isbn)}">—</span>`;
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
    const result = compareValues(left[sortKey], right[sortKey]);
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

function bookMatchesFacets(book) {
  return facetFilters.every((facet) => groupKey(book[facet.field], facet.field) === facet.key);
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
  if (!hasGroups && !hasFacets) {
    viewChips.hidden = true;
    viewChips.innerHTML = "";
    return;
  }

  const groupChips = groupByFields
    .map((field, index) => {
      const label = GROUP_LABELS[field] || field;
      const order = groupByFields.length > 1 ? ` <span class="chip-ord">${index + 1}</span>` : "";
      return `
        <span class="view-chip view-chip-group">
          Agrupar${order} <strong>${escapeHtml(label)}</strong>
          <button type="button" class="chip-clear" data-clear-group="${escapeHtml(field)}" aria-label="Quitar agrupación por ${escapeHtml(label)}">×</button>
        </span>
      `;
    })
    .join("");

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

  const clearAll =
    hasGroups || hasFacets
      ? `<button type="button" class="view-chip view-chip-clear-all" data-clear-view>Limpiar vista</button>`
      : "";

  viewChips.hidden = false;
  viewChips.innerHTML = `${groupChips}${facetChips}${clearAll}`;
}

function findBook(isbn) {
  return books.find((book) => book.isbn === isbn);
}

function bookRowHtml(book) {
  const fav = Boolean(book.favourite);
  return `
    <td class="col-fav">
      <button
        type="button"
        class="fav-btn${fav ? " is-on" : ""}"
        data-fav-toggle="${escapeHtml(book.isbn)}"
        title="${fav ? "Quitar de favoritos" : "Marcar favorito"}"
        aria-pressed="${fav ? "true" : "false"}"
        aria-label="${fav ? "Quitar de favoritos" : "Marcar favorito"}"
      >★</button>
    </td>
    <td class="col-cover">${coverHtml(book, "cover thumb")}</td>
    <td class="col-title">
      <button type="button" class="linkish" data-open="${escapeHtml(book.isbn)}">
        ${escapeHtml(book.title)}
      </button>
    </td>
    <td title="${escapeHtml(book.authors || "")}">${escapeHtml(truncate(book.authors || "—", 28))}</td>
    <td class="col-year">${escapeHtml(book.publication_year ?? "—")}</td>
    <td class="col-isbn">${isbnCellHtml(book)}</td>
    <td class="col-dl">${legalDepositCellHtml(book)}</td>
    <td title="${escapeHtml(book.genre || "")}">${escapeHtml(truncate(book.genre, 28))}</td>
    <td class="col-location">${escapeHtml(book.location || "—")}</td>
    <td title="${escapeHtml(book.publisher || "")}">${escapeHtml(truncate(book.publisher, 22))}</td>
    <td title="${escapeHtml(book.notes || "")}">${escapeHtml(truncate(book.notes, 24))}</td>
    <td class="col-actions">
      <button type="button" class="btn ghost compact" data-open="${escapeHtml(book.isbn)}">Ver</button>
      <button type="button" class="btn danger compact" data-delete="${escapeHtml(book.isbn)}" title="Eliminar">✕</button>
    </td>
  `;
}

function appendGroupHeader({ field, key, label, count, depth, filtered }) {
  const tr = document.createElement("tr");
  tr.className = `group-row depth-${Math.min(depth, 4)}${filtered ? " is-filtered" : ""}`;
  tr.innerHTML = `
    <td colspan="${COL_COUNT}">
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
    const key = groupKey(book[field], field);
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        label: groupLabel(book[field], field),
        items: [],
      });
    }
    groups.get(key).items.push(book);
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
    appendGroupHeader({
      field,
      key: group.key,
      label: group.label,
      count: group.items.length,
      depth,
      filtered,
    });
    renderGrouped(group.items, rest, depth + 1);
  });
}

function renderList() {
  const rows = visibleBooks();
  bookTbody.innerHTML = "";
  emptyState.classList.toggle("hidden", rows.length > 0);

  const q = searchInput.value.trim();
  clearSearchBtn.classList.toggle("hidden", !q);

  const sortHint = `orden: ${SORT_LABELS[sortKey]} ${sortDir === "asc" ? "A→Z" : "Z→A"}`;
  const filterHint = facetFilters.length
    ? ` · ${facetFilters.length} filtro${facetFilters.length === 1 ? "" : "s"}`
    : "";
  const groupHint = groupByFields.length
    ? ` · agrupado: ${groupByFields.map((field) => GROUP_LABELS[field] || field).join(" → ")}`
    : "";
  listMeta.textContent = q
    ? `${rows.length} resultado${rows.length === 1 ? "" : "s"} para “${q}” · ${sortHint}${filterHint}${groupHint}`
    : `${rows.length} libro${rows.length === 1 ? "" : "s"} · ${sortHint}${filterHint}${groupHint}`;

  updateSortButtons();
  updateGroupToggles();
  updateViewChips();

  const activeGroups = groupByFields.filter((field) => GROUP_LABELS[field]);
  if (activeGroups.length) {
    renderGrouped(rows, activeGroups);
    return;
  }

  rows.forEach(appendBookRow);
}

async function toggleFavourite(isbn) {
  const book = findBook(isbn);
  if (!book) return;
  const next = !book.favourite;
  const res = await fetch(`/api/books/${encodeURIComponent(isbn)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ favourite: next }),
  });
  if (!res.ok) {
    setStatus("No se pudo actualizar el favorito.", true);
    return;
  }
  const updated = await res.json();
  const idx = books.findIndex((item) => item.isbn === isbn);
  if (idx >= 0) books[idx] = updated;
  renderList();
}

async function deleteBook(isbn, title) {
  if (!confirm(`¿Eliminar “${title}” del inventario?`)) return false;
  const res = await fetch(`/api/books/${encodeURIComponent(isbn)}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    setStatus("No se pudo eliminar el libro.", true);
    return false;
  }
  setStatus("Libro eliminado.");
  suggestionsLoadedAt = 0;
  await loadBooks(searchInput.value.trim());
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

function filterSuggestions(items, query) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return items.slice(0, 12);
  return items
    .filter((item) => item.value.toLowerCase().includes(q))
    .slice(0, 12);
}

function attachSuggest(input, items, { showCount = false } = {}) {
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

  function render() {
    visible = filterSuggestions(items, input.value);
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
    input.value = item.value;
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
  });
  attachSuggest(root.querySelector('input[name="genre"]'), data.genre || [], {
    showCount: true,
  });
  attachSuggest(root.querySelector('input[name="location"]'), data.location || [], {
    showCount: true,
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
            <input name="authors" type="text" value="${escapeHtml(meta.authors || "")}" />
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
            <span>Género</span>
            <input name="genre" type="text" value="${escapeHtml(meta.genre || "")}" placeholder="Novela, ensayo, poesía…" />
          </label>
          <label class="field">
            <span>Ubicación</span>
            <input name="location" type="text" placeholder="A1, B2, Estantería norte…" autofocus />
          </label>
          <label class="field">
            <span>Notas</span>
            <input name="notes" type="text" placeholder="Donación, estado, préstamo…" />
          </label>
          <label class="field">
            <span>Descripción</span>
            <textarea name="description" rows="3">${escapeHtml(meta.description || "")}</textarea>
          </label>
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

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const yearRaw = String(data.get("publication_year") || "").trim();
    const payload = {
      isbn: pendingIsbn,
      title: String(data.get("title") || "").trim(),
      authors: String(data.get("authors") || "").trim(),
      genre: String(data.get("genre") || "").trim(),
      publisher: String(data.get("publisher") || "").trim(),
      location: String(data.get("location") || "").trim(),
      notes: String(data.get("notes") || "").trim(),
      description: String(data.get("description") || "").trim(),
      cover_url: String(data.get("cover_url") || "").trim(),
      favourite: data.get("favourite") === "on",
    };
    if (yearRaw) payload.publication_year = Number(yearRaw);

    saveBtn.disabled = true;
    reviewStatus.textContent = "Guardando…";
    reviewStatus.classList.remove("error");

    try {
      const res = await fetch("/api/books", {
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
      setStatus(`Añadido: ${body.title}${body.location ? ` · ${body.location}` : ""}`);
      searchInput.value = "";
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
    reviewBody.querySelector('input[name="location"]')?.focus();
  });
}

function openManual() {
  pendingIsbn = "";
  reviewBody.innerHTML = `
    <div class="review-layout">
      <div class="detail-cover placeholder" aria-hidden="true">§</div>
      <div>
        <p class="review-kicker">Alta manual · sin ISBN</p>
        <h3 class="review-title">Libro, revista, manual o documento</h3>
        <p class="authors">Ideal para ediciones con depósito legal u obras sin ISBN. Título obligatorio.</p>

        <form id="review-form" class="review-form">
          <label class="field">
            <span>Título</span>
            <input name="title" type="text" required autofocus placeholder="Nombre del ítem" />
          </label>
          <label class="field">
            <span>Autor(es)</span>
            <input name="authors" type="text" placeholder="Apellido, Nombre…" />
          </label>
          <label class="field">
            <span>Depósito legal</span>
            <input name="legal_deposit" type="text" placeholder="B. 7528-1969" />
          </label>
          <div class="review-grid">
            <label class="field">
              <span>Año</span>
              <input name="publication_year" type="number" min="1000" max="2100" />
            </label>
            <label class="field">
              <span>Editorial</span>
              <input name="publisher" type="text" />
            </label>
          </div>
          <label class="field">
            <span>Género / tipo</span>
            <input name="genre" type="text" placeholder="Teatro, revista, manual…" />
          </label>
          <label class="field">
            <span>Ubicación</span>
            <input name="location" type="text" placeholder="A1, B2, Estantería norte…" />
          </label>
          <label class="field">
            <span>Notas</span>
            <input name="notes" type="text" placeholder="Volumen, estado, préstamo…" />
          </label>
          <label class="field">
            <span>Descripción</span>
            <textarea name="description" rows="3"></textarea>
          </label>
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

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const yearRaw = String(data.get("publication_year") || "").trim();
    const payload = {
      title: String(data.get("title") || "").trim(),
      authors: String(data.get("authors") || "").trim(),
      legal_deposit: String(data.get("legal_deposit") || "").trim(),
      genre: String(data.get("genre") || "").trim(),
      publisher: String(data.get("publisher") || "").trim(),
      location: String(data.get("location") || "").trim(),
      notes: String(data.get("notes") || "").trim(),
      description: String(data.get("description") || "").trim(),
      favourite: data.get("favourite") === "on",
    };
    if (yearRaw) payload.publication_year = Number(yearRaw);

    saveBtn.disabled = true;
    reviewStatus.textContent = "Guardando…";
    reviewStatus.classList.remove("error");

    try {
      const res = await fetch("/api/books", {
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
      setStatus(`Añadido: ${body.title}${body.location ? ` · ${body.location}` : ""}`);
      searchInput.value = "";
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
    reviewBody.querySelector('input[name="title"]')?.focus();
  });
}

function openDetail(book) {
  detailBody.innerHTML = `
    <div class="detail-layout">
      ${coverHtml(book, "detail-cover")}
      <div>
        <h3>${escapeHtml(book.title)}</h3>
        <p class="authors">${escapeHtml(book.authors || "Autor desconocido")}</p>
        <form id="detail-form" class="review-form">
          <dl class="detail-grid detail-grid-2">
            <div>
              <dt>ISBN</dt>
              <dd>${
                isLocalId(book.isbn)
                  ? `<span class="no-isbn" title="${escapeHtml(book.isbn)}">Sin ISBN</span>`
                  : escapeHtml(book.isbn)
              }</dd>
            </div>
            <div><dt>Año</dt><dd>${escapeHtml(book.publication_year ?? "—")}</dd></div>
            <div><dt>Editorial</dt><dd>${escapeHtml(book.publisher || "—")}</dd></div>
            <div><dt>Fuente</dt><dd>${escapeHtml(book.source || "—")}</dd></div>
          </dl>
          <label class="field">
            <span>Depósito legal</span>
            <input name="legal_deposit" type="text" value="${escapeHtml(book.legal_deposit || "")}" placeholder="B. 7528-1969" />
          </label>
          <label class="field">
            <span>Género</span>
            <input name="genre" type="text" value="${escapeHtml(book.genre || "")}" />
          </label>
          <label class="field">
            <span>Ubicación</span>
            <input name="location" type="text" value="${escapeHtml(book.location || "")}" placeholder="A1, B2…" />
          </label>
          <label class="field">
            <span>Notas</span>
            <textarea name="notes" rows="2">${escapeHtml(book.notes || "")}</textarea>
          </label>
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
            <button type="submit" class="btn primary compact">Guardar cambios</button>
            <button type="button" class="btn danger compact" data-delete="${escapeHtml(book.isbn)}">Eliminar</button>
          </div>
          <p id="detail-status" class="status" role="status"></p>
        </form>
      </div>
    </div>
  `;

  const detailStatus = detailBody.querySelector("#detail-status");
  detailBody.querySelector("#detail-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload = {
      legal_deposit: String(data.get("legal_deposit") || "").trim(),
      genre: String(data.get("genre") || "").trim(),
      location: String(data.get("location") || "").trim(),
      notes: String(data.get("notes") || "").trim(),
      favourite: data.get("favourite") === "on",
    };
    const res = await fetch(`/api/books/${encodeURIComponent(book.isbn)}`, {
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
    const idx = books.findIndex((item) => item.isbn === book.isbn);
    if (idx >= 0) books[idx] = updated;
    detailStatus.textContent = "Cambios guardados.";
    detailStatus.classList.remove("error");
    suggestionsLoadedAt = 0;
    renderList();
  });

  detailBody.querySelector("[data-delete]")?.addEventListener("click", async () => {
    const ok = await deleteBook(book.isbn, book.title);
    if (ok) detailDialog.close();
  });

  detailDialog.showModal();
  wireFieldSuggestions(detailBody);
}

async function loadBooks(q = "") {
  const params = new URLSearchParams({ limit: "200" });
  if (q) params.set("q", q);
  const res = await fetch(`/api/books?${params}`);
  if (!res.ok) {
    setStatus("Error al cargar el inventario.", true);
    return;
  }
  books = await res.json();
  renderList();
}

bookTbody.addEventListener("click", async (event) => {
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
    await deleteBook(book.isbn, book.title);
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
    saveViewState();
    renderList();
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
    const existing = await fetch(`/api/books/${encodeURIComponent(isbn)}`);
    if (existing.ok) {
      const book = await existing.json();
      setStatus(`Ya está en inventario: ${book.title}`, true);
      openDetail(book);
      return;
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

searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  clearSearchBtn.classList.toggle("hidden", !searchInput.value.trim());
  searchTimer = setTimeout(() => {
    loadBooks(searchInput.value.trim());
  }, 250);
});

clearSearchBtn.addEventListener("click", () => {
  searchInput.value = "";
  clearSearchBtn.classList.add("hidden");
  loadBooks();
});

async function exportInventory(format) {
  const optionButtons = exportMenu.querySelectorAll(".export-option");
  optionButtons.forEach((btn) => {
    btn.disabled = true;
  });
  try {
    const res = await fetch(`/api/export/books?format=${encodeURIComponent(format)}`);
    if (!res.ok) {
      setStatus("No se pudo exportar el inventario.", true);
      return;
    }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match?.[1] || `alejandrisbn-books.${format}`;
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

function closeOnBackdrop(dialog) {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}

reviewClose.addEventListener("click", () => reviewDialog.close());
detailClose.addEventListener("click", () => detailDialog.close());
closeOnBackdrop(reviewDialog);
closeOnBackdrop(detailDialog);

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
loadBooks();
