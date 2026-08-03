# Pipeline y release (borrador)
#
# Dos productos de distribución:
# 1) Escritorio SQLite (PCs modestos) → start-desktop.bat / futuro instalador
# 2) Self-host Docker (Postgres) → compose + start.bat
# Guía usuarios: `docs/SELFHOSTING.md`.

## Flujo propuesto

```text
push / PR  →  CI (build imagen + smoke compose; opcional smoke SQLite)
tag vX.Y.Z →  Release (push GHCR + GitHub Release notes)
usuario PC flojo → clone/ZIP + Python + start-desktop.bat
usuario Docker   → clone + start.bat  (o compose up --build)
```

## Workflows

| Archivo | Disparador | Qué hace |
|---------|------------|----------|
| `.github/workflows/ci.yml` | push/PR a `main` / `develop` | Build Docker + `compose up` + curl `/api/health` |
| `.github/workflows/release.yml` | tag `v*` | Push a `ghcr.io/<owner>/<repo>` + GitHub Release |

## Cómo publicar una versión

```bash
git checkout main
git pull
git tag v1.0.0
git push origin v1.0.0
```

Comprobar en GitHub → Actions y Packages.

## Imagen vs build local vs escritorio

| Canal | Cómo |
|-------|------|
| Escritorio low-spec | `start-desktop.bat` (SQLite en `%LOCALAPPDATA%`) — **sin Docker** |
| Self-host no técnico | `docker compose up --build` / `start.bat` |
| GHCR (opcional) | imagen preconstruida para servidores / usuarios avanzados |

## Checklist antes del primer tag público

- [ ] Revisar nombre en `LICENSE` (MIT borrador)
- [ ] README enlaza a `docs/SELFHOSTING.md` (desktop + Docker)
- [ ] Probar `start-desktop.bat` en Windows con poca RAM
- [ ] Probar `start.bat` con Docker Desktop
- [ ] Confirmar que el paquete GHCR es visible si el repo es público
- [ ] (Siguiente) PyInstaller / instalador NSIS para no exigir Python a mano

## Fuera de alcance de este borrador

- Instalador `.msi` / MSIX / Store
- Auto-update sin Git
- HTTPS / reverse proxy (uso LAN/localhost)
- Firmas de imagen (cosign) — se puede añadir después
