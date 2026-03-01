"""Bootstrap manager for CGD world dataset artifacts (.tar.gz)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional


class CGDBootstrapManager:
    """Offline-first bootstrap/cache manager for CGD dataset artifacts."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        dataset_id: str = "ne.global",
        dataset_version: Optional[str] = None,
        update_to_latest: bool = False,
        manifest_url: Optional[str] = None,
        artifact_url: Optional[str] = None,
        expected_cgd_sha256: Optional[str] = None,
        timeout_sec: int = 30,
    ):
        self._cache_dir = Path(cache_dir)
        self._dataset_id = dataset_id
        self._dataset_version = dataset_version
        self._update_to_latest = bool(update_to_latest)
        self._manifest_url = manifest_url
        self._artifact_url = artifact_url
        self._expected_cgd_sha256 = expected_cgd_sha256
        self._timeout_sec = timeout_sec

    def ensure_dataset(self) -> Path:
        """Return local CGD path, downloading/extracting tar.gz only when needed."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        with self._file_lock(self._cache_dir / ".cgd_bootstrap.lock"):
            if self._dataset_version and not self._update_to_latest:
                cached = self._resolve_cached_cgd(self._dataset_version)
                if cached is not None:
                    return cached

            remote_manifest = self._resolve_remote_manifest()
            dataset_version = str(
                remote_manifest.get("dataset_version")
                or self._dataset_version
                or "latest"
            )
            cgd_sha256 = str(
                remote_manifest.get("sha256")
                or remote_manifest.get("cgd_sha256")
                or self._expected_cgd_sha256
                or ""
            )

            if not self._update_to_latest:
                cached = self._resolve_cached_cgd(dataset_version, expected_sha256=cgd_sha256 or None)
                if cached is not None:
                    return cached

            artifact_url = self._resolve_artifact_url(remote_manifest)
            artifact_sha256 = remote_manifest.get("artifact_sha256")
            cgd_filename = remote_manifest.get("cgd_filename")

            return self._download_install(
                dataset_version=dataset_version,
                artifact_url=artifact_url,
                cgd_sha256=(cgd_sha256 or None),
                artifact_sha256=(str(artifact_sha256) if artifact_sha256 else None),
                cgd_filename=(str(cgd_filename) if cgd_filename else None),
                manifest_payload=remote_manifest,
            )

    def _resolve_cached_cgd(self, dataset_version: str, expected_sha256: Optional[str] = None) -> Optional[Path]:
        version_dir = self._version_dir(dataset_version)
        cgd_path = version_dir / f"{self._dataset_id}.{dataset_version}.cgd"
        if not cgd_path.exists():
            return None

        if expected_sha256:
            actual = self._sha256_file(cgd_path)
            if actual.lower() != expected_sha256.lower():
                return None

        return cgd_path

    def _resolve_remote_manifest(self) -> dict[str, Any]:
        if self._manifest_url:
            payload = json.loads(self._fetch_text(self._manifest_url))
            if not isinstance(payload, dict):
                raise ValueError("CGD manifest must be a JSON object")
            return payload

        if self._artifact_url:
            if not self._dataset_version:
                raise ValueError("dataset_version is required when using artifact_url without manifest_url")
            return {
                "dataset_id": self._dataset_id,
                "dataset_version": self._dataset_version,
                "artifact_url": self._artifact_url,
                "sha256": self._expected_cgd_sha256,
            }

        raise ValueError(
            "CGD bootstrap requires either manifest_url or artifact_url when cgd_path is not provided"
        )

    def _resolve_artifact_url(self, manifest: dict[str, Any]) -> str:
        raw_url = manifest.get("artifact_url") or self._artifact_url
        if not raw_url:
            raise ValueError("CGD manifest missing artifact_url")
        raw_url = str(raw_url)

        if self._manifest_url:
            return urllib.parse.urljoin(self._manifest_url, raw_url)
        return raw_url

    def _download_install(
        self,
        *,
        dataset_version: str,
        artifact_url: str,
        cgd_sha256: Optional[str],
        artifact_sha256: Optional[str],
        cgd_filename: Optional[str],
        manifest_payload: dict[str, Any],
    ) -> Path:
        version_dir = self._version_dir(dataset_version)
        version_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="cgd-bootstrap-") as tmp:
            tmp_dir = Path(tmp)
            artifact_tmp = tmp_dir / "dataset.tar.gz"
            self._download_file(artifact_url, artifact_tmp)

            if artifact_sha256:
                actual_artifact_sha = self._sha256_file(artifact_tmp)
                if actual_artifact_sha.lower() != artifact_sha256.lower():
                    raise ValueError("CGD artifact sha256 mismatch")

            extract_dir = tmp_dir / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            self._safe_extract_tar_gz(artifact_tmp, extract_dir)

            extracted_cgd = self._locate_cgd(extract_dir, cgd_filename)
            if cgd_sha256:
                actual_cgd_sha = self._sha256_file(extracted_cgd)
                if actual_cgd_sha.lower() != cgd_sha256.lower():
                    raise ValueError("CGD payload sha256 mismatch")

            target_cgd = version_dir / f"{self._dataset_id}.{dataset_version}.cgd"
            self._atomic_copy(extracted_cgd, target_cgd)

            manifest_out = dict(manifest_payload)
            manifest_out.setdefault("dataset_id", self._dataset_id)
            manifest_out.setdefault("dataset_version", dataset_version)
            manifest_out.setdefault("artifact_url", artifact_url)
            if cgd_sha256:
                manifest_out["sha256"] = cgd_sha256
            (version_dir / "manifest.json").write_text(
                json.dumps(manifest_out, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            return target_cgd

    def _version_dir(self, dataset_version: str) -> Path:
        return self._cache_dir / "cgd" / self._dataset_id / dataset_version

    def _fetch_text(self, url: str) -> str:
        with urllib.request.urlopen(url, timeout=self._timeout_sec) as resp:
            return resp.read().decode("utf-8")

    def _download_file(self, url: str, dest_path: Path) -> None:
        with urllib.request.urlopen(url, timeout=self._timeout_sec) as resp:
            with dest_path.open("wb") as f:
                shutil.copyfileobj(resp, f)

    def _safe_extract_tar_gz(self, tar_path: Path, dest_dir: Path) -> None:
        with tarfile.open(tar_path, mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isreg():
                    continue
                name = member.name
                if name.startswith("/"):
                    raise ValueError("Unsafe tar member path")
                target = (dest_dir / name).resolve()
                if not str(target).startswith(str(dest_dir.resolve())):
                    raise ValueError("Unsafe tar path traversal detected")
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tar.extractfile(member)
                if src is None:
                    continue
                with src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)

    def _locate_cgd(self, root: Path, cgd_filename: Optional[str]) -> Path:
        if cgd_filename:
            candidate = root / cgd_filename
            if candidate.exists() and candidate.is_file():
                return candidate
            # fallback by basename search
            matches = list(root.rglob(Path(cgd_filename).name))
            if len(matches) == 1 and matches[0].is_file():
                return matches[0]
            raise FileNotFoundError(f"CGD file declared in manifest not found: {cgd_filename}")

        matches = [p for p in root.rglob("*.cgd") if p.is_file()]
        if not matches:
            raise FileNotFoundError("No .cgd found in downloaded artifact")
        if len(matches) > 1:
            raise ValueError("Multiple .cgd files found; provide cgd_filename in manifest")
        return matches[0]

    def _atomic_copy(self, src: Path, dest: Path) -> None:
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    @contextlib.contextmanager
    def _file_lock(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as lock_file:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                try:
                    import fcntl

                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
