"""
授权数据模型
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LicenseStatus(Enum):
    """授权状态"""
    VALID = "valid"                    # 有效
    NOT_FOUND = "not_found"           # 未找到授权文件
    INVALID_FORMAT = "invalid_format" # 格式错误
    MACHINE_MISMATCH = "machine_mismatch"  # 机器码不匹配
    EXPIRED = "expired"               # 已过期
    TAMPERED = "tampered"             # 被篡改


@dataclass
class LicenseInfo:
    """授权信息"""
    machine_fingerprint: str   # 机器指纹（绑定机器）
    region_code: str           # 授权区域码（6/9/12位）
    region_name: str           # 区域名称（可选，便于显示）
    issued_at: datetime        # 授权时间
    expires_at: datetime | None  # 过期时间（None表示永久）
    version: int               # 授权格式版本
    features: list[str]        # 授权功能列表（预留扩展）
    
    @property
    def region_level(self) -> str:
        """根据区域码长度判断级别"""
        length = len(self.region_code)
        if length == 6:
            return "county"    # 区县级
        elif length == 9:
            return "town"      # 镇级
        elif length == 12:
            return "village"   # 村级
        else:
            return "custom"


@dataclass
class LicenseValidationResult:
    """授权验证结果"""
    status: LicenseStatus
    license_info: LicenseInfo | None = None
    error_message: str | None = None
