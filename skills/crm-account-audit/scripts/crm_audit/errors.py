class SourceError(Exception):
    """A source (API or cache) returned something we can't use."""


class LiveCallLimitReached(SourceError):
    """The run hit APOLLO_MAX_LIVE_CALLS."""
