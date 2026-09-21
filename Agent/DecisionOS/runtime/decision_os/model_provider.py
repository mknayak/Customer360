"""Model-provider boundary for bounded DecisionOS planning and synthesis."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Protocol, Sequence
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ModelRequest:
    question: str
    context: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    max_output_tokens: int = 1200


@dataclass(frozen=True)
class ModelResponse:
    text: str
    provider: str
    model: str
    warnings: tuple[str, ...] = ()


class ModelProvider(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse: ...


class DeterministicModelProvider:
    """Test provider; production model clients can implement the same protocol."""

    def __init__(self, model: str = "deterministic-test") -> None:
        self.model = model

    def complete(self, request: ModelRequest) -> ModelResponse:
        if not request.question.strip():
            raise ValueError("Model question cannot be empty")
        tools = ", ".join(request.allowed_tools) or "none"
        return ModelResponse(
            text=f"Bounded investigation for: {request.question.strip()}\nAllowed tools: {tools}",
            provider="deterministic",
            model=self.model,
            warnings=("Deterministic provider; replace with an approved model client for production.",),
        )


class OpenAICompatibleModelProvider:
    """Use an OpenAI-compatible chat-completions endpoint when configured."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout_seconds: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "OpenAICompatibleModelProvider | None":
        base_url = os.getenv("LLM_BASE_URL")
        api_key = os.getenv("LLM_API_KEY")
        if not base_url or not api_key:
            return None
        return cls(base_url, api_key, os.getenv("LLM_MODEL", "gpt-4o-mini"), float(os.getenv("LLM_TIMEOUT_SECONDS", "20")))

    def complete(self, request: ModelRequest) -> ModelResponse:
        system = "You are a governed enterprise investigator. Use only supplied context. Separate facts from hypotheses and cite evidence IDs. Do not claim causality without comparative evidence."
        prompt = {"question": request.question, "context": request.context, "allowed_tools": request.allowed_tools}
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(prompt)}], "temperature": 0, "max_tokens": request.max_output_tokens}
        http_request = Request(f"{self.base_url}/v1/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, method="POST")
        with urlopen(http_request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read())
        text = payload["choices"][0]["message"]["content"]
        return ModelResponse(text=text, provider="openai-compatible", model=self.model)


def bounded_request(question: str, allowed_tools: Sequence[str], context: Sequence[str] = ()) -> ModelRequest:
    if len(question) > 4000:
        raise ValueError("Question exceeds bounded investigation limit")
    if len(allowed_tools) > 20:
        raise ValueError("Too many tools requested for one investigation")
    return ModelRequest(question=question, context=tuple(context)[:20], allowed_tools=tuple(allowed_tools))
