-- KUBE PLAN exact row-count proof query.
--
-- Plain English: this prints one "schema.table|row_count" line for each
-- non-system table. Use the same file on MSI and Dell, then compare outputs.
SELECT
    schemaname || '.' || tablename,
    (
        (
            xpath(
                '/row/c/text()',
                query_to_xml(
                    format('select count(*) as c from %I.%I', schemaname, tablename),
                    false,
                    true,
                    ''
                )
            )
        )[1]::text
    )::bigint
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1;
