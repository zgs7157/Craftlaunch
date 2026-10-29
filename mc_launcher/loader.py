# -*- coding: utf-8 -*-
"""模组加载器安装：Fabric / Forge。

流程：拉取官方元数据 → 下载官方安装器 jar → 用本机 Java 无头安装到游戏目录。
安装成功后会在 <游戏目录>/versions 下生成新版本（如 1.21.1-fabric、1.21.1-forge）。

说明：
- Fabric 安装器支持 -dir 指定任意游戏目录；
- Forge 安装器装到其默认目录（%APPDATA%\\.minecraft，与官方启动器一致）；
  若用户游戏目录不是默认目录，会在日志中明确提示。
- NeoForge 官方 maven（maven.neoforged.net）在部分网络环境不可达，暂不提供。
"""
import os
import re
import subprocess

from . import network
from . import launch as launch_mod

# 可用加载器：id -> 展示名
LOADER_CHOICES = [("fabric", "Fabric"), ("forge", "Forge")]

_FABRIC_LOADER_URL = "https://meta.fabricmc.net/v2/versions/loader/%s"
_FABRIC_INSTALLER_URL = "https://meta.fabricmc.net/v2/versions/installer"
_FORGE_METADATA_URL = "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"
_FORGE_INSTALLER_URL = "https://maven.minecraftforge.net/net/minecraftforge/forge/%s/forge-%s-installer.jar"


def available_loaders():
    """返回当前可用的加载器列表 [(id, 名称)]。"""
    return list(LOADER_CHOICES)


def fabric_meta(mc_version, log=None):
    """获取 Fabric 最新稳定 loader 版本与安装器下载地址。"""
    log = log or (lambda msg: None)
    loaders = network.fetch_json(_FABRIC_LOADER_URL % mc_version, mirror_mode="mojang")
    if not loaders:
        raise RuntimeError("Fabric 元数据为空，该版本可能不受支持：%s" % mc_version)
    entry = next((e for e in loaders if (e.get("loader") or {}).get("stable")), loaders[0])
    loader_info = entry.get("loader") or {}
    installers = network.fetch_json(_FABRIC_INSTALLER_URL, mirror_mode="mojang")
    inst = installers[0] if installers else None
    if not inst or not inst.get("url") or not loader_info.get("version"):
        raise RuntimeError("无法获取 Fabric 安装器/加载器信息")
    log("Fabric: loader %s，安装器 %s" % (loader_info["version"], inst.get("version")))
    return {"loader_version": loader_info["version"],
            "installer_url": inst.get("url"),
            "installer_version": inst.get("version")}


def forge_meta(mc_version, log=None):
    """从 Maven 元数据中找到该 MC 版本最新的 Forge 构建，返回安装器地址。"""
    log = log or (lambda msg: None)
    xml = network.fetch_text(_FORGE_METADATA_URL, mirror_mode="mojang")
    versions = re.findall(r"<version>([^<]+)</version>", xml)
    prefix = mc_version + "-"
    builds = [v for v in versions if v.startswith(prefix)]
    if not builds:
        raise RuntimeError("Maven 上找不到 %s 的 Forge 构建（该版本可能不受 Forge 支持）" % mc_version)

    def _build_key(v):
        try:
            return int(v[len(prefix):].split("-")[0])
        except ValueError:
            return 0
    vid = max(builds, key=_build_key)
    url = _FORGE_INSTALLER_URL % (vid, vid)
    log("Forge: 选定构建 %s" % vid)
    return {"build_id": vid, "installer_url": url, "installer_version": vid}


def _pick_java(min_major, log=None):
    """挑一个不小于 min_major 的 Java（取最大的可用版本，安装器对高版本兼容）。"""
    log = log or (lambda msg: None)
    found = launch_mod.discover_java()
    ok = {exe: m for exe, m in found.items() if m >= min_major}
    if not ok:
        raise RuntimeError("未找到满足要求的 Java（需要 >= %d），请先安装 JDK" % min_major)
    exe = max(ok, key=ok.get)
    log("使用 Java %d：%s" % (ok[exe], exe))
    return exe


def download_installer(kind, meta, cache_dir, log=None, progress_cb=None):
    """下载安装器到缓存目录（已存在则跳过）。返回本地路径。"""
    log = log or (lambda msg: None)
    os.makedirs(cache_dir, exist_ok=True)
    name = "%s-installer.jar" % kind
    dest = os.path.join(cache_dir, name)
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        log("安装器已缓存：%s" % dest)
        return dest
    log("正在下载 %s 安装器…" % kind)

    def cb(path, n):
        if progress_cb:
            progress_cb(path, n)
    network.download_file(meta["installer_url"], dest, mirror_mode="mojang",
                          progress_cb=cb)
    log("安装器下载完成：%s" % dest)
    return dest


def _run(cmd, game_dir, log):
    """运行安装器并实时把输出计入日志。返回 (退出码, 输出全文)。"""
    log("执行：%s" % " ".join('"%s"' % a if " " in a else a for a in cmd))
    lines = []
    proc = subprocess.Popen(cmd, cwd=game_dir, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            lines.append(line)
            log(line)
    code = proc.wait()
    return code, "\n".join(lines)


def _installed_version_ids(game_dir):
    """当前 <游戏目录>/versions 下已有 JSON 的版本 id 集合。"""
    vdir = os.path.join(game_dir, "versions")
    out = set()
    if os.path.isdir(vdir):
        for name in os.listdir(vdir):
            if os.path.isfile(os.path.join(vdir, name, "%s.json" % name)):
                out.add(name)
    return out


def install_fabric(mc_version, game_dir, cache_dir, log=None, progress_cb=None):
    """安装 Fabric 加载器，返回新版本 id（命名随安装器版本而定，如 fabric-loader-0.19.5-1.21.1）。"""
    log = log or (lambda msg: None)
    meta = fabric_meta(mc_version, log)
    installer = download_installer("fabric", meta, cache_dir, log, progress_cb)
    java = _pick_java(8, log)
    before = _installed_version_ids(game_dir)
    cmd = [java, "-jar", installer, "client", "-mcversion", mc_version,
           "-loader", meta["loader_version"], "-dir", game_dir, "-noprofile"]
    code, output = _run(cmd, game_dir, log)
    after = _installed_version_ids(game_dir)
    new_ids = sorted(after - before)
    if code != 0 or not new_ids:
        raise RuntimeError("Fabric 安装失败（退出码 %d）。输出末尾：\n%s" % (code, output[-1500:]))
    new_id = new_ids[0]
    log("Fabric 安装成功，新版本：%s" % new_id)
    return new_id


def install_forge(mc_version, game_dir, cache_dir, log=None, progress_cb=None):
    """安装 Forge 加载器，返回新版本 id（<mc>-forge）。

    注意：Forge 官方安装器会写到其默认目录 %APPDATA%\\.minecraft，
    与启动器游戏目录不同时会提示（安装仍会完成，只是位置在默认目录）。
    """
    log = log or (lambda msg: None)
    meta = forge_meta(mc_version, log)
    installer = download_installer("forge", meta, cache_dir, log, progress_cb)
    java = _pick_java(17, log)
    import os as _os
    default_dir = _os.path.join(_os.environ.get("APPDATA", _os.path.expanduser("~")), ".minecraft")
    if _os.path.normcase(_os.path.abspath(game_dir)) != _os.path.normcase(_os.path.abspath(default_dir)):
        log("提示：Forge 官方安装器只装到默认目录 %s（你当前游戏目录是 %s）。\n"
            "安装完成后如版本出现在「版本管理」中可直接使用；否则请把游戏目录改为默认目录再装。"
            % (default_dir, game_dir))
    cmd = [java, "-jar", installer, "--installClient"]
    code, output = _run(cmd, game_dir, log)
    new_id = "%s-forge" % mc_version
    # Forge 装到默认目录的 versions 下
    check_dir = game_dir if _os.path.normcase(_os.path.abspath(game_dir)) == \
        _os.path.normcase(_os.path.abspath(default_dir)) else default_dir
    if code != 0 or not os.path.isfile(os.path.join(check_dir, "versions", new_id, "%s.json" % new_id)):
        raise RuntimeError("Forge 安装失败（退出码 %d）。输出末尾：\n%s" % (code, output[-1500:]))
    log("Forge 安装成功，新版本：%s" % new_id)
    return new_id


def install(kind, mc_version, game_dir, cache_dir, log=None, progress_cb=None):
    """按加载器类型安装。返回新版本 id。"""
    log = log or (lambda msg: None)
    if kind == "fabric":
        return install_fabric(mc_version, game_dir, cache_dir, log, progress_cb)
    if kind == "forge":
        return install_forge(mc_version, game_dir, cache_dir, log, progress_cb)
    raise ValueError("未知加载器：%s" % kind)
