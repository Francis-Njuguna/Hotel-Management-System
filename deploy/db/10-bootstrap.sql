-- Official postgres entrypoint runs this once, in POSTGRES_DB, on empty PGDATA.
\set ON_ERROR_STOP on
\getenv app_role HMS_APP_USER
\getenv app_password POSTGRES_PASSWORD
\getenv app_db POSTGRES_DB

BEGIN;
ALTER ROLE postgres PASSWORD NULL;
CREATE ROLE "www-data" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD NULL;
CREATE ROLE :"app_role" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE :"app_role" PASSWORD :'app_password';
\unset app_password

REVOKE ALL ON DATABASE postgres, template1 FROM PUBLIC;
REVOKE ALL ON DATABASE :"app_db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"app_db" TO "www-data", :"app_role";
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO "www-data";
GRANT USAGE ON SCHEMA public TO :"app_role";

-- Install in the target database BEFORE the migration creates room exclusions.
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;

-- Only migration-owned application relations, not arbitrary admin objects.
ALTER DEFAULT PRIVILEGES FOR ROLE "www-data" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE "www-data" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO :"app_role";
COMMIT;
