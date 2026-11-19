"""自检脚本冒烟测试：不允许自检本身崩掉。

自检是用户判断「哪里配错了」的唯一入口，它崩了等于把人扔在原地。
"""
import io
import contextlib

import selfcheck


def test_selfcheck_runs_and_reports_sections():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = selfcheck.main()
    out = buf.getvalue()

    assert code == 0
    for section in ("Python 环境", "公司画像", "推送到手机", "数据与最近运行"):
        assert section in out


def test_selfcheck_always_ends_with_verdict():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        selfcheck.main()
    out = buf.getvalue()
    assert "全部检查通过" in out or "项待处理" in out


def test_selfcheck_does_not_leak_any_token():
    """Token 只能被打码显示，不能整串打印到屏幕。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        selfcheck.main()
    out = buf.getvalue()
    # 允许出现变量名，但不允许出现形如 32 位以上的连续密钥
    import re
    assert not re.search(r"[A-Za-z0-9]{30,}", out)
