"""The application's own database login (phase CM-7, docs/case-management/04 §9, layer 3).

    uv run python -m scripts.db_roles

Runs with the owner login (POSTGRES_USER), after the migrations; the Docker image runs it at every start. It:
1. refreshes the grants of the role cm_runtime from the database rules (cm_grant_runtime(), migration 0014): no DELETE
   on any case record, no UPDATE on permanent ones; new tables are covered automatically;
2. if POSTGRES_APP_USER and POSTGRES_APP_PASSWORD are set, creates that login (or updates its password) as a member of
   cm_runtime, with no other rights. The application then connects with it (settings.runtime_database_url).
The password is passed to PostgreSQL as a parameter and never printed.
"""

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with engine.begin() as connection:
        connection.execute(text("SELECT cm_grant_runtime()"))
        user, password = settings.postgres_app_user, settings.postgres_app_password
        if user and password is not None:
            connection.execute(text("SELECT set_config('kh.app_user', :user, true), set_config('kh.app_password', :password, true)"),
                               {"user": user, "password": password.get_secret_value()})
            connection.execute(text("""
                DO $$
                DECLARE
                    who text := current_setting('kh.app_user');
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = who) THEN
                        EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', who);
                    END IF;
                    EXECUTE format('ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION INHERIT PASSWORD %L',
                                   who, current_setting('kh.app_password'));
                    EXECUTE format('GRANT cm_runtime TO %I', who);
                    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), who);
                END $$
            """))
            print(f"Database login '{user}' is ready (member of cm_runtime: no DELETE on case records); grants refreshed")
        else:
            print("Grants of cm_runtime refreshed. POSTGRES_APP_USER is not set: the application uses the owner login")


if __name__ == "__main__":
    main()
