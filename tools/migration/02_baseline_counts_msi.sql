-- KUBE PLAN Slice 13 row-count baseline query.
--
-- Plain English: this prints one SQL command per user table. Run the generated
-- commands against the source database and the rehearsal restore, then compare
-- the two output files with tools/migration/04_verify_equal.sh.
SELECT format(
    'SELECT %L AS table_name, count(*) AS row_count FROM %I.%I;',
    schemaname || '.' || tablename,
    schemaname,
    tablename
)
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename;
