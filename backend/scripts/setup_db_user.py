"""setup_db_user.py — Instructions for creating the limited application DB user.

Run this script to print the SQL commands you need to execute in the
Railway SQL console (or via psql as the admin user).

Usage:
    python scripts/setup_db_user.py
"""

INSTRUCTIONS = """
╔══════════════════════════════════════════════════════════════════════════════╗
║          WALIX — SETUP USUARIO DE BD PARA LA APLICACIÓN                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

Ejecuta estos comandos en la Railway SQL console (o via psql como admin):

─── PASO 1: Crear el usuario de aplicación ──────────────────────────────────

  CREATE USER walix_app WITH PASSWORD 'CAMBIAR_EN_PRODUCCION';

  -- Reemplaza 'CAMBIAR_EN_PRODUCCION' con una contraseña segura (mínimo 32
  -- caracteres, generada con: openssl rand -base64 32).

─── PASO 2: Permisos de conexión y esquema ──────────────────────────────────

  GRANT CONNECT ON DATABASE railway TO walix_app;
  GRANT USAGE ON SCHEMA public TO walix_app;

─── PASO 3: Permisos sobre tablas y secuencias existentes ───────────────────

  GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO walix_app;

  GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public TO walix_app;

─── PASO 4: Permisos sobre tablas y secuencias futuras ──────────────────────

  ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO walix_app;

  ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO walix_app;

─── PASO 5: Verificar que walix_app NO tiene privilegios de admin ────────────

  -- walix_app NO debe poder: ALTER TABLE, DROP TABLE, TRUNCATE, CREATE TABLE.
  -- Comprueba los privilegios con:
  \\du walix_app

  -- Debe mostrar NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION.

─── PASO 6: Actualizar DATABASE_URL para el servidor FastAPI ────────────────

  En Railway → Variables de entorno del servicio backend, cambia:

    DATABASE_URL=postgresql://admin:adminpass@host:5432/railway
        ↓
    DATABASE_URL=postgresql://walix_app:TU_CONTRASEÑA@host:5432/railway

  IMPORTANTE:
  · Las migraciones de Alembic deben seguir usando el usuario admin (superuser).
    En Railway puedes tener una variable ALEMBIC_DATABASE_URL separada.
  · Los background tasks (webhooks, scheduler) usan AsyncSessionLocal, que
    hereda DATABASE_URL. Al cambiar a walix_app, esas conexiones también
    quedarán sujetas a RLS — asegúrate de que el middleware establece
    app.current_tenant_id antes de cualquier query de esos paths.

─── RESUMEN DE RESTRICCIONES ────────────────────────────────────────────────

  walix_app PUEDE:         SELECT, INSERT, UPDATE, DELETE en tablas públicas
  walix_app NO PUEDE:      ALTER TABLE, DROP TABLE, CREATE TABLE, TRUNCATE
  walix_app NO PUEDE:      modificar roles, crear extensiones, acceder a
                            pg_catalog con privilegios elevados
  walix_app SÍ está sujeto a RLS (no es superuser, no es propietario de tablas)

══════════════════════════════════════════════════════════════════════════════
"""

if __name__ == "__main__":
    print(INSTRUCTIONS)
