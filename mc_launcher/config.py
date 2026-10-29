# -*- coding: utf-8 -*-
"""配置文件读写。首次运行自动生成 config.json（位于启动器根目录）。"""
import json
import os

from .utils import expand_env

CONFIG_NAME = "config.json"

DEFAULTS = {
    "game_dir": "%APPDATA%\\.minecraft",   # 游戏数据目录（版本/库/资源都放这里）
    "username": "Steve",                    # 离线模式玩家名
    "java_path": "",                        # 留空则自动发现系统 Java
    "min_memory_mb": 1024,                  # 最小堆内存
    "max_memory_mb": 2048,                  # 最大堆内存
    "resolution_width": 854,                # 窗口宽度
    "resolution_height": 480,               # 窗口高度
    "download_threads": 8,                  # 并行下载线程数
    "mirror": "auto",                       # auto=官方优先,镜像兜底 / mojang=仅官方 / bmclapi=镜像优先
    "launcher_name": "CraftLaunch",
    "launcher_version": "1.0.0",
    "manifest_cache_ttl_minutes": 30,       # 版本清单缓存时长
}


class Config:
    def __init__(self, launcher_dir):
        self.launcher_dir = launcher_dir
        self.path = os.path.join(launcher_dir, CONFIG_NAME)
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    user = json.load(f)
                if isinstance(user, dict):
                    self.data.update(user)
            except (OSError, ValueError) as exc:
                raise RuntimeError("配置文件 %s 无法解析: %s" % (self.path, exc))
        else:
            self.save()

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value, save=True):
        self.data[key] = value
        if save:
            self.save()

    @property
    def game_dir(self):
        return expand_env(self.get("game_dir", DEFAULTS["game_dir"]))

    @property
    def mirror(self):
        m = str(self.get("mirror", "auto")).strip().lower()
        return m if m in ("auto", "mojang", "bmclapi") else "auto"

    @property
    def threads(self):
        try:
            n = int(self.get("download_threads", 8))
            return max(1, min(n, 32))
        except (TypeError, ValueError):
            return 8
