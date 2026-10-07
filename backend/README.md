# Me&You Backend

## Local PostgreSQL

From the repository root, start PostgreSQL with `docker compose up -d postgres`. The service exposes port 5432 and stores data in the named `me_you_postgres_data` volume. Copy `.env.example` to `.env` and adjust local settings as needed; the example contains placeholders only.

## Client IP and request limits

`TRUSTED_PROXY_COUNT` defaults to `0`, so client IPs come from the direct connection and any `X-Forwarded-For` header is ignored. Set it to the exact number of trusted reverse-proxy hops only when the service is reachable exclusively through those proxies. When enabled, the client address is selected from the right side of the forwarded chain; trusting this header from untrusted clients lets them spoof IPs and evade limits. Rate-limit defaults and individual limit settings are listed in `.env.example`.

Security audit events are retained for 365 days by default. Run `python -m app.cli purge-security-events` from `backend/` to delete events older than `SECURITY_EVENT_RETENTION_DAYS`. `python -m app.cli purge-expired` removes expired rate counters and expired/consumed account email tokens.

## Privacy and institution membership

Profiles default to `NETWORK` visibility, preserving existing shared-institution discovery. Profile visibility may be `PUBLIC`, `AUTHENTICATED`, `NETWORK`, or `PRIVATE`; posts default to `PUBLIC` for compatibility and may be `PUBLIC`, `AUTHENTICATED`, `NETWORK`, or `PRIVATE`. Inactive accounts are hidden from discovery and social collections. Student/teacher self-registration now creates a pending join request; an institution administrator must approve it. Administrators may also invite users, but invitees must accept before an active membership is created. Existing active memberships are retained. List endpoints are capped at 100 rows; cursor-enabled feeds, messages, notifications, comments, likes, followers/following, search, and security events return continuation cursors (array endpoints use `X-Next-Cursor`).

## Platform administrator bootstrap

Run `python -m app.cli create-platform-admin` from `backend/` to create the first administrator or promote an existing account. New-account passwords are entered with `getpass` prompts, never command-line arguments. Use `python -m app.cli grant-platform-admin <email>` and `python -m app.cli revoke-platform-admin <email>` for later changes; revoking the last active platform administrator is refused.

## Account lifecycle

`POST /account/logout` revokes the current JWT version. Account deletion is an anonymizing soft-delete: identifiers are replaced, profiles and authored social content are removed, messages/submission text is redacted, and academic/audit references remain. Password recovery and email verification require an installed `EmailProvider`; no local fake sender is provided. Tokens are random, single-use, expire, and only their SHA-256 digests are stored.

## Tests

Run the backend suite from any directory with:

```sh
./backend/scripts/test.sh
```

Arguments are forwarded to pytest, for example `./backend/scripts/test.sh -m postgres -q`. Set `PYTHON` to select a Python interpreter; by default the script uses the workspace pytest interpreter when available and otherwise uses `python`.

## Migrations

Set `ME_YOU_DATABASE_URL` to a `postgresql+asyncpg://` URL, then run Alembic from this directory, for example `alembic upgrade head`.