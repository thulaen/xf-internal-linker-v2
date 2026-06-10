import codecs
content = codecs.open('backend/apps/analytics/tasks.py', 'r', 'utf-8').read()
content = content.replace(
'''    query = f\"\"\"WITH latest AS (  # nosec B608
            SELECT content_item_id, SUM(clicks) AS latest_clicks
            SELECT content_item_id, SUM(clicks) AS latest_clicks''',
'''    query = f\"\"\"WITH latest AS (  # nosec B608
            SELECT content_item_id, SUM(clicks) AS latest_clicks'''
)
codecs.open('backend/apps/analytics/tasks.py', 'w', 'utf-8').write(content)
