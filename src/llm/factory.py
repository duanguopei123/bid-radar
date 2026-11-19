"""LLM Provider 工厂：根据配置返回 Provider，key 为空时返回模板 Provider。"""
from __future__ import annotations

from .base import LLMProvider
from .openai_provider import OpenAICompatibleProvider
from .templates import TemplateProvider


def build_provider(llm_cfg: dict, db=None) -> LLMProvider:
    if not llm_cfg.get("enabled", False):
        return TemplateProvider()
    api_key = llm_cfg.get("api_key", "")
    if not api_key:
        return TemplateProvider()
    return OpenAICompatibleProvider(
        model=llm_cfg["model"],
        base_url=llm_cfg["base_url"],
        api_key=api_key,
        timeout=int(llm_cfg.get("timeout_seconds", 30)),
        db=db,
    )
