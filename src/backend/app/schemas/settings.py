"""System settings Pydantic schemas."""

from pydantic import BaseModel, Field


class AppSettingsResponse(BaseModel):
    """System-wide application settings."""
    site_name: str = "MChat"
    site_description: str = "垂直 RAG 管理平台"
    language: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
    max_file_size: int = 10
    allowed_file_types: list[str] = ["txt", "pdf", "doc", "docx", "md"]
    enable_websocket: bool = True
    enable_streaming: bool = True
    rate_limit_per_min: int = 60
    maintenance_mode: bool = False
    server_ops_skills_enabled: bool = False
    server_ops_skill_allowlist: list[str] = Field(default_factory=list)
    server_ops_shell_allowlist: list[dict] = Field(default_factory=list)
    milvus_enabled: bool = False
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_api_base: str = "http://localhost:11434"
    embedding_dimension: int = 768
    embedding_api_key: str = ""
    storage_backend: str = "local"
    upload_dir: str = "../../uploads"
    max_upload_size_mb: int = 50
    s3_endpoint: str = ""
    s3_region: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "mchat-uploads"
    s3_use_ssl: bool = False
    s3_public_base_url: str = ""
    s3_force_path_style: bool = True
    worker_enabled: bool = False
    worker_timezone: str = "Asia/Shanghai"
    worker_log_cleanup_enabled: bool = True
    worker_log_retention_days: int = 14
    worker_usage_reset_enabled: bool = True
    notification_skills_enabled: bool = False
    notification_skill_allowlist: list[str] = Field(default_factory=lambda: ["mchat-notify"])
    sms_default_provider: str = "dev"
    sms_phone_allowlist: list[str] = Field(default_factory=list)
    sms_alert_phones: list[str] = Field(default_factory=list)
    sms_send_cooldown_seconds: int = 60
    sms_workflow_alert_enabled: bool = False


class AppSettingsUpdate(BaseModel):
    """Update system settings."""
    site_name: str | None = None
    site_description: str | None = None
    language: str | None = None
    timezone: str | None = None
    max_file_size: int | None = None
    allowed_file_types: list[str] | None = None
    enable_websocket: bool | None = None
    enable_streaming: bool | None = None
    rate_limit_per_min: int | None = None
    maintenance_mode: bool | None = None
    server_ops_skills_enabled: bool | None = None
    server_ops_skill_allowlist: list[str] | None = None
    server_ops_shell_allowlist: list[dict] | None = None
    milvus_enabled: bool | None = None
    milvus_host: str | None = None
    milvus_port: int | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_api_base: str | None = None
    embedding_dimension: int | None = Field(None, ge=128, le=4096)
    embedding_api_key: str | None = None
    storage_backend: str | None = None
    upload_dir: str | None = None
    max_upload_size_mb: int | None = None
    s3_endpoint: str | None = None
    s3_region: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str | None = None
    s3_use_ssl: bool | None = None
    s3_public_base_url: str | None = None
    s3_force_path_style: bool | None = None
    worker_enabled: bool | None = None
    worker_timezone: str | None = None
    worker_log_cleanup_enabled: bool | None = None
    worker_log_retention_days: int | None = Field(None, ge=1, le=3650)
    worker_usage_reset_enabled: bool | None = None
    notification_skills_enabled: bool | None = None
    notification_skill_allowlist: list[str] | None = None
    sms_default_provider: str | None = None
    sms_phone_allowlist: list[str] | None = None
    sms_alert_phones: list[str] | None = None
    sms_send_cooldown_seconds: int | None = Field(None, ge=30, le=3600)
    sms_workflow_alert_enabled: bool | None = None


class AppLogResponse(BaseModel):
    """Backend log tail response."""
    source: str
    lines: list[str]
