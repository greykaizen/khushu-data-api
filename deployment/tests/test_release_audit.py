"""Tests for the published-pack release audit (no network)."""
from __future__ import annotations

import unittest

from deployment.audit_release import audit, expected_releases, release_tag


def _pack(pack_id: str, family: str, size: int, sha: str) -> dict:
    return {
        "id": pack_id,
        "family": family,
        "file": f"{pack_id}.db",
        "version": "v2026.11",
        "bytes": size,
        "sha256": sha,
    }


class ReleaseAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packs = [
            _pack("content", "content", 10, "a" * 64),
            _pack("hadith-bukhari", "hadith", 20, "b" * 64),
        ]
        self.manifest = {
            "version": "v2026.11",
            "total_packs": 2,
            "total_bytes": 30,
            "packs": self.packs,
        }

    def _releases(self):
        return {
            release_tag("content", "v2026.11"): {
                "draft": False,
                "assets": [
                    {
                        "name": "content.db",
                        "size": 10,
                        "state": "uploaded",
                        "digest": "sha256:" + "a" * 64,
                    }
                ],
            },
            release_tag("hadith", "v2026.11"): {
                "draft": False,
                "assets": [
                    {
                        "name": "hadith-bukhari.db",
                        "size": 20,
                        "state": "uploaded",
                        "digest": "sha256:" + "b" * 64,
                    }
                ],
            },
        }

    def test_clean_manifest_passes(self) -> None:
        self.assertEqual([], audit(self.manifest, self._releases()))

    def test_groups_same_family_under_one_release(self) -> None:
        groups = expected_releases(self.manifest)
        self.assertEqual(2, len(groups))
        self.assertEqual(1, len(groups[release_tag("content", "v2026.11")]))

    def test_missing_release_fails(self) -> None:
        releases = self._releases()
        del releases[release_tag("hadith", "v2026.11")]
        self.assertIn("release is missing", " ".join(audit(self.manifest, releases)))

    def test_size_mismatch_fails(self) -> None:
        releases = self._releases()
        releases[release_tag("content", "v2026.11")]["assets"][0]["size"] = 11
        self.assertIn("size 11", " ".join(audit(self.manifest, releases)))

    def test_digest_mismatch_fails(self) -> None:
        releases = self._releases()
        releases[release_tag("content", "v2026.11")]["assets"][0]["digest"] = "sha256:" + "c" * 64
        self.assertIn("digest", " ".join(audit(self.manifest, releases)))

    def test_missing_digest_fails(self) -> None:
        releases = self._releases()
        releases[release_tag("content", "v2026.11")]["assets"][0].pop("digest")
        self.assertIn("no SHA-256 digest", " ".join(audit(self.manifest, releases)))

    def test_missing_and_extra_assets_fail(self) -> None:
        releases = self._releases()
        releases[release_tag("content", "v2026.11")]["assets"] = [
            {"name": "stale.db", "size": 1, "state": "uploaded", "digest": "sha256:" + "d" * 64}
        ]
        errors = " ".join(audit(self.manifest, releases))
        self.assertIn("missing asset content.db", errors)
        self.assertIn("unexpected asset stale.db", errors)

    def test_draft_fails(self) -> None:
        releases = self._releases()
        releases[release_tag("content", "v2026.11")]["draft"] = True
        self.assertIn("still a draft", " ".join(audit(self.manifest, releases)))


if __name__ == "__main__":
    unittest.main()
