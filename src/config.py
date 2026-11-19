"""配置加载：.env 环境变量 + config.yaml。

- 所有密钥/URL/token 只从环境变量读取，禁止硬编码。
- config.yaml 中形如 ${VAR:-default} 的占位符会被环境变量替换。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
ENV_RE = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")


def load_dotenv(env_path: Path | None = None) -> None:
    """轻量 .env 加载（不依赖 python-dotenv，避免额外依赖）。"""
    path = env_path or (ROOT / ".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        def repl(m: re.Match) -> str:
            return os.environ.get(m.group(1), m.group(2) or "")
        return ENV_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def load_config(path: Path | None = None) -> dict[str, Any]:
    load_dotenv()
    cfg_path = path or (ROOT / "config.yaml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cfg = _expand(raw)

    # 目录路径统一转为基于项目根目录的绝对路径
    app = cfg.setdefault("app", {})
    for key in ("data_dir", "db_path", "out_dir", "log_dir"):
        p = Path(app.get(key, key))
        if not p.is_absolute():
            app[key] = str((ROOT / p).resolve())
        else:
            app[key] = str(p)

    for d in cfg.get("datasources", []):
        if d.get("type") == "mock":
            pass  # mock 数据源不需要外部配置
    return cfg
