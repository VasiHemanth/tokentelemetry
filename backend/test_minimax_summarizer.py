import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import summaries
from summarizers import get_summarizer
from summarizers.minimax import DEFAULT_MODEL, MiniMaxSummarizer, available_options


class MiniMaxSummarizerTests(unittest.TestCase):
    def test_protocol_region_endpoint_matrix(self):
        endpoints = [
            ("global_en", "openai", "https://api.minimax.io/v1/chat/completions"),
            ("global_en", "anthropic", "https://api.minimax.io/anthropic/v1/messages"),
            ("cn_zh", "openai", "https://api.minimaxi.com/v1/chat/completions"),
            ("cn_zh", "anthropic", "https://api.minimaxi.com/anthropic/v1/messages"),
        ]

        for region, protocol, expected_url in endpoints:
            with self.subTest(region=region, protocol=protocol):
                sm = MiniMaxSummarizer(
                    model="MiniMax-M3",
                    config={
                        "region": region,
                        "protocol": protocol,
                        "api_key": "test-key",
                        "thinking": "adaptive",
                    },
                )
                captured = {}

                def fake_post(url, payload, headers, timeout):
                    captured.update(
                        url=url,
                        payload=payload,
                        headers=headers,
                        timeout=timeout,
                    )
                    if protocol == "anthropic":
                        return json.dumps({
                            "content": [{"type": "text", "text": "ok"}]
                        })
                    return json.dumps({
                        "choices": [{"message": {"content": "ok"}}]
                    })

                with patch.object(sm, "_post", side_effect=fake_post):
                    self.assertEqual(sm.summarize("hello", timeout=9), "ok")

                self.assertEqual(captured["url"], expected_url)
                self.assertEqual(
                    captured["payload"]["thinking"], {"type": "adaptive"}
                )
                self.assertEqual(
                    captured["headers"]["Authorization"], "Bearer test-key"
                )
                self.assertEqual(captured["timeout"], 9)

    def test_m27_thinking_remains_always_on(self):
        sm = MiniMaxSummarizer(
            model="MiniMax-M2.7",
            config={"region": "global_en", "protocol": "anthropic"},
        )
        captured = {}

        def fake_post(url, payload, headers, timeout):
            captured.update(url=url, payload=payload)
            return json.dumps({
                "content": [
                    {"type": "thinking", "thinking": "hidden"},
                    {"type": "text", "text": "summary"},
                ]
            })

        with patch.object(sm, "_post", side_effect=fake_post):
            self.assertEqual(sm.summarize("hello"), "summary")

        self.assertNotIn("thinking", captured["payload"])

    def test_registry_and_options_expose_current_models(self):
        sm = get_summarizer("minimax", "MiniMax-M3", {"protocol": "openai"})
        self.assertIsInstance(sm, MiniMaxSummarizer)
        self.assertEqual(available_options()["default_model"], DEFAULT_MODEL)
        self.assertEqual(
            [item["name"] for item in available_options()["models"]],
            ["MiniMax-M3", "MiniMax-M2.7"],
        )

    def test_minimax_config_is_coerced_and_persisted(self):
        for model in (None, "unsupported-model"):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                with patch.object(summaries, "TT_HOME", home):
                    with patch.object(
                        summaries, "_CONFIG_PATH", home / "summarizer.json"
                    ):
                        saved = summaries.save_config({
                            "enabled": True,
                            "backend": "minimax",
                            "model": model,
                            "minimax": {
                                "region": "cn_zh",
                                "protocol": "openai",
                                "max_tokens": "768",
                                "thinking": "disabled",
                            },
                        })

                self.assertEqual(saved["model"], DEFAULT_MODEL)
                self.assertEqual(saved["minimax"]["region"], "cn_zh")
                self.assertEqual(saved["minimax"]["protocol"], "openai")
                self.assertEqual(saved["minimax"]["max_tokens"], 768)
                self.assertEqual(saved["minimax"]["thinking"], "disabled")


if __name__ == "__main__":
    unittest.main()
