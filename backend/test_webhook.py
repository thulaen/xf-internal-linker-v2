import requests

# Local URL (when Docker is running, the host port 8000 maps to backend)
# Using 127.0.0.1 for local testing
URL = "http://127.0.0.1:8000/api/sync/webhooks/xenforo/"

# The secret we configured
SECRET = "MySuperSecretSync123"


def test_thread_insert():
    payload = {
        "event": "thread_insert",
        "content_type": "thread",
        "content_id": 999999,  # Dummy ID
        "node_id": 2,
        "data": {
            "title": "Webhook Test Thread",
            "thread_id": 999999,
            "node_id": 2,
            "view_url": "https://www.goldmidi.com/threads/webhook-test.999999/",
        },
    }

    headers = {
        "XF-Webhook-Secret": SECRET,
        "XF-Webhook-Event": "thread_insert",
        "Content-Type": "application/json",
    }

    print(f"Sending thread_insert to {URL}...")
    try:
        response = requests.post(URL, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")


def test_invalid_secret():
    payload = {"event": "test"}
    headers = {"XF-Webhook-Secret": "WRONG_SECRET"}

    print(f"\nSending with WRONG SECRET to {URL}...")
    try:
        response = requests.post(URL, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    # Check if server is up first
    try:
        requests.get("http://127.0.0.1:8000/", timeout=1)
        test_thread_insert()
        test_invalid_secret()
    except requests.exceptions.ConnectionError:
        print("ERROR: Django server is not running on http://127.0.0.1:8000/")
        print("Please run 'docker-compose up' before running this test.")
