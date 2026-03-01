"""Public global orchestration entrypoint."""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import Any, Optional

from .cgd_world_resolver import CGDWorldResolver
from .router import RuntimeRouter
from .version import __version__


class GlobalLookup:
    """Public orchestration layer for world routing + runtime dispatch."""

    ENGINE = "cadis-global"
    VERSION = __version__
    WORLD_TERMINAL_METHODS = {"open_sea", "antarctica", "no_sovereign_land"}
    PARTIAL_REASONS = {
        "unsupported_country_dataset",
        "missing_dataset",
        "runtime_bootstrap_error",
        "runtime_dispatch_error",
        "runtime_invalid_response",
        "admin_interpretation_unavailable",
        "country_unresolved",
    }

    def __init__(self, *, world_resolver: Any, router: RuntimeRouter):
        self._world_resolver = world_resolver
        self._router = router

    @classmethod
    def from_defaults(
        cls,
        *,
        cgd_path: Optional[Path] = None,
        cgd_dataset_id: str = "ne.global",
        cgd_dataset_version: Optional[str] = "v0.1.0",
        cache_dir: Path = Path("/tmp/cadis-cache"),
        update_to_latest: bool = False,
        supported_iso2: Optional[set[str]] = None,
    ) -> "GlobalLookup":
        """Build GlobalLookup with bundled-CGD resolver and runtime router."""
        if cgd_path is None:
            bundled = cls._resolve_bundled_cgd_path(
                dataset_id=cgd_dataset_id,
                dataset_version=cgd_dataset_version,
            )
            if bundled is None:
                raise FileNotFoundError(
                    "Bundled CGD dataset not found. "
                    "Provide cgd_path explicitly or install a wheel that includes "
                    f"'{cgd_dataset_id}.{cgd_dataset_version}.cgd'."
                )
            cgd_path = bundled
        world_resolver = CGDWorldResolver(cgd_path=Path(cgd_path))
        router = RuntimeRouter(
            cache_dir=Path(cache_dir),
            update_to_latest=update_to_latest,
            supported_iso2=supported_iso2,
        )
        return cls(world_resolver=world_resolver, router=router)

    @staticmethod
    def _resolve_bundled_cgd_path(*, dataset_id: str, dataset_version: Optional[str]) -> Optional[Path]:
        if dataset_id != "ne.global" or not dataset_version:
            return None
        filename = f"{dataset_id}.{dataset_version}.cgd"
        try:
            candidate = importlib.resources.files("cadis_global").joinpath("data").joinpath(filename)
            if candidate.is_file():
                return Path(candidate)
        except Exception:
            return None
        return None

    def lookup(self, lat: float, lon: float) -> dict[str, Any]:
        """Execute world resolution + runtime dispatch and return unified envelope."""
        try:
            world_context = self._world_resolver.resolve(lat, lon)
        except Exception as exc:
            return self._failed(world_context={"lookup_status": "failed", "error": str(exc)}, reason="world_runtime_error")

        if world_context.get("lookup_status") != "ok":
            return self._failed(world_context=world_context, reason="world_resolution_failed")

        if world_context.get("resolution_method") in self.WORLD_TERMINAL_METHODS:
            return {
                "lookup_status": "ok",
                "engine": self.ENGINE,
                "version": self.VERSION,
                "reason": "world_terminal",
                "world_context": world_context,
                "admin_result": None,
            }

        country = world_context.get("country") or {}
        iso2 = country.get("iso2")
        admin_result, reason = self._router.dispatch(iso2=iso2 or "", lat=lat, lon=lon)
        if reason:
            return self._partial(world_context=world_context, reason=reason)

        return {
            "lookup_status": "ok",
            "engine": self.ENGINE,
            "version": self.VERSION,
            "reason": None,
            "world_context": world_context,
            "admin_result": admin_result,
        }

    def _partial(self, *, world_context: dict[str, Any], reason: str) -> dict[str, Any]:
        safe_reason = reason if reason in self.PARTIAL_REASONS else "admin_interpretation_unavailable"
        return {
            "lookup_status": "partial",
            "engine": self.ENGINE,
            "version": self.VERSION,
            "reason": safe_reason,
            "world_context": world_context,
            "admin_result": None,
        }

    def _failed(self, *, world_context: dict[str, Any], reason: str) -> dict[str, Any]:
        return {
            "lookup_status": "failed",
            "engine": self.ENGINE,
            "version": self.VERSION,
            "reason": reason,
            "world_context": world_context,
            "admin_result": None,
        }
