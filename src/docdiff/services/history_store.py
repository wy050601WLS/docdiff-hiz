"""会话历史持久化：每个会话一个 JSON 文件，存比对结果、报告与全部对话。

设计取舍：
- 选 JSON 文件而不是 SQLite：单机面试作业的量级（几十上百个会话），
  文件方案零依赖、可直接打开看、拷走即备份；真到多用户/高频写再换库。
- 原子写入（临时文件 + os.replace）：进程中途被杀也不会留下半个坏文件，
  最坏情况是丢「正在写的这一条」，已保存的内容一定完整。
- 所有写操作共用一把线程锁：FastAPI 的同步路由跑在线程池里，
  两个请求同时写同一个文件时，不加锁会出现互相覆盖。
"""

import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from docdiff.models.schemas import CompareResult

_DEFAULT_ROOT = Path("data") / "sessions"


def _now() -> str:
    """当前时间，带本地时区，微秒级。

    不用秒级是因为同一秒内建多个会话很常见，时间戳撞车会让列表排序退化成随机。
    """
    return datetime.now().astimezone().isoformat(timespec="microseconds")


class HistoryStore:
    """会话历史的存取，root 默认是 data/sessions。"""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else _DEFAULT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ---------- 路径与基础工具 ----------

    def _path(self, session_id: str) -> Path:
        # session_id 只允许 uuid4().hex 中可能出现的字符，防止路径穿越
        if not re.fullmatch(r"[0-9a-f]{32}", session_id):
            raise ValueError("非法的会话 ID")
        return self.root / f"{session_id}.json"

    def _write_atomic(self, path: Path, data: Dict[str, Any]) -> None:
        """原子写入：先写临时文件再 replace，任何时刻磁盘上都是完整文件。"""
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # Windows 上 replace 也保证原子性

    def _read(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            # 理论上原子写入后不会出现坏文件；真出现（如磁盘故障）就跳过，
            # 不让一个坏文件拖死整个历史列表
            return None

    # ---------- 对外接口 ----------

    def create(self, result: CompareResult, title: Optional[str] = None) -> str:
        """新建一个会话，写入比对结果。

        Args:
            result: 比对结果
            title: 会话标题，缺省用「旧版文件名 vs 新版文件名」

        Returns:
            会话 ID
        """
        session_id = uuid.uuid4().hex
        if not title:
            old_name = (result.old_meta or {}).get("filename") or "文档A"
            new_name = (result.new_meta or {}).get("filename") or "文档B"
            title = f"{old_name} vs {new_name}"

        record: Dict[str, Any] = {
            "session_id": session_id,
            "title": title,
            "created_at": _now(),
            "updated_at": _now(),
            "compare": json.loads(result.model_dump_json()),
            "report_html": "",
            "report_markdown": "",
            "messages": [],
        }
        with self._lock:
            self._write_atomic(self._path(session_id), record)
        return session_id

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """读取完整会话，不存在返回 None。"""
        with self._lock:
            return self._read(self._path(session_id))

    def append_chat(self, session_id: str, role: str, content: str) -> bool:
        """向会话追加一条对话消息（带时间戳）。

        Returns:
            会话是否存在
        """
        with self._lock:
            path = self._path(session_id)
            record = self._read(path)
            if record is None:
                return False
            record["messages"].append({"role": role, "content": content, "ts": _now()})
            record["updated_at"] = _now()
            self._write_atomic(path, record)
            return True

    def set_report(self, session_id: str, report_html: str, report_markdown: str) -> bool:
        """把生成的报告存进会话，恢复会话时不用重新生成。"""
        with self._lock:
            path = self._path(session_id)
            record = self._read(path)
            if record is None:
                return False
            record["report_html"] = report_html
            record["report_markdown"] = report_markdown
            record["updated_at"] = _now()
            self._write_atomic(path, record)
            return True

    def list_sessions(self, q: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """列出会话（按更新时间倒序），q 非空时做全文过滤。

        搜索范围：标题、综合结论、全部对话内容。返回的是列表摘要
        （不含 diffs 大字段），列表页不需要完整数据。
        """
        needle = (q or "").strip().lower()
        items: List[Dict[str, Any]] = []
        for path in self.root.glob("*.json"):
            record = self._read(path)
            if record is None:
                continue
            if needle:
                haystack = json.dumps(
                    [record.get("title", ""), (record.get("compare") or {}).get("summary", ""),
                     *[m.get("content", "") for m in record.get("messages", [])]],
                    ensure_ascii=False,
                ).lower()
                if needle not in haystack:
                    continue
            messages = record.get("messages", [])
            compare = record.get("compare") or {}
            items.append(
                {
                    "session_id": record["session_id"],
                    "title": record.get("title", ""),
                    "created_at": record.get("created_at", ""),
                    "updated_at": record.get("updated_at", ""),
                    "summary": compare.get("summary", ""),
                    "risk_level": compare.get("risk_level", ""),
                    "stats": compare.get("stats", {}),
                    "message_count": len(messages),
                }
            )
        # 主键时间倒序；再拿 session_id 兜底，保证顺序完全确定
        # （时间戳理论上仍可能撞车，列表顺序不该因此抖动）
        items.sort(key=lambda x: (x["updated_at"], x["session_id"]), reverse=True)
        return items[:limit]

    def delete(self, session_id: str) -> bool:
        """删除会话文件。"""
        with self._lock:
            try:
                path = self._path(session_id)
            except ValueError:
                return False
            if not path.exists():
                return False
            path.unlink()
            return True
