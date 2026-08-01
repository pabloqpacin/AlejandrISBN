const isbnInput = document.getElementById("isbn-input");
const notesInput = document.getElementById("notes-input");
const addForm = document.getElementById("add-form");
const addBtn = document.getElementById("add-btn");
const formStatus = document.getElementById("form-status");
const searchInput = document.getElementById("search-input");
const bookList = document.getElementById("book-list");
const listMeta = document.getElementById("list-meta");
const emptyState = document.getElementById("empty-state");
const detailDialog = document.getElementById("detail-dialog");
const detailBody = document.getElementById("detail-body");

let books = [];
let searchTimer = null;

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
    return `<img class="${className}" src="${escapeHtml(book.cover_url)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'${className} placeholder',textContent:'§'}))" />`;
  }
  return `<div class="${className} placeholder" aria-hidden="true">§</div>`;
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
        <p class="isbn">${escapeHtml(book.isbn)}</p>
      </div>
      <span class="year-chip">${book.publication_year ?? ""}</span>
    `;
    btn.addEventListener("click", () => openDetail(book));
    li.appendChild(btn);
    bookList.appendChild(li);
  });
}

function openDetail(book) {
  detailBody.innerHTML = `
    <div class="detail-layout">
      ${coverHtml(book, "detail-cover")}
      <div>
        <h3>${escapeHtml(book.title)}</h3>
        <p class="authors">${escapeHtml(book.authors || "Autor desconocido")}</p>
        <dl class="detail-grid">
          <div><dt>ISBN</dt><dd>${escapeHtml(book.isbn)}</dd></div>
          <div><dt>Año</dt><dd>${escapeHtml(book.publication_year ?? "—")}</dd></div>
          <div><dt>Género</dt><dd>${escapeHtml(book.genre || "—")}</dd></div>
          <div><dt>Editorial</dt><dd>${escapeHtml(book.publisher || "—")}</dd></div>
          <div><dt>Fuente</dt><dd>${escapeHtml(book.source || "—")}</dd></div>
          <div><dt>Notas</dt><dd>${escapeHtml(book.notes || "—")}</dd></div>
        </dl>
        ${
          book.description
            ? `<p style="margin:1rem 0 0;font-size:0.92rem;color:var(--ink-soft)">${escapeHtml(book.description).slice(0, 420)}${book.description.length > 420 ? "…" : ""}</p>`
            : ""
        }
        <div class="detail-actions">
          <button type="button" class="btn danger" data-delete="${escapeHtml(book.isbn)}">Eliminar</button>
        </div>
      </div>
    </div>
  `;

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
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  const res = await fetch(`/api/books?${params}`);
  if (!res.ok) {
    setStatus("Error al cargar el inventario.", true);
    return;
  }
  books = await res.json();
  renderList();
}

addForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const isbn = isbnInput.value.trim();
  const notes = notesInput.value.trim();
  if (!isbn) return;

  addBtn.disabled = true;
  setStatus("Consultando catálogos online…");

  try {
    const res = await fetch("/api/books", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ isbn, notes }),
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      setStatus(data.detail || "No se pudo añadir el libro.", true);
      return;
    }

    isbnInput.value = "";
    notesInput.value = "";
    setStatus(`Añadido: ${data.title}`);
    searchInput.value = "";
    await loadBooks();
  } catch {
    setStatus("Error de red al añadir el libro.", true);
  } finally {
    addBtn.disabled = false;
  }
});

searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    loadBooks(searchInput.value.trim());
  }, 250);
});

detailDialog.addEventListener("click", (event) => {
  if (event.target === detailDialog) detailDialog.close();
});

loadBooks();
