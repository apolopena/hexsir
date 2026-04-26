"""Root test configuration for rs-src."""


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test")
