# Startup And Deployment Scripts

These scripts support a portable deployment layout where runtime dependencies are stored outside the source code under `runtime/`.

## Recommended Flow

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\init.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-all.ps1
```

Linux:

```bash
bash ./scripts/install.sh
bash ./scripts/init.sh
bash ./scripts/start-all.sh
```

If `start-all.ps1` or `start-all.sh` is run before install/init, it exits with a clear reminder telling you which command to run next.

## Script Roles

- `install.ps1` / `install.sh`: checks whether the portable runtime files exist and writes `runtime/.state/installed.json`.
- `init.ps1` / `init.sh`: initializes PostgreSQL/PostGIS and GeoServer, then writes `runtime/.state/initialized.json`.
- `start-all.ps1` / `start-all.sh`: starts PostgreSQL/PostGIS, GeoServer, and the backend after install/init markers exist.
- `stop-all.ps1` / `stop-all.sh`: stops GeoServer and PostgreSQL/PostGIS.
- `start-postgres.*`: starts or initializes the portable PostgreSQL/PostGIS runtime.
- `start-geoserver.*`: starts the portable GeoServer runtime.
- `start-backend.*`: starts the FastAPI backend.
- `start-frontend.*`: starts the Vue frontend.

## Windows Notes

Expected runtime files:

- `runtime/windows/jdk/bin/java.exe`
- `runtime/windows/python/python.exe` with `backend/requirements.txt` already installed
- `runtime/windows/postgresql/bin/pg_ctl.exe`
- `runtime/windows/postgresql/bin/initdb.exe`
- `runtime/windows/postgresql/bin/psql.exe`
- `runtime/windows/postgresql/bin/createdb.exe`
- `runtime/windows/postgresql/bin/pg_isready.exe`
- `runtime/windows/geoserver/bin/startup.bat`, or `runtime/windows/geoserver/start.jar`

Start backend dependencies only:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-all.ps1
```

Start backend dependencies plus frontend:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-all.ps1 -WithFrontend
```

## Linux Notes

Expected runtime files:

- `runtime/linux/jdk/bin/java`
- `runtime/linux/python/bin/python` with `backend/requirements.txt` already installed
- `runtime/linux/postgresql/bin/pg_ctl`
- `runtime/linux/postgresql/bin/initdb`
- `runtime/linux/postgresql/bin/psql`
- `runtime/linux/postgresql/bin/createdb`
- `runtime/linux/postgresql/bin/pg_isready`
- `runtime/linux/geoserver/bin/startup.sh`, or `runtime/linux/geoserver/start.jar`

Backend startup uses only the bundled runtime Python. It does not create or use a development virtual environment.

## Default Database

- Host: `127.0.0.1`
- Port: `15432`
- Database: `erlunyanbao`
- User: `RurallandContractExtension`
- Password: `RurallandContractExtension`

The portable PostgreSQL runtime uses `15432` by default so it does not conflict with an existing local PostgreSQL on `5432`.

## GeoServer Initialization

The initialization script starts GeoServer and prepares:

- Workspace: `erlunyanbao`
- PostGIS datastore: `postgis`
- Default table/layer: `public.DK3213242017` published as `erlunyanbao:DK3213242017`
- Layer SRS: `EPSG:4527`

The PostGIS table must already exist and contain a geometry column before GeoServer can publish it.

## Database Initialization

During `init`, the backend ORM creates the database tables and applies lightweight migrations by running `app.db.bootstrap --schema`. When the backend starts, it only fills framework seed data.

After initialization, the selected runtime settings are written to:

```text
runtime/.state/runtime.env
```

`start-all` and backend startup read this file so deployment and runtime use the same database port, credentials, and service URLs.

Non-ORM spatial table DDL should be stored in:

```text
scripts/sql/init-postgis-schema.sql
```

This file is executed against the portable target database during `init`; no production initialization depends on an existing `5432` source database.

For local development only, you can explicitly import table structure from an existing source database before the backend bootstrap runs.

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\init.ps1 -ImportSchemaFromSource
```

Linux:

```bash
IMPORT_SCHEMA_FROM_SOURCE=1 bash ./scripts/init.sh
```

The optional source import copies schema only, not business data, from `127.0.0.1:5432/erlunyanbao/public`.
