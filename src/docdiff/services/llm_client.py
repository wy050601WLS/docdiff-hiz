"""大模型客户端封装（OpenAI 兼容接口 + Ollama 原生接口自动加速）。"""

import re
from typing import Any, Dict, List

import httpx

from docdiff.config import settings

# qwen3/deepseek 等推理模型会把思考过程包在 <think>...</think> 里一起返回，
# 不剥掉的话用户会在回答里看到一大段思考过程
_THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)


def _strip_think(text: str) -> str:
    """剥离模型输出中的 <think> 思考块，并去掉首尾空白。"""
    return _THINK_RE.sub("", text or "").strip()


class LLMUnavailableError(RuntimeError):
    """大模型不可用时抛出，调用方据此走离线兜底。"""


class LLMClient:
    """调用大模型对话接口。

    两条路径：
    - OpenAI 兼容接口（/v1/chat/completions）：通用，任何供应商都能用。
    - Ollama 原生接口（/api/chat）：当 base_url 指向本机 Ollama 时自动启用，
      并带上 ``think=false`` 关闭思考模式。

    为什么两条都要：qwen3.5 这类思考型模型走 OpenAI 兼容接口时，思考 token
    也计入生成量，一次问答要 30~40 秒；走原生接口关掉思考后同样的回答
    只要 2 秒左右（本机实测 1.8s vs 37.7s）。但原生接口是 Ollama 私有格式，
    换成 vLLM / 云端供应商就失效，所以保留 OpenAI 兼容作为通用兜底。
    """

    def __init__(self) -> None:
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.enabled = settings.llm_enabled
        self.disable_think = settings.llm_disable_think
        # 本地 7B/9B 模型首 token 可能要几十秒，超时留足
        self.timeout = httpx.Timeout(settings.llm_timeout, connect=10.0)
        # 仅当指向本机 Ollama 时才走原生接口，其他供应商自动回落 OpenAI 兼容
        self.use_native_ollama = settings.llm_native_ollama and ":11434" in self.base_url

    def is_available(self) -> bool:
        """快速探测模型服务是否在线（3 秒超时，不阻塞主流程）。"""
        if not self.enabled:
            return False
        try:
            with httpx.Client(timeout=httpx.Timeout(3.0)) as client:
                resp = client.get(f"{self.base_url}/models")
                return resp.status_code == 200
        except Exception:
            return False

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 512,
    ) -> str:
        """同步调用大模型对话接口。

        Args:
            messages: OpenAI 格式消息列表
            temperature: 采样温度
            max_tokens: 生成上限。思考型模型下思考 token 也计入，
                太小会把正文截断；对话场景 512 够用，长报告可调大。

        Returns:
            模型回答文本（已剥离 <think> 思考块）

        Raises:
            LLMUnavailableError: 未启用或调用失败
        """
        if not self.enabled:
            raise LLMUnavailableError("大模型已被配置禁用（LLM_ENABLED=false）")

        if self.use_native_ollama:
            try:
                return self._chat_ollama_native(messages, temperature, max_tokens)
            except LLMUnavailableError:
                # 原生接口失败（Ollama 版本过旧不支持 think 字段等），
                # 回落 OpenAI 兼容接口再试一次
                pass
        return self._chat_openai_compat(messages, temperature, max_tokens)

    def _chat_ollama_native(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Ollama 原生 /api/chat，支持 think 开关，速度快一个数量级。"""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": not self.disable_think,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            # base_url 形如 http://localhost:11434/v1，原生接口要去掉 /v1
            root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{root}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return _strip_think(data.get("message", {}).get("content", ""))
        except Exception as exc:
            raise LLMUnavailableError(f"Ollama 原生接口调用失败：{exc}") from exc

    def _chat_openai_compat(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """OpenAI 兼容 /v1/chat/completions，通用路径。"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return _strip_think(data["choices"][0]["message"]["content"])
        except Exception as exc:
            raise LLMUnavailableError(f"调用大模型失败：{exc}") from exc
