import json
from abc import ABC, abstractmethod
import httpx
from ..core.config import get_settings


class LLMProvider(ABC):
    @abstractmethod
    async def structured_output(self, prompt: str, schema_name: str) -> dict: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: return []


class OpenAICompatibleProvider(LLMProvider):
    async def structured_output(self, prompt: str, schema_name: str) -> dict:
        settings = get_settings()
        if not settings.llm_api_key or not settings.llm_base_url:
            raise RuntimeError("LLM is not configured")
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(f"{settings.llm_base_url.rstrip('/')}/chat/completions", headers={"Authorization": f"Bearer {settings.llm_api_key}"}, json={"model": settings.llm_model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}})
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict): raise ValueError("LLM response is not a JSON object")
        return parsed


def get_provider() -> LLMProvider | None:
    """Returns the configured provider, or None to use deterministic fallbacks."""
    settings = get_settings()
    return OpenAICompatibleProvider() if settings.llm_api_key and settings.llm_base_url else None
