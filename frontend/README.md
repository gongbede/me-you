# Me&You Frontend

Mobile-first React + TypeScript application for the Me&You learning community.

## Run locally

1. Start the backend API at `http://localhost:8000`.
2. In a second terminal:

   ```sh
   cd /workspaces/me-you/frontend
   npm install
   npm run gen:api
   npm run dev
   ```

3. Open the Vite URL printed by the dev server (normally `http://localhost:5173`).

Vite proxies `/api/*` to `http://localhost:8000`, so browser requests are same-origin and backend CORS does not need a development change. Set `VITE_BACKEND_URL` to use another backend address.

## Checks

```sh
npm run lint
npm run test
npm run build
```

`npm run gen:api` reads `openapi.json`. Generate it without starting the API with `python ../backend/scripts/export_openapi.py` from this directory after installing backend requirements.

## Authentication note

The current foundation stores bearer tokens in `sessionStorage` for the current browser session. Replace this with a server-managed `HttpOnly`, `Secure`, `SameSite` cookie flow before production use; JavaScript-accessible token storage is not the long-term target.
