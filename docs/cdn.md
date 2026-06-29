# CDN Signed-URL Delivery

Generated images and shared assets are delivered through a CDN, never proxied by
the API (design D3). Private assets use short-TTL presigned URLs; public/unlisted
assets are fronted by a CDN with **signed URLs** so access is revocable and
time-bounded even when cached at the edge.

## Topology

```
client ──> CDN (CloudFront / Cloudflare) ──> MinIO/S3 (outputs bucket)
                    │
                    └─ signed URL (key-pair / token), short TTL, per-object
```

- `S3_PUBLIC_ENDPOINT_URL` points at the CDN hostname (e.g. `https://cdn.aimirror.example`).
  The API mints presigned/signed URLs against this hostname so internal
  service names are never leaked to browsers.
- The public share route `/s/{token}` 302-redirects to a signed URL and is itself
  edge-cached briefly (`Cache-Control: public, max-age=300`) — see the Nginx
  `location /s/` block.

## CloudFront (example)

1. Origin: the MinIO/S3 `outputs` bucket (OAC/OAI so the bucket stays private).
2. Behavior: signed URLs required (trusted key group). TTL 5 min default.
3. App side: set `S3_PUBLIC_ENDPOINT_URL=https://<distribution>.cloudfront.net`
   and implement `sign_cloudfront_url()` where the platform currently calls
   `object_store.presign_get` for public/unlisted assets.

## Cloudflare (example)

1. Proxy the bucket via an R2/Cache rule.
2. Use signed URLs (HMAC token) with a short expiry; validate at a Worker.

## Cache invalidation

- Deletes schedule object purge; also issue a CDN invalidation for the object key
  on delete/visibility-downgrade so a cached public copy cannot outlive the
  policy change.
- Share-token rotation changes the redirect target; the old signed URL expires
  by TTL.

## Why signed (not public) URLs

Presigned/CDN-signed URLs are short-lived, per-object, and private-by-default, so
a leaked link expires quickly and never exposes the whole bucket (design risk:
presigned-URL leakage).
