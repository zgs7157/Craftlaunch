# -*- coding: utf-8 -*-
"""通用工具：系统信息、规则求值、离线 UUID、SHA1、路径展开等。"""
import hashlib
import os
import platform
import re
import uuid

# Java 上报的 os.arch -> Minecraft 版本 JSON 中使用的 arch 名称
ARCH_MAP = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "x86": "x86",
    "i386": "x86",
    "i686": "x86",
    "arm": "arm32",
    "arm64": "arm64",
    "aarch64": "arm64",
    "riscv64": "riscv64",
}

# 平台 system() -> 版本 JSON 中使用的 os.name
OS_NAME_MAP = {
    "Windows": "windows",
    "Darwin": "osx",
    "Linux": "linux",
}


def get_os_info():
    """返回当前平台的 os 信息字典（与 Minecraft 版本 JSON 的 rules 对齐）。"""
    mach = (platform.machine() or "").lower()
    arch = ARCH_MAP.get(mach, mach or "x86_64")
    system = platform.system()
    name = OS_NAME_MAP.get(system, (system or "unknown").lower())
    return {
        "name": name,            # windows / osx / linux
        "arch": arch,            # x86_64 / x86 / arm64 ...
        "natives_key": name,     # 老格式 natives 映射表的键
        "version": platform.version() or "",
    }


def evaluate_rules(rules, os_info, features=None):
    """按 Minecraft 版本 JSON 的 rules 求值，返回该库/参数是否应保留。

    无 rules 时返回 True；rules 存在时按“最后一个命中的规则”决定。
    features 形如 {"is_demo_user": False, "has_custom_resolution": False}。
    """
    if not rules:
        return True
    features = features or {}
    allowed = False
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        action = rule.get("action", "allow")
        applies = True
        os_rule = rule.get("os")
        if isinstance(os_rule, dict):
            if os_rule.get("name") and os_rule["name"] != os_info["name"]:
                applies = False
            if os_rule.get("arch") and os_rule["arch"] != os_info["arch"]:
                applies = False
            if os_rule.get("version") and not re.search(os_rule["version"], os_info.get("version", "")):
                applies = False
        feat = rule.get("features")
        if isinstance(feat, dict):
            for key, val in feat.items():
                if features.get(key) is not val:
                    applies = False
        if applies:
            allowed = (action == "allow")
    return allowed


def offline_uuid(username):
    """生成与官方离线模式一致的 UUID（OfflinePlayer:<name> 的 MD5）。"""
    digest = bytearray(hashlib.md5(("OfflinePlayer:" + username).encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(digest)))


def sha1_file(path, chunk_size=1024 * 1024):
    """流式计算文件的 SHA1，文件不存在返回 None。"""
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            while True:
                block = f.read(chunk_size)
                if not block:
                    break
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()


def expand_env(value):
    """展开 %VAR% / ~ 等环境变量写法。"""
    if not isinstance(value, str):
        return value
    return os.path.expandvars(os.path.expanduser(value))


def fmt_size(num):
    """把字节数格式化为人类可读的字符串。"""
    try:
        num = float(num)
    except (TypeError, ValueError):
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            if unit == "B":
                return "%d%s" % (int(num), unit)
            return "%.1f%s" % (num, unit)
        num /= 1024.0
    return "?"


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path
