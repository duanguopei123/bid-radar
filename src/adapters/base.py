"""数据源适配器抽象接口。

新增真实数据源时，继承 DataSourceAdapter 实现 fetch() 即可，主流程无需改动。

【合规红线 · 实现真实适配器时必须遵守】
1. 只访问官方开放接口 / 公共服务平台 / 已获授权的数据服务；
   不绕过验证码、登录墙、频率限制；遵守 robots.txt 与服务条款。
2. 每条数据必须保留 source_url、fetched_at 与 raw_snapshot（原始响应片段）。
3. fetch() 只读：禁止任何报名、提交、下单等对外写入；禁止触碰 CA 锁 / 电子签章。
4. 不做登录态抓取；所有动作记录到审计日志。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import Notice


class DataSourceAdapter(ABC):
    name: str = "base"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    @abstractmethod
    def fetch(self) -> list[Notice]:
        """抓取公告列表（只读）。实现者需保证每条 Notice 含来源/时间/快照。"""
        raise NotImplementedError
