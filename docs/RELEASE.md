# Pipeline y release (borrador)
#
# Objetivo: open source + self-host (clonar repo → Docker Compose).
# Público principal: Windows / usuarios no técnicos → `docs/SELFHOSTING.md`.

## Flujo propuesto

```text
push / PR  →  CI (build imagen + smoke compose)
tag vX.Y.Z →  Release (push GHCR + GitHub Release notes)
usuario    →  clone + start.bat  (o compose up --build)
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

## Imagen vs build local

Para self-host no técnico **priorizamos `docker compose up --build`** desde el clon:

- No requiere `docker login` a GHCR
- El código y la versión coinciden con lo clonado
- Los scripts `start.bat` / `update.bat` ya usan `--build`

GHCR queda como atajo opcional (CI/CD, servidores, usuarios avanzados).  
Si más adelante quieres arranque sin build, se puede añadir un `docker-compose.image.yml` que solo haga `pull` de `ghcr.io/...:latest`.

## Checklist antes del primer tag público

- [ ] Revisar nombre en `LICENSE` (MIT borrador)
- [ ] README enlaza a `docs/SELFHOSTING.md`
- [ ] Probar `start.bat` en un Windows limpio con Docker Desktop
- [ ] Confirmar que el paquete GHCR es visible si el repo es público
- [ ] (Opcional) Añadir badge de CI en el README

## Fuera de alcance de este borrador

- Instalador `.msi` / Store
- Auto-update sin Git
- HTTPS / reverse proxy (uso LAN/localhost)
- Firmas de imagen (cosign) — se puede añadir después
