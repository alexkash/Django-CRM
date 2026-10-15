# Repository Guidelines

## Project Structure & Module Organization

BottleCRM combines a Django REST API, SvelteKit web client, and Flutter mobile app.

- `backend/`: domain apps such as `accounts/`, `leads/`, and `cases/`; shared tenancy/authentication in `common/`; settings in `crm/`. Tests live in each app’s `tests/` directory.
- `frontend/src/routes/`: SvelteKit pages and server routes; `src/lib/`: shared components, API helpers, and server modules. JavaScript tests sit alongside source files.
- `mobile/lib/`: Flutter screens, services, and widgets; `mobile/test/`: tests.
- Assets: `frontend/static/`, `backend/static/`, and `mobile/assets/`.
- `docs/`: MkDocs documentation; `docker/`: container configuration; `ops/suitecrm/`: migration tooling.

## Build, Test, and Development Commands

Run commands from the indicated directory:

- Root: `docker compose up --build` starts the local stack; web runs on port 5181 and API on 8000.
- `backend/`: `uv sync` installs dependencies. Copy `.env.example` to `.env`, configure PostgreSQL/Redis, then run `uv run python manage.py migrate` and `uv run python manage.py runserver`.
- `backend/`: `uv run pytest` runs tests with coverage; `uv run ruff check .` and `uv run ruff format --check .` check style.
- `frontend/`: `pnpm install`, then `pnpm dev`; validate with `pnpm check`, `pnpm lint`, `pnpm test`, and `pnpm build`.
- `mobile/`: `flutter pub get`, `flutter run`, `flutter test`, and `flutter analyze --no-fatal-infos`.

## Coding Style & Naming Conventions

Use four-space Python indentation, double quotes, snake_case functions, and PascalCase classes; Ruff handles formatting and import sorting. Frontend Prettier uses two spaces, single quotes, and no trailing commas; ESLint checks code. Preserve SvelteKit names such as `+page.svelte`. Use Dart snake_case filenames, PascalCase classes, and `dart format .`.

## Testing Guidelines

Backend uses pytest-django and pytest-cov; name tests `test_*.py`. Coverage must meet `.coveragerc`’s 50% minimum. Default tests use SQLite; verify RLS changes with `crm.test_settings_postgres` and `postgres_only` tests under a non-superuser, non-bypass role. Follow `.github/workflows/tests.yml` for database setup. Test permitted, forbidden, and cross-tenant paths. Frontend uses Vitest (`*.test.js`); Flutter tests use `*_test.dart`.

## Commit & Pull Request Guidelines

Follow recent Conventional Commits: `feat: ...`, `fix(scope): ...`, or `docs: ...`. Branch from and target `master`. Keep PRs focused; describe the change, reason, verification, and related issues. Include screenshots for UI changes, migrations for model changes, and documentation for changed behavior.

## Security & Configuration

Never commit secrets or private data. Derive identity from `request.user` and `request.profile`; explicitly scope queries and writes to the organization. Follow `docs/contributing/security-rules.md` when changing permissions or serializers.
