"""通知器工厂：按 config.yaml 的 notifier.channel 装配推送通道。

支持：
- none            不外发，只落盘简报（默认，最安全）
- serverchan      Server酱（微信服务号，免费 5 条/天，无需实名）
- pushplus        PushPlus（微信服务号，需实名，200 条/天）
- wecom_webhook   企业微信群机器人

所有 token 均来自环境变量占位符，工厂只负责选择实现，不接触明文密钥。
"""
from __future__ import annotations

from .base import Notifier
from .wechat_notifier import PushPlusNotifier, ServerChanNotifier
from .wecom_notifier import WecomWebhookNotifier


def build_notifier(cfg: dict, db=None) -> Notifier | None:
    """返回通知器实例；渠道为 none 或未配置时返回 None（流水线会记为 skipped）。"""
    ncfg = cfg.get("notifier") or {}
    channel = str(ncfg.get("channel") or "none").strip().lower()

    if channel in ("", "none", "off", "disabled"):
        return None

    if channel == "serverchan":
        return ServerChanNotifier(ncfg.get("serverchan_sendkey", ""), db=db)

    if channel == "pushplus":
        return PushPlusNotifier(ncfg.get("pushplus_token", ""), db=db)

    if channel == "wecom_webhook":
        return WecomWebhookNotifier(ncfg.get("webhook_url", ""), db=db)

    raise ValueError(
        f"未知的通知渠道：{channel}。"
        f"可选值：none / serverchan / pushplus / wecom_webhook"
    )
