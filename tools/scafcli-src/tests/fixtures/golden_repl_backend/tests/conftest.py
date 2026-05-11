"""Root test configuration for demotoolcli-src."""
import os

os.environ.setdefault("CLI_ROOT_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("AGENT_STREAM_JWT_SECRET", "test-secret-for-unit-tests-ok!32")
os.environ.setdefault("CLI_BACKEND_URL", "http://localhost:8000")
os.environ.setdefault("CLI_AGENTIC_BACKEND_URL", "http://localhost:8001")
os.environ.setdefault("CLI_AGENTIC_BACKEND_WS_URL", "ws://localhost:8001")


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test")
