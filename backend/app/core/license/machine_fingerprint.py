"""
机器码生成模块

基于硬件信息生成唯一机器标识

注意：Windows 11 新版本已废弃 wmic 命令，因此本模块在 wmic 失败时
会自动回退到 PowerShell Get-CimInstance 获取硬件信息。
"""

import hashlib
import logging
import platform
import subprocess
import uuid
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


def get_machine_fingerprint() -> str:
    """
    生成机器指纹（32位MD5）。

    硬件信息在进程生命周期内不会变化，但每次读取（wmic 缺失时要回退 PowerShell）
    需要启动 3 个子进程、耗时约 1.5 秒。授权校验会被中间件在每次 API 请求上调用，
    因此这里做进程级缓存，避免重复探测。

    需要强制重新探测硬件时调用 clear_machine_fingerprint_cache()。
    """
    return _compute_machine_fingerprint()


def clear_machine_fingerprint_cache() -> None:
    """清除机器码缓存（硬件变更或需要重新探测时调用）。"""
    _compute_machine_fingerprint.cache_clear()


@lru_cache(maxsize=1)
def _compute_machine_fingerprint() -> str:
    """
    真正执行硬件探测并计算机器指纹。

    组合因素：
    - 主板序列号
    - CPU ID
    - 磁盘序列号（系统盘）
    - MAC地址
    - 主机名
    """
    components = []
    
    # 1. 主板序列号
    components.append(_get_baseboard_serial())
    
    # 2. CPU ID
    components.append(_get_cpu_id())
    
    # 3. 系统盘序列号
    components.append(_get_disk_serial())
    
    # 4. MAC地址（取第一个物理网卡）
    components.append(_get_mac_address())
    
    # 5. 主机名
    components.append(platform.node())
    
    # 组合并哈希
    raw = "|".join(filter(None, components))
    return hashlib.md5(raw.encode()).hexdigest().upper()


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _run_wmic(args: list[str]) -> str:
    """运行 wmic 命令并返回第二行（数据行）。失败返回空字符串。"""
    try:
        result = subprocess.run(
            ["wmic"] + args,
            capture_output=True, text=True, timeout=5,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            return ""
        lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
        # 第一行是表头，第二行是数据
        return lines[1] if len(lines) > 1 else ""
    except FileNotFoundError:
        # wmic 不存在
        return ""
    except Exception as e:
        logger.debug("wmic %s failed: %s", args, e)
        return ""


def _run_powershell_cim(wmi_class: str, property_name: str) -> str:
    """
    通过 PowerShell Get-CimInstance 获取硬件信息。
    回退方案，当 wmic 不可用时使用。
    """
    ps_cmd = (
        f"(Get-CimInstance {wmi_class} | "
        f"Select-Object -ExpandProperty {property_name}).Trim()"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            # 可能有多行，取第一行非空的
            for line in value.splitlines():
                line = line.strip()
                if line:
                    return line
        return ""
    except Exception as e:
        logger.debug("PowerShell CIM %s.%s failed: %s", wmi_class, property_name, e)
        return ""


def _get_hw_info(wmic_args: list[str], ps_class: str, ps_prop: str) -> str:
    """先尝试 wmic，失败则回退到 PowerShell Get-CimInstance。"""
    value = _run_wmic(wmic_args)
    if value:
        return value
    logger.info("wmic unavailable, falling back to PowerShell for %s.%s", ps_class, ps_prop)
    return _run_powershell_cim(ps_class, ps_prop)


# ---------------------------------------------------------------------------
# 各硬件信息获取函数
# ---------------------------------------------------------------------------

def _get_baseboard_serial() -> str:
    """获取主板序列号"""
    return _get_hw_info(
        ["baseboard", "get", "SerialNumber"],
        "Win32_BaseBoard",
        "SerialNumber",
    )


def _get_cpu_id() -> str:
    """获取CPU ID"""
    return _get_hw_info(
        ["cpu", "get", "ProcessorId"],
        "Win32_Processor",
        "ProcessorId",
    )


def _get_disk_serial() -> str:
    """获取系统盘序列号"""
    if IS_WINDOWS:
        return _get_hw_info(
            ["diskdrive", "where", "DeviceID='\\\\\\\\\\\\.\\\\PHYSICALDRIVE0'", "get", "SerialNumber"],
            "Win32_DiskDrive",
            "SerialNumber",
        )
    else:
        try:
            result = subprocess.run(
                ["lsblk", "-no", "SERIAL", "/dev/sda"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return ""


def _get_mac_address() -> str:
    """获取MAC地址"""
    mac = uuid.getnode()
    return ':'.join(f'{(mac >> i) & 0xff:02x}' for i in range(0, 48, 8)).upper()


if __name__ == "__main__":
    # 测试生成机器码
    fingerprint = get_machine_fingerprint()
    print(f"当前机器的指纹: {fingerprint}")
