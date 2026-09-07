from .base import BaseProvider, ProviderError, ProviderUnavailable


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(self, api_key: str = "", model: str = "", **kwargs):
        self.api_key = api_key or kwargs.get("gemini_api_key") or ""
        self.model = model or kwargs.get("gemini_model") or "gemini-2.5-flash-lite"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise ProviderUnavailable("GEMINI_API_KEY não configurada")
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(system_instruction=system_prompt),
            )
            return response.text or ""
        except Exception as exc:
            raise ProviderError(f"Gemini call failed: {exc}") from exc