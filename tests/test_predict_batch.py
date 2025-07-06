# tests/test_predict_batch.py
import pytest
from fastapi.testclient import TestClient
import torch
import io

# Import constants and the main module to access mocked globals
from app.main import INPUT_SIZE
import app.main as main_module

@pytest.fixture
def setup_batch_mocks():
    """
    A dedicated fixture to set up mock behaviors for batch prediction tests.
    It configures the side_effect for the scaler and model to simulate
    batch processing.
    """
    # scaler and model are already MagicMocks due to the conftest setup.
    # We just configure their behavior for our batch tests.
    def scaler_side_effect(input_np_array):
        # Dummy scaling: just return the input
        return input_np_array

    main_module.scaler.transform.side_effect = scaler_side_effect
    main_module.scaler.transform.reset_mock()

    def model_side_effect_batch(input_tensor_batch):
        num_samples = input_tensor_batch.shape[0]
        # Simulate one attack and one benign prediction
        logits = [[0.8]] * num_samples # Default to "Attack"
        if num_samples > 1:
            logits[1] = [-0.2] # Second sample is "Benign"
        return torch.tensor(logits, dtype=torch.float32)

    main_module.model.side_effect = model_side_effect_batch
    main_module.model.reset_mock()


def test_predict_batch_valid_csv(client: TestClient, setup_batch_mocks):
    """Tests a valid batch prediction request with a well-formed CSV."""
    csv_data = "\n".join([",".join(map(str, [0.1] * INPUT_SIZE)) for i in range(3)])
    csv_file = ("test.csv", io.BytesIO(csv_data.encode('utf-8')), "text/csv")

    response = client.post("/predict_batch/", files={"file": csv_file})

    assert response.status_code == 200
    json_response = response.json()
    assert len(json_response) == 3
    assert json_response[0]["status"] == "Attack"
    assert json_response[1]["status"] == "Benign"
    assert json_response[2]["status"] == "Attack"

    main_module.scaler.transform.assert_called_once()
    main_module.model.assert_called_once()


def test_predict_batch_invalid_file_type(client: TestClient):
    """Tests that a non-CSV file type is rejected with a 400 error."""
    txt_file = ("test.txt", io.BytesIO(b"this is not a csv"), "text/plain")
    response = client.post("/predict_batch/", files={"file": txt_file})

    assert response.status_code == 400
    assert "Invalid file type" in response.json()["detail"]


def test_predict_batch_csv_wrong_columns(client: TestClient):
    """Tests a CSV file with an incorrect number of columns."""
    csv_data = "0.1,0.2,0.3" # Assuming INPUT_SIZE is not 3
    csv_file = ("test.csv", io.BytesIO(csv_data.encode('utf-8')), "text/csv")

    response = client.post("/predict_batch/", files={"file": csv_file})

    assert response.status_code == 400
    assert "incorrect number of columns" in response.json()["detail"]


def test_predict_batch_empty_csv(client: TestClient):
    """Tests that an empty CSV file is correctly handled."""
    csv_file = ("test.csv", io.BytesIO(b""), "text/csv")
    response = client.post("/predict_batch/", files={"file": csv_file})

    assert response.status_code == 400
    assert "CSV file is empty" in response.json()["detail"]


def test_predict_batch_malformed_csv_non_numeric(client: TestClient, setup_batch_mocks):
    """Tests a CSV that contains non-numeric data."""
    csv_data = f"a,b,c\n" + ",".join(["0.1"] * INPUT_SIZE)
    csv_file = ("test.csv", io.BytesIO(csv_data.encode('utf-8')), "text/csv")

    response = client.post("/predict_batch/", files={"file": csv_file})

    assert response.status_code == 400
    assert "Error parsing CSV file" in response.json()["detail"]