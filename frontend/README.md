# AI Mirror — Frontend (Next.js App Router)

The reference web client. Every capability is also a documented API endpoint;
this app is just one consumer.

## Stack

- Next.js 14 (App Router), React 18, TypeScript.
- No CSS framework — a small hand-rolled design system in `app/globals.css`.
- Auth/session in `lib/auth.tsx`; typed API client with refresh-on-401 in `lib/api.ts`.

## Routes

| Path | Purpose |
|------|---------|
| `/` | Landing |
| `/auth/login` `/register` `/verify` `/forgot` `/reset` `/oauth-complete` | Auth flows (incl. Google/Apple) |
| `/studio` | Upload, style select, prompt, stage selection, submit + live SSE progress |
| `/gallery` | Paginated gallery with visibility, share, favorite, delete |
| `/billing` | Plans, credit packs, checkout, invoices, balance |
| `/settings` | Profile, biometric consent, data export, account deletion |
| `/admin` | Users, jobs, reports, moderation, feature flags (role-gated) |

## Develop

```bash
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080 npm run dev
# http://localhost:3000
```

Point `NEXT_PUBLIC_API_BASE_URL` at the Nginx edge (`:8080`) or the API (`:8000`).

## Build

```bash
npm run build && npm start    # standalone output, see docker/Dockerfile.frontend
```
