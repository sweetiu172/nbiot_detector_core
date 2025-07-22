# tests/test_predict_batch.py
import pytest
from fastapi.testclient import TestClient
import numpy as np
import io

# Import the main module to access its mocked globals
import app.main as main_module

@pytest.fixture
def setup_batch_mocks():
    """A fixture to configure mock behaviors for batch prediction tests."""
    def scaler_side_effect(input_np_array):
        return input_np_array

    main_module.scaler.transform.side_effect = scaler_side_effect
    main_module.scaler.transform.reset_mock()

    def model_side_effect_batch(input_np_array):
        num_samples = input_np_array.shape[0]
        # Default to "Attack" probability
        probabilities = [[0.2, 0.8]] * num_samples
        if num_samples > 1:
            # Second sample is "Benign"
            probabilities[1] = [0.7, 0.3]
        return np.array(probabilities)

    main_module.lgbm_model.predict_proba.side_effect = model_side_effect_batch
    main_module.lgbm_model.predict_proba.reset_mock()


def test_predict_batch_valid_csv(client: TestClient, setup_batch_mocks):
    """Tests a valid batch prediction request with a well-formed CSV."""
    csv_data = "\n".join([",".join(map(str, [0.1] * 115)) for i in range(3)])
    csv_file = ("test.csv", io.BytesIO(csv_data.encode('utf-8')), "text/csv")

    response = client.post("/predict_batch", files={"file": csv_file})

    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 3
    assert json_response[0]["status"] == "Attack"
    assert json_response[1]["status"] == "Benign"
    assert json_response[2]["status"] == "Attack"

    main_module.scaler.transform.assert_called_once()
    main_module.lgbm_model.predict_proba.assert_called_once()


def test_predict_batch_invalid_file_type(client: TestClient):
    """Tests that a non-CSV file type is rejected."""
    txt_file = ("test.txt", io.BytesIO(b"this is not a csv"), "text/plain")
    response = client.post("/predict_batch", files={"file": txt_file})
    assert response.status_code == 400

def test_predict_batch_csv_wrong_columns(client: TestClient):
    """Tests a CSV file with an incorrect number of columns."""
    csv_data = "0.1,0.2,0.3"
    csv_file = ("test.csv", io.BytesIO(csv_data.encode('utf-8')), "text/csv")
    response = client.post("/predict_batch", files={"file": csv_file})
    assert response.status_code == 400

def test_predict_batch_empty_csv(client: TestClient):
    """Tests that an empty CSV file is handled."""
    csv_file = ("test.csv", io.BytesIO(b""), "text/csv")
    response = client.post("/predict_batch", files={"file": csv_file})
    assert response.status_code == 400