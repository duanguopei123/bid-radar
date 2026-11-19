# AGENTS.md —— 给 AI 编码工具的环境说明（Codex / CodeBuddy / Cursor 均自动读取本文件）

## 运行环境（重要，不要猜，不要改）

本项目自带虚拟环境，**所有 Python 命令必须使用项目内的解释器**：

```
.venv\Scripts\python.exe
```

绝对路径（Windows）：

```
C:\Users\ZJ\WorkBuddy\2026-11-19-14-31-48\bid-radar\.venv\Scripts\python.exe
```

**已确认的事实：**
- 系统 PATH 里的 `python` / `py` / `pytest` 一律**不要依赖**。本项目不假设它们存在。
- 项目**不使用** `pytest` 命令，统一用 `python -m pytest`。
- `.venv` 内已装好：PyYAML、requests、Jinja2、APScheduler、python-dotenv、tzdata、pytest。
- Python 版本：3.13。

## 标准命令（照抄，不要自己发明）

运行全部测试：
```
.venv\Scripts\python.exe -m pytest tests/ -q
```

运行单个测试文件：
```
.venv\Scripts\python.exe -m pytest tests\test_rules_edge.py -q
```

运行单个测试函数：
```
.venv\Scripts\python.exe -m pytest tests\test_rules_edge.py::test_省份不应被当成城市 -q
```

端到端跑一次流程（**使用 mock 数据源，不联网**）：
```
.venv\Scripts\python.exe run_once.py --all
```

在 Windows 批处理（cmd）里调用时，路径用反斜杠；在 bash 里用正斜杠或双引号包裹均可。

## 当前基线

- 测试数量：**47 个，全部通过**（1 秒内跑完）
- 测试文件：
  - `tests/test_scorer.py`（7）、`tests/test_rules_edge.py`（6）、`tests/test_mock_adapter.py`（2）—— 打分、规则、数据源契约
  - `tests/test_runtime_safety.py`（12）—— 静默失败类回归（状态机、重试、日期基准、入口退出码）
  - `tests/test_notifier_channels.py`（10）—— 推送通道路由与失败处理
  - `tests/test_brief_timezone.py`（7）—— 简报时间必须按本地时区展示，不得出现 `+00:00`
  - `tests/test_selfcheck.py`（3）—— 自检脚本不许崩、不许泄漏 Token

**任何人不许让测试数量减少。** 改了代码后测试总数只能增加。

## 硬性约束

1. 不要创建新的虚拟环境，不要 `pip install` 新依赖（需要新依赖先说明理由）。
2. 不要修改 `.venv`、不要改 `requirements.txt` 的版本号。
3. 不要修改 `tests/` 里已有测试的断言来让代码通过。
4. 不要执行任何会访问真实招标网站的联网请求。数据源只有 `mock`。
5. 不要 `git commit` / `git push`，改动留在工作区由人工审阅。
6. `.env` 里有真实密钥，**不要读取、不要打印、不要提交**。

## 目录速览

```
src/
  pipeline.py          # 主流程编排：采集 → 去重 → 打分 → 简报 → 推送
  config.py            # 配置加载 + .env 注入
  models.py            # 数据模型（Notice / MatchResult / DimensionScore）
  brief.py             # Markdown + HTML 简报渲染
  matcher/
    rules.py           # 规则层：区域、资质、预算、行业词等维度打分
    scorer.py          # 加权汇总 + 推荐阈值判定
  storage/
    db.py              # SQLite：去重指纹、状态变更、审计日志
  adapters/
    mock_adapter.py    # mock 数据源（唯一启用的数据源）
    base.py            # 适配器接口
tests/                 # pytest 用例
run_once.py            # 本地跑一次
selfcheck.py           # 自检：环境/配置/推送/定时/最近运行（只读，不发请求）
index.py               # 腾讯云函数定时入口
启动工作台.bat          # Windows 双击运行（已改用 .venv）
自检.bat                # 双击跑 selfcheck.py
```

## 业务背景（判断问题时需要）

只读 MVP：每天抓公开招标公告 → 按公司资质打分筛选 → 生成简报 → 推企微/邮箱。
**不做**自动报名、不做投标文件提交、不碰 CA 锁与电子签章。
公司画像：徐州运输企业，资质「道路运输经营许可证」，区域徐州/江苏，预算 1–100 万。
