import requests
import json
import urllib.parse
from datetime import datetime, timedelta

LOKI_URL = "http://loki:3100"

def query(service):
    query = f'{{compose_service="{service}"}} |~ "(?i)(warn|error)"'
    url = f"{LOKI_URL}/loki/api/v1/query_range"
    params = {
        'query': query,
        'limit': 10
    }
    response = requests.get(url, params=params)
    print(f"--- {service} ---")
    try:
        results = response.json()['data']['result']
        for stream in results:
            for value in stream['values']:
                print(value[1])
    except Exception as e:
        print(response.text)

for svc in ["agent-guard", "grafana", "celery-beat"]:
    query(svc)
