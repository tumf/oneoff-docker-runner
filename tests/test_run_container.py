from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app

client = TestClient(app)


@patch("docker.models.containers.ContainerCollection.run")
def test_run_container(mock_run):
    # Mock the container object and its methods
    mock_container = MagicMock()
    mock_container.logs.side_effect = [b"stdout", b"stderr"]
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_run.return_value = mock_container

    request_payload = {
        "image": "alpine:latest",
        "command": ["sh", "/app/test.sh"],
        "volumes": {
            "/app/test.sh:ro": {
                "type": "file",
                "content": "IyEvYmluL2FzaAoKZWNobyAiSGVsbG8sIFdvcmxkISIgPiAvYXBwL2RhdGEvdGVzdC50eHQ=",
            },
            "/app/data": {
                "type": "directory",
                "content": "H4sIAGq4eGYAA0tJLEnUZ6AtMDAwMDc1VQDTZhDawMgEQkOBgqGJmbGZobGJobGBgoGhkaGBGYOCKY3dBQalxSWJRUCnlJTmpuFTB1SWhk8B1B9wehSMglEwCgY5AADBaWLyAAYAAA==",
                "response": True,
            },
        },
    }

    response = client.post("/run", json=request_payload)
    response_data = response.json()
    print(f"{response_data=}")
    assert response.status_code == 200
    assert response_data["status"] == "success"
    assert "stdout" in response_data["stdout"]
    assert "stderr" in response_data["stderr"]
    assert "/app/data" in response_data["volumes"]
    assert response_data["volumes"]["/app/data"]["type"] == "directory"
