"""Tests for application release information."""

import re
import tomllib
from pathlib import Path

from app.release_info import CURRENT_VERSION, RELEASES


def test_current_version_uses_semantic_versioning() -> None:
    """The displayed version follows the project's semantic version convention."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", CURRENT_VERSION)


def test_current_version_is_the_latest_release() -> None:
    """The first release is the version shown to users."""
    assert RELEASES[0].version == CURRENT_VERSION
    assert CURRENT_VERSION == "1.2.0"


def test_package_version_matches_displayed_version() -> None:
    """The package and in-app versions must be released together."""
    project_file = Path(__file__).parents[1] / "pyproject.toml"
    with project_file.open("rb") as file:
        project = tomllib.load(file)

    assert project["project"]["version"] == CURRENT_VERSION


def test_first_productive_release_is_version_one() -> None:
    """The March productive release establishes the stable version line."""
    productive_release = next(release for release in RELEASES if release.version == "1.0.0")
    assert productive_release.date == "24. März 2026"


def test_release_history_is_complete_and_readable() -> None:
    """Every release provides concise text suitable for business users."""
    assert len(RELEASES) >= 2
    assert len({release.version for release in RELEASES}) == len(RELEASES)

    for release in RELEASES:
        assert release.date
        assert release.summary.strip()
        assert len(release.summary) <= 60
        assert 1 <= len(release.highlights) <= 3
        assert all(highlight.strip() for highlight in release.highlights)