# Security Overview & Review

Security posture of the AI Mirror Platform and the checklist used for review
(task 14.5).

## Authentication & sessions
- Passwords hashed with **Argon2id** (memory-hard); never stored or logged.
- Access tokens: short-lived (≤15 min) signed JWTs, validated statelessly.
- Refresh tokens: long-lived, **rotated on every use**, with **reuse detection**
  (presenting a rotated token revokes the whole family). Only SHA-256 hashes of
  refresh/verification/reset tokens are stored.
- Logout / password reset / suspension revoke sessions; access tokens can be
  denylisted by `jti` in Redis.
- Auth endpoints are **rate-limited per IP and per account** (429 + Retry-After).

## Authorization
- Role-based access (`user`, `admin`, `moderator`) enforced by route guards;
  authorization failures return 403 and are auditable.
- All user data is scoped by `user_id`; gallery/uploads/jobs only return owned rows.

## Secrets management
- No secrets in code or images. Supplied via env / K8s `Secret` (use sealed-secrets
  or an external-secrets operator in prod). `SECRET_KEY`, DB creds, S3 keys, and
  Stripe keys are all externalised. `.env.example` documents the surface.
- Rotate `SECRET_KEY` with an overlap window; rotate provider keys via the portal.

## Payment integrity
- Webhooks are **signature-verified** and **idempotent** (dedup by
  `provider_event_id`) — retries never double-credit.
- Credits use an **append-only ledger** with row-locked balance updates and a
  `balance >= 0` CHECK — no negative balances from concurrent debits, no
  double-charge (idempotency keys on hold/debit/refund).

## PII & biometric data (GDPR/BIPA)
- **Explicit versioned consent** required before face processing; enforced at job
  submission.
- **EXIF/metadata stripped** on upload ingest (removes GPS/device data).
- **NSFW/abuse screening** on uploads and prompts; violations quarantined with a
  moderation event.
- **Retention & purge**: account deletion soft-deletes immediately, revokes
  sessions, and schedules hard purge of images + PII within
  `PURGE_RETENTION_DAYS` (`purge_expired` task). Data export available on request.
- Full **audit log** of admin/moderation actions.

## Transport & assets
- TLS termination at Nginx/ingress; HSTS + security headers in `tls.conf.example`.
- Objects delivered via short-TTL **presigned / CDN-signed URLs**, never proxied;
  private-by-default visibility. `/metrics` blocked at the edge.

## Input validation
- Uploads validated by magic bytes + dimensions + size before persistence
  (415/413 on violation); images re-encoded.
- Pydantic v2 validates and bounds all request bodies; generation params are
  clamped to configured limits before inference.

## Review checklist
- [ ] No secrets committed; all via env/secret store; rotation documented.
- [ ] Rate limits active on auth; tested for 429 + Retry-After.
- [ ] Webhook signature verification enforced; idempotency tested (see tests).
- [ ] Ledger invariants tested (sum == balance; no negative; idempotent).
- [ ] Consent enforced before InstantID; EXIF stripped; NSFW screening on.
- [ ] Retention/purge job scheduled; export tested.
- [ ] RBAC guards on all admin routes; 403 audited.
- [ ] TLS + security headers in prod ingress; `/metrics` not public.
- [ ] Dependencies patched (Dependabot / `npm audit` / `pip-audit` in CI).

## Dependency hygiene
- Frontend pinned to a patched Next.js 14.2.x; track advisories and bump.
- Run `pip-audit` (backend) and `npm audit` (frontend) in CI; review weekly.
