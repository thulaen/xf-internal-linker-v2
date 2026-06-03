"""Slice 1.6 — private sidecars clients for apps.diagnostics.

Hosts the Python clients for coordd (Zookeeper-style coordination) and
errord (Camel-style exception-policy registry). Both move to
apps.platform._sidecars / apps.operations._sidecars once slice 9 creates
those canonical modules (paper-trail #571).
"""
