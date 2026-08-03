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
tag vX.Y.Z    →  build-windows.yml → AlejandrISBN-windows.zip en el Release
                + release.yml → imagen GHCR (opcional)
usuario final → descarga ZIP → AlejandrISBN.exe / icono Escritorio
```

## Workflows

| Archivo | Disparador | Qué hace |
|---------|------------|----------|
| `.github/workflows/ci.yml` | push/PR | Build Docker + smoke `/api/health` |
| `.github/workflows/build-windows.yml` | tag `v*` / manual | PyInstaller → ZIP del `.exe` |
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

## Experiencia de usuario (exe)

1. Extrae el ZIP  
2. Doble clic en `AlejandrISBN.exe`  
3. Ventanita de control + navegador  
4. Primera ejecución → acceso directo en Escritorio  
5. Cerrar la ventanita = salir  

Datos en `%LOCALAPPDATA%\AlejandrISBN\`. No instala Python en el sistema.

## Checklist

- [ ] Probar artifact `AlejandrISBN-windows.zip` en un Windows real
- [ ] SmartScreen: sin firma puede avisar la primera vez (certificado Authenticode = siguiente nivel)
- [ ] Icono `.ico` custom (opcional)
- [ ] Probar restore JSON vía carpeta `seed` junto al exe

## Fuera de alcance aún

- MSIX / Microsoft Store
- Auto-update
- Firma Authenticode de pago
