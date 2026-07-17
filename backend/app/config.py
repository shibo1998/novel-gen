from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM 配置（统一格式，支持任意兼容 OpenAI API 的 provider）
    llm_base_url: str = "https://api.x6m6x.com/v1"
    llm_api_key: str = ""
    llm_model: str = "glm-5.2"
    llm_provider: str = "openai"

    # 兼容旧配置（可选）
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    deepseek_model: str = "deepseek-chat"
    anthropic_model: str = "claude-3-5-sonnet-20240620"

    # Embedding 配置
    embed_base_url: str = "http://localhost:11434/v1"
    embed_model: str = "bge-m3"
    embed_dim: int = 1024
    embed_api_key: str = "ollama"
    embedding_model: str = "text-embedding-3-small"
    memory_reindex_enabled: bool = True
    memory_reindex_interval_seconds: float = 300.0
    memory_reindex_batch_size: int = 25

    # 数据库配置
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "novel_gen"
    db_user: str = "novel"
    db_password: str = "novel123"
    auto_migrate: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT 配置
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080
    refresh_token_expire_days: int = 30
    login_failure_limit: int = 5
    login_failure_window_seconds: int = 900
    login_throttle_max_entries: int = 10000

    # LLM 熔断配置
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3
    llm_circuit_breaker_threshold: int = 5
    llm_max_tokens: int = 8192
    prompt_version: str = "v4"
    max_recovery_attempts: int = 2
    scene_recovery_allowance: float = 1.0
    max_cost_per_chapter: float = 1.50
    max_cost_per_project: float = 100.00
    budget_warn_threshold: float = 0.7
    budget_fail_closed_without_metrics: bool = False
    budget_reservation_ttl_seconds: int = 600

    # CORS 配置
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # 运行环境：development / production。production 下强制校验密钥非默认值
    environment: str = "development"

    @computed_field
    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in ("production", "prod")

    # 生产环境禁止使用的默认/弱值
    _INSECURE_DEFAULTS = {
        "secret_key": "change-me-in-production",
        "db_password": "novel123",
    }

    def security_warnings(self) -> list[str]:
        """返回当前配置里仍是默认/弱值的安全项（不区分环境）。"""
        warnings: list[str] = []
        if self.secret_key == self._INSECURE_DEFAULTS["secret_key"]:
            warnings.append("secret_key 仍是默认值，JWT 可被伪造")
        if len(self.secret_key) < 32:
            warnings.append("secret_key 长度不足 32 字符，签名强度偏弱")
        if self.db_password == self._INSECURE_DEFAULTS["db_password"]:
            warnings.append("db_password 仍是默认弱口令")
        if "*" in self.cors_origins:
            warnings.append("cors_origins 含通配符 '*'，与带凭证的 CORS 组合不安全")
        return warnings

    def validate_security(self) -> None:
        """启动时安全校验：生产环境下发现不安全默认值直接拒绝启动，开发环境仅告警。"""
        warnings = self.security_warnings()
        if not warnings:
            return
        if self.is_production:
            raise RuntimeError(
                "生产环境安全校验失败，请在环境变量中覆盖以下配置：\n  - "
                + "\n  - ".join(warnings)
            )
        import logging

        logger = logging.getLogger(__name__)
        for w in warnings:
            logger.warning("[安全告警] %s（开发环境放行，生产环境将拒绝启动）", w)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
