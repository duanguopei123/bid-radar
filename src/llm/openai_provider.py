"""OpenAI 兼容协议 LLM Provider。

- 仅用标准库 urllib 发起请求，无额外依赖。
- model / base_url / api_key 来自配置（环境变量），禁止硬编码。
- 本 Provider 只生成文本文案，不做任何对外报名/提交/CA/签章操作。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..models import MatchResult
from .base import LLMProvider
from .templates import template_summary

SYSTEM_PROMPT = (
    "你是招投标分析助手。只根据给定信息生成中文摘要，不得编造事实，"
    "不得建议或执行任何报名、提交投标文件的操作。输出严格 3 行，每行一句。"
)


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, model: str, base_url: str, api_key: str,
                 timeout: int = 30, db=None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.db = db

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def summarize(self, result: MatchResult) -> str:
        if not self.available:
            return template_summary(result)
        n = result.notice
        user_content = (
            f"标题：{n.title}\n采购人：{n.purchaser}\n地区：{n.region}\n"
            f"预算：{n.budget_amount} 元\n资质要求：{n.qualification}\n"
            f"报名截止：{n.registration_deadline}\n匹配分：{result.score}\n"
            f"匹配理由：{'；'.join(result.reasons)}\n风险提示：{'；'.join(result.risks)}\n"
            "请输出 3 行摘要（项目概况 / 匹配亮点 / 风险与截止提醒）。"
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.3,
        }
        url = f"{self.base_url}/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"].strip()
            if self.db:
                self.db.audit("llm", "LLM 摘要生成成功", ref_id=self._ref(result),
                              detail={"model": self.model, "mode": "llm"})
            return content
        except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError) as exc:
            # 失败降级：不阻断流程，保证 run-once 可产出简报
            if self.db:
                self.db.audit("llm", f"LLM 调用失败，降级模板：{exc}", ref_id=self._ref(result),
                              detail={"model": self.model, "mode": "template_fallback"}, level="WARN")
            return template_summary(result)

    @staticmethod
    def _ref(result: MatchResult) -> str:
        return result.notice.notice_id
