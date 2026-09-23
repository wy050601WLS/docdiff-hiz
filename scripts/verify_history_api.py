"""临时脚本：进程内验证「比对 → 报告 → 问答 → 历史列表 → 恢复」整条持久化链路。

不起 Web 服务，用 FastAPI TestClient 直接调路由。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from docdiff.main import app  # noqa: E402

SAMPLES = ROOT / "samples"
OLD_PDF = SAMPLES / "技术规格说明书_Rev01.pdf"
NEW_PDF = SAMPLES / "技术规格说明书_Rev03.pdf"


def main() -> None:
    """按真实使用顺序跑一遍全部会话相关接口。"""
    client = TestClient(app)

    # 1. 比对（应自动创建会话并返回 session_id）
    with OLD_PDF.open("rb") as f1, NEW_PDF.open("rb") as f2:
        r = client.post(
            "/api/compare",
            files={"old_pdf": (OLD_PDF.name, f1, "application/pdf"), "new_pdf": (NEW_PDF.name, f2, "application/pdf")},
        )
    assert r.status_code == 200, r.text
    result = r.json()
    sid = result.get("session_id")
    print(f"[1] compare ok, session_id={sid}, stats={result['stats']}")

    # 2. 报告（应回存到会话）
    r = client.post("/api/report", json=result)
    assert r.status_code == 200, r.text
    print(f"[2] report ok, html_len={len(r.json()['report_html'])}")

    # 3. 问答（带 session_id，问答双方落库）
    r = client.post(
        "/api/chat",
        json={"question": "这两份文档有什么差异？", "context": result, "history": [], "session_id": sid},
    )
    assert r.status_code == 200, r.text
    print(f"[3] chat ok, answer[:60]={r.json()['answer'][:60]!r}")

    # 4. 会话列表
    r = client.get("/api/sessions")
    assert r.status_code == 200, r.text
    items = r.json()
    mine = [s for s in items if s["session_id"] == sid]
    assert mine, "刚创建的会话应出现在列表里"
    assert mine[0]["message_count"] == 2
    print(f"[4] sessions ok, count={len(items)}, message_count={mine[0]['message_count']}")

    # 5. 关键词检索（搜对话内容）
    r = client.get("/api/sessions", params={"q": "差异"})
    assert r.status_code == 200 and any(s["session_id"] == sid for s in r.json())
    print("[5] search ok (hit by chat content)")

    # 6. 恢复会话
    r = client.get(f"/api/sessions/{sid}")
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["compare"]["summary"] == result["summary"]
    assert len(detail["messages"]) == 2
    assert detail["report_html"], "报告应已存进会话"
    assert all(m["ts"] for m in detail["messages"]), "每条消息都应有时间戳"
    print(f"[6] restore ok, title={detail['title']!r}, messages={len(detail['messages'])}")

    # 7. 删除
    r = client.delete(f"/api/sessions/{sid}")
    assert r.status_code == 200
    r = client.get(f"/api/sessions/{sid}")
    assert r.status_code == 404
    print("[7] delete ok (404 after delete)")

    print("\nALL PASS")


if __name__ == "__main__":
    main()
