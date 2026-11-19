"""企业微信机器人 webhook 通知器。

- webhook URL 来自环境变量（config.yaml 中 ${WECOM_WEBHOOK_URL}）。
- URL 为空时只做 dry-run（记录日志），不实际外发：run-once 默认安全行为。
- 仅发送文本/markdown 简报，无任何报名、提交、CA、签章操作。
"""
from __future__ import annotations

import json
import urllib.request

from .base import Notifier

MAX_LEN = 4096  # 企微机器人 markdown 单条消息长度上限


class WecomWebhookNotifier(Notifier):
    def __init__(self, webhook_url: str, db=None):
        self.webhook_url = webhook_url
        self.db = db

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def send(self, title: str, markdown: str) -> bool:
        content = markdown[:MAX_LEN]
        if not self.enabled:
            if self.db:
                self.db.audit("push", "webhook 未配置，跳过外发（dry-run）",
                              detail={"title": title, "dry_run": True})
            return False
        payload = {"msgtype": "markdown", "markdown": {"content": content}}
        req = urllib.request.Request(
            self.webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            ok = body.get("errcode") == 0
            if self.db:
                self.db.audit("push", "企微推送" + ("成功" if ok else "失败"),
                              detail={"title": title, "response": body},
                              level="INFO" if ok else "WARN")
            return ok
        except Exception as exc:  # noqa: BLE001 - 推送失败不应阻断本地简报产出
            if self.db:
                self.db.audit("push", f"企微推送异常：{exc}", detail={"title": title}, level="WARN")
            return False
