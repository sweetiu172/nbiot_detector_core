# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

# Import the app and the main module itself
from app.main import app as fast_api_app
import app.main as main_module

@pytest.fixture
def client(mocker):
    """
    A robust fixture that provides a configured TestClient for the API.

    This fixture directly patches the global `model` and `scaler` variables
    in the `main` module *before* the TestClient starts the app. This
    ensures that the app's startup event operates on our mocks from the
    very beginning, preventing race conditions and initialization errors.
    """
    # 1. Directly patch the global variables in the main module.
    #    This is the most reliable way to ensure the app uses our mocks.
    mock_scaler = MagicMock()
    mocker.patch.object(main_module, 'scaler', mock_scaler)

    mock_model = MagicMock()
    mocker.patch.object(main_module, 'model', mock_model)

    # 2. Although we've replaced the objects, it's good practice to also
    #    patch the loaders themselves to prevent any real file I/O if the
    #    startup logic were ever to change.
    mocker.patch("app.main.joblib.load", return_value=mock_scaler)
    mocker.patch("app.main.torch.load", return_value={}) # Return dummy state dict
    mocker.patch("app.main.MLPDetector", return_value=mock_model)

    # 3. Mock OTLP Exporters to prevent actual HTTP calls during tests.
    mocker.patch("app.main.OTLPSpanExporter", return_value=MagicMock())
    mocker.patch("app.main.OTLPLogExporter", return_value=MagicMock())

    # 4. Now, with all patches in place, safely create the TestClient.
    #    The app's startup event will now use the mocks we defined above.
    with TestClient(fast_api_app) as c:
        yield c