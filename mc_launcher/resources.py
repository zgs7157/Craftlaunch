# -*- coding: utf-8 -*-
"""资源管理：模组(mods)、光影包(shaderpacks)、资源包(resourcepacks)的本地文件管理。

- 列表/导入/启用停用/删除/打开文件夹
- 启用/停用采用 Minecraft 官方约定：文件名加 `.disabled` 后缀即不加载
"""
import os
import shutil

# 类别 -> 游戏目录下的文件夹名
DIRS = {
    "mods": "mods",
    "shaders": "shaderpacks",
    "resources": "resourcepacks",
}

CATEGORY_LABELS = {"mods": "模组", "shaders": "光影包", "resources": "资源包"}

DISABLED_SUFFIX = ".disabled"


def category_dir(game_dir, kind):
    """返回该类别的目录路径（不创建）。"""
    return os.path.join(game_dir, DIRS[kind])


def ensure_dir(game_dir, kind):
    """确保类别目录存在（如 .minecraft 首次运行时没有这些目录）。"""
    d = category_dir(game_dir, kind)
    os.makedirs(d, exist_ok=True)
    return d


def _human_size(n):
    if n < 0:
        return "-"
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024.0)
    if n < 1024 * 1024 * 1024:
        return "%.1f MB" % (n / 1024.0 / 1024.0)
    return "%.1f GB" % (n / 1024.0 / 1024.0 / 1024.0)


def _entry_size(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def list_items(game_dir, kind):
    """列出某类别目录下的全部条目（文件与子文件夹）。

    返回列表，每项：{name, path, enabled, size, is_dir}，按启用状态和名称排序。
    """
    d = category_dir(game_dir, kind)
    if not os.path.isdir(d):
        return []
    items = []
    for name in sorted(os.listdir(d)):
        if name in (".", ".."):
            continue
        full = os.path.join(d, name)
        enabled = not name.endswith(DISABLED_SUFFIX)
        items.append({
            "name": name,
            "path": full,
            "enabled": enabled,
            "size": _entry_size(full),
            "is_dir": os.path.isdir(full),
        })
    items.sort(key=lambda it: (not it["enabled"], it["name"].lower()))
    return items


def toggle_item(game_dir, kind, name):
    """启用/停用切换（重命名加/去 .disabled 后缀）。返回新文件名。"""
    d = category_dir(game_dir, kind)
    src = os.path.join(d, name)
    if not os.path.exists(src):
        raise FileNotFoundError("文件不存在：%s" % src)
    if name.endswith(DISABLED_SUFFIX):
        new_name = name[: -len(DISABLED_SUFFIX)]
    else:
        new_name = name + DISABLED_SUFFIX
    dst = os.path.join(d, new_name)
    if os.path.exists(dst):
        raise OSError("目标已存在：%s" % new_name)
    os.rename(src, dst)
    return new_name


def remove_item(game_dir, kind, name):
    """删除条目（文件或文件夹）。"""
    d = category_dir(game_dir, kind)
    full = os.path.join(d, name)
    if not os.path.exists(full):
        raise FileNotFoundError("文件不存在：%s" % full)
    if os.path.isdir(full):
        shutil.rmtree(full)
    else:
        os.remove(full)


def import_items(game_dir, kind, src_paths, log=None):
    """把外部文件复制进类别目录。重名条目跳过并报告。返回 (成功数, 跳过数)。"""
    log = log or (lambda msg: None)
    d = ensure_dir(game_dir, kind)
    ok = skipped = 0
    for src in src_paths:
        if not os.path.isfile(src):
            log("跳过（不是文件）：%s" % src)
            skipped += 1
            continue
        name = os.path.basename(src)
        dst = os.path.join(d, name)
        if os.path.exists(dst):
            log("跳过（同名已存在）：%s" % name)
            skipped += 1
            continue
        shutil.copy2(src, dst)
        log("已导入：%s" % name)
        ok += 1
    return ok, skipped


def open_dir(game_dir, kind):
    """在资源管理器中打开类别目录。"""
    d = ensure_dir(game_dir, kind)
    os.startfile(d)
