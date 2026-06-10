---
id: data-flow
title: Data Flow
---

# Data Flow

## Federated Search

The Django main application provides a global `/api/search/?q=<query>` endpoint. This endpoint implements a **Federated Search** pattern:
1. It queries the local Django database for application records.
2. It makes a real-time HTTP `GET` request to the Docusaurus Dell container (`http://localhost:3000/search-doc.json`).
3. It uses lightning-fast Python native string matching to parse the Docusaurus search index.
4. It aggregates both results into a single JSON response.

This decoupled architecture ensures the main backend doesn't need to duplicate the documentation text in its database, while keeping `requirements.txt` slim by not requiring heavy Python indexing dependencies.
