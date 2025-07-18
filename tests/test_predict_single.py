# tests/test_predict_single.py
import pytest
from fastapi.testclient import TestClient
import numpy as np

# Import the main module to access its mocked globals
import app.main as main_module

def test_predict_single_instance_valid(client: TestClient):
    """Tests a valid single prediction request for an 'Attack'."""
    # Configure the 'transform' method of the mocked scaler
    main_module.scaler.transform.return_value = np.random.rand(1, 115)
    main_module.scaler.transform.reset_mock()

    # Configure the mocked model to simulate a high probability of attack (class 1)
    # predict_proba returns [[P(class_0), P(class_1)]]
    main_module.lgbm_model.predict_proba.return_value = np.array([[0.3, 0.7]]) # 70% probability of attack
    main_module.lgbm_model.predict_proba.reset_mock()

    valid_features = {"features": [0.1] * 115}
    response = client.post("/predict", json=valid_features)

    assert response.status_code == 200
    json_response = response.json()
    assert json_response["prediction_label"] == 1
    assert json_response["status"] == "Attack"
    assert "probability_attack" in json_response

    # Verify that our mocks' methods were called
    main_module.scaler.transform.assert_called_once()
    main_module.lgbm_model.predict_proba.assert_called_once()


def test_predict_single_instance_invalid_feature_count(client: TestClient):
    """Tests that a request with the wrong number of features is rejected."""
    invalid_features = {"features": [0.1] * 114}
    response = client.post("/predict", json=invalid_features)

    assert response.status_code == 400
    assert "Expected 115 features" in response.json()["detail"]


def test_predict_single_instance_non_numeric_feature(client: TestClient):
    """Tests that FastAPI's Pydantic validation rejects non-numeric features."""
    invalid_features_type = {"features": ["not_a_number"] + [0.1] * 114}
    response = client.post("/predict", json=invalid_features_type)

    assert response.status_code == 422 # Pydantic validation error