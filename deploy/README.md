# Kubernetes Deployment

Production deployment path. Manifests are plain YAML (kustomize-friendly); a Helm
chart skeleton is under `helm/`.

## Layout

```
deploy/
├── namespace.yaml
├── config.yaml            # ConfigMap + Secret (template)
├── api/                   # Deployment, Service, HPA
├── worker/                # Deployment, KEDA ScaledObject (autoscale on queue depth)
├── ingress/               # Ingress + TLS
├── monitoring/            # ServiceMonitor + PrometheusRule
└── helm/                  # Helm chart skeleton
```

## Apply

```bash
kubectl apply -f deploy/namespace.yaml
kubectl apply -f deploy/config.yaml
kubectl apply -f deploy/api/
kubectl apply -f deploy/worker/
kubectl apply -f deploy/ingress/
kubectl apply -f deploy/monitoring/
```

Postgres, Redis, and MinIO are expected as managed services or separate
operators (RDS/ElastiCache/MinIO-operator) in production; wire their endpoints
into `config.yaml`.

## Autoscaling

- **API**: CPU-based `HorizontalPodAutoscaler` (`api/hpa.yaml`).
- **Workers**: scale on **queue depth** using a KEDA `ScaledObject`
  (`worker/keda-scaledobject.yaml`) targeting the Redis list length. This keeps
  GPU capacity matched to backlog (design risk: GPU is the scaling bottleneck).

## Rollback

API and worker images are stateless and versioned — `kubectl rollout undo`
either independently. Migrations are forward-only with paired down-scripts for
the latest step; payment webhooks are replayable and the credit ledger is
auditable/repairable.
