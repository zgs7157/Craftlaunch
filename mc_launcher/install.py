# -*- coding: utf-8 -*-
"""版本安装：下载游戏 jar、库文件、natives、资源，并做完整性校验。"""
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import network
from .utils import ensure_dir, evaluate_rules, fmt_size, sha1_file

# 允许从 natives jar 中解出的文件扩展名
NATIVE_EXT = {".dll", ".so", ".dylib", ".jnilib", ".cfg"}

# natives 分类器中的 OS 名 -> os.name
_NATIVE_OS_ALIASES = {
    "windows": "windows",
    "linux": "linux",
    "osx": "osx",
    "macos": "osx",
}


def _is_native_classifier(classifier, os_info):
    """新版格式：库名第 4 段是 natives-<os>[-<arch>]，需要按当前系统精确选择。"""
    if not classifier or not classifier.startswith("natives-"):
        return False
    rest = classifier[len("natives-"):]
    if not rest:
        return False
    parts = rest.split("-")
    os_key = _NATIVE_OS_ALIASES.get(parts[0])
    if os_key != os_info["name"]:
        return False
    arch = parts[1] if len(parts) > 1 else None
    if arch is None:
        return os_info["arch"] == "x86_64"
    if arch == "arm64":
        return os_info["arch"] == "arm64"
    if arch in ("x86", "i386", "x86_64"):
        return os_info["arch"] == arch
    if arch == "riscv64":
        return os_info["arch"] == "riscv64"
    return True  # 未知架构后缀：OS 匹配即保留


def _maven_artifact(lib):
    """按 Maven 坐标合成 artifact（用于没有 downloads 字段、只有 name+url 的库，如 Fabric 生成的 JSON）。

    name 形如 group:artifact:version[:classifier]，url 是仓库根目录；
    lib 级自带的 sha1/size（Fabric JSON 有此字段）一并带上。
    """
    name = lib.get("name") or ""
    repo = (lib.get("url") or "").rstrip("/")
    if not name or not repo:
        return None
    parts = name.split(":")
    if len(parts) < 3:
        return None
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) >= 4 and parts[3] else None
    base = group.replace(".", "/") + "/" + artifact + "/" + version + "/"
    fname = artifact + "-" + version + ("-" + classifier if classifier else "") + ".jar"
    return {"path": base + fname,
            "url": repo + "/" + base + fname,
            "sha1": lib.get("sha1"),
            "size": lib.get("size")}


def resolve_libraries(version_json, os_info, features=None):
    """解析版本 JSON 的 libraries，返回 (classpath 库列表, natives 列表)。

    每条记录: {"path": 相对路径, "url": ..., "sha1": ..., "size": ...}
    """
    features = features or {}
    jars, natives = [], []

    def _append(artifact, kind):
        if not artifact or not isinstance(artifact, dict):
            return
        rec = {
            "path": artifact.get("path") or "",
            "url": artifact.get("url") or "",
            "sha1": artifact.get("sha1"),
            "size": artifact.get("size"),
        }
        if rec["path"] and rec["url"]:
            (natives if kind == "native" else jars).append(rec)

    for lib in version_json.get("libraries", []):
        if not isinstance(lib, dict):
            continue
        if not evaluate_rules(lib.get("rules"), os_info, features):
            continue
        name_parts = (lib.get("name") or "").split(":")
        classifier = name_parts[3] if len(name_parts) >= 4 else None
        downloads = lib.get("downloads", {}) or {}

        # 新版：natives 是名称带分类器的普通库条目（其 artifact 同时进 classpath 与解压）
        if _is_native_classifier(classifier, os_info):
            _append(downloads.get("artifact"), "native")
            jars.append(downloads.get("artifact"))  # 新版需在 classpath 上，供 lwjgl 自行解压
            continue

        # 老版：natives 映射表 + downloads.classifiers（主 artifact 仍需进 classpath）
        natives_map = lib.get("natives") or {}
        if natives_map:
            cls_name = natives_map.get(os_info["natives_key"])
            if cls_name:
                art = (downloads.get("classifiers") or {}).get(cls_name)
                if art:
                    _append(art, "native")

        # 老老版/兜底：只有 classifiers 字典（按规则逐个匹配）
        if not natives_map and downloads.get("classifiers"):
            for cls_name, art in downloads["classifiers"].items():
                if cls_name.startswith("natives-") and _is_native_classifier(cls_name, os_info):
                    if evaluate_rules(art.get("rules"), os_info, features):
                        _append(art, "native")
                    continue

        artifact = downloads.get("artifact")
        if artifact:
            _append(artifact, "jar")
        else:
            # Maven 坐标兜底（Fabric/NeoForge 等加载器生成的 JSON 只有 name+url）
            _append(_maven_artifact(lib), "jar")

    # 过滤掉意外混入的空记录
    jars = [r for r in jars if r and r.get("path") and r.get("url")]
    natives = [r for r in natives if r and r.get("path") and r.get("url")]
    # 去重（同名同路径只保留一份）
    seen, dedup_jars = set(), []
    for r in jars:
        key = r["path"]
        if key not in seen:
            seen.add(key)
            dedup_jars.append(r)
    return dedup_jars, natives


def _artifact_local_path(game_dir, artifact):
    return os.path.join(game_dir, "libraries", artifact["path"].replace("/", os.sep))


class Installer:
    def __init__(self, config, os_info, log=None):
        self.config = config
        self.os_info = os_info
        self.log = log or (lambda msg, *a: None)

    # ---------- 安装 ----------
    def install(self, version_entry, version_json, skip_assets=False,
                skip_libraries=False, force=False, dry_run=False, progress_cb=None):
        """progress_cb(done, total)：用于 GUI 进度条（按文件数计）。"""
        game_dir = self.config.game_dir
        vid = version_entry["id"]
        parent = version_json.get("inheritsFrom")
        ver_dir = os.path.join(game_dir, "versions", vid)
        ensure_dir(ver_dir)
        ensure_dir(os.path.join(game_dir, "libraries"))
        ensure_dir(os.path.join(game_dir, "assets", "objects"))

        jars, natives = resolve_libraries(version_json, self.os_info)
        client = (version_json.get("downloads") or {}).get("client") or {}
        asset_index = version_json.get("assetIndex") or {}
        logging_file = (version_json.get("logging") or {}).get("client", {}).get("file") or {}

        # 继承版本（Fabric/Forge）的客户端 jar 位于父版本目录
        jar_dir = os.path.join(game_dir, "versions", parent) if parent else ver_dir
        plan = {
            "jar": os.path.join(jar_dir, os.path.basename(client.get("path") or "%s.jar" % (parent or vid))),
            "jar_url": client.get("url") or "",
            "jar_sha1": client.get("sha1"),
            "jar_size": client.get("size"),
            "natives_dir": os.path.join(ver_dir, "natives"),
            "libraries": [{"local": _artifact_local_path(game_dir, a), **a} for a in jars],
            "natives": [{"local": _artifact_local_path(game_dir, a), **a} for a in natives],
            "asset_index": asset_index,
            "asset_index_local": os.path.join(game_dir, "assets", "indexes", "%s.json" % asset_index.get("id", "")),
            "logging": logging_file,
            "logging_local": os.path.join(game_dir, "assets", "log_configs", logging_file.get("id", ""))
            if logging_file else "",
        }

        if dry_run:
            return plan

        # 1) 客户端 jar
        if not skip_libraries and plan["jar_url"]:
            self.log("下载客户端: %s" % os.path.basename(plan["jar"]))
            network.download_file(plan["jar_url"], plan["jar"],
                                  sha1=plan["jar_sha1"], size=plan["jar_size"],
                                  mirror_mode=self.config.mirror)

        # 2) 库文件（并行）
        if not skip_libraries:
            self._download_many(plan["libraries"] + plan["natives"], "库文件", progress_cb=progress_cb)

        # 3) natives 解压
        if not skip_libraries:
            self._extract_natives(plan["natives"], plan["natives_dir"], force=force)

        # 4) 资源索引
        if plan["asset_index"] and plan["asset_index"].get("url"):
            self.log("下载资源索引 %s" % plan["asset_index"].get("id"))
            network.download_file(plan["asset_index"]["url"], plan["asset_index_local"],
                                  sha1=plan["asset_index"].get("sha1"),
                                  size=plan["asset_index"].get("size"),
                                  mirror_mode=self.config.mirror)

        # 5) 日志配置（部分版本需要）
        if plan["logging"] and plan["logging"].get("url") and plan["logging_local"]:
            network.download_file(plan["logging"]["url"], plan["logging_local"],
                                  sha1=plan["logging"].get("sha1"),
                                  size=plan["logging"].get("size"),
                                  mirror_mode=self.config.mirror)

        # 6) 资源文件（大头，可跳过）
        if not skip_assets and plan["asset_index_local"] and os.path.isfile(plan["asset_index_local"]):
            self._download_assets(plan["asset_index_local"], progress_cb=progress_cb)

        return plan

    # ---------- 并行下载 ----------
    def _download_many(self, items, label, progress_cb=None):
        todo = []
        for it in items:
            if _file_ok(it["local"], it.get("sha1"), it.get("size")):
                continue
            todo.append(it)
        if not todo:
            self.log("%s：全部已就绪，无需下载" % label)
            return
        total = sum(int(it.get("size") or 0) for it in todo)
        self.log("%s：需要下载 %d 个文件，共 %s" % (label, len(todo), fmt_size(total)))
        done = [0]

        def worker(it):
            network.download_file(it["url"], it["local"], sha1=it.get("sha1"),
                                  size=it.get("size"), mirror_mode=self.config.mirror)
            done[0] += 1
            if progress_cb:
                progress_cb(done[0], len(todo))
            if done[0] % 5 == 0 or done[0] == len(todo):
                self.log("  进度 %d/%d" % (done[0], len(todo)))

        failures = self._run_parallel(worker, todo)
        if failures:
            raise RuntimeError("%s 有 %d 个文件下载失败：%s" % (label, len(failures), failures[0]))

    def _run_parallel(self, worker, items):
        failures = []
        if len(items) == 1:
            try:
                worker(items[0])
            except Exception as exc:  # noqa: BLE001
                failures.append(str(exc))
            return failures
        with ThreadPoolExecutor(max_workers=self.config.threads) as pool:
            futures = {pool.submit(worker, it): it for it in items}
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as exc:  # noqa: BLE001
                    failures.append("%s: %s" % (futures[fut]["path"], exc))
        return failures

    # ---------- natives 解压 ----------
    def _extract_natives(self, natives, natives_dir, force=False):
        if not natives:
            return
        marker = os.path.join(natives_dir, ".natives.marker")
        current = sorted("%s:%s" % (n["path"], n.get("sha1") or "") for n in natives)
        if not force and os.path.isfile(marker):
            try:
                with open(marker, "r", encoding="utf-8") as f:
                    if f.read().splitlines() == current:
                        return
            except OSError:
                pass
        ensure_dir(natives_dir)
        for old in os.listdir(natives_dir):
            p = os.path.join(natives_dir, old)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        self.log("解压 natives 到 %s" % natives_dir)
        for n in natives:
            if not os.path.isfile(n["local"]):
                self.log("  警告：natives 缺失 %s" % n["path"])
                continue
            self._extract_one(n["local"], natives_dir)
        try:
            with open(marker, "w", encoding="utf-8") as f:
                f.write("\n".join(current))
        except OSError:
            pass

    @staticmethod
    def _extract_one(jar_path, natives_dir):
        try:
            with zipfile.ZipFile(jar_path) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename.replace("\\", "/")
                    if name.startswith("META-INF/") or "/" in name:
                        continue
                    if not name.lower().endswith(tuple(NATIVE_EXT)):
                        continue
                    target = os.path.normpath(os.path.join(natives_dir, name))
                    if not target.startswith(os.path.normpath(natives_dir) + os.sep):
                        continue  # zip-slip 防护
                    with zf.open(info) as src, open(target, "wb") as dst:
                        while True:
                            block = src.read(65536)
                            if not block:
                                break
                            dst.write(block)
        except zipfile.BadZipFile:
            self._log_warn("  警告：%s 不是有效 zip，跳过" % jar_path)

    def _log_warn(self, msg):
        self.log(msg)

    # ---------- 资源文件 ----------
    def _download_assets(self, index_local, progress_cb=None):
        import json
        with open(index_local, "r", encoding="utf-8") as f:
            index = json.load(f)
        objects = index.get("objects", {})
        if not objects:
            self.log("资源索引为空，跳过")
            return
        game_dir = self.config.game_dir
        total_size = sum(int(o.get("size") or 0) for o in objects.values())
        todo = []
        for key, obj in objects.items():
            h = obj.get("hash", "")
            if len(h) < 2:
                continue
            rel = os.path.join("objects", h[:2], h)
            local = os.path.join(game_dir, "assets", rel)
            if _file_ok(local, h, obj.get("size")):
                continue
            todo.append((key, h, obj.get("size"), local))

        if not todo:
            self.log("资源文件：全部已就绪")
            return
        self.log("资源文件：需下载 %d 个，共 %s（%d 线程并行）" % (
            len(todo), fmt_size(total_size), self.config.threads))
        done = [0]
        downloaded = [0]
        last_reported = [0]
        lock = __import__("threading").Lock()

        def worker(item):
            key, h, size, local = item
            url = "https://resources.download.minecraft.net/%s/%s" % (h[:2], h)
            network.download_file(url, local, sha1=h, size=size, mirror_mode=self.config.mirror)
            with lock:
                done[0] += 1
                downloaded[0] += int(size or 0)
                if progress_cb:
                    progress_cb(done[0], len(todo))
                if done[0] - last_reported[0] >= 50 or done[0] == len(todo):
                    last_reported[0] = done[0]
                    self.log("  资源进度 %d/%d（%s）" % (done[0], len(todo), fmt_size(downloaded[0])))

        failures = self._run_parallel(worker, todo)
        if failures:
            raise RuntimeError("资源文件有 %d 个下载失败：%s" % (len(failures), failures[0]))

        # 远古版本（pre-1.6）需要把 virtual 文件复制到 resources 目录
        if index.get("map_to_resources"):
            self._map_to_resources(index, game_dir)

    @staticmethod
    def _map_to_resources(index, game_dir):
        from .utils import ensure_dir
        for key, obj in index.get("objects", {}).items():
            if not key.startswith("virtual/"):
                continue
            h = obj.get("hash", "")
            if len(h) < 2:
                continue
            src = os.path.join(game_dir, "assets", "objects", h[:2], h)
            dst = os.path.join(game_dir, "resources", key[len("virtual/"):].replace("/", os.sep))
            if os.path.isfile(src):
                ensure_dir(os.path.dirname(dst))
                import shutil
                try:
                    shutil.copyfile(src, dst)
                except OSError:
                    pass


def _file_ok(local, sha1, size):
    if not os.path.isfile(local) or os.path.getsize(local) == 0:
        return False
    if sha1:
        return sha1_file(local) == sha1
    if size is not None:
        return os.path.getsize(local) == size
    return True
