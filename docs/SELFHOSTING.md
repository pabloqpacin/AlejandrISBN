# Instalar AlejandrISBN en tu PC (Windows)

## La forma más fácil (sin Python ni Docker)

Para tu colega / PCs modestos: un **icono en el Escritorio**.

1. Descarga **`AlejandrISBN-windows.zip`** desde [Releases](https://github.com/pabloqpacin/AlejandrISBN/releases) (o el artefacto del workflow *build-windows*)
2. Extrae la carpeta donde quieras (p. ej. `Documents\AlejandrISBN`)
3. Doble clic en **`AlejandrISBN.exe`**
4. Se abre el navegador en [http://127.0.0.1:8000](http://127.0.0.1:8000)
5. La **primera vez** se crea un acceso directo **AlejandrISBN** en el Escritorio
6. Para salir: **cierra la ventanita** “AlejandrISBN” (no hace falta tocar `.bat`)

**Datos:** `%LOCALAPPDATA%\AlejandrISBN\alejandrisbn.db`  
**Restaurar un JSON:** en el ZIP ya viene la carpeta `seed\` (con `README.txt`). Copia ahí el JSON y vuelve a abrir el `.exe`.

No hace falta instalar Python ni Docker. El `.exe` lleva todo embebido (~4 GB RAM del PC bastan).

---

## Otras formas

| Modo | Para quién | Arranque |
|------|------------|----------|
| **ZIP + `.exe`** | Uso diario, no técnicos | `AlejandrISBN.exe` / icono Escritorio |
| **Python + SQLite** | Desarrollo sin compilar | `start-desktop.bat` |
| **Docker (Postgres)** | ≥8 GB RAM, contenedores | `start.bat` |

Tus libros se quedan en tu PC. No se suben a ningún servidor externo (salvo consultas opcionales a Open Library / Google Books al buscar un ISBN).

---

## Modo desarrollo — Python + SQLite (sin compilar el .exe)

**No hace falta Docker.** Hace falta Python 3.11+.

### Requisitos

| Requisito | Notas |
|-----------|--------|
| Windows 10 u 11 (64 bits) | — |
| **Python 3.11+** | [python.org/downloads](https://www.python.org/downloads/) — marca *Add python.exe to PATH* |
| ~4 GB de RAM | Suficiente para este modo |
| Navegador | Brave, Edge, Chrome… |
| Internet | Solo para instalar y buscar ISBN |

### Pasos

1. Consigue la carpeta del proyecto (`git clone` o ZIP de GitHub) en una ruta normal, p. ej. `Documents\AlejandrISBN`
2. Doble clic en **`start-desktop.bat`**
3. La primera vez crea `.venv`, instala dependencias y arranca la app (puede tardar unos minutos)
4. Se abre [http://127.0.0.1:8000](http://127.0.0.1:8000) — **deja la ventana negra abierta** mientras uses la app
5. Para parar: Ctrl+C en esa ventana, o `stop-desktop.bat`

**Datos:** `%LOCALAPPDATA%\AlejandrISBN\alejandrisbn.db`  
**Restaurar un JSON de backup:** copia el archivo a la carpeta `seed\` del proyecto y reinicia.

Para probar la ventanita de control sin PyInstaller:

```powershell
.venv\Scripts\python.exe -m app.desktop_app
```

---

## Modo Docker (Postgres) — PCs con más recursos

### Qué vas a instalar

1. **Brave** (recomendado) — navegador  
2. **Docker Desktop** — app + Postgres en contenedores (~8 GB RAM de sistema)  
3. **Git** — clonar / actualizar el repo  
4. **AlejandrISBN** — `start.bat`

### Requisitos

| Requisito | Notas |
|-----------|--------|
| Windows 10 u 11 (64 bits) | Actualizado (incluye `winget`) |
| Cuenta de administrador | Para instalar Docker, Git y Brave |
| **8 GB RAM** (mínimo Docker) | 16 GB recomendado |
| ~15 GB libres en disco | Imágenes + volumen |
| Virtualización en BIOS | VT-x / AMD-V |
| Conexión a Internet | Primera instalación y búsquedas ISBN |

### Opción rápida — PC nuevo (script Docker)

> Estos scripts (`setup-windows.bat` / `.ps1`) **solo funcionan en Windows**. No se pueden ejecutar desde Linux ni desde una terminal WSL sobre la carpeta del repo.

Si ya tienes la carpeta del proyecto (ZIP o USB):

1. Copia/extrae a p. ej. `C:\Users\TU_USUARIO\Documents\AlejandrISBN` (evita `\\wsl$\...`)
2. Doble clic en `setup-windows.bat` → acepta UAC
3. Instala Brave, Git y Docker Desktop; reinicia si Docker lo pide
4. Abre Docker Desktop y espera a que esté en marcha
5. Doble clic en `start.bat`

**Si el `.bat` no hace nada:** clic derecho → *Ejecutar como administrador*. Si Windows bloquea el archivo: *Propiedades* → *Desbloquear*.

**Plan B** (PowerShell como administrador):

```powershell
winget install -e --id Brave.Brave --accept-package-agreements --accept-source-agreements
winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements
winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
```

### Paso 1 — Instalar Docker Desktop (manual)

1. Entra en [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
2. Descarga **Docker Desktop for Windows**
3. Instálalo con las opciones por defecto  
   - Si pide activar **WSL 2**, acepta y reinicia si hace falta
4. Abre **Docker Desktop** y espera a que diga que está en marcha (icono de ballena en la bandeja del sistema)
5. La primera vez puede pedir un reinicio del PC

**Comprobación:** abre PowerShell y escribe:

```powershell
docker version
docker compose version
```

Si ves números de versión (sin error rojo), Docker está listo.

### Paso 2 — Instalar Git (manual)

1. Entra en [https://git-scm.com/download/win](https://git-scm.com/download/win)
2. Instala con las opciones por defecto
3. Cierra y vuelve a abrir PowerShell después de instalar

**Comprobación:**

```powershell
git --version
```

### Paso 3 — Clonar el repositorio

Elige una carpeta fácil de encontrar, por ejemplo `Documentos`:

```powershell
cd $env:USERPROFILE\Documents
git clone https://github.com/pabloqpacin/AlejandrISBN.git
cd AlejandrISBN
```

Si prefieres no usar Git: en GitHub pulsa **Code → Download ZIP**, descomprímelo y entra en esa carpeta con el Explorador.

---

## Paso 4 — Arrancar con Docker (opción fácil)

En el Explorador de archivos, entra en la carpeta `AlejandrISBN` y haz **doble clic** en:

| Archivo | Qué hace |
|---------|----------|
| `start-desktop.bat` | **Sin Docker:** SQLite + Python (recomendado en PCs modestos) |
| `stop-desktop.bat` | Intenta liberar el puerto 8000 del modo escritorio |
| `setup-windows.bat` | (PC nuevo) Instala Brave, Git y Docker Desktop via `winget` |
| `start.bat` | Docker: crea `.env` si no existe, construye e inicia el stack, abre el navegador |
| `stop.bat` | Docker: para la aplicación (los libros **no** se borran) |
| `update.bat` | Docker: descarga cambios del repo y vuelve a levantar el stack |

La **primera** vez `start.bat` / `start-desktop.bat` puede tardar varios minutos. Las siguientes serán más rápidas.

Cuando termine, abre: [http://localhost:8000](http://localhost:8000)

---

## Paso 4 (alternativa) — Arrancar con PowerShell

Desde la carpeta del proyecto:

```powershell
copy .env.example .env
docker compose up --build -d
```

Abre [http://localhost:8000](http://localhost:8000)

Para detener:

```powershell
docker compose down
```

---

## Uso diario

1. Abre **Docker Desktop** (debe estar en marcha)
2. Ejecuta `start.bat` (o `docker compose up -d` si ya construiste antes)
3. Entra en [http://localhost:8000](http://localhost:8000)

Para parar sin perder datos: `stop.bat` o `docker compose down`.

---

## Datos, contraseñas y copias de seguridad

- Los datos viven en el volumen Docker `alejandrisbn_pgdata`.  
  `stop.bat` / `docker compose down` **no** los borra.
- **No uses** `docker compose down -v` salvo que quieras **borrar toda la biblioteca**.
- Opcional: edita el archivo `.env` y cambia `POSTGRES_PASSWORD` **antes del primer arranque**. Si ya arrancaste una vez, cambiar solo la contraseña en `.env` no actualiza la base ya creada.

Clave opcional de Google Books (mejor cobertura de ISBN):

```env
GOOGLE_BOOKS_API_KEY=tu_clave_aqui
```

### Guardar una copia (exportar)

1. Con la app en marcha, abre [http://localhost:8000](http://localhost:8000)
2. Usa la opción de **exportar** el inventario (JSON o CSV) y guarda el archivo en un sitio seguro (Documentos, USB, nube…)

El JSON es el formato ideal para **restaurar** después (cambio de PC, reinstalar Docker, etc.).

### Restaurar desde un JSON

La app lee automáticamente los archivos de la carpeta `seed/` al arrancar.

1. Copia tu archivo exportado a la carpeta `seed` del proyecto, por ejemplo:

   ```text
   Documentos\AlejandrISBN\seed\mi-biblioteca.json
   ```

   (Cualquier nombre vale mientras termine en `.json`. No uses nombres que acaben en `.example.json`.)

2. Reinicia solo la app para que cargue el archivo:

   - Doble clic en `stop.bat`, luego en `start.bat`  
   - O en PowerShell, desde la carpeta del proyecto:

     ```powershell
     docker compose restart alejandrisbn
     ```

3. Abre de nuevo [http://localhost:8000](http://localhost:8000) y comprueba que aparecen los libros.

**Comportamiento:** el JSON **añade** libros que faltan; no pisa los que ya existen con el mismo ISBN (o el mismo id local). Si el mismo archivo ya se aplicó sin cambios, no se vuelve a importar; si editas el JSON o le cambias el nombre, sí se vuelve a procesar.

**PC nuevo / base vacía:** clona el repo, pon el JSON en `seed/` **antes** (o justo después) del primer `start.bat`, y al arrancar se importará solo.

**Empezar de cero y cargar solo el JSON:** eso borra la base actual. Solo si lo tienes claro:

```powershell
docker compose down -v
```

Luego deja el JSON en `seed\` y ejecuta `start.bat`.

---

## Actualizar a una versión nueva

Con Git y el script:

```text
update.bat
```

O a mano:

```powershell
cd $env:USERPROFILE\Documents\AlejandrISBN
git pull
docker compose up --build -d
```

---

## Problemas frecuentes

| Síntoma | Qué probar |
|---------|------------|
| `docker` no se reconoce | Abre Docker Desktop; cierra y abre PowerShell; reinicia el PC |
| El puerto 8000 está ocupado | Cierra la otra app que lo use, o en `docker-compose.yml` cambia `"8000:8000"` por `"8001:8000"` y usa http://localhost:8001 |
| La página no carga | Espera 30–60 s tras el primer arranque; en Docker Desktop comprueba que `alejandrisbn` y `alejandrisbn-db` estén *Running* |
| WSL / virtualización | En BIOS activa virtualización; en Windows activa “Plataforma de máquina virtual” / WSL |
| Antivirus bloquea Docker | Añade excepción para Docker Desktop |

Logs (si alguien te ayuda a depurar):

```powershell
docker compose logs -f
```

---

## Qué incluye el stack

| Contenedor | Rol |
|------------|-----|
| `alejandrisbn-db` | PostgreSQL 16 (datos) |
| `alejandrisbn` | API FastAPI + interfaz web estática (mismo proceso) |

No hace falta instalar Python ni Postgres a mano.

---

## Licencia y código

Proyecto open source (ver `LICENSE` en la raíz del repo).  
Código: [https://github.com/pabloqpacin/AlejandrISBN](https://github.com/pabloqpacin/AlejandrISBN)
