# ADR 0009 — SeaweedFS for development object storage

**Context.** The original plan named MinIO for local S3. MinIO's public container images are no longer pullable from Docker Hub/Quay without credentials (observed 2026-10-06).

**Decision.** Use SeaweedFS (Apache-2.0) in `compose.yml` as the S3-compatible store for development and CI. Production targets AWS S3 (ap-south-1) or Cloudflare R2. Application code talks only the S3 API through boto3 (`app/core/storage.py`), so this is a configuration change.
