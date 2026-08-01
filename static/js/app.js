const isbnInput = document.getElementById("isbn-input");
const lookupForm = document.getElementById("lookup-form");
const lookupBtn = document.getElementById("lookup-btn");
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

const COL_COUNT = 11;

let books = [];
let searchTimer = null;
let pendingIsbn = "";
let sortKey = "title";
let sortDir = "asc";
let groupBy = null;
let suggestions = { authors: [], genre: [], location: [] };
let suggestionsLoadedAt = 0;

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

function visibleBooks() {
  return sortedBooks();
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

function setGroupBy(field) {
  groupBy = groupBy === field ? null : field;
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
    const active = btn.dataset.group === groupBy;
    btn.classList.toggle("is-on", active);
    btn.setAttribute("aria-pressed", active ? "true" : "false");
    const th = btn.closest("th");
    th?.classList.toggle("is-grouped", active);
  });
}

function updateViewChips() {
  if (!viewChips) return;
  if (!groupBy) {
    viewChips.hidden = true;
    viewChips.innerHTML = "";
    return;
  }
  const label = GROUP_LABELS[groupBy] || groupBy;
  viewChips.hidden = false;
  viewChips.innerHTML = `
    <span class="view-chip">
      Agrupado por <strong>${escapeHtml(label)}</strong>
      <button type="button" class="chip-clear" data-clear-group aria-label="Quitar agrupación">×</button>
    </span>
  `;
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
    <td class="col-isbn"><code>${escapeHtml(book.isbn)}</code></td>
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

function appendGroupHeader(label, count) {
  const tr = document.createElement("tr");
  tr.className = "group-row";
  tr.innerHTML = `
    <td colspan="${COL_COUNT}">
      <span class="group-label">${escapeHtml(label)}</span>
      <span class="group-count">${count}</span>
    </td>
  `;
  bookTbody.appendChild(tr);
}

function appendBookRow(book) {
  const tr = document.createElement("tr");
  tr.innerHTML = bookRowHtml(book);
  bookTbody.appendChild(tr);
}

function renderGrouped(rows, field) {
  const groups = new Map();
  rows.forEach((book) => {
    const key = groupLabel(book[field], field);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(book);
  });

  let keys = [...groups.keys()];
  if (field === "favourite") {
    keys = ["Favoritos", "Otros"].filter((key) => groups.has(key));
  } else {
    keys.sort((a, b) => a.localeCompare(b, "es", { sensitivity: "base", numeric: true }));
  }

  keys.forEach((key) => {
    const items = groups.get(key);
    appendGroupHeader(key, items.length);
    items.forEach(appendBookRow);
  });
}

function renderList() {
  const rows = visibleBooks();
  bookTbody.innerHTML = "";
  emptyState.classList.toggle("hidden", rows.length > 0);

  const q = searchInput.value.trim();
  clearSearchBtn.classList.toggle("hidden", !q);

  const sortHint = `orden: ${SORT_LABELS[sortKey]} ${sortDir === "asc" ? "A→Z" : "Z→A"}`;
  listMeta.textContent = q
    ? `${rows.length} resultado${rows.length === 1 ? "" : "s"} para “${q}” · ${sortHint}`
    : `${rows.length} libro${rows.length === 1 ? "" : "s"} · ${sortHint}`;

  updateSortButtons();
  updateGroupToggles();
  updateViewChips();

  if (groupBy && GROUP_LABELS[groupBy]) {
    renderGrouped(rows, groupBy);
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

function openDetail(book) {
  detailBody.innerHTML = `
    <div class="detail-layout">
      ${coverHtml(book, "detail-cover")}
      <div>
        <h3>${escapeHtml(book.title)}</h3>
        <p class="authors">${escapeHtml(book.authors || "Autor desconocido")}</p>
        <form id="detail-form" class="review-form">
          <dl class="detail-grid detail-grid-2">
            <div><dt>ISBN</dt><dd>${escapeHtml(book.isbn)}</dd></div>
            <div><dt>Año</dt><dd>${escapeHtml(book.publication_year ?? "—")}</dd></div>
            <div><dt>Editorial</dt><dd>${escapeHtml(book.publisher || "—")}</dd></div>
            <div><dt>Fuente</dt><dd>${escapeHtml(book.source || "—")}</dd></div>
          </dl>
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
    renderList();
  });
});

groupToggles.forEach((btn) => {
  btn.addEventListener("click", () => {
    setGroupBy(btn.dataset.group);
  });
});

viewChips?.addEventListener("click", (event) => {
  if (event.target.closest("[data-clear-group]")) {
    groupBy = null;
    renderList();
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

loadBooks();
