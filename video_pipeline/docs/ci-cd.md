## CI/CD (GitHub Actions → GHCR)

This repo includes a GitHub Actions workflow that builds and pushes Docker images to GitHub Container Registry (GHCR).

### Workflow
- File: `.github/workflows/docker-images.yml`
- Trigger: push to branches `main` and `dev`

### Images published
- `ghcr.io/<org>/<repo>/video-pipeline-api`
- `ghcr.io/<org>/<repo>/video-pipeline-ui`
- `ghcr.io/<org>/<repo>/video-pipeline-segment-worker`
- `ghcr.io/<org>/<repo>/video-pipeline-ai-worker`

### Tags
- Push to `main`:
  - `:main`
  - `:latest`
  - `:sha-<short>` (from `docker/metadata-action`)
- Push to `dev`:
  - `:dev`
  - `:sha-<short>`

### Requirements
- Repository must have Packages enabled.
- Workflow uses `GITHUB_TOKEN` with `packages:write` permission to push images.

