# cadis-global-dataset Release Layout

This folder contains the release artifacts for the internal `cadis-global-dataset` project.

## Structure

- `CGD_SPEC.md`
- `README.md` (this file)
- `v0.1.0/ne.global/v0.1.0/`
  - `ne.global.v0.1.0.cgd`
  - `ne.global.v0.1.0.tar.gz`
  - `manifest.local-build.json`
  - `manifest.cdn-example.json`
  - `SHA256SUMS`

## Artifact Notes

- `ne.global.v0.1.0.cgd`: CGD payload used by `cadis-global` world resolver.
- `ne.global.v0.1.0.tar.gz`: CDN transport package for bootstrap download.
- `manifest.local-build.json`: builder output metadata.
- `manifest.cdn-example.json`: example CDN/bootstrap manifest (`artifact_url`, `artifact_sha256`, `sha256`, `cgd_filename`).
- `SHA256SUMS`: checksums for `.cgd` and `.tar.gz`.

## Policy

- `cadis-global-dataset` is internal and not published to GitHub.
- Dataset artifact `ne.global.v0.1.0.cgd` is distributed with `cadis-global`.
- Natural Earth attribution and license notice are documented in `CGD_SPEC.md`.
