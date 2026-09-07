"""AI provider interface + factory (AGENTS.md §7.3 multi-provider)."""

from abc import ABC, abstractmethod


class ProviderError(Exception):
    """A provider call failed (retryable)."""


class ProviderUnavailable(ProviderError):
    """Provider is not configured/usable; try the next one in failover."""


class BaseProvider(ABC):
    name: str = "base"

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Returns the raw text response for a completion."""


class FailingProvider(BaseProvider):
    """Never succeeds — used as a placeholder to keep the factory total."""

    def __init__(self, reason: str = "provider não configurado"):
        self.reason = reason

    def complete(self, system_prompt, user_prompt):
        raise ProviderUnavailable(self.reason)


def iter_providers(order: list[str] | None, config: dict | None = None):
    """Yields (provider_name, provider) instances honoring AI_FAILOVER order."""
    from . import gemini, manual, ollama, openai_compat

    config = config or {}
    order = order or []

    registry = {
        "gemini": lambda: gemini.GeminiProvider(**config.get("gemini", {})),
        "openai": lambda: openai_compat.OpenAICompatProvider(**config.get("openai", {})),
        "g4f": lambda: FailingProvider("g4f não suportado no rebuild (use openai-compat)"),
        "ollama": lambda: ollama.OllamaProvider(**config.get("ollama", {})),
        "local": lambda: ollama.OllamaProvider(force=True, **config.get("ollama", {})),
        "manual": lambda: manual.ManualProvider(),
    }

    for name in order:
        if name not in registry:
            continue
        provider = registry[name]()
        if hasattr(provider, "is_available") and not provider.is_available():
            continue
        yield name, provider


def resolve_provider_order(ai_provider: str, failover: str | None = None, configured: dict | None = None) -> list[str]:
    configured = configured or {}
    failover = (failover or "").replace("auto", "").strip(",")
    order = []
    if ai_provider and ai_provider != "auto":
        order.append(ai_provider)
    for item in (failover or "").split(","):
        item = item.strip()
        if item and item not in order:
            order.append(item)
    if not order:
        order = ["gemini", "openai", "ollama", "manual"]
    return order