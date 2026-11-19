"""微信推送通道测试：端点选择、密钥缺失时不外发、成功判定、标题清洗。"""
from __future__ import annotations

import io
import json
import urllib.parse

import pytest

from src.notifier.factory import build_notifier
from src.notifier.wechat_notifier import PushPlusNotifier, ServerChanNotifier


class _FakeResp:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, module, payload, captured: dict):
    def fake_urlopen(req, timeout=15):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = req.data.decode("utf-8")
        captured["headers"] = dict(req.header_items())
        return _FakeResp(payload)

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)


def test_serverchan_endpoint_for_sct_key():
    n = ServerChanNotifier("SCT123abc")
    assert n._endpoint() == "https://sctapi.ftqq.com/SCT123abc.send"


def test_serverchan_endpoint_for_sctp_key():
    n = ServerChanNotifier("sctp9876tXYZ")
    assert n._endpoint() == "https://9876.push.ft07.com/send/sctp9876tXYZ.send"


def test_serverchan_without_key_is_dry_run(monkeypatch):
    """未配置 SendKey 时不得发起任何网络请求。"""

    def boom(*a, **kw):
        raise AssertionError("未配置密钥时不应发起网络请求")

    monkeypatch.setattr("src.notifier.wechat_notifier.urllib.request.urlopen", boom)
    n = ServerChanNotifier("")
    assert n.enabled is False
    assert n.send("标题", "正文") is False


def test_serverchan_success_and_title_sanitized(monkeypatch):
    captured: dict = {}
    _patch_urlopen(monkeypatch, __import__("src.notifier.wechat_notifier", fromlist=["x"]),
                   {"code": 0, "message": "ok"}, captured)

    n = ServerChanNotifier("SCTKEY")
    ok = n.send("招投标日报\n第二行", "**正文**")

    assert ok is True
    form = urllib.parse.parse_qs(captured["body"])
    # 标题里的换行必须被压平（Server酱 遇到换行会返回 999），但内容要保留
    assert form["title"] == ["招投标日报 第二行"]
    assert form["desp"] == ["**正文**"]


def test_serverchan_failure_returns_false(monkeypatch):
    captured: dict = {}
    _patch_urlopen(monkeypatch, __import__("src.notifier.wechat_notifier", fromlist=["x"]),
                   {"code": 999, "message": "标题含换行"}, captured)
    assert ServerChanNotifier("SCTKEY").send("标题", "正文") is False


def test_pushplus_success(monkeypatch):
    captured: dict = {}
    _patch_urlopen(monkeypatch, __import__("src.notifier.wechat_notifier", fromlist=["x"]),
                   {"code": 200, "msg": "执行成功"}, captured)

    assert PushPlusNotifier("TOKEN123").send("日报", "**内容**") is True
    assert captured["url"] == "https://www.pushplus.plus/send"
    payload = json.loads(captured["body"])
    assert payload["token"] == "TOKEN123"
    assert payload["template"] == "markdown"


def test_pushplus_without_token_is_dry_run(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("未配置 token 时不应发起网络请求")

    monkeypatch.setattr("src.notifier.wechat_notifier.urllib.request.urlopen", boom)
    assert PushPlusNotifier("").send("日报", "内容") is False


def test_build_notifier_channel_none_returns_none():
    assert build_notifier({"notifier": {"channel": "none"}}) is None
    assert build_notifier({}) is None


def test_build_notifier_selects_channel():
    assert isinstance(
        build_notifier({"notifier": {"channel": "serverchan", "serverchan_sendkey": "K"}}),
        ServerChanNotifier,
    )
    assert isinstance(
        build_notifier({"notifier": {"channel": "pushplus", "pushplus_token": "T"}}),
        PushPlusNotifier,
    )


def test_build_notifier_rejects_unknown_channel():
    with pytest.raises(ValueError, match="未知的通知渠道"):
        build_notifier({"notifier": {"channel": "telegram"}})
