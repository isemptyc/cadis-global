# cadis-global

`cadis-global` is the public orchestration layer for:

1. world-level resolution (`country` or terminal world state)
2. dataset bootstrap/cache policy
3. runtime dispatch via `cadis-runtime`

## Scope (v0.1.0)

- Uses `cadis-runtime` as admin execution engine.
- Uses `cadis-cdn` indirectly via runtime bootstrap helpers.
- Supports only explicitly configured/known ISO2 datasets (`TW`, `JP` by default).
- Returns deterministic `partial` or `failed` envelopes for unsupported/missing/error paths.

## Install

```bash
pip install cadis-global
```

Legacy NE shapefile mode extras:

```bash
pip install "cadis-global[ne]"
```

## Public API

CGD world dataset mode (recommended):

```python
from pathlib import Path
from cadis_global import GlobalLookup

lookup = GlobalLookup.from_defaults(
    world_dataset_format="cgd",
    cgd_path=Path("/tmp/ne.global.v0.1.0.cgd"),
    cache_dir=Path("/tmp/cadis-cache"),
    update_to_latest=False,
)

result = lookup.lookup(25.0330, 121.5654)
```

CGD bootstrap mode from CDN tar.gz artifact:

```python
from cadis_global import GlobalLookup

lookup = GlobalLookup.from_defaults(
    world_dataset_format="cgd",
    cgd_cache_dir="/tmp/cadis-global-cache",
    cgd_dataset_id="ne.global",
    cgd_dataset_version="v0.1.0",
    cgd_update_to_latest=False,
    cgd_manifest_url="https://cdn.example.com/ne.global/manifest.json",
    # or use cgd_artifact_url directly when no remote manifest is available
    # cgd_artifact_url="https://cdn.example.com/ne.global/ne.global.v0.1.0.tar.gz",
    # cgd_sha256="<sha256-of-cgd-payload>",
)
```

Natural Earth shapefile mode (legacy compatibility):

```python
from pathlib import Path
from cadis_global import GlobalLookup

lookup = GlobalLookup.from_defaults(
    world_dataset_format="ne",
    country_dbf_path=Path("/path/to/world/ne_10m_admin_0_countries.dbf"),
    land_mask_path=Path("/path/to/world/ne_10m_land.shp"),
    ocean_mask_path=Path("/path/to/world/ne_10m_ocean.shp"),
    marine_names_path=Path("/path/to/world/ne_10m_geography_marine_polys.shp"),
    cache_dir=Path("/tmp/cadis-cache"),
    update_to_latest=False,
)

result = lookup.lookup(25.0330, 121.5654)
```

Notes:

- `world_dataset_format` supports `"cgd"` and `"ne"`.
- `"cgd"` mode requires `cadis-global-dataset` to be installed/importable.
- `"ne"` mode additionally requires `cadis-global[ne]` (shapely + fiona).
- CGD bootstrap uses direct manifest/tar.gz download; it does not use `cadis-cdn`.
- Default `world_dataset_format` is `"cgd"` in `GlobalLookup.from_defaults(...)`.
- `"ne"` mode is legacy compatibility fallback and should be selected explicitly.

Envelope contract:

```json
{
  "lookup_status": "ok|partial|failed",
  "engine": "cadis-global",
  "version": "0.1.0",
  "reason": "nullable status reason",
  "world_context": {"...": "world resolver payload"},
  "admin_result": {"...": "raw cadis-runtime payload or null"}
}
```

## Execution flow

1. Resolve world country/terminal state (`open_sea`, `antarctica`, `no_sovereign_land`).
2. If terminal: return world-only result (`admin_result = null`).
3. If country found: bootstrap/cache runtime for ISO2.
4. Execute `runtime.lookup(lat, lon)`.
5. Return unified envelope with `world_context` + untouched `admin_result`.

## Status semantics

- `ok`: world resolution succeeded; runtime either not needed (terminal) or returned a valid payload.
- `partial`: world resolution succeeded but admin runtime could not return a valid payload.
- `failed`: world resolution failed before runtime dispatch.

Common `reason` values for `partial`:

- `unsupported_country_dataset`
- `missing_dataset`
- `runtime_bootstrap_error`
- `runtime_dispatch_error`
- `runtime_invalid_response`
- `admin_interpretation_unavailable`

## Package boundaries

- `cadis-global`: orchestration/bootstrap/world routing.
- `cadis-runtime`: deterministic dataset interpreter only.
- `cadis-core` / `cadis-cdn`: internal-by-contract components.

## Distribution note

- `cadis-global-dataset` tooling is internal and not published to GitHub.
- The built global dataset artifact (for example `ne.global.v0.1.0.cgd`) is distributed alongside `cadis-global`.
