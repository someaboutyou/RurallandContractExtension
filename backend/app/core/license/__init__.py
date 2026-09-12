"""
授权验证模块
"""

from .license_validator import license_validator, LicenseValidator
from .license_models import LicenseInfo, LicenseStatus, LicenseValidationResult

__all__ = [
    "license_validator",
    "LicenseValidator",
    "LicenseInfo",
    "LicenseStatus",
    "LicenseValidationResult",
]
