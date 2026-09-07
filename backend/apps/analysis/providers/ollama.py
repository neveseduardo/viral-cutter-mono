from .base import BaseProvider, ProviderError, ProviderUnavailable


class OllamaProvider(BaseProvider):
    """Local/offline provider via Ollama HTTP API (AGENTS.md §7.3 local)."""

    name = "ollama"

    def __init__(self, base_url: str = "", model: str = "", force: bool = False, **kwargs):
        self.base_url = base_url or kwargs.get("ollama_url") or "http://127.0.0.1:11434"
        self.model = model or kwargs.get("ollama_model") or "llama3.1"
        self.force = force  # instantiate even if unreachable (last-resort path)

    def is_available(self) -> bool:
        if self.force:
            return True
        try:
            import httpx

            resp = httpx.get(f"{self.base_url}/api/tags", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if not self.is_available():
            raise ProviderUnavailable(f"Ollama não alcançável em {self.base_url}")
        try:
            import httpx

            resp = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "system": system_prompt,
                    "prompt": user_prompt,
                    "stream": False,
                    "options": {"temperature": 0.4},
                },
                timeout=300,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as exc:
            raise ProviderError(f"Ollama call failed: {exc}") from exc