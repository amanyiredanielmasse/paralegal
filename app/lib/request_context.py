from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class ToolTracking:
    """Collects which tools actually ran and any captured download URL,
    across the whole delegation tree (root agent + every sub-agent),
    for a single request."""

    tools_used: set[str] = field(default_factory=set)
    download_url: str | None = None


current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)
current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)
current_tracking: ContextVar[ToolTracking | None] = ContextVar("current_tracking", default=None)