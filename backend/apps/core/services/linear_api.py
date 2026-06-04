import requests
from django.conf import settings

class LinearClient:
    def __init__(self):
        self.api_key = getattr(settings, 'LINEAR_API_KEY', None)
        self.base_url = "https://api.graphql.linear.app/"

    def _get_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = self.api_key
        return headers

    def sync_autoissue_to_linear(self, issue) -> None:
        query = f"""
        mutation {{
          issueCreate(input: {{
            title: "{issue.title}",
            description: "{issue.description}",
            stateId: "{issue.status}",
            identifier: "{issue.external_id}"
          }}) {{
            success
            issue {{
              id
              title
            }}
          }}
        }}
        """
        response = requests.post(
            self.base_url,
            headers=self._get_headers(),
            json={"query": query}
        )
        response.raise_for_status()

    def sync_papertrail_to_linear(self, entry) -> None:
        query = f"""
        mutation {{
          issueCreate(input: {{
            title: "{entry.title}",
            description: "{entry.abstract}",
            stateId: "{entry.status}",
            identifier: "{entry.fingerprint}"
          }}) {{
            success
            issue {{
              id
              title
            }}
          }}
        }}
        """
        response = requests.post(
            self.base_url,
            headers=self._get_headers(),
            json={"query": query}
        )
        response.raise_for_status()

    def fetch_open_linear_issues(self, limit: int = 5) -> list[dict]:
        query = f"""
        query {{
          issues(first: {limit}, filter: {{ state: {{ type: {{ eq: "unstarted" }} }} }}) {{
            nodes {{
              id
              title
              url
            }}
          }}
        }}
        """
        response = requests.post(
            self.base_url,
            headers=self._get_headers(),
            json={"query": query}
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", {}).get("issues", {}).get("nodes", [])


def sync_autoissue_to_linear(issue) -> None:
    client = LinearClient()
    client.sync_autoissue_to_linear(issue)


def sync_papertrail_to_linear(entry) -> None:
    client = LinearClient()
    client.sync_papertrail_to_linear(entry)


def fetch_open_linear_issues(limit: int = 5) -> list[dict]:
    client = LinearClient()
    return client.fetch_open_linear_issues(limit)
