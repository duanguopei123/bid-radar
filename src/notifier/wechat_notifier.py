"""微信推送通道：Server酱 与 PushPlus。

两者都是「微信扫码登录 → 拿 token → 一个 HTTP 请求 → 手机微信收到服务号消息」，
不需要企业认证、不需要装额外 App，适合个人每日简报。

- token 只从环境变量读取（SERVERCHAN_SENDKEY / PUSHPLUS_TOKEN），禁止硬编码。
- token 为空时只做 dry-run 并写审计日志，不实际外发。
- 仅推送简报文本，无任何报名、提交、CA 签章逻辑。
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from .base import Notifier

MAX_LEN = 8000  # 两个渠道内容上限都远大于此，这里保守截断避免超长报错


class _HttpMixin:
    """公共发送逻辑：POST 并解析 JSON 结果。"""

    name = "http"

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        timeout: int = 15,
    ) -> dict[str, Any]:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post_form(self, url: str, payload: dict[str, str], *, timeout: int = 15) -> dict[str, Any]:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _audit(self, message: str, *, detail: dict | None = None, level: str = "INFO") -> None:
        if getattr(self, "db", None):
            self.db.audit("push", message, detail=detail or {}, level=level)


class ServerChanNotifier(_HttpMixin, Notifier):
    """Server酱（sct.ftqq.com）。

    免费额度 5 条/天，微信扫码登录即可拿 SendKey，无需实名。
    - sct 开头：POST https://sctapi.ftqq.com/{key}.send
    - sctp 开头：POST https://{uid}.push.ft07.com/send/{key}.send（uid 是 sctp 与 t 之间的数字）
    成功判定：返回 JSON 的 code == 0。
    """

    name = "serverchan"

    def __init__(self, sendkey: str, db=None):
        self.sendkey = (sendkey or "").strip()
        self.db = db

    @property
    def enabled(self) -> bool:
        return bool(self.sendkey)

    def _endpoint(self) -> str:
        key = self.sendkey
        if key.startswith("sctp"):
            body = key[4:]
            uid = body.split("t")[0] if "t" in body else ""
            if uid:
                return f"https://{uid}.push.ft07.com/send/{key}.send"
        return f"https://sctapi.ftqq.com/{key}.send"

    def send(self, title: str, markdown: str) -> bool:
        # Server酱 的 title 不允许含换行，否则返回 999
        safe_title = " ".join((title or "").split()) or "招投标机会日报"
        content = (markdown or "")[:MAX_LEN]

        if not self.enabled:
            self._audit("Server酱 SendKey 未配置，跳过外发（dry-run）",
                        detail={"title": safe_title, "dry_run": True})
            return False

        try:
            body = self._post_form(self._endpoint(), {"title": safe_title, "desp": content})
        except Exception as exc:  # noqa: BLE001 - 推送失败不阻断本地简报
            self._audit(f"Server酱推送异常：{exc}", detail={"title": safe_title}, level="ERROR")
            return False

        ok = body.get("code") == 0
        self._audit(
            "Server酱推送" + ("成功" if ok else "失败"),
            detail={"title": safe_title, "response": body},
            level="INFO" if ok else "ERROR",
        )
        return ok


class PushPlusNotifier(_HttpMixin, Notifier):
    """PushPlus（pushplus.plus）。

    微信渠道需实名后可用（200 条/天）。接口：POST https://www.pushplus.plus/send
    body: {token, title, content, template="markdown"}
    成功判定：返回 JSON 的 code == 200。
    """

    name = "pushplus"

    def __init__(self, token: str, db=None):
        self.token = (token or "").strip()
        self.db = db

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def send(self, title: str, markdown: str) -> bool:
        safe_title = " ".join((title or "").split()) or "招投标机会日报"
        content = (markdown or "")[:MAX_LEN]

        if not self.enabled:
            self._audit("PushPlus token 未配置，跳过外发（dry-run）",
                        detail={"title": safe_title, "dry_run": True})
            return False

        try:
            body = self._post_json(
                "https://www.pushplus.plus/send",
                {
                    "token": self.token,
                    "title": safe_title,
                    "content": content,
                    "template": "markdown",
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._audit(f"PushPlus 推送异常：{exc}", detail={"title": safe_title}, level="ERROR")
            return False

        ok = body.get("code") == 200
        self._audit(
            "PushPlus 推送" + ("成功" if ok else "失败"),
            detail={"title": safe_title, "response": body},
            level="INFO" if ok else "ERROR",
        )
        return ok
