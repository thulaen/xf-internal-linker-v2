"""Slice 1.6 — private sidecars clients for apps.auto_issues.

Hosts the Python clients for snapshotd (the durable evidence layer for
AutoIssues) and schemard (the Avro-style schema registry snapshotd
consults). Both will move to apps.governance._sidecars once slice 9
creates the canonical governance module — tracked at paper-trail #571.
"""
