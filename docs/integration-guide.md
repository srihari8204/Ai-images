# Integration Guide

This walks through the full happy path: register → verify → log in → upload →
generate → poll → fetch from the gallery. Base URL below is the dev edge
(`http://localhost:8080`); replace with your deployment.

## 1. Register & verify

```bash
curl -X POST $BASE/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"Str0ngPassw0rd","display_name":"Me"}'
```

In dev, the verification link is printed to the API logs (no SMTP). Confirm:

```bash
curl -X POST $BASE/api/v1/auth/verify-email -d '{"token":"<token>"}' \
  -H 'Content-Type: application/json'
```

## 2. Log in

```bash
curl -X POST $BASE/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"Str0ngPassw0rd"}'
# => { "access_token": "...", "refresh_token": "...", "expires_in": 900 }
```

Send `Authorization: Bearer <access_token>` on subsequent calls. Rotate tokens
with `POST /api/v1/auth/refresh` before the access token expires.

## 3. (Optional) Record biometric consent

Required only when you request face consistency (`instantid`):

```bash
curl -X POST $BASE/api/v1/me/consents -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' \
  -d '{"type":"biometric","version":"2025-01","granted":true}'
```

## 4. Upload a reference image (presigned)

```bash
# a) get a presigned PUT URL
curl -X POST $BASE/api/v1/uploads/presign -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{"content_type":"image/jpeg"}'
# => { "upload_url": "...", "object_key": "...", ... }

# b) PUT the bytes straight to storage
curl -X PUT "<upload_url>" -H 'Content-Type: image/jpeg' --data-binary @face.jpg

# c) register/validate it (strips EXIF, screens, dedups)
curl -X POST $BASE/api/v1/uploads/register -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{"object_key":"<object_key>"}'
# => { "id": "<image_id>", ... }
```

Or upload directly (multipart fallback): `POST /api/v1/uploads` with a file part.

## 5. Submit a generation job

```bash
curl -X POST $BASE/api/v1/jobs -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: 4f1c-unique-key' \
  -d '{
        "prompt": "a portrait in a neon city",
        "style_slug": "cinematic",
        "stages": ["generate", "gfpgan", "realesrgan"],
        "params": {"width":1024,"height":1024,"steps":28}
      }'
# => 202 { "job_id": "...", "status": "queued", "cost_credits": 4,
#          "estimated_wait_seconds": 20 }
```

Insufficient credits → `402`. Disallowed prompt → `422 policy_violation`.

## 6. Track progress

Poll:

```bash
curl $BASE/api/v1/jobs/<job_id> -H "Authorization: Bearer $TOK"
```

Or stream (Server-Sent Events):

```bash
curl -N $BASE/api/v1/jobs/<job_id>/events -H "Authorization: Bearer $TOK"
# event: progress  data: {"status":"running","progress":60,"stage":"gfpgan"}
# event: progress  data: {"status":"completed","progress":100}
```

Cancel a running/queued job (releases the credit hold):

```bash
curl -X POST $BASE/api/v1/jobs/<job_id>/cancel -H "Authorization: Bearer $TOK"
```

## 7. Browse results

```bash
curl "$BASE/api/v1/gallery?limit=24" -H "Authorization: Bearer $TOK"
curl $BASE/api/v1/gallery/<image_id> -H "Authorization: Bearer $TOK"

# Make it shareable
curl -X PATCH $BASE/api/v1/gallery/<image_id> -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{"visibility":"unlisted"}'
curl -X POST $BASE/api/v1/gallery/<image_id>/share -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{}'
# => { "share_url": "http://localhost:8080/s/<token>" }
```

## 8. Buy credits

```bash
curl $BASE/api/v1/billing/credit-packs -H "Authorization: Bearer $TOK"
curl -X POST $BASE/api/v1/billing/checkout -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{"plan_slug":"pack_100"}'
# => { "checkout_url": "...", "session_id": "..." }
```

With no Stripe key configured, the built-in mock provider is used; credits are
granted when the (signed) webhook is delivered to `POST /webhooks/payments`.

## Pagination

List endpoints return `{ items, next_cursor, has_more }`. Pass `?cursor=` (and
`?limit=`) to fetch the next page. Cursors are opaque — don't parse them.

## Rate limits

Auth endpoints are throttled per IP and per account. On breach you get `429`
with a `Retry-After` header.
