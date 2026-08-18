import json
import os
import tempfile
import unittest
from pathlib import Path

from bridge.config import load_gateway_token


class TokenResolveTests(unittest.TestCase):
    def test_exec_secretref_resolves_without_env(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        helper = Path(temporary.name) / "resolver.py"
        helper.write_text(
            "import json,sys\n"
            "req=json.load(sys.stdin)\n"
            "sid=req['ids'][0]\n"
            "json.dump({'protocolVersion':1,'values':{sid:'resolved-token'}}, sys.stdout)\n"
        )
        config_path = Path(temporary.name) / "openclaw.json"
        config_path.write_text(
            json.dumps(
                {
                    "gateway": {
                        "auth": {
                            "token": {
                                "source": "exec",
                                "provider": "macos_keychain",
                                "id": "gateway/auth/token",
                            }
                        }
                    },
                    "secrets": {
                        "providers": {
                            "macos_keychain": {
                                "source": "exec",
                                "command": sys_executable(),
                                "args": [str(helper)],
                            }
                        }
                    },
                }
            )
        )
        os.environ["OPENCLAW_CONFIG"] = str(config_path)
        os.environ.pop("EVA_VOICE_BRIDGE_GATEWAY_TOKEN", None)
        os.environ.pop("OPENCLAW_GATEWAY_TOKEN", None)
        self.addCleanup(lambda: os.environ.pop("OPENCLAW_CONFIG", None))
        self.assertEqual(load_gateway_token(), "resolved-token")


def sys_executable():
    import sys

    return sys.executable
