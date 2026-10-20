from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parent.parent / "compose.yaml"


def _service() -> dict:
    return yaml.safe_load(COMPOSE.read_text())["services"]["wheel-n-deal"]


def test_service_drops_privileges():
    service = _service()
    assert service["cap_drop"] == ["ALL"]
    assert "cap_add" not in service
    assert "no-new-privileges:true" in service["security_opt"]


def test_service_has_resource_limits():
    service = _service()
    assert service["mem_limit"] == "1536m"
    assert service["pids_limit"] == 512


def test_root_filesystem_is_read_only_with_writable_scratch():
    service = _service()
    assert service["read_only"] is True
    mounts = [entry.split(":", 1)[0] for entry in service["tmpfs"]]
    # Chromium's crashpad handler needs a writable $HOME, its shared memory lives in /tmp.
    assert mounts == ["/tmp", "/home/app"]


def test_keeps_host_networking():
    assert _service()["network_mode"] == "host"
