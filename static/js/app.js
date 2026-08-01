const isbnInput = document.getElementById("isbn-input");
const lookupForm = document.getElementById("lookup-form");
const lookupBtn = document.getElementById("lookup-btn");
const formStatus = document.getElementById("form-status");
const searchInput = document.getElementById("search-input");
const bookList = document.getElementById("book-list");
const listMeta = document.getElementById("list-meta");
const emptyState = document.getElementById("empty-state");

const reviewDialog = document.getElementById("review-dialog");
const reviewBody = document.getElementById("review-body");
const reviewClose = document.getElementById("review-close");

const detailDialog = document.getElementById("detail-dialog");
const detailBody = document.getElementById("detail-body");
const detailClose = document.getElementById("detail-close");

let books = [];
let searchTimer = null;
let pendingIsbn = "";

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

function detailMessage(text, isError = false) {
  return Array.isArray(text)
    ? text.map((item) => item.msg || item).join(", ")
    : text || (isError ? "Error" : "");
}

function renderList() {
  bookList.innerHTML = "";
  emptyState.classList.toggle("hidden", books.length > 0);

  const q = searchInput.value.trim();
  listMeta.textContent = q
    ? `${books.length} resultado${books.length === 1 ? "" : "s"} para “${q}”`
    : `${books.length} libro${books.length === 1 ? "" : "s"} en inventario`;

  books.forEach((book, index) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "book-row";
    btn.style.animationDelay = `${Math.min(index * 0.04, 0.4)}s`;
    btn.innerHTML = `
      ${coverHtml(book)}
      <div class="meta">
        <h3>${escapeHtml(book.title)}</h3>
        <p>${escapeHtml(book.authors || "Autor desconocido")}</p>
        <p class="isbn">${escapeHtml(book.isbn)}${book.location ? ` · ${escapeHtml(book.location)}` : ""}</p>
      </div>
      <span class="year-chip">${book.publication_year ?? ""}</span>
    `;
    btn.addEventListener("click", () => openDetail(book));
    li.appendChild(btn);
    bookList.appendChild(li);
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
        reviewStatus.textContent = detailMessage(body.detail, true) || "No se pudo guardar.";
        reviewStatus.classList.add("error");
        return;
      }
      reviewDialog.close();
      isbnInput.value = "";
      setStatus(`Añadido: ${body.title}${body.location ? ` · ${body.location}` : ""}`);
      searchInput.value = "";
      await loadBooks();
    } catch {
      reviewStatus.textContent = "Error de red al guardar.";
      reviewStatus.classList.add("error");
    } finally {
      saveBtn.disabled = false;
    }
  });

  reviewDialog.showModal();
  reviewBody.querySelector('input[name="location"]')?.focus();
}

function openDetail(book) {
  detailBody.innerHTML = `
    <div class="detail-layout">
      ${coverHtml(book, "detail-cover")}
      <div>
        <h3>${escapeHtml(book.title)}</h3>
        <p class="authors">${escapeHtml(book.authors || "Autor desconocido")}</p>
        <form id="detail-form" class="review-form">
          <dl class="detail-grid">
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
    renderList();
  });

  detailBody.querySelector("[data-delete]")?.addEventListener("click", async (event) => {
    const isbn = event.currentTarget.getAttribute("data-delete");
    if (!isbn || !confirm(`¿Eliminar ${book.title} del inventario?`)) return;
    const res = await fetch(`/api/books/${encodeURIComponent(isbn)}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) {
      setStatus("No se pudo eliminar el libro.", true);
      return;
    }
    detailDialog.close();
    await loadBooks(searchInput.value.trim());
    setStatus("Libro eliminado.");
  });

  detailDialog.showModal();
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
      setStatus(detailMessage(data.detail, true) || "No se encontró ese ISBN.", true);
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
  searchTimer = setTimeout(() => {
    loadBooks(searchInput.value.trim());
  }, 250);
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
