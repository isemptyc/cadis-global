# cadis-global

⚠️ This repository is deprecated.

The functionality previously provided by `cadis-global`
has been integrated into the unified `cadis` package
since Cadis v0.2.0.

`cadis-global` is the public orchestration layer for:

1. world-level resolution (`country` or terminal world state)
2. bundled CGD dataset loading
3. runtime dispatch via `cadis-runtime`

## Scope (v0.1.0)

- Uses `cadis-runtime` as admin execution engine.
- Ships with bundled `ne.global.v0.1.0.cgd`.
- Supports only explicitly configured/known ISO2 datasets (`TW`, `JP` by default).
- Returns deterministic `partial` or `failed` envelopes for unsupported/missing/error paths.

## Install

```bash
pip install cadis-global
```

## Public API

Bundled CGD world dataset mode (default):

```python
from cadis_global import GlobalLookup

lookup = GlobalLookup.from_defaults(
    cache_dir="/tmp/cadis-cache",
    update_to_latest=False,
)

result = lookup.lookup(25.0330, 121.5654)
```

Custom local CGD override:

```python
from pathlib import Path
from cadis_global import GlobalLookup

lookup = GlobalLookup.from_defaults(
    cgd_path=Path("/path/to/custom/ne.global.v0.1.0.cgd"),
    cache_dir=Path("/tmp/cadis-cache"),
    update_to_latest=False,
)

result = lookup.lookup(25.0330, 121.5654)
```

Notes:

- `"cgd"` mode uses bundled `ne.global.v0.1.0.cgd` by default.
- Set `cgd_path` to override the bundled dataset with a custom local CGD file.
- CGD binary spec lives at `cadis_global/data/CGD_SPEC.md`.
- Current bundled dataset/spec uses `float32` coordinates (bbox + geometry points).
- Custom CGD files must follow the same float32 layout expected by this runtime.

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

Runtime bootstrap note:

- Country runtime bootstrap is lazy per ISO2 and may trigger on-demand CDN download on first country hit.
- First lookup latency for an ISO2 can increase while bootstrap/download is in progress.
- If bootstrap/download cannot complete, result is deterministic `partial` with reason such as `missing_dataset` or `runtime_bootstrap_error`.

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
- Bundled dataset `ne.global.v0.1.0.cgd` is approximately 12 MB (uncompressed package content).
