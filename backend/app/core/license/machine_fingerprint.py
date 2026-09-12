"""
机器码生成模块

基于硬件信息生成唯一机器标识
"""

import hashlib
import platform
import subprocess
import uuid
from pathlib import Path


def get_machine_fingerprint() -> str:
    """
    生成机器指纹（32位MD5）
    
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


def _get_baseboard_serial() -> str:
    """获取主板序列号"""
    try:
        result = subprocess.run(
            ["wmic", "baseboard", "get", "SerialNumber"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        )
        lines = result.stdout.strip().split('\n')
        return lines[1].strip() if len(lines) > 1 else ""
    except:
        return ""


def _get_cpu_id() -> str:
    """获取CPU ID"""
    try:
        result = subprocess.run(
            ["wmic", "cpu", "get", "ProcessorId"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        )
        lines = result.stdout.strip().split('\n')
        return lines[1].strip() if len(lines) > 1 else ""
    except:
        return ""


def _get_disk_serial() -> str:
    """获取系统盘序列号"""
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["wmic", "diskdrive", "where", "DeviceID='\\\\\\\\\\\\.\\\\PHYSICALDRIVE0'", "get", "SerialNumber"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            lines = result.stdout.strip().split('\n')
            return lines[1].strip() if len(lines) > 1 else ""
        else:
            result = subprocess.run(
                ["lsblk", "-no", "SERIAL", "/dev/sda"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip()
    except:
        return ""


def _get_mac_address() -> str:
    """获取MAC地址"""
    mac = uuid.getnode()
    return ':'.join(f'{(mac >> i) & 0xff:02x}' for i in range(0, 48, 8)).upper()


if __name__ == "__main__":
    # 测试生成机器码
    fingerprint = get_machine_fingerprint()
    print(f"当前机器的指纹: {fingerprint}")
