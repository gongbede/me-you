# me-you

## Run everything locally

One-time setup in a Codespace:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
```

`./scripts/dev-up.sh` creates `backend/.env` from the safe example when it is missing; it never overwrites an existing file. Set `ME_YOU_ENV` to exactly `development`, `test`, or `production`. For production, generate a fresh JWT secret with `openssl rand -hex 32`. Set `ME_YOU_CORS_ORIGINS` to `http://localhost:5173` plus `https://${CODESPACE_NAME}-5173.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}`. Set `ME_YOU_PUBLIC_BASE_URL` to the Codespaces origin. The env file is ignored by Git. PostgreSQL binds to loopback only; do not forward port 5432.

Run these steps in order. Run each server command in its own terminal:

```sh
docker compose up -d --wait postgres
(cd backend && .venv/bin/alembic upgrade head)
(cd backend && ME_YOU_ENV=development .venv/bin/python -m app.cli seed-demo)
(cd backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000)
(cd frontend && npm run dev -- --host 0.0.0.0)
```

`seed-demo` prints generated account credentials only once; rerunning it creates no duplicates and prints no new credentials. Vite runs on port 5173 and proxies `/api` to the API. Check readiness with `curl http://localhost:8000/health/ready`. Stop the backend and database with `./scripts/dev-down.sh`.

Registration creates an account without sending or requiring an email-verification message, so the new account can log in immediately. Email verification and password recovery require an installed email provider; no local fake sender is configured.