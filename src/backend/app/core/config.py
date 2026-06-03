"""Application configuration using pydantic-settings."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database (lite MySQL: make setup / make db-mysql-dev → mchat / mchat123 / mchat)
    database_url: str = "mysql+aiomysql://mchat:mchat123@localhost:3307/mchat"

    # JWT
    jwt_secret: str = "change-this-to-a-random-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_enabled: bool = False

    # Embedding global defaults (admin UI → DB overrides these at runtime; .env is fallback only)
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_api_base: str = "http://localhost:11434"
    embedding_dimension: int = 768
    embedding_model_max_mb: int = 2048

    # Maintenance & server ops (persisted in settings DB; synced at startup)
    maintenance_mode: bool = False
    server_ops_skills_enabled: bool = False
    server_ops_skill_allowlist: list[str] | None = None
    server_ops_shell_allowlist: list[dict] | None = None

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Cloud portal: SMS OTP (dev: fixed code when sms_dev_mode=true)
    sms_dev_mode: bool = False
    sms_dev_code: str = "123456"
    otp_expire_seconds: int = 600
    otp_send_cooldown_seconds: int = 60
    # Aliyun SMS (same template as www.9235.net — patentapi UserService)
    aliyun_sms_access_key_id: str = ""
    aliyun_sms_access_key_secret: str = ""
    aliyun_sms_sign_name: str = "笑溢网络"
    aliyun_sms_template_code: str = "SMS_289525897"
    aliyun_sms_alert_template_code: str = ""
    aliyun_sms_region: str = "cn-hangzhou"

    # Notification (runtime synced from settings DB; default dev=log only)
    sms_default_provider: str = "dev"
    sms_phone_allowlist: list[str] | None = None
    sms_alert_phones: list[str] | None = None
    sms_send_cooldown_seconds: int = 60
    sms_workflow_alert_enabled: bool = False
    notification_skills_enabled: bool = False
    notification_skill_allowlist: list[str] | None = None

    # Patent portal / SSO (optional; set in .env for your deployment)
    patent9235_base_url: str = ""
    patent_portal_url_template: str = ""
    patent9235_jwt_secret: str = ""
    patent9235_sso_product_id: str = "pdmchat"
    patent9235_sso_channel_id: str = "mchat01"
    patent9235_sso_login_url: str = ""

    # Encrypt skill_bindings secrets at rest (Fernet key or any string — hashed if needed)
    secrets_encryption_key: str = ""

    # Invoice header (portal order PDF/HTML)
    invoice_company_name: str = "MChat Cloud"
    invoice_company_tax_id: str = ""
    invoice_support_email: str = ""

    # Public site URL (checkout callbacks, invoices)
    mchat_public_base_url: str = ""
    alipay_app_id: str = ""
    alipay_private_key: str = ""
    alipay_public_key: str = ""
    alipay_notify_path: str = "/api/pay/alipay/notify"
    wechat_pay_app_id: str = "wx72863a0d11e809e0"
    wechat_pay_mch_id: str = "1679561189"
    wechat_pay_api_key: str = ""
    wechat_pay_notify_path: str = "/api/pay/wechat/notify"

    # Default admin (created on first startup if missing)
    admin_username: str = "admin"
    admin_password: str = "admin123"
    show_bootstrap_credentials: bool = True

    # CORS
    cors_origins: str = "*"

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 3001
    # development | production — production enforces secure defaults at startup
    environment: str = "development"

    # Background worker (independent process)
    worker_enabled: bool = False
    worker_timezone: str = "Asia/Shanghai"
    worker_log_cleanup_enabled: bool = True
    worker_log_retention_days: int = 14
    worker_usage_reset_enabled: bool = True

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 60
    rate_limit_period: int = 60
    login_rate_limit: int = 5
    login_rate_limit_period: int = 60

    # Skills — platform dir + optional external packs (e.g. separate patent repo)
    skills_dir: str = "../../skills"
    # Comma/colon-separated extra roots scanned after SKILLS_DIR (absolute path recommended)
    extra_skills_dirs: str = ""
    # Patent workflow showcase (templates/presets reference these skill names; not bundled in mchat)
    patent_workflow_showcase_enabled: bool = True
    patent_workflow_search_skill: str = "patent-search"
    patent_workflow_report_skill: str = "patent-report"
    # Optional note for ops/docs (e.g. /path/to/skills/patents)
    patent_skills_source: str = ""

    # Tenant workspace (Plan A local volume + Plan B container sidecar)
    workspace_root_dir: str = "../../data/tenants"
    workspace_default_mode: str = "local"  # local | container
    workspace_container_enabled: bool = False
    workspace_container_image: str = "python:3.12-slim"
    workspace_container_python: str = "python3"
    workspace_container_name_prefix: str = "mchat-ws"
    workspace_container_label: str = "mchat.workspace"
    # Sidecar hardening (Phase 1): empty network = default bridge; use "none" to isolate
    workspace_container_network: str = ""
    workspace_container_pids_limit: int = 256
    workspace_container_memory: str = ""  # e.g. 512m
    workspace_container_cpus: str = ""  # e.g. 1.0
    # Sidecar idle recycle (worker); 0 = disabled
    workspace_sidecar_idle_minutes: int = 120
    workspace_sidecar_recycle_enabled: bool = False
    # Optional legacy Cloud studio root ({root}/{user_id}/{channel_id}); empty = unified layout
    workspace_legacy_studio_dir: str = ""

    # File uploads
    upload_dir: str = "../../uploads"
    max_upload_size_mb: int = 50
    storage_backend: str = "local"  # local | s3 | minio
    s3_endpoint: str = ""
    s3_region: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "mchat-uploads"
    s3_use_ssl: bool = False
    s3_public_base_url: str = ""
    s3_force_path_style: bool = True
    # Require ?exp=&sig= on GET /uploads (legacy tokenless URLs still work when false)
    uploads_require_signed_access: bool = False
    uploads_signed_url_ttl_seconds: int = 60 * 60 * 24 * 365

    # LLM provider API keys (optional env fallback when DB config key is empty)
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    moonshot_api_key: str = ""
    zhipu_api_key: str = ""
    groq_api_key: str = ""
    siliconflow_api_key: str = ""
    together_api_key: str = ""

    # Embedding API key (falls back to openai_api_key)
    embedding_api_key: str = ""

    # Reranker (global defaults; per KB can override)
    rerank_provider: str = "lexical"  # none, lexical, cohere, bge, cross-encoder
    rerank_model: str = ""
    cohere_api_key: str = ""

    # Speech-to-text (STT)
    stt_enabled: bool = True
    # openai = Whisper API; local = faster-whisper (optional pip install)
    stt_provider: str = "openai"
    stt_openai_api_key: str = ""
    stt_model: str = "whisper-1"
    stt_language: str = "zh"
    stt_max_audio_mb: int = 10
    # local faster-whisper model size: tiny, base, small, medium, large-v3
    stt_local_model: str = "base"

    @property
    def upload_path(self) -> Path:
        from app.utils.upload_paths import resolve_upload_root

        return resolve_upload_root(self.upload_dir)

    @property
    def skills_path(self) -> Path:
        from app.core.skills_paths import resolve_skills_root

        return resolve_skills_root(self.skills_dir)


settings = Settings()
