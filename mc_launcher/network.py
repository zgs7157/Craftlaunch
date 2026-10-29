# -*- coding: utf-8 -*-
"""网络模块：带镜像兜底与重试的下载、JSON 拉取。

镜像策略（config.mirror）：
  auto    —— 先官方源，失败再试 BMCLAPI 镜像
  mojang  —— 只用官方源
  bmclapi —— 先镜像，失败再试官方源
"""
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

from . import __version__

USER_AGENT = "CraftLaunch/%s" % __version__
CONNECT_TIMEOUT = 20
READ_TIMEOUT = 60

# 官方域名 -> BMCLAPI 镜像域名（BMCLAPI 保留相同路径）
_MIRROR_HOST = {
    "piston-meta.mojang.com": "bmclapi2.bangbang93.com",
    "piston-data.mojang.com": "bmclapi2.bangbang93.com",
    "launchermeta.mojang.com": "bmclapi2.bangbang93.com",
    "launcher.mojang.com": "bmclapi2.bangbang93.com",
}


class DownloadError(RuntimeError):
    pass


def mirror_url(url):
    """把官方 URL 转成 BMCLAPI 镜像 URL；无法镜像时返回 None。"""
    parts = urlsplit(url)
    host = (parts.netloc or "").lower()
    if host == "libraries.minecraft.net":
        # 库文件：https://libraries.minecraft.net/<path> -> https://bmclapi2.bangbang93.com/maven/<path>
        return urlunsplit(("https", "bmclapi2.bangbang93.com", "/maven" + parts.path, parts.query, parts.fragment))
    new_host = _MIRROR_HOST.get(host)
    if not new_host:
        return None
    return urlunsplit((parts.scheme, new_host, parts.path, parts.query, parts.fragment))


def _ordered_urls(url, mirror_mode, force_mirror_url=None):
    """按镜像策略返回依次尝试的 URL 列表。"""
    mirror = force_mirror_url if force_mirror_url else mirror_url(url)
    primary, backup = url, mirror
    if mirror_mode == "bmclapi" and backup:
        primary, backup = backup, primary
    elif mirror_mode == "mojang":
        return [url] if url else []
    urls = []
    for u in (primary, backup):
        if u and u not in urls:
            urls.append(u)
    return urls


def _open(url, timeout=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    return urllib.request.urlopen(req, timeout=timeout or READ_TIMEOUT)


def fetch_json(url, mirror_mode="auto", timeout=READ_TIMEOUT, force_mirror_url=None):
    """拉取并解析 JSON，自动重试与镜像兜底。"""
    last_err = None
    for u in _ordered_urls(url, mirror_mode, force_mirror_url):
        for attempt in range(2):
            try:
                with _open(u, timeout) as resp:
                    data = resp.read()
                return json.loads(data.decode("utf-8"))
            except Exception as exc:  # noqa: BLE001 —— 网络错误类型繁多，统一捕获重试
                last_err = exc
    raise DownloadError("下载 JSON 失败: %s（%s）" % (url, last_err))


def fetch_text(url, mirror_mode="auto", timeout=READ_TIMEOUT, force_mirror_url=None):
    """拉取纯文本（如 maven-metadata.xml），自动重试与镜像兜底。"""
    last_err = None
    for u in _ordered_urls(url, mirror_mode, force_mirror_url):
        for attempt in range(2):
            try:
                with _open(u, timeout) as resp:
                    data = resp.read()
                return data.decode("utf-8", "replace")
            except Exception as exc:  # noqa: BLE001
                last_err = exc
    raise DownloadError("下载文本失败: %s（%s）" % (url, last_err))


def download_file(url, dest, sha1=None, size=None, mirror_mode="auto",
                  retries=2, progress_cb=None, force_mirror_url=None):
    """下载单个文件到 dest。

    返回 True=本次实际下载；False=本地已存在且校验通过（跳过）。
    下载到临时文件后改名，避免半成品污染目录；校验失败会重试。
    """
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if _verify_existing(dest, sha1, size):
        return False

    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".dl-", suffix=".part", dir=os.path.dirname(dest) or ".")
    os.close(tmp_fd)
    last_err = None
    try:
        for u in _ordered_urls(url, mirror_mode, force_mirror_url):
            for attempt in range(max(1, retries)):
                try:
                    with _open(u) as resp, open(tmp_path, "wb") as out:
                        while True:
                            block = resp.read(65536)
                            if not block:
                                break
                            out.write(block)
                    if sha1:
                        got = _file_sha1(tmp_path)
                        if got != sha1:
                            raise DownloadError("SHA1 校验失败: %s 期望 %s 实际 %s" % (dest, sha1, got))
                    if size is not None:
                        actual = os.path.getsize(tmp_path)
                        if actual != size:
                            raise DownloadError("大小校验失败: %s 期望 %d 实际 %d" % (dest, size, actual))
                    os.replace(tmp_path, dest)
                    if progress_cb:
                        progress_cb(dest, os.path.getsize(dest))
                    return True
                except Exception as exc:  # noqa: BLE001
                    last_err = exc
                    if progress_cb:
                        progress_cb(dest, -1)
        raise DownloadError("下载失败: %s（%s）" % (url, last_err))
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _verify_existing(dest, sha1, size):
    if not os.path.isfile(dest) or os.path.getsize(dest) == 0:
        return False
    if sha1:
        return _file_sha1(dest) == sha1
    if size is not None:
        return os.path.getsize(dest) == size
    return True


def _file_sha1(path):
    import hashlib
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()
