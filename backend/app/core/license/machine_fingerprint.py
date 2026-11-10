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
    return _run_powershell(ps_cmd)


def _run_powershell(ps_cmd: str) -> str:
    """执行 PowerShell 命令并返回去掉首尾空白的输出；失败返回空字符串。"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return ""
    except Exception as e:
        logger.debug("PowerShell command failed: %s", e)
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
    """获取系统盘序列号。

    ⛔ 必须锁定「系统盘」，不能取 Win32_DiskDrive 的第一条序列号：
    多块硬盘 / 插拔 USB 移动盘时 WMI 枚举顺序会变，机器码随之漂移，
    表现为授权突然变「机器码不匹配」（2026-11-09 事故：USB 盘排到第一）。
    - 优先 Get-Disk 的 IsSystem（系统盘，Win8+）
    - 回退排除 USB 后按 Index 取第一块（至少不受外接盘插拔影响）
    - 最后才走原 wmic PHYSICALDRIVE0 路径（同时修正 DeviceID 转义）
    """
    if IS_WINDOWS:
        system_serial = _run_powershell(
            "Get-Disk | Where-Object { $_.IsSystem } | "
            "Select-Object -First 1 -ExpandProperty SerialNumber"
        )
        if system_serial:
            return system_serial.splitlines()[0].strip()
        fallback_serial = _run_powershell(
            "Get-CimInstance Win32_DiskDrive | "
            "Where-Object { $_.InterfaceType -ne 'USB' } | "
            "Sort-Object Index | Select-Object -First 1 -ExpandProperty SerialNumber"
        )
        if fallback_serial:
            return fallback_serial.splitlines()[0].strip()
        return _get_hw_info(
            ["diskdrive", "where", "DeviceID='\\\\.\\PHYSICALDRIVE0'", "get", "SerialNumber"],
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


# 排除规则：蓝牙 PAN、USB 外接网卡（扩展坞/USB 转接）、虚拟网卡。
# 这些设备的插拔/枚举顺序会变化，若被选中会导致机器码漂移（2026-10-09、2026-10-16 两次事故）。
_MAC_EXCLUDE_PATTERN = (
    r"Bluetooth|USB|Virtual|VMware|Hyper-V|VBox|Loopback|TAP|TUN|VPN|WAN Miniport"
)


def _normalize_mac(raw: str) -> str:
    """把任意分隔符的 MAC 归一化为 12 位大写十六进制（无分隔符）。非法返回空串。"""
    hex_part = "".join(c for c in raw if c.isalnum())
    if len(hex_part) != 12 or not all(c in "0123456789abcdefABCDEF" for c in hex_part):
        return ""
    return hex_part.upper()


def _list_candidate_macs() -> list[str]:
    """
    枚举"稳定"物理网卡的 MAC（归一化 12 位大写十六进制）。

    确定性选择规则：物理网卡、排除蓝牙/USB/虚拟，剩余候选按 MAC 排序取最小。
    主板内置网卡与 Wi-Fi 始终在列，不受扩展坞插拔影响。
    """
    macs: list[str] = []

    if IS_WINDOWS:
        # 首选 PowerShell Get-NetAdapter -Physical（Win8+/Server2012+）
        ps_cmd = (
            "$ErrorActionPreference='SilentlyContinue';"
            "Get-NetAdapter -Physical | "
            f"Where-Object {{ $_.Status -ne 'Disabled' -and $_.InterfaceDescription -notmatch '{_MAC_EXCLUDE_PATTERN}' }} | "
            "Select-Object -ExpandProperty MacAddress"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=15,
                creationflags=CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    mac = _normalize_mac(line.strip())
                    if mac:
                        macs.append(mac)
        except Exception as e:
            logger.debug("Get-NetAdapter failed: %s", e)

        # 回退 wmic（老系统）
        if not macs:
            try:
                result = subprocess.run(
                    ["wmic", "path", "Win32_NetworkAdapter", "where",
                     "PhysicalAdapter=True AND NetConnectionID IS NOT NULL"
                     " AND Description NOT LIKE '%Bluetooth%'"
                     " AND Description NOT LIKE '%USB%'"
                     " AND Description NOT LIKE '%Virtual%'"
                     " get MACAddress"],
                    capture_output=True, text=True, timeout=10,
                    creationflags=CREATE_NO_WINDOW,
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().splitlines()[1:]:
                        mac = _normalize_mac(line.strip())
                        if mac:
                            macs.append(mac)
            except Exception as e:
                logger.debug("wmic nic failed: %s", e)
    else:
        # Linux/macOS：读 /sys/class/net，排除虚拟接口
        try:
            net_dir = Path("/sys/class/net")
            if net_dir.is_dir():
                virtual_prefixes = ("lo", "docker", "veth", "br-", "vmnet", "tun", "tap", "virbr")
                for iface in net_dir.iterdir():
                    if iface.name.startswith(virtual_prefixes):
                        continue
                    mac = _normalize_mac((iface / "address").read_text().strip())
                    # 全 0 或组播位（第二位 hex 是奇数）的不算单播物理地址
                    if mac and mac != "000000000000" and int(mac[1], 16) % 2 == 0:
                        macs.append(mac)
        except Exception as e:
            logger.debug("list /sys/class/net failed: %s", e)

    return sorted(set(macs))


def _get_mac_address() -> str:
    """
    获取 MAC 地址（确定性）。

    旧实现用 uuid.getnode()，它从系统枚举的网卡里不确定地返回一个，
    扩展坞插拔/蓝牙 PAN/虚拟网卡都会让结果漂移（已两次造成 machine_mismatch）。
    现改为：物理网卡排除蓝牙/USB/虚拟后按 MAC 取最小；全部失败才退回 uuid.getnode()。
    """
    macs = _list_candidate_macs()
    if macs:
        chosen = macs[0]
        return "-".join(chosen[i:i + 2] for i in range(0, 12, 2))
    # 兜底：探测不到物理网卡时退回旧行为（不保证稳定）
    logger.warning("no stable physical NIC found, falling back to uuid.getnode()")
    mac = uuid.getnode()
    return ':'.join(f'{(mac >> i) & 0xff:02x}' for i in range(0, 48, 8)).upper()


if __name__ == "__main__":
    # 测试生成机器码
    fingerprint = get_machine_fingerprint()
    print(f"当前机器的指纹: {fingerprint}")
