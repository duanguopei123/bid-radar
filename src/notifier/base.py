"""通知器抽象接口。

【合规红线】notifier 仅推送「简报文本」给负责人本人/内部群，属于人工决策辅助；
系统绝不通过本通道或任何通道执行报名、提交投标文件、CA 签章等对外写入动作。
所有推送结果写入审计日志。webhook URL 只从环境变量读取，禁止硬编码。
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class Notifier(ABC):
    @abstractmethod
    def send(self, title: str, markdown: str) -> bool:
        """发送简报。返回是否成功。实现者不得包含任何报名/提交逻辑。"""
        raise NotImplementedError
