"""应用配置。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从 .env 加载的环境配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DocDiff HIZ"
    app_port: int = 8000

    # 大模型配置（OpenAI 兼容接口）
    # 默认走本地 Ollama（http://localhost:11434/v1），无需联网、无需 API Key
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen3.5:9b"
    llm_timeout: float = 300.0  # 本地小模型推理慢，超时给足
    llm_enabled: bool = True  # 关掉则完全走离线规则报告
    # base_url 指向本机 Ollama 时自动改走原生 /api/chat 并关闭思考模式，
    # 思考型模型（qwen3.5 等）关掉后问答从 ~40s 降到 ~2s；其他供应商不受影响
    llm_native_ollama: bool = True
    llm_disable_think: bool = True

    # 解析与比对参数
    parse_max_pages: int = 0  # 0 表示不限制
    parse_prefer: str = "docling"  # docling 优先，失败自动降级 pypdf
    diff_similarity_threshold: float = 0.6  # 段落匹配阈值


settings = Settings()
