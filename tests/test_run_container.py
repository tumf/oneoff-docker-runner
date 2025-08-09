from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app, get_docker_client

client = TestClient(app)


def _dummy_client():
    class _DummyContainer:
        def wait(self):
            return {"StatusCode": 0}

        def logs(self, stdout=False, stderr=False):
            if stdout:
                return b"stdout"
            if stderr:
                return b"stderr"
            return b""

        def remove(self):
            return None

    class _DummyContainers:
        def run(self, *args, **kwargs):
            return _DummyContainer()

    class _DummyImages:
        def pull(self, *args, **kwargs):
            return None

    class _DummyVolume:
        def __init__(self, name: str):
            self.name = name

    class _DummyVolumes:
        def create(self, name: str, **kwargs):
            return _DummyVolume(name)

    class _DummyClient:
        containers = _DummyContainers()
        images = _DummyImages()
        volumes = _DummyVolumes()

        def info(self):
            return {"status": "ok"}

    return _DummyClient()


@patch("main.get_docker_client", side_effect=_dummy_client)
def test_run_container(_mock_get_client):

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
