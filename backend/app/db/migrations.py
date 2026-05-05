from sqlalchemy import inspect
from sqlalchemy.engine import Engine


def upgrade_schema(engine: Engine) -> None:
    _upgrade_import_trace_columns(engine)
    _upgrade_contractor_group_region(engine)
    _upgrade_survey_phase2(engine)
    _upgrade_map_layers(engine)
    _upgrade_tenants(engine)
    _upgrade_regions(engine)
    _upgrade_users(engine)
    _upgrade_user_region_permissions(engine)
    _upgrade_request_cases(engine)
    _upgrade_request_attachment_templates(engine)
    _upgrade_request_case_attachments(engine)
    _upgrade_request_case_participants(engine)
    _upgrade_workflow_definition_versions(engine)
    _upgrade_request_workflow_mappings(engine)
    _upgrade_tenant_scope_columns(engine)
    _migrate_legacy_cbf_tables_to_survey(engine)


def _add_column_if_missing(connection, columns: set[str], table_name: str, column_name: str, column_type: str) -> None:
    if column_name not in columns:
        connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def _ensure_scope_columns(engine: Engine, table_name: str) -> None:
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    with engine.begin() as connection:
        _add_column_if_missing(connection, columns, table_name, "tenant_code", "VARCHAR(12)")
        _add_column_if_missing(connection, columns, table_name, "region_code", "VARCHAR(32)")
        connection.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_tenant_code ON {table_name}(tenant_code)")
        connection.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_region_code ON {table_name}(region_code)")


def _mark_scope_not_null(engine: Engine, table_name: str) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(f"ALTER TABLE {table_name} ALTER COLUMN tenant_code SET NOT NULL")
        connection.exec_driver_sql(f"ALTER TABLE {table_name} ALTER COLUMN region_code SET NOT NULL")


def _upgrade_tenant_scope_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    for table_name in (
        "fbf",
        "cbf",
        "cbf_jtcy",
        "cbht",
        "issuers",
        "request_cases",
        "request_case_participants",
        "request_case_attachments",
        "data_import_batches",
        "data_import_files",
        "data_import_rows",
        "survey_batches",
        "survey_contractor_tasks",
        "survey_cbf_base",
        "survey_cbf_result",
        "survey_cbf_jtcy_base",
        "survey_cbf_jtcy_result",
        "survey_fbf_base",
        "survey_fbf_result",
        "survey_cbdkxx_base",
        "survey_cbdkxx_result",
        "survey_dk_base",
        "survey_dk_result",
        "survey_change_records",
        "survey_change_diffs",
        "survey_household_restructures",
        "survey_household_restructure_members",
        "survey_household_tags",
        "survey_authorizations",
        "survey_attachments",
    ):
        _ensure_scope_columns(engine, table_name)

    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE fbf SET tenant_code = LEFT(fbfbm, 6), region_code = LEFT(fbfbm, 14) WHERE tenant_code IS NULL OR region_code IS NULL")
        if inspector.has_table("cbf"):
            connection.exec_driver_sql("UPDATE cbf SET tenant_code = LEFT(cbfbm, 6), region_code = LEFT(cbfbm, 14) WHERE tenant_code IS NULL OR region_code IS NULL")
        if inspector.has_table("cbf_jtcy"):
            connection.exec_driver_sql("UPDATE cbf_jtcy SET tenant_code = LEFT(cbfbm, 6), region_code = LEFT(cbfbm, 14) WHERE tenant_code IS NULL OR region_code IS NULL")
        connection.exec_driver_sql(
            "UPDATE cbht SET tenant_code = LEFT(COALESCE(cbfbm, fbfbm, cbhtbm), 6), region_code = LEFT(COALESCE(cbfbm, fbfbm, cbhtbm), 14) WHERE tenant_code IS NULL OR region_code IS NULL"
        )
        connection.exec_driver_sql("UPDATE issuers SET tenant_code = LEFT(code, 6), region_code = LEFT(code, 14) WHERE tenant_code IS NULL OR region_code IS NULL")
        if inspector.has_table("request_cases"):
            connection.exec_driver_sql(
                """
                UPDATE request_cases
                SET tenant_code = LEFT(COALESCE(region_code, issuer_code, contractor_code, contract_code), 6),
                    region_code = LEFT(COALESCE(region_code, issuer_code, contractor_code, contract_code), 14)
                WHERE tenant_code IS NULL OR region_code IS NULL
                """
            )
        if inspector.has_table("request_case_participants") and inspector.has_table("request_cases"):
            connection.exec_driver_sql(
                """
                UPDATE request_case_participants AS p
                SET tenant_code = rc.tenant_code,
                    region_code = rc.region_code
                FROM request_cases AS rc
                WHERE p.case_id = rc.id
                  AND (p.tenant_code IS NULL OR p.region_code IS NULL)
                """
            )
        if inspector.has_table("request_case_attachments") and inspector.has_table("request_cases"):
            connection.exec_driver_sql(
                """
                UPDATE request_case_attachments AS a
                SET tenant_code = rc.tenant_code,
                    region_code = rc.region_code
                FROM request_cases AS rc
                WHERE a.case_id = rc.id
                  AND (a.tenant_code IS NULL OR a.region_code IS NULL)
                """
            )
        for table_name in (
            "data_import_batches",
            "data_import_files",
            "data_import_rows",
            "survey_batches",
            "survey_contractor_tasks",
            "survey_cbf_base",
            "survey_cbf_result",
            "survey_cbf_jtcy_base",
            "survey_cbf_jtcy_result",
            "survey_fbf_base",
            "survey_fbf_result",
            "survey_cbdkxx_base",
            "survey_cbdkxx_result",
            "survey_dk_base",
            "survey_dk_result",
            "survey_change_records",
            "survey_change_diffs",
            "survey_household_restructures",
            "survey_household_restructure_members",
            "survey_household_tags",
            "survey_authorizations",
            "survey_attachments",
        ):
            if not inspector.has_table(table_name):
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            candidates = [
                column_name
                for column_name in (
                    "region_code",
                    "cbfbm",
                    "source_cbfbm",
                    "fbfbm",
                    "source_fbfbm",
                    "dkbm",
                    "source_dkbm",
                    "target_cbfbm",
                    "new_cbfbm",
                    "from_cbfbm",
                    "to_cbfbm",
                )
                if column_name in columns
            ]
            source_expr = "COALESCE(" + ", ".join(candidates + ["'321324'"]) + ")"
            connection.exec_driver_sql(
                f"""
                UPDATE {table_name}
                SET tenant_code = COALESCE(tenant_code, LEFT({source_expr}, 6)),
                    region_code = COALESCE(region_code, LEFT({source_expr}, 14))
                WHERE tenant_code IS NULL OR region_code IS NULL
                """
            )

    for table_name in (
        "fbf",
        "cbht",
        "issuers",
        "request_cases",
        "request_case_participants",
        "request_case_attachments",
    ):
        _mark_scope_not_null(engine, table_name)
    for table_name in ("cbf", "cbf_jtcy"):
        if inspector.has_table(table_name):
            _mark_scope_not_null(engine, table_name)


def _upgrade_user_region_permissions(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("user_region_permissions"):
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE user_region_permissions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    tenant_code VARCHAR(12) NOT NULL,
                    region_code VARCHAR(32) NOT NULL,
                    level VARCHAR(16) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX uq_user_region_permissions_user_region ON user_region_permissions(user_id, region_code)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_user_region_permissions_user_id ON user_region_permissions(user_id)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_user_region_permissions_tenant_code ON user_region_permissions(tenant_code)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_user_region_permissions_region_code ON user_region_permissions(region_code)"
            )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO user_region_permissions (user_id, tenant_code, region_code, level)
            SELECT u.id,
                   LEFT(r.code, 6),
                   r.code,
                   CASE LENGTH(r.code)
                       WHEN 6 THEN 'county'
                       WHEN 9 THEN 'town'
                       WHEN 12 THEN 'village'
                       WHEN 14 THEN 'group'
                       ELSE 'custom'
                   END
            FROM users AS u
            JOIN regions AS r ON r.id = u.region_id
            WHERE NOT EXISTS (
                SELECT 1
                FROM user_region_permissions AS p
                WHERE p.user_id = u.id
            )
            """
        )
        connection.exec_driver_sql(
            """
            DELETE FROM user_region_permissions AS p
            USING user_region_permissions AS kept
            WHERE p.level = 'group'
              AND kept.level = 'group'
              AND p.region_code = kept.region_code
              AND kept.id < p.id
            """
        )
        connection.exec_driver_sql(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_user_region_permissions_group_region
            ON user_region_permissions(region_code)
            WHERE level = 'group'
            """
        )


def _upgrade_import_trace_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    trace_columns = [
        ("source_import_batch_id", "INTEGER"),
        ("source_import_file_id", "INTEGER"),
        ("source_import_row_id", "INTEGER"),
        ("last_import_batch_id", "INTEGER"),
        ("last_import_file_id", "INTEGER"),
        ("last_import_row_id", "INTEGER"),
        ("data_origin", "VARCHAR(32)"),
        ("imported_at", "TIMESTAMP WITH TIME ZONE"),
    ]
    with engine.begin() as connection:
        if inspector.has_table("data_import_batches"):
            batch_columns = {column["name"] for column in inspector.get_columns("data_import_batches")}
            if "linked_survey_batch_id" not in batch_columns:
                connection.exec_driver_sql("ALTER TABLE data_import_batches ADD COLUMN linked_survey_batch_id INTEGER")
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_data_import_batches_linked_survey_batch_id ON data_import_batches(linked_survey_batch_id)"
            )
        for table_name in ("cbf", "cbf_jtcy"):
            if not inspector.has_table(table_name):
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in trace_columns:
                if column_name not in columns:
                    connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            connection.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_source_import_batch_id ON {table_name}(source_import_batch_id)"
            )
            connection.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_source_import_file_id ON {table_name}(source_import_file_id)"
            )
            connection.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_last_import_batch_id ON {table_name}(last_import_batch_id)"
            )
            connection.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_last_import_file_id ON {table_name}(last_import_file_id)"
            )


def _upgrade_contractor_group_region(engine: Engine) -> None:
    inspector = inspect(engine)
    target_tables = ("cbf", "survey_cbf_base", "survey_cbf_result")
    with engine.begin() as connection:
        for table_name in target_tables:
            if not inspector.has_table(table_name):
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            _add_column_if_missing(connection, columns, table_name, "group_region_code", "VARCHAR(32)")
            _add_column_if_missing(connection, columns, table_name, "group_region_name", "VARCHAR(120)")
            connection.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_group_region_code ON {table_name}(group_region_code)"
            )
        if inspector.has_table("cbf"):
            connection.exec_driver_sql(
                "UPDATE cbf SET group_region_code = COALESCE(group_region_code, LEFT(cbfbm, 14)) WHERE group_region_code IS NULL"
            )
        if inspector.has_table("survey_cbf_base"):
            connection.exec_driver_sql(
                "UPDATE survey_cbf_base SET group_region_code = COALESCE(group_region_code, LEFT(cbfbm, 14)) WHERE group_region_code IS NULL"
            )
        if inspector.has_table("survey_cbf_result"):
            connection.exec_driver_sql(
                "UPDATE survey_cbf_result SET group_region_code = COALESCE(group_region_code, LEFT(cbfbm, 14)) WHERE group_region_code IS NULL"
            )


def _migrate_legacy_cbf_tables_to_survey(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("cbf"):
        if inspector.has_table("cbf_jtcy"):
            with engine.begin() as connection:
                connection.exec_driver_sql("DROP TABLE IF EXISTS cbf_jtcy")
        return
    if not inspector.has_table("survey_batches") or not inspector.has_table("survey_cbf_base") or not inspector.has_table("survey_cbf_result"):
        return

    uuid_expr = (
        "LOWER(SUBSTR(MD5(%s), 1, 8) || '-' || SUBSTR(MD5(%s), 9, 4) || '-' || "
        "SUBSTR(MD5(%s), 13, 4) || '-' || SUBSTR(MD5(%s), 17, 4) || '-' || SUBSTR(MD5(%s), 21, 12))"
    )
    with engine.begin() as connection:
        batch_id = connection.exec_driver_sql("SELECT id FROM survey_batches WHERE batch_no = 'SURLEGACYCBF'").scalar()
        if batch_id is None:
            batch_id = connection.exec_driver_sql(
                """
                INSERT INTO survey_batches (
                    tenant_code, region_code, batch_no, batch_name, region_name, survey_type, status, started_at, created_at, updated_at, remark
                )
                SELECT
                    COALESCE(MIN(tenant_code), LEFT(MIN(cbfbm), 6), '321324'),
                    COALESCE(MIN(region_code), LEFT(MIN(cbfbm), 12), '321324'),
                    'SURLEGACYCBF',
                    '承包方历史数据迁移批次',
                    '历史迁移',
                    'legacy_import',
                    'active',
                    NOW(),
                    NOW(),
                    NOW(),
                    '由 cbf/cbf_jtcy 迁移生成'
                FROM cbf
                RETURNING id
                """
            ).scalar()
        if batch_id is None:
            connection.exec_driver_sql("DROP TABLE IF EXISTS cbf_jtcy")
            connection.exec_driver_sql("DROP TABLE IF EXISTS cbf")
            return

        contractor_uid_expr = uuid_expr % tuple([f"'survey:' || {batch_id} || ':cbf:' || c.cbfbm"] * 5)
        connection.exec_driver_sql(
            f"""
            INSERT INTO survey_cbf_base (
                tenant_code, region_code, batch_id, contractor_uid, source_cbfbm, cbfbm, cbflx, cbfmc,
                cbfzjlx, cbfzjhm, cbfdz, yzbm, lxdh, cbfcysl, cbfdcrq, cbfdcy, cbfdcjs,
                gsjs, gsjsr, gsshrq, gsshr, group_region_code, group_region_name,
                source_import_batch_id, source_import_row_id, last_import_batch_id, last_import_row_id,
                initialized_from_table, initialized_from_key, initialized_at, snapshot_at, created_at, updated_at
            )
            SELECT
                c.tenant_code, c.region_code, {batch_id}, {contractor_uid_expr}, c.cbfbm, c.cbfbm, c.cbflx, c.cbfmc,
                c.cbfzjlx, c.cbfzjhm, c.cbfdz, c.yzbm, c.lxdh, c.cbfcysl, c.cbfdcrq, c.cbfdcy, c.cbfdcjs,
                c.gsjs, c.gsjsr, c.gsshrq, c.gsshr, c.group_region_code, c.group_region_name,
                c.source_import_batch_id, c.source_import_row_id, c.last_import_batch_id, c.last_import_row_id,
                'cbf', c.cbfbm, COALESCE(c.imported_at, NOW()), NOW(), NOW(), NOW()
            FROM cbf AS c
            WHERE NOT EXISTS (
                SELECT 1 FROM survey_cbf_base AS b
                WHERE b.batch_id = {batch_id} AND b.source_cbfbm = c.cbfbm
            )
            """
        )
        connection.exec_driver_sql(
            f"""
            INSERT INTO survey_cbf_result (
                tenant_code, region_code, batch_id, contractor_uid, base_id, cbfbm, cbflx, cbfmc,
                cbfzjlx, cbfzjhm, cbfdz, yzbm, lxdh, cbfcysl, cbfdcrq, cbfdcy, cbfdcjs,
                gsjs, gsjsr, gsshrq, gsshr, group_region_code, group_region_name,
                survey_status, result_status, is_changed, change_type,
                source_import_batch_id, source_import_row_id, last_import_batch_id, last_import_row_id,
                initialized_from_base_id, initialized_at, created_at, updated_at
            )
            SELECT
                b.tenant_code, b.region_code, b.batch_id, b.contractor_uid, b.id, b.cbfbm, b.cbflx, b.cbfmc,
                b.cbfzjlx, b.cbfzjhm, b.cbfdz, b.yzbm, b.lxdh, b.cbfcysl, b.cbfdcrq, b.cbfdcy, b.cbfdcjs,
                b.gsjs, b.gsjsr, b.gsshrq, b.gsshr, b.group_region_code, b.group_region_name,
                'not_surveyed', 'normal', FALSE, 'none',
                b.source_import_batch_id, b.source_import_row_id, b.last_import_batch_id, b.last_import_row_id,
                b.id, b.initialized_at, NOW(), NOW()
            FROM survey_cbf_base AS b
            WHERE b.batch_id = {batch_id}
              AND NOT EXISTS (
                  SELECT 1 FROM survey_cbf_result AS r
                  WHERE r.batch_id = b.batch_id AND r.base_id = b.id
              )
            """
        )
        connection.exec_driver_sql(
            f"""
            INSERT INTO survey_contractor_tasks (
                tenant_code, region_code, batch_id, contractor_uid, cbfbm, cbfmc, task_status, has_change, change_count, created_at, updated_at
            )
            SELECT b.tenant_code, b.region_code, b.batch_id, b.contractor_uid, b.cbfbm, b.cbfmc, 'not_started', FALSE, 0, NOW(), NOW()
            FROM survey_cbf_base AS b
            WHERE b.batch_id = {batch_id}
              AND NOT EXISTS (
                  SELECT 1 FROM survey_contractor_tasks AS t
                  WHERE t.batch_id = b.batch_id AND t.cbfbm = b.cbfbm
              )
            """
        )
        if inspector.has_table("cbf_jtcy") and inspector.has_table("survey_cbf_jtcy_base") and inspector.has_table("survey_cbf_jtcy_result"):
            member_uid_expr = uuid_expr % tuple([f"'survey:' || {batch_id} || ':member:' || m.cbfbm || ':' || m.cyzjhm"] * 5)
            connection.exec_driver_sql(
                f"""
                INSERT INTO survey_cbf_jtcy_base (
                    tenant_code, region_code, batch_id, contractor_uid, member_uid, base_contractor_code, base_member_id_no,
                    cbfbm, cyxm, cyzjlx, cyzjhm, cyxb, yhzgx, cybz, sfgyr, cybzsm,
                    source_import_batch_id, source_import_row_id, last_import_batch_id, last_import_row_id,
                    initialized_from_table, initialized_from_key, initialized_at, snapshot_at, created_at, updated_at
                )
                SELECT
                    COALESCE(m.tenant_code, b.tenant_code), COALESCE(m.region_code, b.region_code),
                    {batch_id}, b.contractor_uid, {member_uid_expr}, m.cbfbm, m.cyzjhm,
                    m.cbfbm, m.cyxm, m.cyzjlx, m.cyzjhm, m.cyxb, m.yhzgx, m.cybz, m.sfgyr, m.cybzsm,
                    m.source_import_batch_id, m.source_import_row_id, m.last_import_batch_id, m.last_import_row_id,
                    'cbf_jtcy', m.cbfbm || ':' || m.cyzjhm, COALESCE(m.imported_at, NOW()), NOW(), NOW(), NOW()
                FROM cbf_jtcy AS m
                JOIN survey_cbf_base AS b ON b.batch_id = {batch_id} AND b.source_cbfbm = m.cbfbm
                WHERE NOT EXISTS (
                    SELECT 1 FROM survey_cbf_jtcy_base AS mb
                    WHERE mb.batch_id = {batch_id}
                      AND mb.base_contractor_code = m.cbfbm
                      AND mb.base_member_id_no = m.cyzjhm
                )
                """
            )
            connection.exec_driver_sql(
                f"""
                INSERT INTO survey_cbf_jtcy_result (
                    tenant_code, region_code, batch_id, contractor_uid, member_uid, base_id,
                    cbfbm, cyxm, cyzjlx, cyzjhm, cyxb, yhzgx, cybz, sfgyr, cybzsm,
                    member_result_status, survey_status, is_changed, is_household_head,
                    is_urban_settled, is_married_out_woman, is_deceased, is_five_guarantees,
                    source_import_batch_id, source_import_row_id, last_import_batch_id, last_import_row_id,
                    initialized_from_base_id, initialized_at, created_at, updated_at
                )
                SELECT
                    mb.tenant_code, mb.region_code, mb.batch_id, mb.contractor_uid, mb.member_uid, mb.id,
                    mb.cbfbm, mb.cyxm, mb.cyzjlx, mb.cyzjhm, mb.cyxb, mb.yhzgx, mb.cybz, mb.sfgyr, mb.cybzsm,
                    'normal', 'not_surveyed', FALSE,
                    CASE WHEN mb.yhzgx = '01' THEN TRUE ELSE FALSE END,
                    FALSE, FALSE, FALSE, FALSE,
                    mb.source_import_batch_id, mb.source_import_row_id, mb.last_import_batch_id, mb.last_import_row_id,
                    mb.id, mb.initialized_at, NOW(), NOW()
                FROM survey_cbf_jtcy_base AS mb
                WHERE mb.batch_id = {batch_id}
                  AND NOT EXISTS (
                      SELECT 1 FROM survey_cbf_jtcy_result AS mr
                      WHERE mr.batch_id = mb.batch_id AND mr.base_id = mb.id
                  )
                """
            )
        connection.exec_driver_sql("DROP TABLE IF EXISTS cbf_jtcy")
        connection.exec_driver_sql("DROP TABLE IF EXISTS cbf")


def _upgrade_survey_phase2(engine: Engine) -> None:
    inspector = inspect(engine)
    target_columns = [
        ("generated_request_id", "INTEGER"),
        ("generated_request_no", "VARCHAR(64)"),
        ("generated_request_at", "TIMESTAMP WITH TIME ZONE"),
    ]
    with engine.begin() as connection:
        for table_name in ("survey_cbf_result", "survey_change_records"):
            if not inspector.has_table(table_name):
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in target_columns:
                if column_name not in columns:
                    connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            connection.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_generated_request_id ON {table_name}(generated_request_id)"
            )


def _upgrade_map_layers(engine: Engine) -> None:
    inspector = inspect(engine)
    if inspector.has_table("map_layers"):
        columns = {column["name"] for column in inspector.get_columns("map_layers")}
        statements: list[str] = []
        if "service_config" not in columns:
            statements.append("ALTER TABLE map_layers ADD COLUMN service_config TEXT")

        with engine.begin() as connection:
            for statement in statements:
                connection.exec_driver_sql(statement)
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_map_layers_key ON map_layers(key)")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_map_layers_category ON map_layers(category)")
        return

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE map_layers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                key VARCHAR(64) NOT NULL UNIQUE,
                layer_type VARCHAR(32) NOT NULL,
                category VARCHAR(16) NOT NULL,
                group_name VARCHAR(64),
                service_config TEXT,
                service_url TEXT NOT NULL,
                projection VARCHAR(32),
                default_visible BOOLEAN NOT NULL DEFAULT FALSE,
                is_default BOOLEAN NOT NULL DEFAULT FALSE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
            )
            """
        )
        connection.exec_driver_sql("CREATE INDEX ix_map_layers_key ON map_layers(key)")
        connection.exec_driver_sql("CREATE INDEX ix_map_layers_category ON map_layers(category)")


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
    if "status" not in columns:
        statements.append("ALTER TABLE regions ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'active'")
    if "sort_order" not in columns:
        statements.append("ALTER TABLE regions ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
    if "remark" not in columns:
        statements.append("ALTER TABLE regions ADD COLUMN remark TEXT")

    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_regions_tenant_code ON regions(tenant_code)")
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_regions_status ON regions(status)")
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
        columns = {item["name"] for item in inspector.get_columns("request_attachment_templates")}
        with engine.begin() as connection:
            if "parent_id" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE request_attachment_templates ADD COLUMN parent_id INTEGER REFERENCES request_attachment_templates(id) ON DELETE CASCADE"
                )
                connection.exec_driver_sql(
                    "CREATE INDEX ix_request_attachment_templates_parent_id ON request_attachment_templates(parent_id)"
                )
        return

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE request_attachment_templates (
                id SERIAL PRIMARY KEY,
                tenant_code VARCHAR(12) REFERENCES tenants(code),
                parent_id INTEGER REFERENCES request_attachment_templates(id) ON DELETE CASCADE,
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
            "CREATE INDEX ix_request_attachment_templates_parent_id ON request_attachment_templates(parent_id)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_request_attachment_templates_request_type ON request_attachment_templates(request_type)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_request_attachment_templates_stage_code ON request_attachment_templates(stage_code)"
        )
