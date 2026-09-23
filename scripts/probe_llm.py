"""临时脚本：验证 LLMClient 的原生 Ollama 加速路径（think=false）。

不起 Web 服务，只验证 LLMClient -> Ollama 这一段的耗时与输出。
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from docdiff.services.llm_client import LLMClient  # noqa: E402


def main() -> None:
    """跑一次探活 + 一次真实对话，打印耗时。"""
    client = LLMClient()
    print("use_native_ollama =", client.use_native_ollama)
    t0 = time.time()
    online = client.is_available()
    print(f"probe: online={online}  ({time.time() - t0:.1f}s)")
    if not online:
        return

    messages = [
        {"role": "system", "content": "你是文档审阅助手，回答简明，引用差异用 [序号] 格式。"},
        {
            "role": "system",
            "content": "比对结果上下文：\n[1] 修改：应用服务器数量：1 台 -> 2 台\n[2] 修改：并发能力要求：不低于 200 QPS -> 500 QPS",
        },
        {"role": "user", "content": "这两份文档有什么差异？"},
    ]
    for i in range(2):
        t1 = time.time()
        answer = client.chat(messages)
        dt = time.time() - t1
        print(f"chat#{i + 1}: {dt:.1f}s")
        print(answer)
        print("-" * 40)


if __name__ == "__main__":
    main()
