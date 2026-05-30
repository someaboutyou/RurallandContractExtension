from sqlalchemy import inspect
from sqlalchemy.engine import Engine


def upgrade_schema(engine: Engine) -> None:
    _upgrade_data_import_operations(engine)
    _upgrade_import_trace_columns(engine)
    _upgrade_import_performance_indexes(engine)
    _upgrade_survey_search_indexes(engine)
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
    _drop_survey_result_batch_ids(engine)
    _migrate_legacy_cbf_tables_to_survey(engine)
    _upgrade_survey_dk_postgis_geometry(engine)
    _upgrade_spatial_tables(engine)


def _upgrade_data_import_operations(engine: Engine) -> None:
    inspector = inspect(engine)
    if inspector.has_table("data_import_operations"):
        _ensure_scope_columns(engine, "data_import_operations")
        return
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE data_import_operations (
                id SERIAL PRIMARY KEY,
                import_batch_id INTEGER NOT NULL,
                import_file_id INTEGER,
                import_row_id INTEGER,
                chunk_no INTEGER NOT NULL DEFAULT 0,
                table_name VARCHAR(64) NOT NULL,
                primary_key JSON NOT NULL,
                operation_type VARCHAR(16) NOT NULL,
                before_snapshot JSON,
                after_snapshot JSON,
                tenant_code VARCHAR(12),
                region_code VARCHAR(32),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
            )
            """
        )
        connection.exec_driver_sql("CREATE INDEX ix_data_import_operations_import_batch_id ON data_import_operations(import_batch_id)")
        connection.exec_driver_sql("CREATE INDEX ix_data_import_operations_import_file_id ON data_import_operations(import_file_id)")
        connection.exec_driver_sql("CREATE INDEX ix_data_import_operations_import_row_id ON data_import_operations(import_row_id)")
        connection.exec_driver_sql("CREATE INDEX ix_data_import_operations_table_name ON data_import_operations(table_name)")
        connection.exec_driver_sql("CREATE INDEX ix_data_import_operations_tenant_code ON data_import_operations(tenant_code)")
        connection.exec_driver_sql("CREATE INDEX ix_data_import_operations_region_code ON data_import_operations(region_code)")


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


def _create_index_if_columns_exist(connection, inspector, table_name: str, index_name: str, columns: tuple[str, ...], expression: str) -> None:
    if not inspector.has_table(table_name):
        return
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    if all(column in existing_columns for column in columns):
        connection.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({expression})")


def _upgrade_import_performance_indexes(engine: Engine) -> None:
    inspector = inspect(engine)
    index_specs = [
        ("data_import_rows", "ix_data_import_rows_batch_id_desc", ("import_batch_id", "id"), "import_batch_id, id DESC"),
        ("data_import_rows", "ix_data_import_rows_batch_status_id_desc", ("import_batch_id", "status", "id"), "import_batch_id, status, id DESC"),
        ("data_import_operations", "ix_data_import_operations_batch_id_desc", ("import_batch_id", "id"), "import_batch_id, id DESC"),
        ("survey_cbf_base", "ix_survey_cbf_base_batch_source_cbfbm", ("batch_id", "source_cbfbm"), "batch_id, source_cbfbm"),
        ("survey_cbf_result", "ix_survey_cbf_result_base_id", ("base_id",), "base_id"),
        ("survey_cbf_result", "ix_survey_cbf_result_cbfbm_id", ("cbfbm", "id"), "cbfbm, id DESC"),
        (
            "survey_cbf_jtcy_base",
            "ix_survey_cbf_jtcy_base_batch_contractor_member",
            ("batch_id", "base_contractor_code", "base_member_id_no"),
            "batch_id, base_contractor_code, base_member_id_no",
        ),
        ("survey_cbf_jtcy_result", "ix_survey_cbf_jtcy_result_base_id", ("base_id",), "base_id"),
        ("survey_cbf_jtcy_result", "ix_survey_cbf_jtcy_result_cbfbm_cyzjhm_id", ("cbfbm", "cyzjhm", "id"), "cbfbm, cyzjhm, id DESC"),
        ("survey_fbf_base", "ix_survey_fbf_base_batch_source_fbfbm", ("batch_id", "source_fbfbm"), "batch_id, source_fbfbm"),
        ("survey_fbf_result", "ix_survey_fbf_result_base_id", ("base_id",), "base_id"),
        ("survey_fbf_result", "ix_survey_fbf_result_fbfbm_id", ("fbfbm", "id"), "fbfbm, id DESC"),
        ("survey_cbdkxx_base", "ix_survey_cbdkxx_base_batch_source_dkbm_cbfbm", ("batch_id", "source_dkbm", "cbfbm"), "batch_id, source_dkbm, cbfbm"),
        ("survey_cbdkxx_result", "ix_survey_cbdkxx_result_base_id", ("base_id",), "base_id"),
        ("survey_cbdkxx_result", "ix_survey_cbdkxx_result_dkbm_cbfbm_id", ("dkbm", "cbfbm", "id"), "dkbm, cbfbm, id DESC"),
        ("survey_cbdkxx_result", "ix_survey_cbdkxx_result_fbfbm_cbfbm", ("fbfbm", "cbfbm"), "fbfbm, cbfbm"),
        ("survey_dk_base", "ix_survey_dk_base_batch_source_dkbm", ("batch_id", "source_dkbm"), "batch_id, source_dkbm"),
        ("survey_dk_result", "ix_survey_dk_result_base_id", ("base_id",), "base_id"),
        ("survey_dk_result", "ix_survey_dk_result_dkbm_id", ("dkbm", "id"), "dkbm, id DESC"),
        ("survey_contractor_tasks", "ix_survey_contractor_tasks_batch_cbfbm", ("batch_id", "cbfbm"), "batch_id, cbfbm"),
        ("survey_contractor_tasks", "ix_survey_contractor_tasks_batch_status_cbfbm", ("batch_id", "task_status", "cbfbm"), "batch_id, task_status, cbfbm"),
        ("survey_contractor_tasks", "ix_survey_contractor_tasks_batch_region_cbfbm", ("batch_id", "region_code", "cbfbm"), "batch_id, region_code, cbfbm"),
    ]
    with engine.begin() as connection:
        for table_name, index_name, columns, expression in index_specs:
            _create_index_if_columns_exist(connection, inspector, table_name, index_name, columns, expression)


def _upgrade_survey_search_indexes(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    inspector = inspect(engine)
    index_specs = [
        ("survey_contractor_tasks", "ix_survey_contractor_tasks_cbfbm_trgm", ("cbfbm",), "cbfbm"),
        ("survey_contractor_tasks", "ix_survey_contractor_tasks_cbfmc_trgm", ("cbfmc",), "cbfmc"),
        ("survey_fbf_result", "ix_survey_fbf_result_fbfbm_trgm", ("fbfbm",), "fbfbm"),
        ("survey_fbf_result", "ix_survey_fbf_result_fbfmc_trgm", ("fbfmc",), "fbfmc"),
        ("survey_fbf_result", "ix_survey_fbf_result_fbffzrxm_trgm", ("fbffzrxm",), "fbffzrxm"),
    ]
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        for table_name, index_name, columns, column_name in index_specs:
            if not inspector.has_table(table_name):
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            if all(column in existing_columns for column in columns):
                connection.exec_driver_sql(
                    f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} USING GIN ({column_name} gin_trgm_ops)"
                )


def _upgrade_survey_dk_postgis_geometry(engine: Engine) -> None:
    inspector = inspect(engine)
    target_tables = ("survey_dk_base", "survey_dk_result")
    if not any(inspector.has_table(table_name) for table_name in target_tables):
        return

    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS postgis")
        connection.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION public.survey_dk_json_to_geom(input_geometry json)
            RETURNS public.geometry AS $$
            BEGIN
                IF input_geometry IS NULL THEN
                    RETURN NULL;
                END IF;
                RETURN ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(input_geometry::text), 4527));
            EXCEPTION WHEN OTHERS THEN
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql IMMUTABLE;
            """
        )

        for table_name in target_tables:
            if not inspector.has_table(table_name):
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            _add_column_if_missing(connection, columns, table_name, "geom", "public.geometry(MultiPolygon, 4527)")
            if "geometry" in columns:
                if table_name == "survey_dk_result":
                    connection.exec_driver_sql("DROP VIEW IF EXISTS public.survey_dk_result_geoserver")
                connection.exec_driver_sql(
                    f"""
                    UPDATE {table_name}
                    SET geom = public.survey_dk_json_to_geom(geometry)
                    WHERE geom IS NULL
                      AND geometry IS NOT NULL
                    """
                )
                connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS trg_sync_{table_name}_geom ON {table_name}")
                connection.exec_driver_sql(f"ALTER TABLE {table_name} DROP COLUMN geometry")
            connection.exec_driver_sql(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table_name}_geom_gist
                ON {table_name}
                USING GIST (geom)
                WHERE geom IS NOT NULL
                """
            )
            connection.exec_driver_sql(f"ANALYZE {table_name}")

        connection.exec_driver_sql("DROP FUNCTION IF EXISTS public.sync_survey_dk_geom()")
        connection.exec_driver_sql("DROP FUNCTION IF EXISTS public.survey_dk_json_to_geom(json)")


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
                tenant_code, region_code, contractor_uid, base_id, cbfbm, cbflx, cbfmc,
                cbfzjlx, cbfzjhm, cbfdz, yzbm, lxdh, cbfcysl, cbfdcrq, cbfdcy, cbfdcjs,
                gsjs, gsjsr, gsshrq, gsshr, group_region_code, group_region_name,
                survey_status, result_status, is_changed, change_type,
                source_import_batch_id, source_import_row_id, last_import_batch_id, last_import_row_id,
                initialized_from_base_id, initialized_at, created_at, updated_at
            )
            SELECT
                b.tenant_code, b.region_code, b.contractor_uid, b.id, b.cbfbm, b.cbflx, b.cbfmc,
                b.cbfzjlx, b.cbfzjhm, b.cbfdz, b.yzbm, b.lxdh, b.cbfcysl, b.cbfdcrq, b.cbfdcy, b.cbfdcjs,
                b.gsjs, b.gsjsr, b.gsshrq, b.gsshr, b.group_region_code, b.group_region_name,
                'not_surveyed', 'normal', FALSE, 'none',
                b.source_import_batch_id, b.source_import_row_id, b.last_import_batch_id, b.last_import_row_id,
                b.id, b.initialized_at, NOW(), NOW()
            FROM survey_cbf_base AS b
            WHERE b.batch_id = {batch_id}
              AND NOT EXISTS (
                  SELECT 1 FROM survey_cbf_result AS r
                  WHERE r.base_id = b.id
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
                    tenant_code, region_code, contractor_uid, member_uid, base_id,
                    cbfbm, cyxm, cyzjlx, cyzjhm, cyxb, yhzgx, cybz, sfgyr, cybzsm,
                    member_result_status, survey_status, is_changed, is_household_head,
                    is_urban_settled, is_married_out_woman, is_deceased, is_five_guarantees,
                    source_import_batch_id, source_import_row_id, last_import_batch_id, last_import_row_id,
                    initialized_from_base_id, initialized_at, created_at, updated_at
                )
                SELECT
                    mb.tenant_code, mb.region_code, mb.contractor_uid, mb.member_uid, mb.id,
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
                      WHERE mr.base_id = mb.id
                  )
                """
            )
        connection.exec_driver_sql("DROP TABLE IF EXISTS cbf_jtcy")
        connection.exec_driver_sql("DROP TABLE IF EXISTS cbf")


def _drop_survey_result_batch_ids(engine: Engine) -> None:
    inspector = inspect(engine)
    result_tables = (
        "survey_cbf_result",
        "survey_cbf_jtcy_result",
        "survey_fbf_result",
        "survey_cbdkxx_result",
        "survey_dk_result",
    )
    existing_tables = [table_name for table_name in result_tables if inspector.has_table(table_name)]
    if not existing_tables:
        return
    with engine.begin() as connection:
        legacy_indexes = (
            "ix_survey_cbf_result_batch_id",
            "ix_survey_cbf_result_batch_base_id",
            "ix_survey_cbf_jtcy_result_batch_id",
            "ix_survey_cbf_jtcy_result_batch_base_id",
            "ix_survey_fbf_result_batch_id",
            "ix_survey_fbf_result_batch_base_id",
            "ix_survey_fbf_result_batch_fbfbm",
            "ix_survey_cbdkxx_result_batch_id",
            "ix_survey_cbdkxx_result_batch_base_id",
            "ix_survey_cbdkxx_result_batch_fbfbm_cbfbm",
            "ix_survey_dk_result_batch_id",
            "ix_survey_dk_result_batch_base_id",
        )
        for index_name in legacy_indexes:
            connection.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")
        for table_name in existing_tables:
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if "batch_id" in columns:
                connection.exec_driver_sql(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS batch_id")
        if "survey_cbf_result" in existing_tables:
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_survey_cbf_result_base_id ON survey_cbf_result(base_id)")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_survey_cbf_result_cbfbm_id ON survey_cbf_result(cbfbm, id DESC)")
        if "survey_cbf_jtcy_result" in existing_tables:
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_survey_cbf_jtcy_result_base_id ON survey_cbf_jtcy_result(base_id)")
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_survey_cbf_jtcy_result_cbfbm_cyzjhm_id ON survey_cbf_jtcy_result(cbfbm, cyzjhm, id DESC)"
            )
        if "survey_fbf_result" in existing_tables:
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_survey_fbf_result_base_id ON survey_fbf_result(base_id)")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_survey_fbf_result_fbfbm_id ON survey_fbf_result(fbfbm, id DESC)")
        if "survey_cbdkxx_result" in existing_tables:
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_survey_cbdkxx_result_base_id ON survey_cbdkxx_result(base_id)")
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_survey_cbdkxx_result_dkbm_cbfbm_id ON survey_cbdkxx_result(dkbm, cbfbm, id DESC)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_survey_cbdkxx_result_fbfbm_cbfbm ON survey_cbdkxx_result(fbfbm, cbfbm)"
            )
        if "survey_dk_result" in existing_tables:
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_survey_dk_result_base_id ON survey_dk_result(base_id)")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_survey_dk_result_dkbm_id ON survey_dk_result(dkbm, id DESC)")


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


def _upgrade_spatial_tables(engine: Engine) -> None:
    inspector = inspect(engine)
    missing = [
        table
        for table in ("czkfbj", "dltb", "gdbhmb", "stbhhx", "xzq", "xzqjx", "yjjbntbhtb")
        if not inspector.has_table(table)
    ]

    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS postgis")

        if "czkfbj" in missing:
            connection.exec_driver_sql(
                """
                CREATE TABLE public.czkfbj (
                    "OBJECTID" int8 NOT NULL,
                    "Shape" public.geometry(multipolygon, 4527) NULL,
                    "BSM" varchar(18) NULL,
                    "YSDM" varchar(10) NULL,
                    "XZQDM" varchar(12) NULL,
                    "XZQMC" varchar(100) NULL,
                    "GHFQDM" varchar(3) NULL,
                    "GHFQMC" varchar(50) NULL,
                    "MJ" numeric NULL,
                    "BZ" varchar(255) NULL,
                    "Shape_Length" numeric NULL,
                    "Shape_Area" numeric NULL,
                    "MJ_YS" numeric NULL,
                    "MJ_YS_DOUBLE" numeric NULL,
                    "MJ_TQ" numeric NULL,
                    CONSTRAINT czkfbj_pkey PRIMARY KEY ("OBJECTID")
                )
                """
            )

        if "dltb" in missing:
            connection.exec_driver_sql(
                """
                CREATE TABLE public.dltb (
                    "OBJECTID" int8 NOT NULL,
                    "Shape" public.geometry(multipolygon, 4527) NULL,
                    "BSM" varchar(18) NULL,
                    "YSDM" varchar(10) NULL,
                    "TBYBH" varchar(18) NULL,
                    "TBBH" varchar(8) NULL,
                    "DLBM" varchar(5) NULL,
                    "DLMC" varchar(60) NULL,
                    "QSXZ" varchar(2) NULL,
                    "QSDWDM" varchar(19) NULL,
                    "ZLDWDM" varchar(19) NULL,
                    "ZLDWMC" varchar(255) NULL,
                    "TBMJ" numeric NULL,
                    "KCDLBM" varchar(5) NULL,
                    "KCXS" numeric NULL,
                    "KCMJ" numeric NULL,
                    "TBDLMJ" numeric NULL,
                    "GDLX" varchar(2) NULL,
                    "GDPDJB" varchar(2) NULL,
                    "XZDWKD" numeric NULL,
                    "TBXHMC" varchar(100) NULL,
                    "ZZSXDM" varchar(30) NULL,
                    "ZZSXMC" varchar(100) NULL,
                    "GDDB" int4 NULL,
                    "FRDBS" varchar(1) NULL,
                    "CZCSXM" varchar(4) NULL,
                    "SJNF" int4 NULL,
                    "MSSM" varchar(2) NULL,
                    "HDMC" varchar(100) NULL,
                    "BZ" varchar(255) NULL,
                    "TBXHDM" varchar(30) NULL,
                    "Shape_Length" numeric NULL,
                    "Shape_Area" numeric NULL,
                    CONSTRAINT dltb_pkey PRIMARY KEY ("OBJECTID")
                )
                """
            )

        if "gdbhmb" in missing:
            connection.exec_driver_sql(
                """
                CREATE TABLE public.gdbhmb (
                    "OBJECTID" int8 NOT NULL,
                    "Shape" public.geometry(multipolygon, 4527) NULL,
                    "BSM" varchar(18) NULL,
                    "YSDM" varchar(10) NULL,
                    "TBYBH" varchar(18) NULL,
                    "TBBH" varchar(8) NULL,
                    "DLBM" varchar(5) NULL,
                    "DLMC" varchar(60) NULL,
                    "QSXZ" varchar(2) NULL,
                    "QSDWDM" varchar(19) NULL,
                    "QSDWMC" varchar(255) NULL,
                    "ZLDWDM" varchar(19) NULL,
                    "ZLDWMC" varchar(255) NULL,
                    "TBMJ" numeric NULL,
                    "KCDLBM" varchar(5) NULL,
                    "KCXS" numeric NULL,
                    "KCMJ" numeric NULL,
                    "TBDLMJ" numeric NULL,
                    "GDLX" varchar(2) NULL,
                    "SFWHTD" int4 NULL,
                    "GDPDJB" varchar(2) NULL,
                    "TBXHDM" varchar(6) NULL,
                    "TBXHMC" varchar(20) NULL,
                    "ZZSXDM" varchar(6) NULL,
                    "ZZSXMC" varchar(20) NULL,
                    "GDDB" int4 NULL,
                    "FRDBS" varchar(1) NULL,
                    "SJNF" int4 NULL,
                    "ORIG_FID" int4 NULL,
                    "TBMJ_YS" numeric NULL,
                    "TBDLMJ_YS" numeric NULL,
                    "KCMJ_YS" numeric NULL,
                    "Shape_Length" numeric NULL,
                    "Shape_Area" numeric NULL,
                    CONSTRAINT gdbhmb_pkey PRIMARY KEY ("OBJECTID")
                )
                """
            )

        if "stbhhx" in missing:
            connection.exec_driver_sql(
                """
                CREATE TABLE public.stbhhx (
                    "OBJECTID" int8 NOT NULL,
                    "Shape" public.geometry(multipolygon, 4490) NULL,
                    "BSM" varchar(255) NULL,
                    "YSDM" varchar(255) NULL,
                    "XZQDM" varchar(255) NULL,
                    "XZQMC" varchar(255) NULL,
                    "SHENG" varchar(255) NULL,
                    "SHI" varchar(255) NULL,
                    "XIAN" varchar(255) NULL,
                    "HXBM" varchar(255) NULL,
                    "HXMC" varchar(255) NULL,
                    "HXLX" varchar(255) NULL,
                    "LXBM" varchar(255) NULL,
                    "MJ" numeric NULL,
                    "ZRBHDMC" varchar(255) NULL,
                    "ZRBHDJB" varchar(255) NULL,
                    "ZRBHDLX" varchar(255) NULL,
                    "ZRBHDFQ" varchar(255) NULL,
                    "XTYZBLX" varchar(255) NULL,
                    "GKCS" varchar(255) NULL,
                    "SZXJXZQDM" varchar(255) NULL,
                    "SZXJXZQMC" varchar(255) NULL,
                    "BZ" varchar(255) NULL,
                    "MJ_YS" numeric NULL,
                    "MJ_YS_DOUBLE" numeric NULL,
                    "MJ_TQ" numeric NULL,
                    "Shape_Length" numeric NULL,
                    "Shape_Area" numeric NULL,
                    CONSTRAINT stbhhx_pkey PRIMARY KEY ("OBJECTID")
                )
                """
            )

        if "xzq" in missing:
            connection.exec_driver_sql(
                """
                CREATE TABLE public.xzq (
                    "OBJECTID" int8 NOT NULL,
                    "SHAPE" public.geometry(multipolygon, 4527) NULL,
                    "BSM" varchar(18) NULL,
                    "YSDM" varchar(10) NULL,
                    "XZQDM" varchar(9) NULL,
                    "XZQMC" varchar(100) NULL,
                    "DCMJ" numeric NULL,
                    "JSMJ" numeric NULL,
                    "MSSM" varchar(2) NULL,
                    "HDMC" varchar(100) NULL,
                    "BZ" varchar(255) NULL,
                    "SHAPE_Length" numeric NULL,
                    "SHAPE_Area" numeric NULL,
                    CONSTRAINT xzq_pkey PRIMARY KEY ("OBJECTID")
                )
                """
            )

        if "xzqjx" in missing:
            connection.exec_driver_sql(
                """
                CREATE TABLE public.xzqjx (
                    "OBJECTID" int8 NOT NULL,
                    "SHAPE" public.geometry(multilinestring, 4527) NULL,
                    "BSM" varchar(18) NULL,
                    "YSDM" varchar(10) NULL,
                    "JXLX" varchar(6) NULL,
                    "JXXZ" varchar(6) NULL,
                    "JXSM" varchar(100) NULL,
                    "BZ" varchar(255) NULL,
                    "SHAPE_Length" numeric NULL,
                    CONSTRAINT xzqjx_pkey PRIMARY KEY ("OBJECTID")
                )
                """
            )

        if "yjjbntbhtb" in missing:
            connection.exec_driver_sql(
                """
                CREATE TABLE public.yjjbntbhtb (
                    "OBJECTID" int8 NOT NULL,
                    "Shape" public.geometry(multipolygon, 4527) NULL,
                    "BSM" varchar(18) NULL,
                    "YSDM" varchar(10) NULL,
                    "XZQDM" varchar(12) NULL,
                    "XZQMC" varchar(100) NULL,
                    "YJJBNTTBBH" varchar(20) NULL,
                    "TBBH" varchar(8) NULL,
                    "DLBM" varchar(5) NULL,
                    "DLMC" varchar(60) NULL,
                    "QSXZ" varchar(2) NULL,
                    "QSDWDM" varchar(19) NULL,
                    "ZLDWDM" varchar(19) NULL,
                    "YJJBNTTBMJ" numeric NULL,
                    "KCDLBM" varchar(5) NULL,
                    "KCXS" numeric NULL,
                    "KCMJ" numeric NULL,
                    "YJJBNTMJ" numeric NULL,
                    "GDLX" varchar(2) NULL,
                    "GDPDJB" varchar(2) NULL,
                    "GGBZL" varchar(10) NULL,
                    "TBXHDM" varchar(6) NULL,
                    "TBXHMC" varchar(20) NULL,
                    "ZZSXDM" varchar(6) NULL,
                    "ZZSXMC" varchar(20) NULL,
                    "GDDB" int4 NULL,
                    "GDDJ" int4 NULL,
                    "ZLFLDM" varchar(12) NULL,
                    "FRDBS" varchar(1) NULL,
                    "SJNF" int4 NULL,
                    "CFZR" varchar(20) NULL,
                    "ZMC" varchar(50) NULL,
                    "ZZRR" varchar(20) NULL,
                    "ZRRZJHM" varchar(18) NULL,
                    "ZRRMC" varchar(20) NULL,
                    "LXDH" varchar(20) NULL,
                    "JZDZ" varchar(50) NULL,
                    "BHKSSJ" timestamp NULL,
                    "BHJSSJ" timestamp NULL,
                    "SJBH" varchar(20) NULL,
                    "SJMC" varchar(50) NULL,
                    "ZRSYX" varchar(100) NULL,
                    "WDGD" varchar(10) NULL,
                    "SFWYYJJBNT" varchar(10) NULL,
                    "BZ" varchar(50) NULL,
                    "QSDWMC" varchar(255) NULL,
                    "ZLDWMC" varchar(255) NULL,
                    "FWDGDHRLY" varchar(255) NULL,
                    "ORIG_FID" int4 NULL,
                    "YJJBNTTBMJ_YS" numeric NULL,
                    "YJJBNTMJ_YS" numeric NULL,
                    "KCMJ_YS" numeric NULL,
                    "Shape_Length" numeric NULL,
                    "Shape_Area" numeric NULL,
                    "WDGD_YS" varchar(10) NULL,
                    CONSTRAINT yjjbntbhtb_pkey PRIMARY KEY ("OBJECTID")
                )
                """
            )

        spatial_index_specs = (
            ("czkfbj", "Shape"),
            ("dltb", "Shape"),
            ("gdbhmb", "Shape"),
            ("stbhhx", "Shape"),
            ("xzq", "SHAPE"),
            ("xzqjx", "SHAPE"),
            ("yjjbntbhtb", "Shape"),
        )
        for table_name, geom_column in spatial_index_specs:
            if not inspector.has_table(table_name) and table_name not in missing:
                continue
            connection.exec_driver_sql(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table_name}_{geom_column.lower()}_gist
                ON public.{table_name}
                USING GIST ("{geom_column}")
                WHERE "{geom_column}" IS NOT NULL
                """
            )
            connection.exec_driver_sql(f"ANALYZE public.{table_name}")
