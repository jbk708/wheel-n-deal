import httpx
import pytest
import respx

from wheel_n_deal.fetch import make_client
from wheel_n_deal.heartbeat import ping

URL = "https://status.example/api/push/secret-push-token?status=up"


@pytest.fixture
async def client():
    async with make_client() as c:
        yield c


async def test_ping_gets_url(client):
    with respx.mock:
        route = respx.get(URL).respond(200)
        await ping(client, URL)
    assert route.call_count == 1


async def test_no_url_is_noop(client):
    with respx.mock:
        await ping(client, None)


@pytest.mark.parametrize("side_effect", [httpx.ConnectError("down"), httpx.Response(404)])
async def test_failure_warns_without_url(client, caplog, side_effect):
    with respx.mock:
        respx.get(URL).mock(side_effect=[side_effect])
        await ping(client, URL)
    assert "heartbeat ping failed" in caplog.text
    assert "secret-push-token" not in caplog.text
    assert "status.example" not in caplog.text
