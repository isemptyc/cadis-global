"""Runtime dispatch and dataset bootstrap orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from cadis_runtime import CadisRuntime


BootstrapFactory = Callable[[str, Path, bool], Any]


class RuntimeRouter:
    """Country runtime registry with lazy bootstrap and caching."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        update_to_latest: bool = False,
        supported_iso2: Optional[set[str]] = None,
        bootstrap_factory: Optional[BootstrapFactory] = None,
    ):
        self._cache_dir = Path(cache_dir)
        self._update_to_latest = bool(update_to_latest)
        self._supported_iso2 = {
            code.strip().upper() for code in (supported_iso2 or {"TW", "JP"}) if code
        }
        self._bootstrap_factory = bootstrap_factory or self._default_bootstrap_factory
        self._runtime_cache: dict[str, Any] = {}

    @staticmethod
    def _default_bootstrap_factory(iso2: str, cache_dir: Path, update_to_latest: bool) -> Any:
        from_iso2 = getattr(CadisRuntime, "from_iso2", None)
        if not callable(from_iso2):
            raise RuntimeError(
                "CadisRuntime.from_iso2(...) is unavailable. "
                "Install cadis-runtime with bootstrap support."
            )
        return from_iso2(
            iso2,
            cache_dir=str(cache_dir),
            update_to_latest=update_to_latest,
        )

    def get_runtime(self, iso2: str) -> tuple[Optional[Any], Optional[str]]:
        """Return runtime for ISO2 or a deterministic failure reason."""
        normalized_iso2 = (iso2 or "").strip().upper()
        if not normalized_iso2:
            return None, "country_unresolved"

        if normalized_iso2 not in self._supported_iso2:
            return None, "unsupported_country_dataset"

        cached = self._runtime_cache.get(normalized_iso2)
        if cached is not None:
            return cached, None

        try:
            runtime = self._bootstrap_factory(
                normalized_iso2,
                self._cache_dir,
                self._update_to_latest,
            )
        except FileNotFoundError:
            return None, "missing_dataset"
        except Exception:
            return None, "runtime_bootstrap_error"

        self._runtime_cache[normalized_iso2] = runtime
        return runtime, None

    def dispatch(self, *, iso2: str, lat: float, lon: float) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """Dispatch lookup to country runtime, preserving runtime return payload."""
        runtime, reason = self.get_runtime(iso2)
        if runtime is None:
            return None, reason

        try:
            result = runtime.lookup(lat, lon)
        except Exception:
            return None, "runtime_dispatch_error"

        if result is None:
            return None, "admin_interpretation_unavailable"
        if isinstance(result, dict) and result.get("lookup_status") == "failed":
            return None, "admin_interpretation_unavailable"
        if not isinstance(result, dict):
            return None, "runtime_invalid_response"

        return result, None
