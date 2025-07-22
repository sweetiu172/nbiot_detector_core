# tests/test_main_endpoints.py
from fastapi.testclient import TestClient

def test_read_root(client: TestClient):
    """
    Tests the root endpoint to ensure the API is running and returns the
    expected welcome message.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "message": "N-BaIoT Botnet Detector API with LightGBM model is running."
    }