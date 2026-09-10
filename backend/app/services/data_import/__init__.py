"""Data import package.

Public API is intentionally kept identical to the old single-file module::

    from app.services.data_import_service import data_import_service
    from app.services.data_import_service import ImportCanceled

Both symbols are re-exported here for forward compatibility.
"""

from .errors import ImportCanceled
from .core import data_import_service

__all__ = ["data_import_service", "ImportCanceled"]
