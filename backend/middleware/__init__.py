"""Request guards: JWT verification and role-based access control.

Implemented as FastAPI dependencies (the idiomatic 'middleware' in FastAPI) so
individual routes opt in explicitly — e.g. official-only actions depend on
``require_role('official')``.
"""
