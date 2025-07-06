# tests/test_main.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock # patch is also from unittest.mock
import numpy as np
import io
import torch

# Import the app instance and constants
from app.main import app as fast_api_app # The FastAPI app instance
from app.main import INPUT_SIZE
import app.main as main_module # Import the main module to access its globals

from app.model_definition import MLPDetector

@pytest.fixture # Default scope is "function"
def client(mocker):
    # 1. Mock OTLP Exporters to prevent actual HTTP calls during tests
    mocker.patch("app.main.OTLPSpanExporter", return_value=MagicMock())
    mocker.patch("app.main.OTLPLogExporter", return_value=MagicMock())

    # 2. Mock ML asset loading (joblib.load, torch.load, MLPDetector constructor)
    mock_scaler_object = MagicMock()
    mocker.patch("app.main.joblib.load", return_value=mock_scaler_object)

    mock_model_object = MagicMock(spec=MLPDetector)
    mock_model_object.to.return_value = mock_model_object
    mock_model_object.eval.return_value = mock_model_object
    mock_model_object.load_state_dict = MagicMock()
    mocker.patch("app.main.MLPDetector", return_value=mock_model_object)
    mocker.patch("app.main.torch.load", return_value={})

    # Create TestClient AFTER mocks are in place so startup uses them
    with TestClient(fast_api_app) as c: # Use the imported app instance
        # Ensure that after startup, the globals in app.main are the mocks
        # This is implicitly handled as load_assets will use the patched loaders
        yield c

# --- Test for Root Endpoint ---
def test_read_root(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "N-BaIoT Botnet Detector API. Navigate to /docs for API documentation."}

# --- Tests for Single Prediction Endpoint (/predict/) ---
def test_predict_single_instance_valid(client: TestClient, mocker):
    # scaler is now our mock_scaler_object from the client fixture
    # model is now our mock_model_object from the client fixture

    # Configure the 'transform' method of the mocked scaler for this specific test
    main_module.scaler.transform.return_value = np.random.rand(1, INPUT_SIZE)

    # Configure the 'forward' method (or __call__) of the mocked model for this test
    # Since we mocked the entire MLPDetector to return mock_model_object,
    # model(features) calls mock_model_object(features).
    # MagicMock is callable by default. We set its return_value.
    main_module.model.return_value = torch.tensor([[0.9]]) # Output of model(features_tensor)

    valid_features = {"features": [0.1] * INPUT_SIZE}
    response = client.post("/predict/", json=valid_features)

    assert response.status_code == 200
    json_response = response.json()
    assert json_response["prediction_label"] == 1
    assert json_response["status"] == "Attack"

    main_module.scaler.transform.assert_called_once()
    main_module.model.assert_called_once() # Checks if mock_model_object was called


def test_predict_single_instance_invalid_feature_count(client: TestClient):
    invalid_features = {"features": [0.1] * (INPUT_SIZE - 1)}
    response = client.post("/predict/", json=invalid_features)
    assert response.status_code == 400
    response_detail = response.json()["detail"]
    assert f"Expected {INPUT_SIZE} features" in response_detail
    assert f"got {INPUT_SIZE - 1}" in response_detail

def test_predict_single_instance_non_numeric_feature(client: TestClient):
    invalid_features_type = {"features": ["not_a_number"] + [0.1] * (INPUT_SIZE - 1)}
    response = client.post("/predict/", json=invalid_features_type)
    assert response.status_code == 422


# --- Tests for Batch Prediction Endpoint (/predict_batch/) ---
@pytest.fixture
def setup_batch_mocks(mocker): # Renamed from mock_loaded_assets_for_batch for clarity
    """Sets up mock behaviors for main_module.scaler.transform and model() for batch tests."""
    # scaler and model are already MagicMock instances
    # due to the client fixture. We just configure their behavior for batch.

    def scaler_side_effect(input_np_array):
        return input_np_array * 0.9 # Dummy scaling
    main_module.scaler.transform.side_effect = scaler_side_effect
    main_module.scaler.transform.reset_mock() # Reset from any single prediction calls

    def model_side_effect_batch(input_tensor_batch):
        num_samples = input_tensor_batch.shape[0]
        logits = [[0.8]] * num_samples
        if num_samples > 1: logits[1] = [-0.2]
        return torch.tensor(logits, dtype=torch.float32)
    # If model is a MagicMock instance, its return_value is for model() call
    main_module.model.side_effect = model_side_effect_batch # model() will use this
    main_module.model.reset_mock()

    return main_module.scaler.transform, main_module.model # Return the actual mock methods/objects

def test_predict_batch_valid_csv(client: TestClient, setup_batch_mocks):
    mock_scaler_transform, mock_model_callable = setup_batch_mocks

    csv_data = "\n".join([",".join(map(str, [0.1 + i*0.01] * INPUT_SIZE)) for i in range(3)])
    csv_file_like = io.BytesIO(csv_data.encode('utf-8'))
    response = client.post("/predict_batch/", files={"file": ("test.csv", csv_file_like, "text/csv")})

    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 3
    assert json_response[0]["status"] == "Attack"
    if len(json_response) > 1: assert json_response[1]["status"] == "Benign"

    mock_scaler_transform.assert_called_once()
    mock_model_callable.assert_called_once()


def test_predict_batch_invalid_file_type(client: TestClient):
    txt_file_like = io.BytesIO(b"this is not a csv")
    response = client.post("/predict_batch/", files={"file": ("test.txt", txt_file_like, "text/plain")})
    assert response.status_code == 400
    assert "Invalid file type" in response.json()["detail"]

def test_predict_batch_csv_wrong_columns(client: TestClient):
    # This test previously failed with 500 instead of 400.
    # The API logic needs to be robust to ensure HTTPExceptions are not caught by general 'except Exception'.
    # Assuming main.py's error handling for this specific case is fixed to return 400.
    csv_data = "0.1,0.2,0.3"
    csv_file_like = io.BytesIO(csv_data.encode('utf-8'))
    response = client.post("/predict_batch/", files={"file": ("test.csv", csv_file_like, "text/csv")})
    assert response.status_code == 400 # Expecting 400 after API error handling fix
    assert "incorrect number of columns" in response.json()["detail"]


def test_predict_batch_empty_csv(client: TestClient):
    csv_file_like = io.BytesIO(b"")
    response = client.post("/predict_batch/", files={"file": ("test.csv", csv_file_like, "text/csv")})
    assert response.status_code == 400
    assert "CSV file is empty" in response.json()["detail"]

def test_predict_batch_malformed_csv_non_numeric(client: TestClient, setup_batch_mocks):
    # This test also depends on refined error handling in main.py
    # to convert a ValueError from data conversion into a 400/422.
    mock_scaler_transform, mock_model_callable = setup_batch_mocks
    csv_data = "\n".join([",".join(["text_instead_of_number"] + ["0.1"]*(INPUT_SIZE-1))])
    csv_file_like = io.BytesIO(csv_data.encode('utf-8'))
    response = client.post("/predict_batch/", files={"file": ("test.csv", csv_file_like, "text/csv")})

    # Expecting 400 if main.py catches ValueError and raises HTTPException
    assert response.status_code == 400
    assert "CSV contains non-numeric data" in response.json()["detail"] # Or similar refined message