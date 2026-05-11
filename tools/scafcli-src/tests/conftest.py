"""Shared fixtures for scafcli tests."""

import json
import os
from pathlib import Path

import pytest

# Tool source directory (tests/ → scafcli-src/)
_TOOL_DIR = Path(__file__).resolve().parent.parent

# Set CLI_ROOT_DIR for all tests if not already set
os.environ.setdefault("CLI_ROOT_DIR", str(_TOOL_DIR.parent.parent))


@pytest.fixture
def source_repo():
    """Return the root directory path."""
    return Path(os.environ["CLI_ROOT_DIR"])


@pytest.fixture
def scaf_dir():
    """Return the scafcli-src tool directory."""
    return _TOOL_DIR


@pytest.fixture
def scaf_data():
    """Return the scafcli data directory."""
    return _TOOL_DIR / "data"


@pytest.fixture
def manifest_path(scaf_dir):
    """Return the manifest.json path."""
    return scaf_dir / "data" / "manifest.json"


@pytest.fixture
def schema_path(scaf_dir):
    """Return the schema path."""
    return scaf_dir / "data" / "schemas" / "manifest.schema.json"


@pytest.fixture
def manifest(manifest_path):
    """Load and return the manifest dict."""
    with open(manifest_path) as f:
        return json.load(f)


@pytest.fixture
def sample_manifest():
    """Return a minimal valid manifest for testing."""
    return {
        "modules": {
            "base": {
                "files": [],
                "dirs": [".claude/"],
                "snippets": {},
            }
        }
    }
