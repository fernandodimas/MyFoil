import pytest


@pytest.fixture
def client(app_config):
    """
    Provide a Flask test client for the application.

    This tries to use the application factory `create_app()` from `app.app`.
    If the factory is not importable, it will attempt to import the already
    instantiated `app` object. The provided `app_config` dict is applied to
    the app before yielding the test client.
    """
    try:
        from app.app import create_app

        _app = create_app()
    except Exception:
        try:
            from app.app import app as _app
        except Exception:
            raise

    # Apply testing config overrides
    _app.config.update(app_config)

    with _app.test_client() as client:
        with _app.app_context():
            yield client
