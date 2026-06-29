# Object storage (MinIO / S3)

Three buckets back the platform. They are created and configured automatically on
API startup (`object_store.ensure_buckets`) and by the `minio-init` Compose
service, but the policies below document the intended configuration for
production/manual setup.

| Bucket    | Contents                              | Access            | Lifecycle |
|-----------|---------------------------------------|-------------------|-----------|
| `uploads` | User-uploaded source images (EXIF-stripped) | Private, presigned only | Expire abandoned objects after 365d (app-driven purge for deletes) |
| `outputs` | Generated images                      | Private, presigned + CDN signed URLs | 365d backstop |
| `exports` | Data-export archives, invoices        | Private, presigned only | **7d** expiry |

## Policy files

- [`policies/lifecycle.json`](policies/lifecycle.json) — retention/expiry rules
  applied via `object_store.apply_lifecycle_policies()` or `mc ilm import`.
- [`policies/cors.json`](policies/cors.json) — CORS for direct browser
  presigned PUT/GET.

## Principles

- The API **never** proxies object bytes for delivery (design D3). Clients
  upload via presigned `PUT` and download via presigned `GET` / CDN signed URLs.
- Uploads are re-encoded on ingest to strip EXIF/metadata (GPS, device).
- Private-by-default visibility; share links mint short-TTL presigned URLs.
- Deleted images are scheduled for hard purge within the retention SLA
  (`PURGE_RETENTION_DAYS`).

## Manual setup with `mc`

```bash
mc alias set local http://localhost:9000 minioadmin minioadmin
mc mb local/uploads local/outputs local/exports
mc ilm import local/exports < storage/policies/lifecycle.json
```
