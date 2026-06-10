import codecs
content = codecs.open('backend/apps/analytics/tasks.py', 'r', 'utf-8').read()
old = '''    query = (  # nosec B608
        f\"\"\"
        WITH latest AS ('''

new = '''    query = f\"\"\"WITH latest AS (  # nosec B608
            SELECT content_item_id, SUM(clicks) AS latest_clicks'''

content = content.replace(old, new)

old2 = '''          AND latest.latest_clicks > trailing.avg_clicks * {_SPIKE_RATIO}
        \"\"\"
    )
    table = engine.execute_sql(query)'''

new2 = '''          AND latest.latest_clicks > trailing.avg_clicks * {_SPIKE_RATIO}
        \"\"\"
    table = engine.execute_sql(query)'''

content = content.replace(old2, new2)
codecs.open('backend/apps/analytics/tasks.py', 'w', 'utf-8').write(content)
