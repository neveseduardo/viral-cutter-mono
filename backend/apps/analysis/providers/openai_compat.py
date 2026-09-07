from .base import BaseProvider, ProviderError, ProviderUnavailable


class OpenAICompatProvider(BaseProvider):
    name = "openai"

    def __init__(self, api_key: str = "", model: str = "", base_url: str = "", **kwargs):
        self.api_key = api_key or kwargs.get("openai_api_key") or ""
        self.model = model or kwargs.get("openai_model") or "gpt-4o-mini"
        self.base_url = base_url or kwargs.get("openai_base_url") or ""

    def is_available(self) -> bool:
        return bool(self.api_key)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise ProviderUnavailable("OPENAI_API_KEY não configurada")
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, base_url=self.base_url or None)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:
            raise ProviderError(f"OpenAI-compatible call failed: {exc}") from exc