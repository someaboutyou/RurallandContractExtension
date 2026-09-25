"""
授权文件验证器

验证授权文件的有效性
"""

import hashlib
import json
import struct
import logging
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature

from .license_models import LicenseInfo, LicenseStatus, LicenseValidationResult
from .machine_fingerprint import clear_machine_fingerprint_cache, get_machine_fingerprint

logger = logging.getLogger(__name__)

# 内嵌的公钥（用于验证授权文件签名）
PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAn3jtt6WLyy/mllwnJt6A
oCGL08qsi19rlbp3lkR1U3mB3XThkDdKrpUl9LwVjd8m0EiH1lrtqRqe7IHsWMTC
xZuj/bjIrQPkRuABj6TXnnltLLfgcETLTQ/RGym/fYUL/g/1KUK6876IPMT2Cr/2
7aa9vK3PhP8LUJ6lSAIsB1KWPiD7t1xJBTwypKmklswQE2VPPLB/yzbFYy2o1JfB
WF0Qp3UPd0FsO9OjVYSu8ILfr/E3y09e/FjUIQjjHYCrAEVW5IG+KYVxlp0plFjx
+47BA8XH8DIH5VFcByaW4dqgJtYEoRS2VHV+wqT9SxX7QTBZdanJN+shPh0/DPBn
LQIDAQAB
-----END PUBLIC KEY-----"""

# 授权文件路径
LICENSE_FILE_PATH = Path(__file__).resolve().parents[3] / "storage" / "license.dat"


class LicenseValidator:
    """授权文件验证器"""

    def __init__(self, license_path: Path | None = None):
        self.license_path = license_path or LICENSE_FILE_PATH
        self._public_key = None
        self._cached_license: LicenseInfo | None = None
        self._last_validation_result: LicenseValidationResult | None = None
        # 缓存对应的授权文件签名 (mtime_ns, size)；文件一变即失效
        self._cached_signature: tuple[int, int] | None = None

    def _load_public_key(self):
        """加载公钥"""
        if self._public_key is None:
            self._public_key = serialization.load_pem_public_key(PUBLIC_KEY_PEM)
        return self._public_key

    def _file_signature(self) -> tuple[int, int] | None:
        """授权文件的 (mtime_ns, size)；文件不存在时返回 None。"""
        try:
            stat = self.license_path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def validate(self, force: bool = False) -> LicenseValidationResult:
        """
        验证授权文件

        Args:
            force: 强制重新验证，忽略缓存

        缓存与授权文件的 (mtime_ns, size) 绑定：文件被替换、删除或改名后，
        下一次调用会立即重新读取磁盘，不再沿用旧结果。
        """
        signature = self._file_signature()

        if (
            not force
            and self._last_validation_result is not None
            and signature == self._cached_signature
        ):
            return self._last_validation_result

        result = self._validate_file()
        self._last_validation_result = result
        self._cached_signature = signature
        self._cached_license = result.license_info if result.status == LicenseStatus.VALID else None
        return result

    def _validate_file(self) -> LicenseValidationResult:
        """真实读取磁盘并校验（不写缓存）。"""
        # 1. 检查文件是否存在
        if not self.license_path.exists():
            logger.warning("授权校验失败: 授权文件不存在 (%s)", self.license_path)
            return LicenseValidationResult(
                status=LicenseStatus.NOT_FOUND,
                error_message="授权文件不存在，请获取授权"
            )

        try:
            # 2. 读取文件
            data = self.license_path.read_bytes()

            # 3. 解析文件结构
            if len(data) < 10:
                logger.warning("授权校验失败: 文件长度异常 (%s bytes)", len(data))
                return LicenseValidationResult(
                    status=LicenseStatus.INVALID_FORMAT,
                    error_message="授权文件格式错误"
                )

            # 解析头部
            offset = 0
            magic = data[offset:offset+4]
            if magic != b"RLEC":
                logger.warning("授权校验失败: 魔数不正确 (%r)", magic)
                return LicenseValidationResult(
                    status=LicenseStatus.INVALID_FORMAT,
                    error_message="无效的授权文件"
                )
            offset += 4

            version = data[offset]
            offset += 1

            data_len = struct.unpack('>I', data[offset:offset+4])[0]
            offset += 4

            # 提取数据和签名
            data_json = data[offset:offset+data_len]
            signature = data[offset+data_len:]

            # 4. 验证签名（核心安全步骤）
            if not self._verify_signature(data_json, signature):
                logger.warning("授权校验失败: 签名验证不通过 (%s)", self.license_path)
                return LicenseValidationResult(
                    status=LicenseStatus.TAMPERED,
                    error_message="授权文件签名验证失败，文件可能被篡改"
                )

            # 5. 解析授权数据
            license_data = json.loads(data_json)
            license_info = LicenseInfo(
                machine_fingerprint=license_data["machine_fingerprint"],
                region_code=license_data["region_code"],
                region_name=license_data.get("region_name", ""),
                issued_at=datetime.fromtimestamp(license_data["issued_at"]),
                expires_at=datetime.fromtimestamp(license_data["expires_at"]) if license_data.get("expires_at") else None,
                version=license_data.get("version", 1),
                features=license_data.get("features", []),
            )

            # 6. 验证机器码
            current_fingerprint = get_machine_fingerprint()
            if license_info.machine_fingerprint != current_fingerprint:
                logger.warning(
                    "授权校验失败: 机器码不匹配 (授权文件=%s 本机=%s)",
                    license_info.machine_fingerprint,
                    current_fingerprint,
                )
                return LicenseValidationResult(
                    status=LicenseStatus.MACHINE_MISMATCH,
                    error_message="授权文件与当前服务器不匹配"
                )

            # 7. 验证是否过期
            if license_info.expires_at and license_info.expires_at < datetime.now():
                logger.warning("授权校验失败: 授权已过期 (%s)", license_info.expires_at)
                return LicenseValidationResult(
                    status=LicenseStatus.EXPIRED,
                    error_message="授权已过期，请续期"
                )

            # 8. 验证通过
            logger.info(
                "授权校验通过: %s (%s) 有效期至 %s",
                license_info.region_name,
                license_info.region_code,
                license_info.expires_at.strftime("%Y-%m-%d %H:%M:%S") if license_info.expires_at else "永久",
            )
            return LicenseValidationResult(
                status=LicenseStatus.VALID,
                license_info=license_info
            )

        except Exception as e:
            logger.exception("授权文件解析失败")
            return LicenseValidationResult(
                status=LicenseStatus.INVALID_FORMAT,
                error_message=f"授权文件解析错误: {str(e)}"
            )

    def _verify_signature(self, data_json: bytes, signature: bytes) -> bool:
        """验证RSA签名"""
        try:
            public_key = self._load_public_key()
            data_hash = hashlib.sha256(data_json).digest()

            public_key.verify(
                signature,
                data_hash,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except InvalidSignature:
            return False
        except Exception as e:
            logger.exception("签名验证异常")
            return False

    def get_authorized_region_code(self) -> str | None:
        """获取授权的区域码（供拦截器使用）"""
        result = self.validate()
        if result.status != LicenseStatus.VALID:
            return None
        return result.license_info.region_code

    def get_license_info(self) -> LicenseInfo | None:
        """获取授权信息"""
        result = self.validate()
        if result.status != LicenseStatus.VALID:
            return None
        return result.license_info

    def is_valid(self) -> bool:
        """检查授权是否有效"""
        return self.validate().status == LicenseStatus.VALID

    def reload(self) -> LicenseValidationResult:
        """清除缓存并重新验证授权文件（同时重新探测硬件信息）。"""
        self._cached_license = None
        self._last_validation_result = None
        self._cached_signature = None
        clear_machine_fingerprint_cache()
        return self.validate(force=True)

    def get_status_message(self) -> str:
        """获取状态消息"""
        result = self.validate()
        if result.status == LicenseStatus.VALID:
            info = result.license_info
            return f"授权有效 - {info.region_name} ({info.region_code})"
        else:
            return result.error_message


# 全局实例
license_validator = LicenseValidator()
