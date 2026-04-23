from sqlalchemy import inspect
from sqlalchemy.engine import Engine


def upgrade_schema(engine: Engine) -> None:
    _upgrade_tenants(engine)
    _upgrade_regions(engine)
    _upgrade_users(engine)
    _upgrade_request_cases(engine)
    _upgrade_request_attachment_templates(engine)
    _upgrade_request_case_attachments(engine)
    _upgrade_request_case_participants(engine)
    _upgrade_workflow_definition_versions(engine)
    _upgrade_request_workflow_mappings(engine)


def _upgrade_tenants(engine: Engine) -> None:
    inspector = inspect(engine)
    if inspector.has_table("tenants"):
        return

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE tenants (
                code VARCHAR(12) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                region_code VARCHAR(32) UNIQUE,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                description TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
            )
            """
        )
        connection.exec_driver_sql("CREATE INDEX ix_tenants_code ON tenants(code)")
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_tenants_region_code ON tenants(region_code)")


def _upgrade_regions(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("regions"):
        return

    columns = {column["name"] for column in inspector.get_columns("regions")}
    statements: list[str] = []
    if "tenant_code" not in columns:
        statements.append("ALTER TABLE regions ADD COLUMN tenant_code VARCHAR(12)")

    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_regions_tenant_code ON regions(tenant_code)")
        connection.exec_driver_sql(
            """
            UPDATE regions
            SET tenant_code = CASE
                WHEN level = 'county' THEN LEFT(code, 6)
                WHEN level IN ('town', 'village') THEN LEFT(code, 6)
                ELSE tenant_code
            END
            WHERE tenant_code IS NULL
            """
        )


def _upgrade_users(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("users"):
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    statements: list[str] = []
    if "tenant_code" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN tenant_code VARCHAR(12)")

    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_users_tenant_code ON users(tenant_code)")
        connection.exec_driver_sql(
            """
            UPDATE users AS u
            SET tenant_code = LEFT(r.code, 6)
            FROM regions AS r
            WHERE u.region_id = r.id
              AND u.tenant_code IS NULL
            """
        )


def _upgrade_request_cases(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("request_cases"):
        return

    columns = {column["name"] for column in inspector.get_columns("request_cases")}
    alter_statements: list[str] = []

    if "request_title" not in columns:
        alter_statements.append("ALTER TABLE request_cases ADD COLUMN request_title VARCHAR(120)")
    if "issuer_code" not in columns:
        alter_statements.append("ALTER TABLE request_cases ADD COLUMN issuer_code VARCHAR(14)")
    if "issuer_name" not in columns:
        alter_statements.append("ALTER TABLE request_cases ADD COLUMN issuer_name VARCHAR(50)")
    if "tenant_code" not in columns:
        alter_statements.append("ALTER TABLE request_cases ADD COLUMN tenant_code VARCHAR(12)")
    if "region_code" not in columns:
        alter_statements.append("ALTER TABLE request_cases ADD COLUMN region_code VARCHAR(16)")
    if "contractor_code" not in columns:
        alter_statements.append("ALTER TABLE request_cases ADD COLUMN contractor_code VARCHAR(18)")
    if "contract_code" not in columns:
        alter_statements.append("ALTER TABLE request_cases ADD COLUMN contract_code VARCHAR(19)")
    if "workflow_state" not in columns:
        alter_statements.append("ALTER TABLE request_cases ADD COLUMN workflow_state TEXT")
    if "workflow_code" not in columns:
        alter_statements.append("ALTER TABLE request_cases ADD COLUMN workflow_code VARCHAR(32)")
    if "workflow_version_id" not in columns:
        alter_statements.append("ALTER TABLE request_cases ADD COLUMN workflow_version_id INTEGER")
    if "workflow_version_no" not in columns:
        alter_statements.append("ALTER TABLE request_cases ADD COLUMN workflow_version_no VARCHAR(16)")
    if "submitted_at" not in columns:
        alter_statements.append("ALTER TABLE request_cases ADD COLUMN submitted_at TIMESTAMP")
    if "completed_at" not in columns:
        alter_statements.append("ALTER TABLE request_cases ADD COLUMN completed_at TIMESTAMP")

    with engine.begin() as connection:
        for statement in alter_statements:
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_request_cases_tenant_code ON request_cases(tenant_code)")
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_request_cases_region_code ON request_cases(region_code)")
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_request_cases_workflow_version_id ON request_cases(workflow_version_id)"
        )

        connection.exec_driver_sql("ALTER TABLE request_cases ALTER COLUMN issuer_id DROP NOT NULL")
        connection.exec_driver_sql(
            """
            UPDATE request_cases AS rc
            SET issuer_code = i.code,
                issuer_name = i.name
            FROM issuers AS i
            WHERE rc.issuer_id = i.id
              AND (rc.issuer_code IS NULL OR rc.issuer_name IS NULL)
            """
        )
        connection.exec_driver_sql(
            """
            UPDATE request_cases
            SET request_title = request_type || '-' || contractor_name
            WHERE request_title IS NULL
            """
        )
        connection.exec_driver_sql(
            """
            UPDATE request_cases
            SET workflow_code = 'rural_contract'
            WHERE workflow_code IS NULL
            """
        )
        connection.exec_driver_sql("ALTER TABLE request_cases ALTER COLUMN workflow_code TYPE VARCHAR(64)")
        connection.exec_driver_sql(
            """
            UPDATE request_cases
            SET tenant_code = LEFT(COALESCE(issuer_code, contractor_code, contract_code), 6)
            WHERE tenant_code IS NULL
              AND COALESCE(issuer_code, contractor_code, contract_code) IS NOT NULL
            """
        )
        connection.exec_driver_sql(
            """
            UPDATE request_cases
            SET region_code = LEFT(COALESCE(issuer_code, contractor_code), 12)
            WHERE region_code IS NULL
              AND COALESCE(issuer_code, contractor_code) IS NOT NULL
            """
        )


def _upgrade_request_case_participants(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("request_case_participants"):
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE request_case_participants (
                    id SERIAL PRIMARY KEY,
                    case_id INTEGER NOT NULL REFERENCES request_cases(id),
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    tenant_code VARCHAR(12),
                    action VARCHAR(32) NOT NULL,
                    step_name VARCHAR(64),
                    comment TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_request_case_participants_case_id ON request_case_participants(case_id)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_request_case_participants_user_id ON request_case_participants(user_id)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_request_case_participants_tenant_code ON request_case_participants(tenant_code)"
            )
        return

    columns = {column["name"] for column in inspector.get_columns("request_case_participants")}
    statements: list[str] = []
    if "tenant_code" not in columns:
        statements.append("ALTER TABLE request_case_participants ADD COLUMN tenant_code VARCHAR(12)")

    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_request_case_participants_tenant_code ON request_case_participants(tenant_code)"
        )
        connection.exec_driver_sql(
            """
            UPDATE request_case_participants AS p
            SET tenant_code = rc.tenant_code
            FROM request_cases AS rc
            WHERE p.case_id = rc.id
              AND p.tenant_code IS NULL
            """
        )


def _upgrade_request_case_attachments(engine: Engine) -> None:
    inspector = inspect(engine)
    if inspector.has_table("request_case_attachments"):
        return

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE request_case_attachments (
                id SERIAL PRIMARY KEY,
                case_id INTEGER NOT NULL REFERENCES request_cases(id),
                tenant_code VARCHAR(12),
                category VARCHAR(64),
                stage_code VARCHAR(64),
                original_name VARCHAR(255) NOT NULL,
                stored_name VARCHAR(255) NOT NULL UNIQUE,
                content_type VARCHAR(128),
                file_size INTEGER NOT NULL DEFAULT 0,
                storage_path VARCHAR(500) NOT NULL,
                uploaded_by_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_request_case_attachments_case_id ON request_case_attachments(case_id)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_request_case_attachments_tenant_code ON request_case_attachments(tenant_code)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_request_case_attachments_uploaded_by_id ON request_case_attachments(uploaded_by_id)"
        )


def _upgrade_request_workflow_mappings(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("request_workflow_mappings"):
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE request_workflow_mappings (
                    id SERIAL PRIMARY KEY,
                    tenant_code VARCHAR(12) REFERENCES tenants(code),
                    request_type VARCHAR(32) NOT NULL,
                    workflow_key VARCHAR(64) NOT NULL,
                    workflow_version_id INTEGER REFERENCES workflow_definition_versions(id),
                    workflow_version_no INTEGER,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    remark TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX uq_request_workflow_mappings_tenant_request_type ON request_workflow_mappings(tenant_code, request_type)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_request_workflow_mappings_tenant_code ON request_workflow_mappings(tenant_code)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_request_workflow_mappings_request_type ON request_workflow_mappings(request_type)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_request_workflow_mappings_workflow_key ON request_workflow_mappings(workflow_key)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_request_workflow_mappings_workflow_version_id ON request_workflow_mappings(workflow_version_id)"
            )
        return

    columns = {column["name"] for column in inspector.get_columns("request_workflow_mappings")}
    statements: list[str] = []
    if "workflow_version_id" not in columns:
        statements.append("ALTER TABLE request_workflow_mappings ADD COLUMN workflow_version_id INTEGER")
    if "workflow_version_no" not in columns:
        statements.append("ALTER TABLE request_workflow_mappings ADD COLUMN workflow_version_no INTEGER")

    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_request_workflow_mappings_workflow_version_id ON request_workflow_mappings(workflow_version_id)"
        )


def _upgrade_workflow_definition_versions(engine: Engine) -> None:
    inspector = inspect(engine)
    if inspector.has_table("workflow_definition_versions"):
        return

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE workflow_definition_versions (
                id SERIAL PRIMARY KEY,
                workflow_key VARCHAR(64) NOT NULL,
                version_no INTEGER NOT NULL,
                name VARCHAR(120) NOT NULL,
                process_ids TEXT NOT NULL,
                content TEXT NOT NULL,
                remark TEXT,
                is_active BOOLEAN NOT NULL DEFAULT FALSE,
                published_by_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_workflow_definition_versions_workflow_key_version_no ON workflow_definition_versions(workflow_key, version_no)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_workflow_definition_versions_workflow_key ON workflow_definition_versions(workflow_key)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_workflow_definition_versions_published_by_id ON workflow_definition_versions(published_by_id)"
        )
def _upgrade_request_attachment_templates(engine: Engine) -> None:
    inspector = inspect(engine)
    if inspector.has_table("request_attachment_templates"):
        return

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE request_attachment_templates (
                id SERIAL PRIMARY KEY,
                tenant_code VARCHAR(12) REFERENCES tenants(code),
                request_type VARCHAR(32) NOT NULL,
                stage_code VARCHAR(64) NOT NULL,
                stage_name VARCHAR(100),
                category VARCHAR(64) NOT NULL,
                name VARCHAR(120) NOT NULL,
                required BOOLEAN NOT NULL DEFAULT TRUE,
                description TEXT,
                example_file_name VARCHAR(255),
                sort_order INTEGER NOT NULL DEFAULT 0,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_request_attachment_templates_tenant_code ON request_attachment_templates(tenant_code)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_request_attachment_templates_request_type ON request_attachment_templates(request_type)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_request_attachment_templates_stage_code ON request_attachment_templates(stage_code)"
        )
