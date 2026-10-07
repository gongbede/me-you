# me-you

## Run everything locally

One-time setup in a Codespace:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
```

In `backend/.env`, keep `ME_YOU_ENV=development`, set the database URL to `postgresql+asyncpg://me_you:placeholder-local-password@127.0.0.1:5432/me_you`, and replace the JWT placeholder with a fresh value from `openssl rand -hex 32`. Set `ME_YOU_CORS_ORIGINS` to `http://localhost:5173` plus `https://${CODESPACE_NAME}-5173.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}`. Set `ME_YOU_PUBLIC_BASE_URL` to the Codespaces origin. The env file is ignored by Git. PostgreSQL binds to loopback only; do not forward port 5432.

Run these three commands each day:

```sh
./scripts/dev-up.sh
cd frontend
npm run dev -- --host 0.0.0.0
```

The first command starts only PostgreSQL, waits for health, applies migrations, and launches the API on port 8000. Vite runs on port 5173 and proxies `/api` to the API. Check readiness with `curl http://localhost:8000/health/ready`. Stop the backend and database with `./scripts/dev-down.sh`.

Registration creates an account without sending or requiring an email-verification message, so the new account can log in immediately. Email verification and password recovery require an installed email provider; no local fake sender is configured.