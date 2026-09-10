"""Exception types for data import."""


class ImportCanceled(Exception):
    """Raised when a user requests cancellation of a running import job."""
    pass
