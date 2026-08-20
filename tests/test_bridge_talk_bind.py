import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from bridge.app import bind_talk_client, create_app
from bridge.config import BridgeConfig
from bridge.talk import FakeTalkClient, GatewayTalkClient


class RecoveringTalk:
    def __init__(self):
        self._connected = False
        self.attempts = 0
        self.stats = {"reconnects": 0, "create_ok": 0, "disconnects": 0, "create_fail": 0}

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self.attempts += 1
        if self.attempts < 2:
            raise RuntimeError("gateway down")
        self._connected = True

    async def reconnect(self) -> None:
        self.stats["reconnects"] += 1
        await self.connect()

    async def close(self) -> None:
        self._connected = False

    def set_listener(self, _listener) -> None:
        return None


class BindTalkTests(unittest.IsolatedAsyncioTestCase):
    async def test_talk_disabled_uses_faketalk(self):
        client = await bind_talk_client(BridgeConfig(talk_enabled=False, log_path=":memory:"))
        self.assertIsInstance(client, FakeTalkClient)

    async def test_talk_enabled_keeps_gateway_client_when_connect_fails(self):
        class DownClient(GatewayTalkClient):
            async def connect(self) -> None:
                raise RuntimeError("gateway down")

        with patch("bridge.app.load_gateway_token", return_value="tok"), patch(
            "bridge.app.GatewayTalkClient", DownClient
        ):
            client = await bind_talk_client(BridgeConfig(talk_enabled=True, log_path=":memory:"))
        self.assertIsInstance(client, DownClient)
        self.assertFalse(client.connected)
        self.assertNotIsInstance(client, FakeTalkClient)


class GatewayLaterUpTests(unittest.TestCase):
    def test_supervisor_recovers_without_switching_to_faketalk(self):
        talk = RecoveringTalk()
        app = create_app(config=BridgeConfig(talk_enabled=True, log_path=":memory:"), talk=talk)
        with TestClient(app) as client:
            first = client.get("/healthz").json()
            self.assertEqual(first["talk_kind"], "RecoveringTalk")
            self.assertFalse(first["talk_connected"])
            deadline = time.time() + 4
            later = first
            while time.time() < deadline:
                later = client.get("/healthz").json()
                if later.get("talk_connected"):
                    break
                time.sleep(0.2)
            self.assertEqual(later["talk_kind"], "RecoveringTalk")
            self.assertTrue(later["talk_connected"])
            self.assertGreaterEqual(talk.stats["reconnects"], 1)
