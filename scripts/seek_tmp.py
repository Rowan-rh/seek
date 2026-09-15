#!/usr/bin/env python3
"""Create isolated repository-local temporary workspaces for seek development."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence


SCHEMA_VERSION = 1
STAGE_DIRS = ("inputs", "work", "outputs", "logs")
_SLUG_SEPARATOR = re.compile(r"[^a-z0-9]+")
_MAX_SLUG_LENGTH = 48
_MAX_CREATE_ATTEMPTS = 16


def repository_root() -> Path:
    """Return the repository root containing this helper."""
    return Path(__file__).resolve().parents[1]


def normalize_slug(value: str) -> str:
    """Normalize a task label to a portable lowercase kebab-case slug.

    Args:
        value: Human-provided task label.

    Returns:
        A lowercase ASCII slug no longer than 48 characters.

    Raises:
        ValueError: If the value contains no ASCII letters or digits.
    """
    slug = _SLUG_SEPARATOR.sub("-", value.strip().lower()).strip("-")
    slug = slug[:_MAX_SLUG_LENGTH].rstrip("-")
    if not slug:
        raise ValueError(
            "slug must contain at least one ASCII letter or digit "
            "(for example: review-cli-output)"
        )
    return slug


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def _random_short_id() -> str:
    """Return an eight-character collision-resistant identifier."""
    return secrets.token_hex(4)


def _format_created_at(now: datetime) -> str:
    """Format a datetime as an RFC 3339 UTC timestamp."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _write_manifest(run_dir: Path, manifest: Dict[str, object]) -> None:
    """Write a newly-created run manifest."""
    manifest_path = run_dir / "manifest.json"
    with manifest_path.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def create_workspace(
    slug: str,
    root: Optional[Path] = None,
    now: Optional[datetime] = None,
    short_id_factory: Callable[[], str] = _random_short_id,
) -> Dict[str, object]:
    """Create one isolated temporary run directory and return its metadata.

    Args:
        slug: Task label used in the run directory name.
        root: Temporary workspace root. Defaults to ``<repo>/.seek-tmp``.
        now: Creation time, primarily injectable for deterministic tests.
        short_id_factory: Callable producing an eight-character hex identifier.

    Returns:
        Manifest-compatible metadata with absolute paths for callers.

    Raises:
        ValueError: If ``slug`` or a generated short identifier is invalid.
        FileExistsError: If a unique run directory cannot be allocated.
        OSError: If the workspace cannot be created; a partial run directory is
            removed before the error is re-raised.
    """
    normalized_slug = normalize_slug(slug)
    created = now or _utc_now()
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    created = created.astimezone(timezone.utc)

    workspace_root = (root or (repository_root() / ".seek-tmp")).resolve()
    date_dir = workspace_root / "runs" / created.strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    (workspace_root / "cache").mkdir(parents=True, exist_ok=True)

    last_collision: Optional[Path] = None
    for _ in range(_MAX_CREATE_ATTEMPTS):
        short_id = short_id_factory().lower()
        if not re.fullmatch(r"[0-9a-f]{8}", short_id):
            raise ValueError("short id factory must return exactly eight hex characters")

        run_id = f"{created.strftime('%H%M%SZ')}-{normalized_slug}-{short_id}"
        run_dir = date_dir / run_id
        try:
            run_dir.mkdir()
        except FileExistsError:
            last_collision = run_dir
            continue

        try:
            for stage in STAGE_DIRS:
                (run_dir / stage).mkdir()

            manifest: Dict[str, object] = {
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "slug": normalized_slug,
                "created_at": _format_created_at(created),
                "status": "active",
                "paths": {stage: stage for stage in STAGE_DIRS},
            }
            _write_manifest(run_dir, manifest)
        except (OSError, ValueError):
            shutil.rmtree(run_dir, ignore_errors=True)
            raise

        return {
            **manifest,
            "root": str(workspace_root),
            "run_dir": str(run_dir),
            **{stage: str(run_dir / stage) for stage in STAGE_DIRS},
        }

    raise FileExistsError(
        f"could not allocate a unique run directory after "
        f"{_MAX_CREATE_ATTEMPTS} attempts; last collision: {last_collision}"
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Create a structured .seek-tmp workspace for one repository task."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create", help="create one run workspace")
    create_parser.add_argument(
        "--slug",
        required=True,
        help="task label; normalized to lowercase ASCII kebab-case",
    )
    create_parser.add_argument(
        "--root",
        type=Path,
        help="override the .seek-tmp root (mainly for isolated tooling/tests)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the helper CLI and return a process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "create":
            result = create_workspace(args.slug, root=args.root)
        else:  # pragma: no cover - argparse rejects unknown commands
            raise ValueError(f"unsupported command: {args.command}")
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": {
                        "code": "TEMP_WORKSPACE_CREATE_FAILED",
                        "message": str(exc),
                    },
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    print(json.dumps({"status": "ok", "data": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
