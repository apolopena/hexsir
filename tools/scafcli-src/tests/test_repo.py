"""Tests for repo command preflight check functions."""

import subprocess
from unittest.mock import patch

import pytest

from commands.repo import (
    _check_git,
    _check_gh,
    _check_gh_auth,
    _check_gh_network,
    _check_ssh,
)


def _completed(returncode=0, stdout="", stderr=""):
    """Build a CompletedProcess result."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestCheckGit:
    """Tests for _check_git()."""

    @patch("commands.repo.subprocess.run")
    def test_success(self, mock_run):
        """Should return None when git is found."""
        mock_run.return_value = _completed(returncode=0)
        assert _check_git() is None

    @patch("commands.repo.subprocess.run")
    def test_failure(self, mock_run):
        """Should raise SystemExit when git is not found."""
        mock_run.return_value = _completed(returncode=1)
        with pytest.raises(SystemExit):
            _check_git()


class TestCheckGh:
    """Tests for _check_gh()."""

    @patch("commands.repo.subprocess.run")
    def test_success(self, mock_run):
        """Should return None when gh is found."""
        mock_run.return_value = _completed(returncode=0)
        assert _check_gh() is None

    @patch("commands.repo.subprocess.run")
    def test_failure(self, mock_run):
        """Should raise SystemExit when gh is not found."""
        mock_run.return_value = _completed(returncode=1)
        with pytest.raises(SystemExit):
            _check_gh()


class TestCheckGhAuth:
    """Tests for _check_gh_auth()."""

    @patch("commands.repo._run")
    def test_success(self, mock_run):
        """Should return None when authenticated."""
        mock_run.return_value = _completed(returncode=0)
        assert _check_gh_auth() is None

    @patch("commands.repo._run")
    def test_failure(self, mock_run):
        """Should raise SystemExit when not authenticated."""
        mock_run.return_value = _completed(returncode=1)
        with pytest.raises(SystemExit):
            _check_gh_auth()


class TestCheckGhNetwork:
    """Tests for _check_gh_network()."""

    @patch("commands.repo._run")
    def test_success(self, mock_run):
        """Should return None when API is reachable."""
        mock_run.return_value = _completed(returncode=0)
        assert _check_gh_network() is None

    @patch("commands.repo._run")
    def test_failure(self, mock_run):
        """Should raise SystemExit when API is unreachable."""
        mock_run.return_value = _completed(returncode=1)
        with pytest.raises(SystemExit):
            _check_gh_network()


class TestCheckSsh:
    """Tests for _check_ssh() with multiple error branches."""

    @patch("commands.repo._run")
    def test_success(self, mock_run):
        """Should return None on successful authentication."""
        mock_run.return_value = _completed(
            returncode=1, stderr="Hi user! You've successfully authenticated"
        )
        assert _check_ssh() is None

    @patch("commands.repo._run")
    def test_changed_host_key(self, mock_run):
        """Should raise SystemExit on changed host key."""
        mock_run.return_value = _completed(
            returncode=255,
            stderr="REMOTE HOST IDENTIFICATION HAS CHANGED",
        )
        with pytest.raises(SystemExit):
            _check_ssh()

    @patch("commands.repo._run")
    def test_host_key_verification_failed(self, mock_run):
        """Should raise SystemExit when host not in known_hosts."""
        mock_run.return_value = _completed(
            returncode=255, stderr="Host key verification failed"
        )
        with pytest.raises(SystemExit):
            _check_ssh()

    @patch("commands.repo._run")
    def test_connection_timed_out(self, mock_run):
        """Should raise SystemExit on connection timeout."""
        mock_run.return_value = _completed(
            returncode=255, stderr="Connection timed out"
        )
        with pytest.raises(SystemExit):
            _check_ssh()

    @patch("commands.repo._run")
    def test_connection_refused(self, mock_run):
        """Should raise SystemExit on connection refused."""
        mock_run.return_value = _completed(returncode=255, stderr="Connection refused")
        with pytest.raises(SystemExit):
            _check_ssh()

    @patch("commands.repo._run")
    def test_ssh_agent_not_running(self, mock_run):
        """Should raise SystemExit when SSH agent not running."""
        mock_run.return_value = _completed(
            returncode=255, stderr="Could not open a connection to your agent"
        )
        with pytest.raises(SystemExit):
            _check_ssh()

    @patch("commands.repo._run")
    def test_permission_denied_returns_warning(self, mock_run):
        """Should return warning string on permission denied."""
        mock_run.return_value = _completed(
            returncode=255, stderr="Permission denied (publickey)"
        )
        result = _check_ssh()
        assert result is not None
        assert "passphrase" in result.lower()

    @patch("commands.repo._run")
    def test_unknown_error(self, mock_run):
        """Should raise SystemExit on unknown SSH error."""
        mock_run.return_value = _completed(
            returncode=255, stderr="Some unexpected error"
        )
        with pytest.raises(SystemExit):
            _check_ssh()
