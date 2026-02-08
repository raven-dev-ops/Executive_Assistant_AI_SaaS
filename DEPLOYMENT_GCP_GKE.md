GCP Deployment (GKE) - Notes
============================

This repo historically referenced GKE in some docs. The current reference deployment described in
`WIKI.md` uses Cloud Run + Cloud SQL, but GKE can still be used if desired.

If deploying on GKE, ensure:
- The backend is exposed over HTTPS behind an ingress/load balancer
- Dashboards and widget are served from a trusted origin and can reach the backend origin
- Secrets are provided via Kubernetes secrets (or a secret manager integration), never committed
- Webhook signature verification and replay protection remain enabled

For Cloud Run notes and the current deployment posture, see `WIKI.md`.

