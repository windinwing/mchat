"""Lightweight schema patches for columns added after initial deploy."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.core.database import Base


def _column_names(conn: Connection, table: str) -> set[str]:
    insp = inspect(conn)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def apply_schema_patches(conn: Connection) -> list[str]:
    """Add missing columns on existing databases. Returns applied patch names."""
    applied: list[str] = []
    dialect = conn.dialect.name

    if "customer_configs" in inspect(conn).get_table_names():
        cols = _column_names(conn, "customer_configs")
        if "skill_ids" not in cols:
            if dialect == "mysql":
                conn.execute(
                    text(
                        "ALTER TABLE customer_configs "
                        "ADD COLUMN skill_ids JSON NULL"
                    )
                )
            else:
                conn.execute(
                    text(
                        "ALTER TABLE customer_configs "
                        "ADD COLUMN skill_ids TEXT NULL"
                    )
                )
            applied.append("customer_configs.skill_ids")
        if "knowledge_base_ids" not in cols:
            if dialect == "mysql":
                conn.execute(
                    text(
                        "ALTER TABLE customer_configs "
                        "ADD COLUMN knowledge_base_ids JSON NULL"
                    )
                )
            else:
                conn.execute(
                    text(
                        "ALTER TABLE customer_configs "
                        "ADD COLUMN knowledge_base_ids TEXT NULL"
                    )
                )
            applied.append("customer_configs.knowledge_base_ids")
        if "auto_reply_rules" not in cols:
            if dialect == "mysql":
                conn.execute(
                    text(
                        "ALTER TABLE customer_configs "
                        "ADD COLUMN auto_reply_rules JSON NULL"
                    )
                )
            else:
                conn.execute(
                    text(
                        "ALTER TABLE customer_configs "
                        "ADD COLUMN auto_reply_rules TEXT NULL"
                    )
                )
            applied.append("customer_configs.auto_reply_rules")
        if "channel_prompt" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE customer_configs "
                    "ADD COLUMN channel_prompt TEXT NULL"
                )
            )
            applied.append("customer_configs.channel_prompt")
        if "widget_session_ttl_hours" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE customer_configs "
                    "ADD COLUMN widget_session_ttl_hours INTEGER NOT NULL DEFAULT 24"
                )
            )
            applied.append("customer_configs.widget_session_ttl_hours")
        if "short_code" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE customer_configs "
                    "ADD COLUMN short_code VARCHAR(32) NULL"
                )
            )
            try:
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX idx_customer_configs_short_code "
                        "ON customer_configs(short_code)"
                    )
                )
            except Exception:
                pass
            applied.append("customer_configs.short_code")

    # Expand users.role column for custom role names
    if "users" in inspect(conn).get_table_names():
        try:
            if dialect == "mysql":
                conn.execute(
                    text("ALTER TABLE users MODIFY COLUMN role VARCHAR(50) NOT NULL DEFAULT 'agent'")
                )
            elif dialect == "postgresql":
                conn.execute(
                    text("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(50)")
                )
            applied.append("users.role_size")
        except Exception:
            pass

    if "conversations" in inspect(conn).get_table_names():
        cols = _column_names(conn, "conversations")
        if "client_ip" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE conversations "
                    "ADD COLUMN client_ip VARCHAR(64) NULL"
                )
            )
            applied.append("conversations.client_ip")
        if "customer_id" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE conversations "
                    "ADD COLUMN customer_id VARCHAR(36) NULL"
                )
            )
            applied.append("conversations.customer_id")
        if "scope_type" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE conversations "
                    "ADD COLUMN scope_type VARCHAR(20) NOT NULL DEFAULT 'personal'"
                )
            )
            applied.append("conversations.scope_type")
        if "scope_id" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE conversations "
                    "ADD COLUMN scope_id VARCHAR(36) NULL"
                )
            )
            applied.append("conversations.scope_id")
        # Create index separately (MySQL does not support IF NOT EXISTS)
        try:
            conn.execute(
                text(
                    "CREATE INDEX idx_conversations_customer_id "
                    "ON conversations(customer_id)"
                )
            )
        except Exception:
            pass

    if "knowledge_bases" in inspect(conn).get_table_names():
        cols = _column_names(conn, "knowledge_bases")
        kb_patches = [
            ("group_id", "VARCHAR(36) NULL"),
            ("chunk_strategy", "VARCHAR(20) NOT NULL DEFAULT 'fixed'"),
            ("chunk_size", "INTEGER NOT NULL DEFAULT 500"),
            ("chunk_overlap", "INTEGER NOT NULL DEFAULT 50"),
            ("chunk_min_size", "INTEGER NOT NULL DEFAULT 80"),
            ("embedding_provider", "VARCHAR(50) NULL"),
            ("embedding_model", "VARCHAR(100) NULL"),
            ("embedding_api_base", "VARCHAR(500) NULL"),
            ("embedding_dimension", "INTEGER NOT NULL DEFAULT 1536"),
            ("retrieval_mode", "VARCHAR(20) NOT NULL DEFAULT 'hybrid'"),
            ("retrieval_top_k", "INTEGER NOT NULL DEFAULT 5"),
            ("retrieval_candidate_k", "INTEGER NOT NULL DEFAULT 20"),
            ("rerank_enabled", "BOOLEAN NOT NULL DEFAULT 1" if dialect == "mysql" else "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("rerank_top_n", "INTEGER NOT NULL DEFAULT 5"),
            ("retrieval_bm25_enabled", "BOOLEAN NOT NULL DEFAULT 1" if dialect == "mysql" else "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("retrieval_bm25_k1", "FLOAT NOT NULL DEFAULT 1.5"),
            ("retrieval_bm25_b", "FLOAT NOT NULL DEFAULT 0.75"),
            ("rerank_provider", "VARCHAR(20) NOT NULL DEFAULT 'lexical'"),
            ("rerank_model", "VARCHAR(100) NULL"),
            ("retrieval_query_rewrite_enabled", "BOOLEAN NOT NULL DEFAULT 0" if dialect == "mysql" else "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("retrieval_query_rewrite_count", "INTEGER NOT NULL DEFAULT 3"),
            ("chunk_semantic_threshold", "FLOAT NOT NULL DEFAULT 0.7"),
            ("chunk_parent_enabled", "BOOLEAN NOT NULL DEFAULT 1" if dialect == "mysql" else "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("indexed_embedding_key", "VARCHAR(255) NULL"),
            ("reindex_status", "VARCHAR(20) NOT NULL DEFAULT 'idle'"),
        ]
        for col_name, col_def in kb_patches:
            if col_name not in cols:
                conn.execute(
                    text(f"ALTER TABLE knowledge_bases ADD COLUMN {col_name} {col_def}")
                )
                applied.append(f"knowledge_bases.{col_name}")

    # ---- user fields added for channel rental ----
    if "users" in inspect(conn).get_table_names():
        cols = _column_names(conn, "users")
        user_patches = [
            ("email", "VARCHAR(255) NULL"),
            ("account_status", "VARCHAR(20) NOT NULL DEFAULT 'active'"),
            ("workspace_container_allowed", "BOOLEAN NULL"),
            ("workspace_sidecar_memory", "VARCHAR(32) NULL"),
            ("workspace_sidecar_cpus", "VARCHAR(16) NULL"),
            ("phone", "VARCHAR(20) NULL"),
            ("phone_verified_at", "DATETIME NULL"),
            ("external_provider", "VARCHAR(50) NULL"),
            ("external_id", "VARCHAR(64) NULL"),
            ("password_set_at", "DATETIME NULL"),
            ("skill_ids", "JSON NULL"),
        ]
        for col_name, col_def in user_patches:
            if col_name not in cols:
                conn.execute(
                    text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
                )
                applied.append(f"users.{col_name}")
        if "password_set_at" in _column_names(conn, "users"):
            conn.execute(
                text(
                    "UPDATE users SET password_set_at = created_at "
                    "WHERE password_set_at IS NULL "
                    "AND external_provider IS NULL "
                    "AND phone IS NULL"
                )
            )
            applied.append("users.password_set_at_backfill")

    # ---- customer_configs fields for channel rental ----
    if "customer_configs" in inspect(conn).get_table_names():
        cols = _column_names(conn, "customer_configs")
        cc_patches = [
            ("plan", "VARCHAR(20) NOT NULL DEFAULT 'free'"),
            ("trial_ends_at", "DATETIME NULL"),
            ("pre_chat_fields", "JSON NULL" if dialect == "mysql" else "TEXT NULL"),
            ("subscription_ends_at", "DATETIME NULL"),
            (
                "skill_bindings",
                "JSON NULL" if dialect == "mysql" else "TEXT NULL",
            ),
            ("template_id", "VARCHAR(36) NULL"),
            ("channel_category", "VARCHAR(50) NOT NULL DEFAULT 'customer_service'"),
            ("usage_messages_month", "INTEGER NOT NULL DEFAULT 0"),
            ("usage_tokens_month", "INTEGER NOT NULL DEFAULT 0"),
            ("usage_documents_count", "INTEGER NOT NULL DEFAULT 0"),
            ("usage_storage_bytes", "INTEGER NOT NULL DEFAULT 0"),
            ("usage_messages_limit", "INTEGER NOT NULL DEFAULT 1000"),
            ("usage_tokens_limit", "INTEGER NOT NULL DEFAULT 100000"),
            ("last_usage_reset_at", "DATETIME NULL"),
            ("active_order_id", "VARCHAR(36) NULL"),
            (
                "ai_override",
                "BOOLEAN NOT NULL DEFAULT 0"
                if dialect == "mysql"
                else "BOOLEAN NOT NULL DEFAULT FALSE",
            ),
            ("workspace_mode", "VARCHAR(20) NULL"),
        ]
        for col_name, col_def in cc_patches:
            if col_name not in cols:
                conn.execute(
                    text(
                        f"ALTER TABLE customer_configs ADD COLUMN {col_name} {col_def}"
                    )
                )
                applied.append(f"customer_configs.{col_name}")
        if "template_id" in _column_names(conn, "customer_configs"):
            try:
                conn.execute(
                    text(
                        "CREATE INDEX idx_customer_configs_template_id "
                        "ON customer_configs(template_id)"
                    )
                )
            except Exception:
                pass

    # ---- messages: token tracking ----
    if "messages" in inspect(conn).get_table_names():
        cols = _column_names(conn, "messages")
        msg_patches = [
            ("prompt_tokens", "INTEGER NULL"),
            ("completion_tokens", "INTEGER NULL"),
        ]
        for col_name, col_def in msg_patches:
            if col_name not in cols:
                conn.execute(
                    text(f"ALTER TABLE messages ADD COLUMN {col_name} {col_def}")
                )
                applied.append(f"messages.{col_name}")

    if "skills" in inspect(conn).get_table_names():
        cols = _column_names(conn, "skills")
        if "group_id" not in cols:
            conn.execute(text("ALTER TABLE skills ADD COLUMN group_id VARCHAR(36) NULL"))
            applied.append("skills.group_id")

    # ---- channel_templates: new columns ----
    if "channel_templates" in inspect(conn).get_table_names():
        cols = _column_names(conn, "channel_templates")
        if "default_ai_config_id" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE channel_templates "
                    "ADD COLUMN default_ai_config_id VARCHAR(36) NULL"
                )
            )
            applied.append("channel_templates.default_ai_config_id")
        if "default_knowledge_base_ids" not in cols:
            if dialect == "mysql":
                conn.execute(
                    text(
                        "ALTER TABLE channel_templates "
                        "ADD COLUMN default_knowledge_base_ids JSON NULL"
                    )
                )
            else:
                conn.execute(
                    text(
                        "ALTER TABLE channel_templates "
                        "ADD COLUMN default_knowledge_base_ids TEXT NULL"
                    )
                )
            applied.append("channel_templates.default_knowledge_base_ids")
        if "integration_schema" not in cols:
            if dialect == "mysql":
                conn.execute(
                    text(
                        "ALTER TABLE channel_templates "
                        "ADD COLUMN integration_schema JSON NULL"
                    )
                )
            else:
                conn.execute(
                    text(
                        "ALTER TABLE channel_templates "
                        "ADD COLUMN integration_schema TEXT NULL"
                    )
                )
            applied.append("channel_templates.integration_schema")

    if "portal_orders" in inspect(conn).get_table_names():
        po_cols = _column_names(conn, "portal_orders")
        if "subscription_ends_at" not in po_cols:
            conn.execute(
                text("ALTER TABLE portal_orders ADD COLUMN subscription_ends_at DATETIME NULL")
            )
            applied.append("portal_orders.subscription_ends_at")

    # document_chunks migration
    if "document_chunks" in inspect(conn).get_table_names():
        cols = _column_names(conn, "document_chunks")
        dc_patches = [
            ("parent_content", "TEXT NULL"),
            ("chunk_type", "VARCHAR(10) NOT NULL DEFAULT 'child'"),
        ]
        for col_name, col_def in dc_patches:
            if col_name not in cols:
                conn.execute(
                    text(f"ALTER TABLE document_chunks ADD COLUMN {col_name} {col_def}")
                )
                applied.append(f"document_chunks.{col_name}")

    if "skill_schedules" in inspect(conn).get_table_names():
        cols = _column_names(conn, "skill_schedules")
        if "workflow_id" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE skill_schedules "
                    "ADD COLUMN workflow_id VARCHAR(36) NULL"
                )
            )
            applied.append("skill_schedules.workflow_id")
        if "target_type" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE skill_schedules "
                    "ADD COLUMN target_type VARCHAR(20) NOT NULL DEFAULT 'skill'"
                )
            )
            applied.append("skill_schedules.target_type")
        # allow workflow schedules without skill_id
        try:
            if dialect == "mysql":
                conn.execute(
                    text(
                        "ALTER TABLE skill_schedules "
                        "MODIFY COLUMN skill_id VARCHAR(36) NULL"
                    )
                )
                applied.append("skill_schedules.skill_id_nullable")
            elif dialect == "postgresql":
                conn.execute(
                    text(
                        "ALTER TABLE skill_schedules "
                        "ALTER COLUMN skill_id DROP NOT NULL"
                    )
                )
                applied.append("skill_schedules.skill_id_nullable")
        except Exception:
            pass
        try:
            conn.execute(
                text(
                    "CREATE INDEX idx_skill_schedules_workflow_id "
                    "ON skill_schedules(workflow_id)"
                )
            )
        except Exception:
            pass

    if "skill_schedule_runs" in inspect(conn).get_table_names():
        cols = _column_names(conn, "skill_schedule_runs")
        run_patches = [
            ("workflow_id", "VARCHAR(36) NULL"),
            ("target_type", "VARCHAR(20) NOT NULL DEFAULT 'skill'"),
            ("target_name", "VARCHAR(200) NULL"),
        ]
        for col_name, col_def in run_patches:
            if col_name not in cols:
                conn.execute(
                    text(
                        f"ALTER TABLE skill_schedule_runs "
                        f"ADD COLUMN {col_name} {col_def}"
                    )
                )
                applied.append(f"skill_schedule_runs.{col_name}")
        try:
            if dialect == "mysql":
                conn.execute(
                    text(
                        "ALTER TABLE skill_schedule_runs "
                        "MODIFY COLUMN skill_id VARCHAR(36) NULL"
                    )
                )
                applied.append("skill_schedule_runs.skill_id_nullable")
            elif dialect == "postgresql":
                conn.execute(
                    text(
                        "ALTER TABLE skill_schedule_runs "
                        "ALTER COLUMN skill_id DROP NOT NULL"
                    )
                )
                applied.append("skill_schedule_runs.skill_id_nullable")
        except Exception:
            pass
        try:
            conn.execute(
                text(
                    "CREATE INDEX idx_skill_schedule_runs_workflow_id "
                    "ON skill_schedule_runs(workflow_id)"
                )
            )
        except Exception:
            pass

    if "channel_workflow_bindings" not in inspect(conn).get_table_names():
        Base.metadata.create_all(conn)
    else:
        cols = _column_names(conn, "channel_workflow_bindings")
        binding_patches = [
            ("match_type", "VARCHAR(20) NOT NULL DEFAULT 'all'"),
            ("match_expr", "TEXT NULL"),
        ]
        for col_name, col_def in binding_patches:
            if col_name not in cols:
                conn.execute(
                    text(
                        f"ALTER TABLE channel_workflow_bindings "
                        f"ADD COLUMN {col_name} {col_def}"
                    )
                )
                applied.append(f"channel_workflow_bindings.{col_name}")

    if "skill_workflow_approvals" in inspect(conn).get_table_names():
        cols = _column_names(conn, "skill_workflow_approvals")
        approval_patches = [
            ("comment", "TEXT NULL"),
            ("approved_by", "VARCHAR(36) NULL"),
            ("decision_payload", "JSON NULL" if dialect == "mysql" else "TEXT NULL"),
        ]
        for col_name, col_def in approval_patches:
            if col_name not in cols:
                conn.execute(
                    text(
                        f"ALTER TABLE skill_workflow_approvals "
                        f"ADD COLUMN {col_name} {col_def}"
                    )
                )
                applied.append(f"skill_workflow_approvals.{col_name}")

    if "groups" in inspect(conn).get_table_names():
        cols = _column_names(conn, "groups")
        if "gamecenter_project_allowlist" not in cols:
            if dialect == "mysql":
                conn.execute(
                    text(
                        "ALTER TABLE `groups` "
                        "ADD COLUMN gamecenter_project_allowlist JSON NULL"
                    )
                )
            else:
                conn.execute(
                    text(
                        "ALTER TABLE `groups` "
                        "ADD COLUMN gamecenter_project_allowlist TEXT NULL"
                    )
                )
            applied.append("groups.gamecenter_project_allowlist")
        if "devbridge_project_allowlists" not in cols:
            if dialect == "mysql":
                conn.execute(
                    text(
                        "ALTER TABLE `groups` "
                        "ADD COLUMN devbridge_project_allowlists JSON NULL"
                    )
                )
            else:
                conn.execute(
                    text(
                        "ALTER TABLE `groups` "
                        "ADD COLUMN devbridge_project_allowlists TEXT NULL"
                    )
                )
            applied.append("groups.devbridge_project_allowlists")

    if "skill_workflow_templates" in inspect(conn).get_table_names():
        cols = _column_names(conn, "skill_workflow_templates")
        tpl_patches = [
            ("visibility", "VARCHAR(20) NOT NULL DEFAULT 'private'"),
            ("use_count", "INTEGER NOT NULL DEFAULT 0"),
        ]
        for col_name, col_def in tpl_patches:
            if col_name not in cols:
                conn.execute(
                    text(
                        f"ALTER TABLE skill_workflow_templates ADD COLUMN {col_name} {col_def}"
                    )
                )
                applied.append(f"skill_workflow_templates.{col_name}")

    # Ensure any new tables from models exist
    Base.metadata.create_all(conn)
    return applied
