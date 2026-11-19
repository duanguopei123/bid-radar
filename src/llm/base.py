"""LLM Provider 抽象接口（OpenAI 兼容协议）。

【合规红线】LLM 仅用于生成「摘要」与「匹配理由」文案，不参与任何对外报名/提交动作。
model / base_url / api_key 全部来自配置与环境变量，禁止硬编码。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import MatchResult


class LLMProvider(ABC):
    @abstractmethod
    def summarize(self, result: MatchResult) -> str:
        """为一个匹配结果生成 3 行中文摘要。失败时由调用方降级到模板。"""
        raise NotImplementedError
