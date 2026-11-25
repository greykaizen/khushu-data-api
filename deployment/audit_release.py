#!/usr/bin/env python3
"""Audit published pack releases against data/manifest/packs.json.

Uses the GitHub REST API and the asset `digest` field, so it verifies every
manifest pack's family/tag, name, byte size and SHA-256 without downloading the
~832 MB set. Requires network access; set GITHUB_TOKEN/GH_TOKEN for a higher
rate limit.

Run after deployment/publish_packs.sh:
    python3 deployment/audit_release.py
    python3 deployment/audit_release.py --repo greykaizen/khushu-data-api
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_MANIFEST = os.path.join(ROOT, "data", "manifest", "packs.json")
DEFAULT_REPO = "greykaizen/khushu-data-api"
MB = 1048576


def release_tag(family: str, version: str) -> str:
    return f"packs-{family}-{version}"


def expected_releases(manifest: dict) -> dict[str, list[dict]]:
    """Group manifest packs by the release tag they must be published under."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for pack in manifest.get("packs", []):
        groups[release_tag(pack["family"], pack["version"])].append(pack)
    return dict(groups)


def fetch_release(repo: str, tag: str, timeout: int = 30) -> dict | None:
    """Fetch one release; None means 404 (release/tag does not exist)."""
    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "khushu-release-audit",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, headers=headers), timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f"GitHub API {exc.code} for {tag}: {exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"cannot reach GitHub API for {tag}: {exc.reason}") from exc


def audit(manifest: dict, releases: dict[str, dict | None]) -> list[str]:
    """Return human-readable failures for a fully-published manifest."""
    errors: list[str] = []
    groups = expected_releases(manifest)
    pack_count = sum(len(packs) for packs in groups.values())
    total_bytes = sum(p["bytes"] for packs in groups.values() for p in packs)

    if manifest.get("total_packs") != pack_count:
        errors.append(
            f"manifest total_packs={manifest.get('total_packs')} but packs list has {pack_count}"
        )
    if manifest.get("total_bytes") != total_bytes:
        errors.append(
            f"manifest total_bytes={manifest.get('total_bytes')} but packs sum to {total_bytes}"
        )

    for tag, packs in sorted(groups.items()):
        release = releases.get(tag)
        if release is None:
            errors.append(f"{tag}: release is missing")
            continue
        if release.get("draft"):
            errors.append(f"{tag}: release is still a draft")

        assets = {a.get("name"): a for a in release.get("assets", [])}
        wanted = {p["file"]: p for p in packs}
        for name in sorted(set(wanted) - set(assets)):
            errors.append(f"{tag}: missing asset {name}")
        for name in sorted(set(assets) - set(wanted)):
            errors.append(f"{tag}: unexpected asset {name}")

        for name, pack in sorted(wanted.items()):
            asset = assets.get(name)
            if asset is None:
                continue
            if asset.get("state") != "uploaded":
                errors.append(f"{tag}/{name}: asset state={asset.get('state')!r}, not uploaded")
            if asset.get("size") != pack["bytes"]:
                errors.append(
                    f"{tag}/{name}: size {asset.get('size')} != manifest {pack['bytes']}"
                )
            digest = (asset.get("digest") or "").lower()
            expected = f"sha256:{pack['sha256']}".lower()
            if not digest:
                errors.append(f"{tag}/{name}: GitHub asset has no SHA-256 digest")
            elif digest != expected:
                errors.append(f"{tag}/{name}: digest {digest} != manifest {expected}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    with open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)
    groups = expected_releases(manifest)

    releases: dict[str, dict | None] = {}
    for tag in sorted(groups):
        releases[tag] = fetch_release(args.repo, tag, args.timeout)

    for tag, packs in sorted(groups.items()):
        release = releases.get(tag)
        size = sum(p["bytes"] for p in packs)
        state = "MISSING" if release is None else ("DRAFT" if release.get("draft") else "OK")
        print(f"  {tag:34} {len(packs):3} assets  {size / MB:7.1f} MiB  {state}")

    errors = audit(manifest, releases)
    print(
        f"\nRESULT: {'ALL GREEN — every published pack matches the manifest size and SHA-256.' if not errors else 'FAILURES: ' + '; '.join(errors)}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
