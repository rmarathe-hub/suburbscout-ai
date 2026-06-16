"""Shim — legacy router archived to app.legacy.query_router (Phase 9).

QueryRoute for plan trust gates lives in app.query_route_types.
"""

from app.legacy.query_router import *  # noqa: F403
from app.query_route_types import QueryIntent, QueryRoute  # noqa: F401
