"""Backward-compatible shim.

The implementation has been refactored into the data_import package.
All symbols are re-exported here so existing imports continue to work::

    from app.services.data_import_service import data_import_service
    from app.services.data_import_service import ImportCanceled
"""

from app.services.data_import import ImportCanceled, data_import_service

__all__ = ["data_import_service", "ImportCanceled"]
