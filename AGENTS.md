# Agent Guide

Short routing notes for LLM agents. Keep this file compact; do not turn it into docs.

## Repo Map
- Main repo root: `C:\Anton\VS_Code\scccraper\google-maps-scraper`.
- Go scraper core: `gmaps/`, `scraper/`, `runner/`, `rqueue/`, `postgres/`.
- CLI entrypoint: `main.go`.
- SaaS entrypoint: `cmd/gmapssaas/main.go`; API/admin code in `api/`, `admin/`, `web/`.
- Local dashboard scripts: `scripts/*.py`.
- Local dashboard artifacts: `output/`.
- Sample/runtime scraper data: `gmapsdata/`.
- Upstream docs/assets are large: `README.md`, `docs/`, `img/`, sponsor markdown files.

## Recent Commits
- `5dd9d18` Add Leaflet Da Nang restaurant maps.
- `8377e95` Add contact validation dashboard data.
- `b1aca75` Add Google Maps CSV visualizations.
- Older upstream commits before that are scraper version/features, not local dashboard work.

## Pipeline
- Scrape: upstream scraper exports raw records, usually JSONL for local dashboard work.
- Normalize: `python scripts/normalize_results.py <raw-jsonl> [normalized.json]`.
- Enrich contacts: `python scripts/validate_contacts.py <normalized.json> [enriched.json]`.
- Generate list/dashboard HTML: `python scripts/build_dashboard.py <enriched.json> [output/dashboard.html]`.
- Generate map/zones/assets: `python scripts/build_danang_dashboard_pages.py <enriched.json> [output-dir]`.
- Legacy CSV visualizations: `scripts/visualize_gmaps_csv.py`, `scripts/visualize_gmaps_market.py`.

## Inputs / Outputs
- Current input query list: `output/input-danang.txt`.
- Current JSON chain:
  - `output/danang-restaurants.json` raw/local source.
  - `output/danang-restaurants-normalized.json`.
  - `output/danang-restaurants-enriched.json`.
- Generated pages:
  - `output/dashboard.html` is the list page.
  - `output/map.html` is the Leaflet map page.
  - `output/zones.html` is the zone analysis page.
- Shared generated assets:
  - `output/assets/danang-restaurants-data.js`.
  - `output/assets/danang-dashboard.js`.
  - `output/assets/danang-dashboard.css`.
- CSV report outputs live under `gmapsdata/*-dashboard.html` and `gmapsdata/*-market.html`.

## Entry Points
- Scraper CLI: `main.go`.
- Web UI/server: `web/`, `runner/webrunner/`.
- SaaS app: `cmd/gmapssaas/`, `api/`, `admin/`.
- Dashboard data normalization: `scripts/normalize_results.py`.
- Contact/messenger enrichment: `scripts/validate_contacts.py`.
- List dashboard HTML: `scripts/build_dashboard.py`.
- Map/zones dashboard pages: `scripts/build_danang_dashboard_pages.py`.

## Fast Paths
- Need dashboard list changes: start in `scripts/build_dashboard.py`.
- Need map markers, filters, Leaflet behavior: start in `scripts/build_danang_dashboard_pages.py`, JS section.
- Need zone polygons/classification: edit `LINE_ZONES`, `AREA_ZONES`, `classify_line`, `area_ids_for`.
- Need phone/email/social extraction: start in `scripts/normalize_results.py`.
- Need WhatsApp/Zalo/Messenger/Telegram/Viber validation: start in `scripts/validate_contacts.py`.
- Need scraper behavior: inspect `gmaps/`, then `scraper/`, then `runner/`.
- Need web UI behavior: inspect `web/` templates/service first.
- Need SaaS/admin behavior: inspect `cmd/gmapssaas/`, `api/`, `admin/`.

## Common Tasks
- Rebuild normalized JSON:
  `python scripts/normalize_results.py output/danang-restaurants.json output/danang-restaurants-normalized.json`
- Rebuild enriched JSON:
  `python scripts/validate_contacts.py output/danang-restaurants-normalized.json output/danang-restaurants-enriched.json`
- Rebuild list page:
  `python scripts/build_dashboard.py output/danang-restaurants-enriched.json output/dashboard.html`
- Rebuild map/zones:
  `python scripts/build_danang_dashboard_pages.py output/danang-restaurants-enriched.json output`
- Go smoke tests: `go test ./...`.
- Full repo test target: `make test`.
- Format Go only when needed: `make format`.

## Do Not Waste Tokens On
- Do not read full `README.md`, `docs/`, `img/`, sponsor `.md` files unless the task is docs/marketing.
- Do not inspect migrations/SaaS/admin for dashboard-only tasks.
- Do not read generated `output/*.html` in full; inspect scripts and spot-check output.
- Do not read `gmapsdata/jobs.db*` unless debugging local DB state.
- Do not expand `build_dashboard.py` or `build_danang_dashboard_pages.py` with unrelated features.

## Guardrails
- Change only files needed for the task; preserve generated outputs unless asked to rebuild them.
- Treat `output/*.json` as data inputs; do not rewrite them casually.
- Keep new dashboard logic in existing script sections instead of adding new frameworks.
- Keep generated pages self-contained/static; current map pages use Leaflet CDN assets.
- Existing untracked runtime files may exist in `gmapsdata/` and `output/playwright/`; do not delete them.
