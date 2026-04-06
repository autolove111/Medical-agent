"""Experimental module package.

Important: keep package init side-effect free.
Do not import submodules eagerly here, otherwise it can create circular imports
during application startup (e.g. graph <-> rag <-> experimental).
"""

__all__ = []
