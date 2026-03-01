"""Public global orchestration entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .cgd_bootstrap import CGDBootstrapManager
from .cgd_world_resolver import CGDWorldResolver
from .router import RuntimeRouter
from .version import __version__
from .world_resolver import WorldCountryResolver


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
        world_dataset_format: str = "cgd",
        cgd_path: Optional[Path] = None,
        cgd_cache_dir: Path = Path("/tmp/cadis-global-cache"),
        cgd_dataset_id: str = "ne.global",
        cgd_dataset_version: Optional[str] = None,
        cgd_update_to_latest: bool = False,
        cgd_manifest_url: Optional[str] = None,
        cgd_artifact_url: Optional[str] = None,
        cgd_sha256: Optional[str] = None,
        country_dbf_path: Optional[Path] = None,
        land_mask_path: Optional[Path] = None,
        ocean_mask_path: Optional[Path] = None,
        marine_names_path: Optional[Path] = None,
        cache_dir: Path = Path("/tmp/cadis-cache"),
        update_to_latest: bool = False,
        supported_iso2: Optional[set[str]] = None,
    ) -> "GlobalLookup":
        """Build GlobalLookup with default resolver/router implementations.

        Default world resolver is CGD (`world_dataset_format="cgd"`).
        Use `world_dataset_format="ne"` only for legacy shapefile fallback mode.
        """
        normalized_format = (world_dataset_format or "ne").strip().lower()
        if normalized_format == "cgd":
            if cgd_path is None:
                bootstrap = CGDBootstrapManager(
                    cache_dir=Path(cgd_cache_dir),
                    dataset_id=cgd_dataset_id,
                    dataset_version=cgd_dataset_version,
                    update_to_latest=cgd_update_to_latest,
                    manifest_url=cgd_manifest_url,
                    artifact_url=cgd_artifact_url,
                    expected_cgd_sha256=cgd_sha256,
                )
                cgd_path = bootstrap.ensure_dataset()
            world_resolver = CGDWorldResolver(cgd_path=Path(cgd_path))
        elif normalized_format == "ne":
            if country_dbf_path is None:
                raise ValueError("country_dbf_path is required when world_dataset_format='ne'")
            world_resolver = WorldCountryResolver(
                country_dbf_path=Path(country_dbf_path),
                land_mask_path=Path(land_mask_path) if land_mask_path is not None else None,
                ocean_mask_path=Path(ocean_mask_path) if ocean_mask_path is not None else None,
                marine_names_path=Path(marine_names_path) if marine_names_path is not None else None,
            )
        else:
            raise ValueError(
                "world_dataset_format must be one of: 'cgd', 'ne' "
                f"(got: {world_dataset_format!r})"
            )
        router = RuntimeRouter(
            cache_dir=Path(cache_dir),
            update_to_latest=update_to_latest,
            supported_iso2=supported_iso2,
        )
        return cls(world_resolver=world_resolver, router=router)

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
