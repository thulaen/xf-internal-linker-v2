"""Slice 1.6 — private sidecars clients for apps.sources.

Hosts the Python client for attrouted (NiFi-style route-on-attribute work
routing). attrouted stays in apps.sources because routing decisions are
source-tier work (which queue gets a XenForo sync vs a crawler fetch).
"""
