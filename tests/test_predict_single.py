# tests/test_predict_single.py
import pytest
from fastapi.testclient import TestClient
import numpy as np
import torch

# Import constants and the main module to access mocked globals
from app.main import INPUT_SIZE
import app.main as main_module

def test_predict_single_instance_valid(client: TestClient):
    """
    Tests a valid single prediction request.
    It configures the return values of the mocked model and scaler for this
    specific success scenario.
    """
    # Configure the 'transform' method of the mocked scaler
    main_module.scaler.transform.return_value = np.random.rand(1, INPUT_SIZE)
    main_module.scaler.transform.reset_mock() # Reset mock for clean test

    # Configure the mocked model's return value for this test
    main_module.model.return_value = torch.tensor([[0.9]]) # Represents an "Attack" logit
    main_module.model.reset_mock()

    valid_features = {"features": [0.1] * INPUT_SIZE}
    response = client.post("/predict/", json=valid_features)

    assert response.status_code == 200
    json_response = response.json()
    assert json_response["prediction_label"] == 1
    assert json_response["status"] == "Attack"

    # Verify that our mocks were called as expected
    main_module.scaler.transform.assert_called_once()
    main_module.model.assert_called_once()


def test_predict_single_instance_invalid_feature_count(client: TestClient):
    """
    Tests that the endpoint correctly handles a request with the wrong
    number of features, expecting a 400 Bad Request error.
    """
    invalid_features = {"features": [0.1] * (INPUT_SIZE - 1)}
    response = client.post("/predict/", json=invalid_features)

    assert response.status_code == 400
    response_detail = response.json()["detail"]
    assert f"Expected {INPUT_SIZE} features" in response_detail
    assert f"got {INPUT_SIZE - 1}" in response_detail


def test_predict_single_instance_non_numeric_feature(client: TestClient):
    """
    Tests that the endpoint correctly handles a request with non-numeric
    data, which FastAPI should reject with a 422 Unprocessable Entity error.
    """
    invalid_features_type = {"features": ["not_a_number"] + [0.1] * (INPUT_SIZE - 1)}
    response = client.post("/predict/", json=invalid_features_type)

    assert response.status_code == 422 # Pydantic validation error