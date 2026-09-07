from .base import BaseProvider, ProviderError, ProviderUnavailable


class ManualProvider(BaseProvider):
    """No provider configured: the user pastes JSON manually (§7.3 manual)."""

    name = "manual"

    def __init__(self, **kwargs):
        self.pending = []

    def is_available(self) -> bool:
        return True

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        raise ProviderError(
            "manual: nenhum provider de IA configurado. Cole o JSON em 'manual', "
            "ou defina GEMINI_API_KEY / OPENAI_API_KEY / Ollama."
        )