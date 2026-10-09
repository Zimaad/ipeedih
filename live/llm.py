"""Groq chat client: OpenAI-compatible, retries across keys, rotates on rate limits.

Nothing here is ContainMAS-specific. It just turns messages + tool specs into a model reply.
"""
from __future__ import annotations

import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"
MODELS = {  # friendly name -> (provider, model id)
    "gpt-oss-20b": ("groq", "openai/gpt-oss-20b"),
    "gpt-oss-120b": ("groq", "openai/gpt-oss-120b"),
    "qwen3-27b": ("groq", "qwen/qwen3.8-27b"),
    "gemini-flash": ("gemini", "gemini-2.0-flash"),
}


def _groq_keys() -> list[str]:
    keys = [os.environ.get("GROQ_API_KEY", "")]
    keys += [os.environ.get(f"GROQ_API_KEY{i}", "") for i in (2, 3, 4)]
    return [k for k in keys if k]


class LLM:
    def __init__(self, model: str = "gpt-oss-20b", temperature: float = 0.0):
        self.provider, self.model_id = MODELS.get(model, ("groq", model))
        self.temperature = temperature
        self.calls = 0

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Return the assistant message dict ({role, content, tool_calls?})."""
        body = {"model": self.model_id, "temperature": self.temperature, "messages": messages}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        self.calls += 1
        if self.provider == "gemini":
            return self._post(GEMINI_URL, [os.environ.get("GEMINI_API_KEY", "")], body)
        return self._post(GROQ_URL, _groq_keys(), body)

    def _post(self, url: str, keys: list[str], body: dict) -> dict:
        if not keys:
            raise RuntimeError(f"no API key for provider {self.provider}")
        last = None
        for attempt in range(6):
            key = keys[attempt % len(keys)]
            try:
                r = httpx.post(url, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=60)
                if r.status_code == 429:  # rate limited: try the next key, then back off
                    last = RuntimeError("429 rate limit")
                    time.sleep(min(2 ** attempt, 8) if attempt >= len(keys) else 0)
                    continue
                if r.status_code >= 400:
                    last = RuntimeError(f"{r.status_code}: {r.text[:300]}")
                    if r.status_code == 400:
                        break   # bad request won't fix itself on retry
                    time.sleep(min(2 ** attempt, 8))
                    continue
                return r.json()["choices"][0]["message"]
            except httpx.HTTPError as e:
                last = e
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"LLM call failed after retries: {last}")
