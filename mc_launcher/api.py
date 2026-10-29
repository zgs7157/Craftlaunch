# -*- coding: utf-8 -*-
"""Mojang 数据源：版本清单、版本 JSON、资源索引的获取与缓存。"""
import json
import os
import time

from . import network

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


def get_manifest(config, launcher_dir, force=False):
    """获取版本清单（含缓存，默认 30 分钟过期）。"""
    cache_dir = os.path.join(launcher_dir, ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "version_manifest.json")
    ttl = 0
    try:
        ttl = int(config.get("manifest_cache_ttl_minutes", 30)) * 60
    except (TypeError, ValueError):
        ttl = 1800
    if not force and os.path.isfile(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < ttl:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data and "versions" in data:
                return data
    data = network.fetch_json(MANIFEST_URL, mirror_mode=config.mirror)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def resolve_version_entry(manifest, version):
    """把用户输入的版本号解析为清单条目（支持 latest / latest-release / latest-snapshot）。"""
    v = (version or "").strip()
    if v in ("latest", "latest-release"):
        vid = manifest.get("latest", {}).get("release")
        if vid:
            v = vid
    elif v == "latest-snapshot":
        vid = manifest.get("latest", {}).get("snapshot")
        if vid:
            v = vid
    for entry in manifest.get("versions", []):
        if entry.get("id") == v:
            return entry
    raise LookupError("找不到版本 %r。可用 `launcher.py versions --type all` 查看全部版本。" % version)


def get_version_json(config, version_entry):
    """获取版本 JSON 并缓存到 <游戏目录>/versions/<id>/<id>.json。"""
    vid = version_entry["id"]
    game_dir = config.game_dir
    ver_dir = os.path.join(game_dir, "versions", vid)
    os.makedirs(ver_dir, exist_ok=True)
    cache = os.path.join(ver_dir, "%s.json" % vid)
    if os.path.isfile(cache):
        try:
            with open(cache, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    data = network.fetch_json(version_entry["url"], mirror_mode=config.mirror)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def get_asset_index(config, asset_index):
    """下载资源索引到 <游戏目录>/assets/indexes/<id>.json，返回其 JSON。"""
    idx_id = asset_index["id"]
    game_dir = config.game_dir
    dest = os.path.join(game_dir, "assets", "indexes", "%s.json" % idx_id)
    network.download_file(
        asset_index["url"], dest,
        sha1=asset_index.get("sha1"), size=asset_index.get("size"),
        mirror_mode=config.mirror,
    )
    with open(dest, "r", encoding="utf-8") as f:
        return json.load(f)


def version_required_java(version_json):
    """版本要求的 Java 主版本号（缺省按 8）。"""
    try:
        return int(version_json.get("javaVersion", {}).get("majorVersion", 8))
    except (TypeError, ValueError):
        return 8


def local_installed_versions(game_dir):
    """扫描 <游戏目录>/versions，返回本机已装的版本条目（含加载器版本，如 1.21.1-fabric）。"""
    out = []
    vdir = os.path.join(game_dir, "versions")
    if not os.path.isdir(vdir):
        return out
    for name in sorted(os.listdir(vdir)):
        if os.path.isfile(os.path.join(vdir, name, "%s.json" % name)):
            out.append({"id": name, "type": "本地", "url": None,
                        "releaseTime": os.path.getmtime(os.path.join(vdir, name, "%s.json" % name))})
    return out


def load_local_version_json(game_dir, version):
    """读取本地版本 JSON（不存在返回 None），用于加载器生成的本地版本。"""
    vid = (version or "").strip()
    p = os.path.join(game_dir, "versions", vid, "%s.json" % vid)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def resolve_any_version(config, manifest, version):
    """解析版本：官方清单优先，找不到时回退到本地已装版本（如 1.21.1-fabric）。

    返回 (entry, version_json)。
    """
    try:
        entry = resolve_version_entry(manifest, version)
        return entry, get_version_json(config, entry)
    except LookupError:
        vid = (version or "").strip()
        vj = load_local_version_json(config.game_dir, vid)
        if vj is None:
            raise LookupError("找不到版本 %r（官方清单和本地目录都没有）" % version)
        return {"id": vid, "type": "本地", "url": None,
                "releaseTime": os.path.getmtime(
                    os.path.join(config.game_dir, "versions", vid, "%s.json" % vid))}, vj
