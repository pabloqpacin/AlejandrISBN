# Instalar AlejandrISBN

Hay dos caminos principales:

1. **Windows — instalador** (`AlejandrISBN-Setup.exe`): uso diario sin Docker ni Python. Incluye *Buscar actualizaciones* en la ventanita de la app.
2. **Git + Docker** (Windows, macOS o Linux): clonas el repo y levantas el stack; mismo flujo en los tres sistemas.

- [Instalar AlejandrISBN](#instalar-alejandrisbn)
  - [La forma más fácil (instalador)](#la-forma-más-fácil-instalador)
  - [Otras formas](#otras-formas)
  - [Modo desarrollo — Python + SQLite (sin compilar el .exe)](#modo-desarrollo--python--sqlite-sin-compilar-el-exe)
    - [Requisitos](#requisitos)
    - [Pasos](#pasos)
  - [Modo Docker (Postgres) — Windows, macOS y Linux](#modo-docker-postgres--windows-macos-y-linux)
    - [Qué vas a instalar](#qué-vas-a-instalar)
    - [Requisitos](#requisitos-1)
    - [Opción rápida — PC nuevo (script de prerequisitos)](#opción-rápida--pc-nuevo-script-de-prerequisitos)
    - [Paso 1 — Instalar Docker Desktop (manual)](#paso-1--instalar-docker-desktop-manual)
    - [Paso 2 — Instalar Git (manual)](#paso-2--instalar-git-manual)
    - [Paso 3 — Clonar el repositorio](#paso-3--clonar-el-repositorio)
    - [Paso 4 — Arrancar con Docker](#paso-4--arrancar-con-docker)
  - [Uso diario](#uso-diario)
  - [Datos, contraseñas y copias de seguridad](#datos-contraseñas-y-copias-de-seguridad)
    - [Guardar una copia (exportar)](#guardar-una-copia-exportar)
    - [Restaurar desde un JSON](#restaurar-desde-un-json)
  - [Actualizar a una versión nueva](#actualizar-a-una-versión-nueva)
  - [Problemas frecuentes](#problemas-frecuentes)
  - [Qué incluye el stack](#qué-incluye-el-stack)
  - [Licencia y código](#licencia-y-código)


## La forma más fácil (instalador)

1. Descarga **`AlejandrISBN-Setup.exe`** desde [Releases](https://github.com/pabloqpacin/AlejandrISBN/releases)
2. Ejecútalo (no hace falta administrador)
3. Se crea icono en el Escritorio / menú Inicio
4. Puedes **borrar el Setup** descargado; la app queda en `%LOCALAPPDATA%\Programs\AlejandrISBN`
5. Para salir: cierra la ventanita “AlejandrISBN”
6. **Actualizar:** en esa ventanita, *Buscar actualizaciones* descarga e instala el último `Setup.exe` del Release (solo el build Windows; no aplica a Docker)
7. Para quitar la app: Ajustes → Aplicaciones → AlejandrISBN → Desinstalar  
   (los libros en `%LOCALAPPDATA%\AlejandrISBN\` **no** se borran)

**Restaurar un JSON:** con la app abierta, usa **Importar** (junto a Exportar).

No hace falta Python ni Docker. Inno Setup / el build son **gratis** (sin certificado de firma; Windows puede avisar “origen desconocido” la primera vez — *Más información → Ejecutar de todas formas*).

---

## Otras formas

| Modo | Para quién | Arranque |
|------|------------|----------|
| **Setup.exe** | Windows, uso diario | Instalador → icono Escritorio; actualizaciones desde la ventanita de la app |
| **Git + Docker** | Windows, macOS o Linux | `git clone` + `docker compose up --build -d` |

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
2. En PowerShell, desde esa carpeta:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   $env:ALEJANDRISBN_BACKEND = "sqlite"
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

3. Abre [http://127.0.0.1:8000](http://127.0.0.1:8000) — **deja la terminal abierta** mientras uses la app
4. Para parar: Ctrl+C

**Datos:** `%LOCALAPPDATA%\AlejandrISBN\alejandrisbn.db`  
**Restaurar un JSON de backup:** con la app abierta, usa **Importar** (junto a Exportar).

Para probar la ventanita de control sin PyInstaller:

```powershell
.venv\Scripts\python.exe -m app.desktop_app
```

---

## Modo Docker (Postgres) — Windows, macOS y Linux

Mismo enfoque en los tres sistemas: Git + Docker Desktop (o el motor Docker de tu distro en Linux).

### Qué vas a instalar

1. **Brave** (recomendado) — navegador  
2. **Docker Desktop** — app + Postgres en contenedores (~8 GB RAM de sistema)  
3. **Git** — clonar / actualizar el repo  
4. **AlejandrISBN** — `docker compose up --build -d`

### Requisitos

| Requisito | Notas |
|-----------|--------|
| Windows 10 u 11 (64 bits) | Actualizado (incluye `winget`) |
| Cuenta de administrador | Para instalar Docker, Git y Brave |
| **8 GB RAM** (mínimo Docker) | 16 GB recomendado |
| ~15 GB libres en disco | Imágenes + volumen |
| Virtualización en BIOS | VT-x / AMD-V |
| Conexión a Internet | Primera instalación y búsquedas ISBN |

### Opción rápida — PC nuevo (script de prerequisitos)

> El script `packaging/windows/setup-windows.bat` (y `.ps1`) **solo funciona en Windows**. No se puede ejecutar desde Linux ni desde una terminal WSL sobre la carpeta del repo.

Si ya tienes la carpeta del proyecto (ZIP o USB):

1. Copia/extrae a p. ej. `C:\Users\TU_USUARIO\Documents\AlejandrISBN` (evita `\\wsl$\...`)
2. Doble clic en `packaging\windows\setup-windows.bat` → acepta UAC
3. Instala Brave, Git y Docker Desktop; reinicia si Docker lo pide
4. Abre Docker Desktop y espera a que esté en marcha
5. En PowerShell, desde la raíz del repo:

   ```powershell
   copy .env.example .env
   docker compose up --build -d
   ```

6. Abre [http://localhost:8000](http://localhost:8000)

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

### Paso 4 — Arrancar con Docker

Desde la carpeta del proyecto (con Docker Desktop en marcha):

```powershell
copy .env.example .env
docker compose up --build -d
```

La **primera** vez puede tardar varios minutos. Abre [http://localhost:8000](http://localhost:8000)

Para detener (los libros **no** se borran):

```powershell
docker compose down
```

---

## Uso diario

1. Abre **Docker Desktop** (debe estar en marcha)
2. Desde la carpeta del repo: `docker compose up -d` (o `docker compose up --build -d` tras cambios)
3. Entra en [http://localhost:8000](http://localhost:8000)

Para parar sin perder datos: `docker compose down`.

---

## Datos, contraseñas y copias de seguridad

- Los datos viven en el volumen Docker `alejandrisbn_pgdata`.  
  `docker compose down` **no** los borra.
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

1. Con la app en marcha, abre [http://localhost:8000](http://localhost:8000)
2. Usa **Importar** (junto a Exportar) y elige tu archivo `.json` o `.csv`
3. Comprueba que aparecen los libros

**Comportamiento:** la importación **añade** libros que faltan; no pisa los que ya existen con el mismo ISBN (o el mismo id local).

**Empezar de cero y cargar solo el JSON:** eso borra la base actual. Solo si lo tienes claro:

```powershell
docker compose down -v
```

Luego `docker compose up --build -d`, abre la UI e **Importar**.

---

## Actualizar a una versión nueva

**Instalador Windows:** en la ventanita de control de AlejandrISBN, *Buscar actualizaciones*. Comprueba el último Release en GitHub, descarga el `Setup.exe` nuevo e instala (los datos en `%LOCALAPPDATA%\AlejandrISBN\` no se tocan).

**Git + Docker** (cualquier SO):

```bash
cd AlejandrISBN   # o la ruta donde clonaste
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
