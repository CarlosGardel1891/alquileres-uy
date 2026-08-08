# Upgrade

How to move the running API to a new version — of the code, the
serving bundle, or both.

## Contents

- [Versioning](#versioning)
- [Upgrading the code](#upgrading-the-code)
- [Upgrading the serving bundle](#upgrading-the-serving-bundle)
- [Bundle compatibility](#bundle-compatibility)
- [Rollback](#rollback)

## Versioning

The project follows **Semantic Versioning 2.0.0** (`MAJOR.MINOR.PATCH`).
The number lives in `src/alquileres_uy/_version.py` and everything
else derives from it:

- `pyproject.toml` reads it via `[tool.setuptools.dynamic]`.
- `ApiSettings.APP_VERSION` defaults to it.
- The Dockerfile takes it as an `APP_VERSION` build arg and stamps
  the `org.opencontainers.image.version` label.
- `CHANGELOG.md` has one section per released version.
- `GET /build` exposes it at runtime alongside the git SHA.
- The release workflow fires on `v<version>` tags.

Rules:

- **PATCH** — bug fixes and doc-only changes.
- **MINOR** — new endpoints, new config knobs, new metrics that are
  additive.
- **MAJOR** — any breaking change to a public contract (`POST /predict`
  request/response, `/version` shape, environment variable rename,
  metric rename, minimum bundle version bump).

## Upgrading the code

1. Bump `src/alquileres_uy/_version.py`.
2. Add a `## [<new-version>] — YYYY-MM-DD` block in `CHANGELOG.md`.
3. `python scripts/release.py` — validates the tree, runs the fast
   tests, checks the CHANGELOG entry, creates the annotated
   `v<new-version>` tag. Does not push.
4. `git push origin main --tags` — the `release.yml` workflow fires,
   builds the wheel + sdist + Docker image, attaches the artifacts
   and drafts a GitHub Release.
5. Deploy the new image alongside the old one, run
   `scripts/smoke_api.py`, then cut over.

`scripts/release.py` prints the suggested next patch / minor / major
version so the operator can immediately branch off a follow-up.

## Upgrading the serving bundle

1. Retrain with `scripts/train_models.py` and copy the new
   `serving_bundle/` directory into the target environment.
2. Set `ALQUILERES_API_MODEL_BUNDLE_PATH` to the new location or
   mount the new bundle over the old volume.
3. Restart the API — the startup will re-validate checksums, verify
   `minimum_api_version`, run the warmup and only then flip
   `model_loaded` to `1`.
4. Confirm `GET /version` reports the new `model_version` and
   `bundle_sha256`.

A bundle change alone does not require a code release — the API
version does not move. Update `CHANGELOG.md` only if you are also
changing code.

## Bundle compatibility

Every bundle emitted by Fase 5+ carries `metadata.minimum_api_version`
(default `0.1.0`). Startup calls
`verify_bundle_compatibility(loaded, api_version=APP_VERSION)`:

- If `APP_VERSION >= minimum_api_version` → OK.
- If `APP_VERSION <  minimum_api_version` → `IncompatibleBundleError`,
  the container exits non-zero.
- Bundles produced *before* the field existed load unconditionally.

To retire an old API version, bump the bundle's `minimum_api_version`
at emit time; deployments on older code will refuse the bundle
instead of silently producing wrong predictions.

## Rollback

Because the API version and the bundle are independent, rollback is a
two-lever operation.

**Code-only rollback** (bad release, bundle still good):

```bash
# Redeploy the previous image tag.
docker pull alquileres-uy-api:0.10.0
docker run ... alquileres-uy-api:0.10.0
```

The GitHub Release artifacts contain the wheel, sdist and Docker
image tarball for every tagged version — nothing is lost when a
release is superseded.

**Bundle-only rollback** (bad model, code still good):

```bash
# Point the running API at the previous bundle directory.
ALQUILERES_API_MODEL_BUNDLE_PATH=/path/to/previous/serving_bundle
```

Restart the API; startup revalidates the older bundle. Because the
API version has not changed, no `CHANGELOG` update is needed.

**Both** — do the code rollback first, then the bundle rollback. Run
`scripts/smoke_api.py` after each step to confirm the endpoints
respond and the `/version` payload matches expectations.
