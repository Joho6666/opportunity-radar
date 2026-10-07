import json
from abc import ABC, abstractmethod
import httpx
from ..core.config import get_settings
from ..services import embedding_service


class LLMProvider(ABC):
    @abstractmethod
    async def structured_output(self, prompt: str, schema_name: str) -> dict: ...

    async def structured_output_with_usage(self, prompt: str, schema_name: str, model: str | None = None) -> tuple[dict, dict | None]:
        """Returns (payload, usage). Usage None = provider did not report tokens.
        model=None uses the default settings.llm_model."""
        return await self.structured_output(prompt, schema_name), None

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        """None means embeddings unavailable; callers must degrade gracefully."""
        return embedding_service.embed_texts_async(texts)


class OpenAICompatibleProvider(LLMProvider):
    async def structured_output_with_usage(self, prompt: str, schema_name: str, model: str | None = None) -> tuple[dict, dict | None]:
        settings = get_settings()
        if not settings.llm_api_key or not settings.llm_base_url:
            raise RuntimeError("LLM is not configured")
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(f"{settings.llm_base_url.rstrip('/')}/chat/completions", headers={"Authorization": f"Bearer {settings.llm_api_key}"}, json={"model": model or settings.llm_model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}})
            response.raise_for_status()
            payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
        parsed = json.loads(content)
        if not isinstance(parsed, dict): raise ValueError("LLM response is not a JSON object")
        return parsed, usage

    async def structured_output(self, prompt: str, schema_name: str) -> dict:
        payload, _usage = await self.structured_output_with_usage(prompt, schema_name)
        return payload


def get_provider() -> LLMProvider | None:
    """Returns the configured provider, or None to use deterministic fallbacks."""
    settings = get_settings()
    return OpenAICompatibleProvider() if settings.llm_api_key and settings.llm_base_url else None
