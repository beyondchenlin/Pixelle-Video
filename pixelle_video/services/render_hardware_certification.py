from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Iterable

from pixelle_video.services.render_output_probe import RenderOutputProbe
from pixelle_video.utils.ffmpeg_encoder import supported_hardware_h264_codecs

HARDWARE_HOST_REPORT_VERSION = "render_hardware_host_report.v1"
HARDWARE_CERTIFICATION_REPORT_VERSION = "render_hardware_certification_report.v1"
_MAX_JSON_EVIDENCE_BYTES = 1024 * 1024
_MAX_VIDEO_EVIDENCE_BYTES = 64 * 1024 * 1024
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")


def collect_hardware_provenance(*, repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    revision = _git_text(root, "rev-parse", "HEAD")
    status = _git_text(root, "status", "--porcelain", "--untracked-files=all")
    ffmpeg_version = _command_first_line(("ffmpeg", "-hide_banner", "-version"))
    github_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    return {
        "source_revision": revision,
        "source_tree_clean": status == "",
        "host": {
            "operating_system": platform.system(),
            "operating_system_release": platform.release(),
            "architecture": platform.machine(),
            "ffmpeg_version": ffmpeg_version,
            "hardware_devices": _hardware_device_inventory(),
        },
        "ci": {
            "provider": "github_actions" if github_actions else "local",
            "run_id": os.environ.get("GITHUB_RUN_ID") if github_actions else None,
            "run_attempt": (
                os.environ.get("GITHUB_RUN_ATTEMPT") if github_actions else None
            ),
            "job": os.environ.get("GITHUB_JOB") if github_actions else None,
        },
    }


def build_file_evidence(*, path: str | Path, evidence_root: str | Path) -> dict[str, Any]:
    root = Path(evidence_root).resolve()
    unresolved_artifact = Path(path)
    if unresolved_artifact.is_symlink():
        raise ValueError(f"hardware evidence must not be a symbolic link: {path}")
    artifact = unresolved_artifact.resolve(strict=True)
    try:
        relative = artifact.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"hardware evidence resolves outside its report root: {artifact}") from exc
    if artifact.is_symlink() or not artifact.is_file():
        raise ValueError(f"hardware evidence must be a regular file: {artifact}")
    size_bytes = artifact.stat().st_size
    if size_bytes <= 0:
        raise ValueError(f"hardware evidence must be non-empty: {artifact}")
    return {
        "relative_path": relative.as_posix(),
        "size_bytes": size_bytes,
        "sha256": _sha256_file(artifact),
    }


def sanitize_hardware_diagnostic(
    value: object,
    *,
    private_roots: Iterable[str | Path] = (),
) -> str:
    """Bound diagnostics and remove host-specific roots before artifact upload."""

    text = str(value or "")
    supplied_roots = [str(item) for item in private_roots if str(item)]
    roots: list[tuple[str, str]] = [
        ("<repo>", supplied_roots[0])
    ] if supplied_roots else []
    roots.extend(
        ("<private-root>", item)
        for item in supplied_roots[1:]
    )
    for label, candidate in (
        ("<runner-temp>", os.environ.get("RUNNER_TEMP", "")),
        ("<workspace>", os.environ.get("GITHUB_WORKSPACE", "")),
        ("<home>", Path.home()),
    ):
        raw = str(candidate or "").strip()
        if raw:
            roots.append((label, raw))
    for label, raw in sorted(roots, key=lambda item: len(item[1]), reverse=True):
        variants = {raw, raw.replace("\\", "/"), raw.replace("/", "\\")}
        for variant in sorted(variants, key=len, reverse=True):
            if variant:
                text = re.sub(re.escape(variant), label, text, flags=re.IGNORECASE)
    text = "".join(character for character in text if character >= " " or character in "\n\t")
    return text[:2000]


class HardwareCertificationAggregator:
    """Fail-closed aggregation of exact-codec reports from trusted device runners."""

    def __init__(self, *, probe: RenderOutputProbe | None = None) -> None:
        self.probe = probe or RenderOutputProbe()

    def aggregate(
        self,
        *,
        evidence_root: str | Path,
        output_path: str | Path,
        expected_run_id: str,
        expected_revision: str,
    ) -> dict[str, Any]:
        root = Path(evidence_root).resolve()
        supported = supported_hardware_h264_codecs()
        revision = self._normalize_revision(expected_revision)
        run_id = self._normalize_run_id(expected_run_id)
        reports = (
            sorted(root.glob("hardware-*/hardware_report.json"))
            if root.is_dir()
            else []
        )
        errors: list[str] = []
        summaries: list[dict[str, Any]] = []
        passed: dict[str, dict[str, Any]] = {}
        if not reports:
            errors.append("no hardware host reports found under evidence root")
        elif len(reports) > len(supported):
            errors.append(
                "hardware evidence contains more host reports than supported codecs"
            )
        for report_path in reports:
            report_errors: list[str] = []
            relative_report = report_path.relative_to(root).as_posix()
            if report_path.parent.is_symlink() or report_path.is_symlink():
                errors.append(
                    f"{relative_report}: report path must not contain symbolic links"
                )
                continue
            resolved_report = report_path.resolve()
            try:
                resolved_report.relative_to(root)
            except ValueError:
                errors.append(f"{relative_report}: report resolves outside evidence root")
                continue
            try:
                report = _read_json_object(resolved_report)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"{relative_report}: invalid report: {exc}")
                continue
            raw_codec = str(report.get("required_codec") or "")
            codec = _bounded_text(raw_codec, limit=64)
            if raw_codec != codec:
                report_errors.append("required codec identifier is too long")
            if report.get("version") != HARDWARE_HOST_REPORT_VERSION:
                report_errors.append("unsupported hardware host report version")
            if report.get("kind") != "hardware_host_matrix":
                report_errors.append("unexpected hardware host report kind")
            if codec not in supported:
                report_errors.append(f"required codec is not product-supported: {codec!r}")
            if report.get("supported_codecs") != list(supported):
                report_errors.append("report hardware codec registry does not match product")
            if report.get("requested_codecs") != [codec]:
                report_errors.append("exact-codec report requested an unexpected codec set")
            if report.get("ok") is not True or report.get("host_ok") is not True:
                report_errors.append("hardware host gate did not pass")
            report_gate_errors = report.get("errors")
            if not isinstance(report_gate_errors, list) or report_gate_errors:
                report_errors.append("hardware host report contains gate errors")
            actual_revision = _bounded_text(report.get("source_revision"), limit=64)
            if actual_revision != revision:
                report_errors.append(
                    "source revision mismatch: "
                    f"expected {revision}, got {actual_revision!r}"
                )
            if report.get("source_tree_clean") is not True:
                report_errors.append("source tree was not clean when evidence was generated")
            host = _normalized_host(report.get("host"))
            for field in (
                "operating_system",
                "operating_system_release",
                "architecture",
                "ffmpeg_version",
            ):
                if not str(host.get(field) or "").strip():
                    report_errors.append(f"host provenance is missing {field}")
            hardware_devices = host.get("hardware_devices")
            if (
                not isinstance(hardware_devices, list)
                or not hardware_devices
                or not all(
                    isinstance(item, str) and item.strip()
                    for item in hardware_devices
                )
            ):
                report_errors.append("host provenance is missing hardware device identity")
            elif not _device_inventory_matches_codec(codec, hardware_devices):
                report_errors.append(
                    "hardware device identity does not match the required codec family"
                )
            ci = _normalized_ci(report.get("ci"))
            if ci.get("provider") != "github_actions":
                report_errors.append("report was not generated by GitHub Actions")
            if str(ci.get("run_id") or "") != run_id:
                report_errors.append(
                    "workflow run mismatch: "
                    f"expected {run_id}, got {ci.get('run_id')!r}"
                )
            if not str(ci.get("job") or "").strip():
                report_errors.append("report is missing its workflow job identity")
            results = report.get("results")
            if not isinstance(results, list) or len(results) != 1:
                report_errors.append("exact-codec report must contain exactly one result")
                result: dict[str, Any] = {}
            else:
                candidate = results[0]
                result = candidate if isinstance(candidate, dict) else {}
                if not result:
                    report_errors.append("hardware result must be an object")
            if result:
                if result.get("codec") != codec:
                    report_errors.append("result codec does not match required codec")
                if result.get("hardware") is not True:
                    report_errors.append("result is not marked as a hardware encoder")
                if result.get("available_on_host") is not True:
                    report_errors.append("required hardware device was unavailable")
                if result.get("status") != "passed" or result.get("ok") is not True:
                    report_errors.append(
                        f"hardware result did not pass: {result.get('status')!r}"
                    )
                if result.get("encoder_backend") != codec:
                    report_errors.append("final artifact used a different encoder backend")
                self._validate_result_files(
                    report_root=resolved_report.parent,
                    codec=codec,
                    result=result,
                    errors=report_errors,
                )
            if report.get("available_codecs") != [codec]:
                report_errors.append("available codec summary is inconsistent")
            if report.get("unavailable_codecs") != []:
                report_errors.append("exact-codec passing report lists unavailable codecs")
            if report.get("passed_codecs") != [codec]:
                report_errors.append("passed codec summary is inconsistent")
            if codec in passed:
                report_errors.append(f"duplicate passing report for codec {codec}")
            summary = {
                "report": relative_report,
                "codec": codec,
                "host": host,
                "ci": ci,
                "artifact": result.get("artifact") if result else None,
                "errors": report_errors,
                "ok": not report_errors,
            }
            summaries.append(summary)
            if report_errors:
                errors.extend(f"{relative_report}: {item}" for item in report_errors)
            elif codec:
                passed[codec] = summary
        missing = [codec for codec in supported if codec not in passed]
        if missing:
            errors.append(
                "missing verified hardware evidence for: " + ", ".join(missing)
            )
        payload = {
            "version": HARDWARE_CERTIFICATION_REPORT_VERSION,
            "kind": "hardware_cross_device_certification",
            "source_revision": revision,
            "workflow_run_id": run_id,
            "supported_codecs": list(supported),
            "passed_codecs": [codec for codec in supported if codec in passed],
            "missing_codecs": missing,
            "reports": summaries,
            "errors": errors,
            "ok": not errors,
        }
        _write_json_report(output_path, payload)
        return payload

    def _validate_result_files(
        self,
        *,
        report_root: Path,
        codec: str,
        result: dict[str, Any],
        errors: list[str],
    ) -> None:
        artifact = self._resolve_file_evidence(
            report_root=report_root,
            evidence=result.get("artifact"),
            label="final video",
            max_size_bytes=_MAX_VIDEO_EVIDENCE_BYTES,
            errors=errors,
        )
        probe_artifact = self._resolve_file_evidence(
            report_root=report_root,
            evidence=result.get("probe_artifact"),
            label="output probe",
            max_size_bytes=_MAX_JSON_EVIDENCE_BYTES,
            errors=errors,
        )
        if probe_artifact is not None:
            try:
                probe_payload = _read_json_object(probe_artifact)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"output probe is invalid: {exc}")
            else:
                if probe_payload.get("ok") is not True:
                    errors.append("output probe did not pass")
                if probe_payload.get("encoder_backend") != codec:
                    errors.append("output probe encoder does not match required codec")
                if int(probe_payload.get("lossy_encode_count") or 0) != 1:
                    errors.append("output probe does not prove a single lossy encode")
                expected_artifact_path = (
                    result.get("artifact", {}).get("relative_path")
                    if isinstance(result.get("artifact"), dict)
                    else None
                )
                if probe_payload.get("path_kind") != "relative_to_report_root":
                    errors.append("output probe path is not portable")
                if probe_payload.get("path") != expected_artifact_path:
                    errors.append("output probe path does not match final video evidence")
        if artifact is not None:
            try:
                self.probe.validate(
                    output_path=artifact,
                    width=320,
                    height=180,
                    fps=30,
                    duration=1.2,
                    report_path=None,
                    encoder_backend=codec,
                    lossy_encode_count=1,
                )
            except Exception as exc:
                errors.append(
                    "final video failed independent aggregate probe: "
                    + sanitize_hardware_diagnostic(
                        exc,
                        private_roots=(report_root,),
                    )
                )

    @staticmethod
    def _resolve_file_evidence(
        *,
        report_root: Path,
        evidence: object,
        label: str,
        max_size_bytes: int,
        errors: list[str],
    ) -> Path | None:
        if not isinstance(evidence, dict):
            errors.append(f"{label} evidence is missing")
            return None
        relative_text = str(evidence.get("relative_path") or "")
        if len(relative_text) > 1024:
            errors.append(f"{label} evidence path is too long")
            return None
        relative = Path(relative_text)
        if not relative_text or relative.is_absolute():
            errors.append(f"{label} evidence path must be relative")
            return None
        root = report_root.resolve()
        unresolved_candidate = root / relative
        if _path_has_symlink_within(unresolved_candidate, root=root):
            errors.append(f"{label} evidence must not be a symbolic link")
            return None
        candidate = unresolved_candidate.resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            errors.append(f"{label} evidence path escapes its report root")
            return None
        if candidate.is_symlink() or not candidate.is_file():
            errors.append(f"{label} evidence file does not exist")
            return None
        actual_size = candidate.stat().st_size
        if actual_size <= 0 or actual_size > max_size_bytes:
            errors.append(
                f"{label} evidence size must be between 1 and {max_size_bytes} bytes"
            )
            return None
        expected_size = evidence.get("size_bytes")
        if not isinstance(expected_size, int) or expected_size <= 0:
            errors.append(f"{label} evidence size is invalid")
        elif actual_size != expected_size:
            errors.append(f"{label} evidence size does not match report")
        expected_digest = str(evidence.get("sha256") or "").lower()
        if not _SHA256_PATTERN.fullmatch(expected_digest):
            errors.append(f"{label} evidence digest is invalid")
        elif _sha256_file(candidate) != expected_digest:
            errors.append(f"{label} evidence digest does not match report")
        return candidate

    @staticmethod
    def _normalize_revision(value: str) -> str:
        revision = str(value or "").strip().lower()
        if not _REVISION_PATTERN.fullmatch(revision):
            raise ValueError("expected_revision must be a full 40-character Git commit SHA")
        return revision

    @staticmethod
    def _normalize_run_id(value: str) -> str:
        run_id = str(value or "").strip()
        if not run_id or len(run_id) > 128 or any(character.isspace() for character in run_id):
            raise ValueError("expected_run_id must be a non-empty bounded identifier")
        return run_id


def _git_text(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _command_first_line(command: tuple[str, ...]) -> str:
    output = _bounded_command_output(command, limit=2048)
    return next((line.strip() for line in output.splitlines() if line.strip()), "")


def _hardware_device_inventory() -> list[str]:
    commands: list[tuple[str, ...]] = [
        (
            "nvidia-smi",
            "--query-gpu=name,driver_version",
            "--format=csv,noheader",
        ),
    ]
    if platform.system() == "Windows":
        commands.append(
            (
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | "
                "ForEach-Object { \"$($_.Name) | driver=$($_.DriverVersion)\" }",
            )
        )
    else:
        commands.append(("lspci", "-mm", "-nn"))
    values: list[str] = []
    for command in commands:
        output = _bounded_command_output(command, limit=8192)
        for line in output.splitlines():
            normalized = " ".join(line.strip().split())
            if not normalized:
                continue
            if command[0] == "lspci" and not any(
                marker in normalized.lower()
                for marker in ("vga compatible", "display controller", "3d controller")
            ):
                continue
            values.append(normalized[:512])
    if platform.system() == "Linux":
        for uevent_path in sorted(Path("/sys/class/drm").glob("card*/device/uevent")):
            try:
                raw = uevent_path.read_text(encoding="utf-8", errors="replace")[:16384]
            except OSError:
                continue
            fields = {}
            for line in raw.splitlines():
                key, separator, value = line.partition("=")
                if separator and key in {"DRIVER", "PCI_ID", "PCI_SUBSYS_ID"}:
                    fields[key] = value.strip()
            if fields:
                values.append(
                    " | ".join(
                        f"{key.lower()}={fields[key]}"
                        for key in ("DRIVER", "PCI_ID", "PCI_SUBSYS_ID")
                        if fields.get(key)
                    )[:512]
                )
    return list(dict.fromkeys(values))[:16]


def _bounded_command_output(command: tuple[str, ...], *, limit: int) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ""
    output = completed.stdout if completed.returncode == 0 else completed.stderr
    return output[:limit]


def _normalized_host(value: object) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    devices = source.get("hardware_devices")
    return {
        "operating_system": _bounded_text(source.get("operating_system"), limit=128),
        "operating_system_release": _bounded_text(
            source.get("operating_system_release"),
            limit=128,
        ),
        "architecture": _bounded_text(source.get("architecture"), limit=128),
        "ffmpeg_version": _bounded_text(source.get("ffmpeg_version"), limit=512),
        "hardware_devices": [
            _bounded_text(item, limit=512)
            for item in (devices if isinstance(devices, list) else [])[:16]
            if isinstance(item, str) and item.strip()
        ],
    }


def _normalized_ci(value: object) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "provider": _bounded_text(source.get("provider"), limit=64),
        "run_id": _bounded_text(source.get("run_id"), limit=128),
        "run_attempt": _bounded_text(source.get("run_attempt"), limit=32),
        "job": _bounded_text(source.get("job"), limit=128),
    }


def _bounded_text(value: object, *, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _device_inventory_matches_codec(codec: str, devices: list[str]) -> bool:
    normalized = "\n".join(devices).casefold()
    if codec == "h264_nvenc":
        return "nvidia" in normalized or "pci_id=10de:" in normalized
    if codec == "h264_qsv":
        return "intel" in normalized or "pci_id=8086:" in normalized
    if codec == "h264_vaapi":
        return any(
            marker in normalized
            for marker in (
                "driver=",
                "pci_id=",
                "intel",
                "nvidia",
                "amd",
                "radeon",
            )
        )
    return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_has_symlink_within(path: Path, *, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            return True
    return False


def _read_json_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"JSON evidence must be a regular file: {path}")
    size = path.stat().st_size
    if size <= 0 or size > _MAX_JSON_EVIDENCE_BYTES:
        raise ValueError(
            f"JSON evidence size must be between 1 and {_MAX_JSON_EVIDENCE_BYTES} bytes"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON evidence root must be an object")
    return payload


def _write_json_report(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


__all__ = [
    "HARDWARE_CERTIFICATION_REPORT_VERSION",
    "HARDWARE_HOST_REPORT_VERSION",
    "HardwareCertificationAggregator",
    "build_file_evidence",
    "collect_hardware_provenance",
    "sanitize_hardware_diagnostic",
]
