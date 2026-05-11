"""Unit tests for stream_event_display module."""

from display_lib.stream_event_display import (
    display_event,
    format_model_info,
    format_step_model,
    format_timestamp,
)


class TestFormatTimestamp:
    """Tests for format_timestamp."""

    def test_empty_timestamp(self):
        assert format_timestamp("") == ""

    def test_none_timestamp(self):
        assert format_timestamp(None) == ""

    def test_valid_utc_timestamp(self):
        result = format_timestamp("2024-01-15T14:32:05Z", utc=True)
        assert "UTC" in result
        assert "14:32:05" in result

    def test_valid_local_timestamp(self):
        result = format_timestamp("2024-01-15T14:32:05Z", utc=False)
        assert result  # Should return non-empty

    def test_invalid_timestamp(self):
        assert format_timestamp("not-a-date") == ""


class TestFormatModelInfo:
    """Tests for format_model_info."""

    def test_returns_none_when_no_model(self):
        assert format_model_info("", {}) is None

    def test_returns_none_when_low_verbosity(self):
        assert format_model_info("claude", {}, min_verbosity=2, verbosity=1) is None

    def test_returns_info_with_model(self):
        result = format_model_info(
            "claude-haiku-4-5", {"provider": "anthropic"}, verbosity=1
        )
        assert result is not None
        assert "claude-haiku-4-5" in result
        assert "anthropic" in result

    def test_dual_model_display(self):
        result = format_model_info(
            "claude-haiku-4-5",
            {"provider": "anthropic", "verify_model": "claude-opus-4-5"},
            verbosity=1,
        )
        assert "claude-haiku-4-5" in result
        assert "claude-opus-4-5" in result


class TestFormatStepModel:
    """Tests for format_step_model."""

    def test_draft_start_shows_model(self):
        result = format_step_model(
            "draft_start", "claude-haiku-4-5", {"provider": "anthropic"}
        )
        assert "claude-haiku-4-5" in result

    def test_non_start_returns_empty(self):
        assert format_step_model("draft_complete", "model", {}) == ""

    def test_no_model_returns_empty(self):
        assert format_step_model("draft_start", "", {}) == ""


class TestDisplayEvent:
    """Tests for display_event."""

    def test_start_event(self, capsys):
        event = {
            "state": "start",
            "agent": "Insights",
            "timestamp": "",
            "model": "claude-haiku-4-5",
            "data": {"provider": "anthropic"},
        }
        result = display_event(event)
        assert result is None
        captured = capsys.readouterr()
        assert "[Insights]" in captured.out

    def test_complete_event(self, capsys):
        event = {
            "state": "complete",
            "agent": "Insights",
            "timestamp": "",
            "data": {"duration_ms": 5000},
        }
        result = display_event(event)
        assert result == "complete"

    def test_error_event(self, capsys):
        event = {
            "state": "error",
            "agent": "Insights",
            "timestamp": "",
            "data": {"error": "Something failed"},
        }
        result = display_event(event)
        assert result == "error"

    def test_step_complete_event(self, capsys):
        event = {
            "state": "draft_complete",
            "agent": "Insights",
            "timestamp": "",
            "data": {"duration_ms": 1234},
        }
        result = display_event(event)
        assert result is None
        captured = capsys.readouterr()
        assert "draft_complete" in captured.out
        assert "(1234ms)" in captured.out
