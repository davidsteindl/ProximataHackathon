"""Replay uses only REST; test human decisions are explicit fixture actions."""

import json

import pytest

from app.extraction import CachedExtractor, validate_quotes
from conftest import BACKEND


def test_offline_preflight_does_not_return_provider_configuration(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_KEY", "synthetic-secret-not-for-response")
    assert client.get("/replay/config").json() == {"offline_ready": False}
    monkeypatch.setenv("LLM_PROVIDER", "cached")
    assert client.get("/replay/config").json() == {"offline_ready": True}


def test_all_scenario_messages_have_offline_extraction_fixtures():
    scenario = json.loads((BACKEND / "demo/hero-scenario.json").read_text(encoding="utf-8"))
    extractor = CachedExtractor(BACKEND / "demo/extraction-cache.json")
    for step in scenario["steps"]:
        if "text" not in step:
            continue
        text = (f"Subject: {step['subject']}\n\n{step['text']}" if step.get("subject") else step["text"])
        batch = extractor.extract(text, step["sender_role"])
        statements = validate_quotes(batch, text, text)
        assert statements, step["id"]
