from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from urllib import error as urllib_error
from urllib import request as urllib_request

from .errors import OllamaConnectionError, OllamaModelNotFoundError, OllamaResponseError


@dataclass(frozen=True)
class OllamaConfig:
    model: str = "llama3.2:3b"
    base_url: str = "http://localhost:11434"
    timeout_seconds: int = 90
    temperature: float = 0.0


@dataclass(frozen=True)
class OllamaResult:
    content: str
    model: str
    latency_ms: int
    prompt_eval_count: int | None
    eval_count: int | None
    raw: dict


class OllamaClient:
    def __init__(self, config: OllamaConfig | None = None) -> None:
        self.config = config or OllamaConfig()

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> OllamaResult:
        endpoint = f"{self.config.base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.config.model,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.config.temperature,
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        req = urllib_request.Request(
            endpoint,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        started = perf_counter()
        try:
            with urllib_request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8", errors="replace")
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            self._raise_from_body(body, fallback=f"Ollama HTTP error {exc.code}")
        except urllib_error.URLError as exc:
            raise OllamaConnectionError(
                "Unable to reach Ollama at "
                f"{self.config.base_url}. Ensure Ollama is running (e.g., `ollama serve`)."
            ) from exc
        except TimeoutError as exc:
            raise OllamaConnectionError(
                f"Timed out calling Ollama after {self.config.timeout_seconds}s"
            ) from exc

        latency_ms = int((perf_counter() - started) * 1000)

        try:
            payload_obj = json.loads(raw_body)
        except Exception as exc:
            raise OllamaResponseError("Ollama returned non-JSON response") from exc

        if not isinstance(payload_obj, dict):
            raise OllamaResponseError("Ollama response must be a JSON object")

        if payload_obj.get("error"):
            self._raise_from_body(str(payload_obj["error"]), fallback="Ollama returned an error")

        message = payload_obj.get("message")
        if not isinstance(message, dict):
            raise OllamaResponseError("Ollama response is missing 'message' object")

        content = str(message.get("content", "")).strip()
        if not content:
            raise OllamaResponseError("Ollama returned an empty message content")

        return OllamaResult(
            content=content,
            model=str(payload_obj.get("model", self.config.model)),
            latency_ms=latency_ms,
            prompt_eval_count=_maybe_int(payload_obj.get("prompt_eval_count")),
            eval_count=_maybe_int(payload_obj.get("eval_count")),
            raw=payload_obj,
        )

    def _raise_from_body(self, body: str, *, fallback: str) -> None:
        lowered = body.lower()
        if "model" in lowered and "not found" in lowered:
            raise OllamaModelNotFoundError(
                f"Model '{self.config.model}' not found in Ollama. Pull it with: `ollama pull {self.config.model}`"
            )
        if "connect" in lowered or "refused" in lowered:
            raise OllamaConnectionError(
                "Unable to connect to Ollama. Start it with `ollama serve` and retry."
            )
        raise OllamaResponseError(f"{fallback}: {body[:300]}")


def _maybe_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None