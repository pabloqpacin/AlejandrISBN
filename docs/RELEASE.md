# Pipeline y release (borrador)
#
# Producto principal Windows (PCs modestos / no técnicos):
#   ZIP con AlejandrISBN.exe (PyInstaller) → icono Escritorio, sin Python ni Docker
# Alternativas:
#   start-desktop.bat (dev con Python + SQLite)
#   Docker Compose + Postgres (self-host)
# Guía: `docs/SELFHOSTING.md`.

## Flujo propuesto

```text
push / PR     →  CI Docker smoke
tag vX.Y.Z    →  build-windows.yml → AlejandrISBN-Setup.exe (+ ZIP) en el Release
                + release.yml → imagen GHCR (opcional)
usuario final → Setup.exe → icono; luego “Buscar actualizaciones” en la ventanita
```

## Workflows

| Archivo | Disparador | Qué hace |
|---------|------------|----------|
| `.github/workflows/ci.yml` | push/PR | Build Docker + smoke `/api/health` |
| `.github/workflows/build-windows.yml` | tag `v*` / manual | PyInstaller → Inno Setup → Setup.exe + ZIP |
| `.github/workflows/release.yml` | tag `v*` | Push GHCR + notas |

## Cómo publicar una versión para tu colega

```bash
git checkout main
git pull
git tag v1.0.0
git push origin v1.0.0
```

En Actions debe aparecer **build-windows**; el Release incluirá `AlejandrISBN-windows.zip`.

También puedes lanzar *build-windows* a mano (workflow_dispatch) y bajar el artifact sin tag.

## Actualizaciones (solo Windows instalado)

El botón **Buscar actualizaciones** aparece únicamente en el `.exe` empaquetado (Inno).  
Comprueba el último Release en GitHub, descarga `AlejandrISBN-Setup.exe` e instala en silencio.

- **No afecta** a `docker compose` / Linux / desarrollo con git  
- La base de datos en `%LOCALAPPDATA%\AlejandrISBN\` **no se borra**  
- Repo configurable: env `ALEJANDRISBN_GITHUB_REPO` (por defecto `pabloqpacin/AlejandrISBN`)

## Checklist

- [ ] Probar artifact `AlejandrISBN-windows.zip` en un Windows real
- [ ] SmartScreen: sin firma puede avisar la primera vez (certificado Authenticode = siguiente nivel)
- [ ] Icono `.ico` custom (opcional)
- [ ] Probar restore JSON vía carpeta `seed` junto al exe

## Fuera de alcance aún

- MSIX / Microsoft Store
- Firma Authenticode de pago
