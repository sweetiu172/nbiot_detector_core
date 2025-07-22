# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import json

# Import the main module itself to patch its globals
import app.main as main_module

@pytest.fixture
def client(mocker):
    """
    A robust fixture that provides a configured TestClient for the API.
    It patches the global ML assets in the `main` module before the app starts.
    """
    # 1. Create mocks for all ML assets
    mock_scaler = MagicMock()
    mock_lgbm_model = MagicMock()
    # Mock a feature list with the correct length
    mock_feature_list = ["feature_" + str(i) for i in range(115)]

    # 2. Directly patch the global variables in the main module.
    mocker.patch.object(main_module, 'scaler', mock_scaler)
    mocker.patch.object(main_module, 'lgbm_model', mock_lgbm_model)
    mocker.patch.object(main_module, 'feature_list', mock_feature_list)

    # 3. Patch the file loaders themselves as a safety measure.
    #    Use side_effect for joblib.load since it's called for both scaler and model.
    mocker.patch("app.main.joblib.load", side_effect=[mock_scaler, mock_lgbm_model])
    #    Patch open and json.load for the feature list.
    mocker.patch("builtins.open", mocker.mock_open(read_data=json.dumps(mock_feature_list)))
    mocker.patch("app.main.json.load", return_value=mock_feature_list)

    # 4. Mock OTLP Exporters to prevent actual HTTP calls during tests.
    mocker.patch("app.main.OTLPSpanExporter", return_value=MagicMock())
    mocker.patch("app.main.OTLPLogExporter", return_value=MagicMock())

    # 5. Now, with all patches in place, safely create the TestClient.
    from app.main import app
    with TestClient(app) as c:
        yield c