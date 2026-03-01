"""World-level country and terminal-state resolver."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import fiona
except ModuleNotFoundError:  # pragma: no cover - import guard
    fiona = None

try:
    import shapely.geometry
    import shapely.ops
    import shapely.prepared
except ModuleNotFoundError:  # pragma: no cover - import guard
    shapely = None


@dataclass(frozen=True)
class CountryFeature:
    """Prepared country geometry for fast point-in-polygon lookup."""

    iso2: str
    name: str
    bbox: tuple[float, float, float, float]
    raw_geom: Any
    geom: Any


class GlobalSurfaceMask:
    """Land/ocean semantic gate based on Natural Earth layers."""

    def __init__(
        self,
        *,
        land_mask_path: Path,
        ocean_mask_path: Optional[Path] = None,
        marine_names_path: Optional[Path] = None,
    ):
        if shapely is None or fiona is None:
            raise ModuleNotFoundError(
                "GlobalSurfaceMask requires 'shapely' and 'fiona'."
            )
        self._prepared_land = self._load_prepared_union(land_mask_path)
        self._prepared_ocean = (
            self._load_prepared_union(ocean_mask_path)
            if ocean_mask_path is not None and ocean_mask_path.exists()
            else None
        )
        self._ocean_named: list[tuple[str, Any]] = []
        if marine_names_path is not None and marine_names_path.exists():
            self._load_marine_names(marine_names_path)

    @staticmethod
    def _load_prepared_union(path: Path) -> Any:
        geoms: list[Any] = []
        with fiona.open(path) as src:
            for feat in src:
                geom = feat.get("geometry")
                if geom:
                    geoms.append(shapely.geometry.shape(geom))
        if not geoms:
            raise ValueError(f"Mask contains no geometries: {path}")
        return shapely.prepared.prep(shapely.ops.unary_union(geoms))

    def _load_marine_names(self, path: Path) -> None:
        named: list[tuple[str, Any]] = []
        with fiona.open(path) as src:
            for feat in src:
                geom = feat.get("geometry")
                if not geom:
                    continue
                props = feat.get("properties") or {}
                name = (
                    props.get("NAME")
                    or props.get("name")
                    or props.get("NAME_LONG")
                    or props.get("name_long")
                )
                if not name:
                    continue
                shp = shapely.geometry.shape(geom)
                named.append((str(name), shapely.prepared.prep(shp)))
        self._ocean_named = named

    def is_land(self, lat: float, lon: float) -> bool:
        pt = shapely.geometry.Point(lon, lat)
        return bool(self._prepared_land.covers(pt))

    def is_ocean(self, lat: float, lon: float) -> bool:
        if self._prepared_ocean is None:
            return False
        pt = shapely.geometry.Point(lon, lat)
        return bool(self._prepared_ocean.covers(pt))

    def is_water(self, lat: float, lon: float) -> bool:
        if self.is_land(lat, lon):
            return False
        if self._prepared_ocean is None:
            return True
        return self.is_ocean(lat, lon)

    def ocean_name(self, lat: float, lon: float) -> Optional[str]:
        if not self._ocean_named:
            return None
        pt = shapely.geometry.Point(lon, lat)
        for name, prepared_geom in self._ocean_named:
            if prepared_geom.covers(pt):
                return name
        return None


class WorldCountryResolver:
    """Resolve coordinate to sovereign country or world terminal state."""

    ISO2_PATTERN = re.compile(r"^[A-Z]{2}$")
    ISO2_NORMALIZATION_MAP = {
        "CN-TW": "TW",
        "CN-HK": "HK",
        "CN-MO": "MO",
    }

    SOURCE = "natural_earth"
    OPEN_SEA_LABEL = "Open Sea"
    ANTARCTICA_ISO2 = "AQ"
    ANTARCTICA_LABEL = "Antarctica"
    NO_SOVEREIGN_LAND_LABEL = "No Sovereign Land"

    def __init__(
        self,
        *,
        country_dbf_path: Path,
        land_mask_path: Optional[Path] = None,
        ocean_mask_path: Optional[Path] = None,
        marine_names_path: Optional[Path] = None,
    ):
        if shapely is None or fiona is None:
            raise ModuleNotFoundError(
                "WorldCountryResolver requires 'shapely' and 'fiona'."
            )

        self._countries: list[CountryFeature] = []
        self._surface_mask: Optional[GlobalSurfaceMask] = None
        self._load(country_dbf_path)

        if land_mask_path is not None and land_mask_path.exists():
            self._surface_mask = GlobalSurfaceMask(
                land_mask_path=land_mask_path,
                ocean_mask_path=ocean_mask_path,
                marine_names_path=marine_names_path,
            )

    def _load(self, path: Path) -> None:
        if not Path(path).exists():
            raise FileNotFoundError(f"country_dbf_path not found: {path}")

        with fiona.open(path) as src:
            for feat in src:
                geom = feat.get("geometry")
                if not geom:
                    continue
                props = feat.get("properties") or {}
                iso2 = self._extract_iso2(props)
                name = props.get("NAME") or props.get("ADMIN")
                if not iso2 or not name:
                    continue
                shp = shapely.geometry.shape(geom)
                self._countries.append(
                    CountryFeature(
                        iso2=iso2,
                        name=str(name),
                        bbox=tuple(shp.bounds),
                        raw_geom=shp,
                        geom=shapely.prepared.prep(shp),
                    )
                )

        if not self._countries:
            raise ValueError(f"No country polygons loaded from: {path}")

    def _extract_iso2(self, props: dict[str, Any]) -> Optional[str]:
        candidate_keys = ("ISO_A2_EH", "WB_A2", "ISO_A2", "ISO2", "ISO")
        for key in candidate_keys:
            raw = props.get(key)
            if raw is None:
                continue
            iso2 = str(raw).strip().upper()
            if not iso2 or iso2 == "-99":
                continue
            iso2 = self.ISO2_NORMALIZATION_MAP.get(iso2, iso2)
            if self.ISO2_PATTERN.fullmatch(iso2):
                return iso2
        return None

    @staticmethod
    def _point_in_bbox(point: Any, bbox: tuple[float, float, float, float]) -> bool:
        min_lon, min_lat, max_lon, max_lat = bbox
        return min_lon <= point.x <= max_lon and min_lat <= point.y <= max_lat

    def _find_country(self, point: Any) -> Optional[CountryFeature]:
        for country in self._countries:
            if not self._point_in_bbox(point, country.bbox):
                continue
            if country.geom.contains(point):
                return country
        return None

    def resolve(self, lat: float, lon: float) -> dict[str, Any]:
        """Resolve point to country or world terminal state envelope."""
        point = shapely.geometry.Point(lon, lat)
        resolved_at = datetime.now(timezone.utc).isoformat()

        country = self._find_country(point)
        if country is not None:
            if country.iso2 == self.ANTARCTICA_ISO2:
                return {
                    "lookup_status": "ok",
                    "source": self.SOURCE,
                    "resolved_at": resolved_at,
                    "resolution_method": "antarctica",
                    "country": {
                        "iso2": country.iso2,
                        "name": country.name,
                    },
                    "world_result": {
                        "type": "antarctica",
                        "name": self.ANTARCTICA_LABEL,
                    },
                }
            return {
                "lookup_status": "ok",
                "source": self.SOURCE,
                "resolved_at": resolved_at,
                "country": {
                    "iso2": country.iso2,
                    "name": country.name,
                },
            }

        if self._surface_mask is not None and self._surface_mask.is_land(lat, lon):
            return {
                "lookup_status": "ok",
                "source": self.SOURCE,
                "resolved_at": resolved_at,
                "resolution_method": "no_sovereign_land",
                "world_result": {
                    "type": "no_sovereign_land",
                    "name": self.NO_SOVEREIGN_LAND_LABEL,
                },
            }

        ocean_name = None
        if self._surface_mask is not None and self._surface_mask.is_water(lat, lon):
            ocean_name = self._surface_mask.ocean_name(lat, lon)

        return {
            "lookup_status": "ok",
            "source": self.SOURCE,
            "resolved_at": resolved_at,
            "resolution_method": "open_sea",
            "world_result": {
                "type": "open_sea",
                "name": ocean_name or self.OPEN_SEA_LABEL,
            },
        }
