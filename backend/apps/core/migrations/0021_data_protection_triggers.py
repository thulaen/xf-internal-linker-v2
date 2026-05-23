# ruff: noqa
# Generated migration: data-protection triggers + dependency pin to
# paper_trail.0004 to break the __latest__ inconsistency cycle that
# would otherwise fire when paper_trail.0005 lands.
from django.db import migrations


FORWARD_SQL = """
CREATE OR REPLACE FUNCTION xf_block_admin_delete()
RETURNS trigger AS $$
BEGIN
  IF OLD.username = 'admin'
     AND current_setting('xf.allow_admin_delete', true) IS DISTINCT FROM 'true'
  THEN
    RAISE EXCEPTION 'admin user is protected; use SET LOCAL xf.allow_admin_delete=true only inside an audited recovery transaction';
  END IF;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS auth_user_admin_protect ON auth_user;
CREATE TRIGGER auth_user_admin_protect
BEFORE DELETE ON auth_user
FOR EACH ROW
EXECUTE FUNCTION xf_block_admin_delete();

CREATE OR REPLACE FUNCTION xf_block_autoissue_truncate()
RETURNS trigger AS $$
BEGIN
  IF current_setting('xf.allow_bulk_delete', true) IS DISTINCT FROM 'true'
  THEN
    RAISE EXCEPTION 'AutoIssue table is protected; use SET LOCAL xf.allow_bulk_delete=true only inside an audited recovery transaction';
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS auto_issues_protect ON auto_issues_autoissue;
CREATE TRIGGER auto_issues_protect
BEFORE TRUNCATE ON auto_issues_autoissue
FOR EACH STATEMENT
EXECUTE FUNCTION xf_block_autoissue_truncate();

CREATE OR REPLACE FUNCTION xf_block_papertrail_truncate()
RETURNS trigger AS $$
BEGIN
  IF current_setting('xf.allow_bulk_delete', true) IS DISTINCT FROM 'true'
  THEN
    RAISE EXCEPTION 'PaperTrail table is protected; use SET LOCAL xf.allow_bulk_delete=true only inside an audited recovery transaction';
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS paper_trail_protect ON paper_trail_papertrailentry;
CREATE TRIGGER paper_trail_protect
BEFORE TRUNCATE ON paper_trail_papertrailentry
FOR EACH STATEMENT
EXECUTE FUNCTION xf_block_papertrail_truncate();
"""


REVERSE_SQL = """
DROP TRIGGER IF EXISTS auth_user_admin_protect ON auth_user;
DROP TRIGGER IF EXISTS auto_issues_protect ON auto_issues_autoissue;
DROP TRIGGER IF EXISTS paper_trail_protect ON paper_trail_papertrailentry;
DROP FUNCTION IF EXISTS xf_block_admin_delete();
DROP FUNCTION IF EXISTS xf_block_autoissue_truncate();
DROP FUNCTION IF EXISTS xf_block_papertrail_truncate();
"""


def _is_test_database(schema_editor):
    return schema_editor.connection.alias.startswith("test") or schema_editor.connection.settings_dict[
        "NAME"
    ].startswith("test_")


def apply_triggers(_apps, schema_editor):
    if _is_test_database(schema_editor):
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(FORWARD_SQL)


def remove_triggers(_apps, schema_editor):
    if _is_test_database(schema_editor):
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(REVERSE_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_scheduledtaskrun"),
        ("auth", "__latest__"),
        ("auto_issues", "__latest__"),
        # Pinned to 0004 (the latest paper_trail migration at the time
        # core.0021 was authored). Using __latest__ here creates an
        # InconsistentMigrationHistory error when later paper_trail
        # migrations (e.g. 0005) land, because they would need to be
        # applied BEFORE core.0021 yet core.0021 is already in the
        # database. Pinning to 0004 keeps the original applied order
        # valid and lets new paper_trail migrations land freely.
        ("paper_trail", "0004_papertrailentry_test_case_autoissue_id"),
    ]

    operations = [
        migrations.RunPython(apply_triggers, remove_triggers),
    ]
