"""HistoryStore 单元测试：持久化、追加、检索、删除。"""

import pytest

from docdiff.models.schemas import CompareResult
from docdiff.services.history_store import HistoryStore


def _make_result(**overrides) -> CompareResult:
    """构造一个最小可用的比对结果。"""
    base = dict(
        comparable=True,
        summary="共比对 17 组段落，风险等级 中。",
        risk_level="中",
        stats={"similar": 5, "modified": 8, "added": 3, "deleted": 1, "total": 17},
        old_meta={"filename": "旧版.pdf"},
        new_meta={"filename": "新版.pdf"},
    )
    base.update(overrides)
    return CompareResult(**base)


def test_create_and_get(tmp_path) -> None:
    """创建后能读回，字段完整，消息为空。"""
    store = HistoryStore(root=tmp_path / "sessions")
    sid = store.create(_make_result())

    assert len(sid) == 32 and all(c in "0123456789abcdef" for c in sid)

    record = store.get(sid)
    assert record is not None
    assert record["title"] == "旧版.pdf vs 新版.pdf"
    assert record["compare"]["summary"].startswith("共比对 17 组")
    assert record["messages"] == []
    assert record["report_html"] == ""
    assert record["created_at"] and record["updated_at"]


def test_append_chat_with_timestamp(tmp_path) -> None:
    """追加的消息带时间戳，计数正确。"""
    store = HistoryStore(root=tmp_path / "sessions")
    sid = store.create(_make_result())

    assert store.append_chat(sid, "user", "这两份文档有什么差异？") is True
    assert store.append_chat(sid, "assistant", "共 15 处差异…") is True

    record = store.get(sid)
    assert len(record["messages"]) == 2
    assert record["messages"][0]["role"] == "user"
    assert "T" in record["messages"][0]["ts"]  # ISO 格式时间戳


def test_append_chat_missing_session(tmp_path) -> None:
    """往不存在的会话追加应返回 False 而不是抛异常。"""
    store = HistoryStore(root=tmp_path / "sessions")
    assert store.append_chat("0" * 32, "user", "hi") is False


def test_set_report(tmp_path) -> None:
    """报告写进会话后可读回。"""
    store = HistoryStore(root=tmp_path / "sessions")
    sid = store.create(_make_result())
    assert store.set_report(sid, "<h1>报告</h1>", "# 报告") is True

    record = store.get(sid)
    assert record["report_html"] == "<h1>报告</h1>"
    assert record["report_markdown"] == "# 报告"


def test_list_and_search(tmp_path) -> None:
    """列表按时间倒序；搜索能命中对话内容。"""
    store = HistoryStore(root=tmp_path / "sessions")
    sid_a = store.create(_make_result(), title="规格书 A vs B")
    sid_b = store.create(_make_result(), title="合同 2025 vs 2026")

    store.append_chat(sid_b, "user", "违约责任改成了什么？")
    store.append_chat(sid_b, "assistant", "违约责任按合同总金额的 5% 计算。")

    sessions = store.list_sessions()
    assert len(sessions) == 2
    assert sessions[0]["session_id"] == sid_b  # b 更新过，排前面

    # 按对话内容搜
    hit = store.list_sessions(q="违约责任")
    assert [s["session_id"] for s in hit] == [sid_b]

    # 按标题搜
    hit = store.list_sessions(q="规格书")
    assert [s["session_id"] for s in hit] == [sid_a]

    # 列表条目是摘要，不含 diffs 大字段
    assert "compare" not in sessions[0]
    assert "message_count" in sessions[0]


def test_list_order_is_stable_within_same_second(tmp_path) -> None:
    """同一秒内连续建两个会话并更新其中一个，顺序必须仍然是确定的。

    这是一个真实踩过的坑：updated_at 原先只精确到秒，A、B 和「对 B 的更新」
    全落在同一秒里，排序退化成随机，界面表现为「刚操作过的会话没排到最前」。
    """
    store = HistoryStore(root=tmp_path / "sessions")
    sid_a = store.create(_make_result(), title="A")
    sid_b = store.create(_make_result(), title="B")
    store.append_chat(sid_b, "user", "更新一下 B")

    for _ in range(5):  # 反复取，顺序不能抖
        order = [s["session_id"] for s in store.list_sessions()]
        assert order == [sid_b, sid_a]


def test_delete(tmp_path) -> None:
    """删除后读不到，重复删除返回 False。"""
    store = HistoryStore(root=tmp_path / "sessions")
    sid = store.create(_make_result())

    assert store.delete(sid) is True
    assert store.get(sid) is None
    assert store.delete(sid) is False


def test_invalid_session_id_rejected(tmp_path) -> None:
    """非法 ID（路径穿越尝试）不允许读/删。"""
    store = HistoryStore(root=tmp_path / "sessions")
    with pytest.raises(ValueError):
        store.get("../../etc/passwd")
    assert store.delete("../../etc/passwd") is False
