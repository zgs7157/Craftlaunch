# -*- coding: utf-8 -*-
"""启动模块：Java 自动发现、启动命令构建（兼容新旧格式）、进程拉起。"""
import glob
import os
import re
import shutil
import subprocess
import uuid as uuid_mod

from . import APP_NAME, __version__
from .install import resolve_libraries
from .utils import ensure_dir, evaluate_rules, offline_uuid

# 常见 JDK 安装位置（用于自动发现）
_JAVA_ROOTS = [
    r"C:\Program Files\Java",
    r"C:\Program Files\Eclipse Adoptium",
    r"C:\Program Files\Microsoft",
    r"C:\Program Files\Zulu",
    r"C:\Program Files\Amazon Corretto",
    r"C:\Program Files\BellSoft",
    r"C:\Program Files\AdoptOpenJDK",
    r"C:\Program Files (x86)\Java",
]
_JAVA_USER_ROOTS = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
]


def java_major(java_exe):
    """运行 java -version 解析主版本号；失败返回 None。"""
    try:
        proc = subprocess.run(
            [java_exe, "-version"], capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    m = re.search(r'version\s+"([0-9]+)(?:\.([0-9]+))?', text)
    if not m:
        return None
    first, second = int(m.group(1)), int(m.group(2) or 0)
    return second if first == 1 else first


def discover_java():
    """发现系统里的所有 Java，返回 {java_exe: major}。"""
    found = {}

    def add(java_exe):
        java_exe = os.path.normpath(java_exe)
        if not os.path.isfile(java_exe) or java_exe in found:
            return
        major = java_major(java_exe)
        if major:
            found[java_exe] = major

    # 1) JAVA_HOME
    jh = os.environ.get("JAVA_HOME", "")
    if jh:
        add(os.path.join(jh, "bin", "java.exe"))
    # 2) PATH
    on_path = shutil.which("java")
    if on_path:
        add(on_path)
    # 3) 常见安装目录
    patterns = []
    for root in _JAVA_ROOTS + _JAVA_USER_ROOTS:
        if root:
            patterns.append(os.path.join(root, "*", "bin", "java.exe"))
            patterns.append(os.path.join(root, "*", "*", "bin", "java.exe"))
    for pattern in patterns:
        for p in glob.glob(pattern):
            add(p)
    return found


def pick_java(required_major, config):
    """按版本要求挑选 Java：优先精确匹配，否则用最高的可用版本并告警。"""
    explicit = (config.get("java_path") or "").strip()
    candidates = {}
    if explicit:
        exe = os.path.normpath(explicit)
        if not os.path.isfile(exe):
            raise RuntimeError("配置的 java_path 不存在: %s" % explicit)
        major = java_major(exe)
        if not major:
            raise RuntimeError("无法识别 java_path 的版本: %s" % explicit)
        candidates[exe] = major
    else:
        candidates = discover_java()
    if not candidates:
        return None, None, "未在系统里找到任何 Java"

    exact = [(p, m) for p, m in candidates.items() if m == required_major]
    if exact:
        return exact[0][0], exact[0][1], None
    usable = [(p, m) for p, m in candidates.items() if m >= required_major]
    if usable:
        path, major = max(usable, key=lambda x: x[1])
        return path, major, "未找到精确匹配 Java %d 的版本，改用 Java %d（可能不兼容）" % (required_major, major)
    best = max(candidates.items(), key=lambda x: x[1])
    return best[0], best[1], "本机 Java 版本(%d)低于要求(%d)，启动大概率失败" % (best[1], required_major)


def _flatten(args_list, features, os_info):
    """展开 [str | {rules, value}] 形式的参数列表。"""
    out = []
    for item in args_list or []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            if not evaluate_rules(item.get("rules"), os_info, features):
                continue
            value = item.get("value")
            if isinstance(value, list):
                out.extend(str(v) for v in value)
            elif value is not None:
                out.append(str(value))
    return out


def _substitute(text, tokens):
    if not isinstance(text, str) or "${" not in text:
        return text

    def repl(m):
        return tokens.get(m.group(1), "")

    return re.sub(r"\$\{([^}]+)\}", repl, text)


class LaunchSpec:
    """一次启动的全部参数。"""

    def __init__(self, java_exe, args, java_major_used, warning, game_dir, version_id):
        self.java_exe = java_exe
        self.args = args
        self.java_major_used = java_major_used
        self.warning = warning
        self.game_dir = game_dir
        self.version_id = version_id


def build_launch_spec(config, version_entry, version_json, plan, username=None,
                      max_mem=None, min_mem=None, width=None, height=None,
                      server=None, port=None, demo=False, os_info=None, log=None):
    """构建启动命令（不执行）。"""
    log = log or (lambda msg: None)
    from .utils import get_os_info
    os_info = os_info or get_os_info()
    vid = version_entry["id"]
    game_dir = config.game_dir
    username = username or config.get("username") or "Steve"

    try:
        max_mem = int(max_mem) if max_mem else int(config.get("max_memory_mb", 2048))
    except (TypeError, ValueError):
        max_mem = 2048
    try:
        min_mem = int(min_mem) if min_mem else int(config.get("min_memory_mb", 1024))
    except (TypeError, ValueError):
        min_mem = 1024
    width = width or config.get("resolution_width", 854)
    height = height or config.get("resolution_height", 480)

    # Java 发现
    required = version_json.get("javaVersion", {}).get("majorVersion")
    try:
        required = int(required) if required else 8
    except (TypeError, ValueError):
        required = 8
    java_exe, used_major, warn = pick_java(required, config)
    if not java_exe:
        raise RuntimeError(
            "找不到 Java。该版本需要 Java %d，请安装后重试（推荐 Adoptium Temurin：https://adoptium.net/）"
            % required
        )
    if warn:
        log("提示：%s" % warn)

    # 库与 natives
    jars, _natives = resolve_libraries(version_json, os_info)
    # 游戏本体 jar 必须放在 classpath 最前（官方启动器同款做法）
    # 继承版本（Fabric/Forge）的客户端 jar 在父版本目录
    parent = version_json.get("inheritsFrom")
    client = (version_json.get("downloads") or {}).get("client") or {}
    client_name = os.path.basename(client.get("path") or "%s.jar" % (parent or vid))
    client_dir = os.path.join(game_dir, "versions", parent) if parent else os.path.join(game_dir, "versions", vid)
    client_jar = os.path.join(client_dir, client_name)
    if not os.path.isfile(client_jar):
        client_jar = os.path.join(client_dir, "%s.jar" % (parent or vid))
    classpath = os.pathsep.join(
        [client_jar] + [os.path.join(game_dir, "libraries", j["path"].replace("/", os.sep)) for j in jars]
    )
    natives_dir = os.path.join(game_dir, "versions", vid, "natives")

    # 资源
    assets_root = os.path.join(game_dir, "assets")
    asset_index_id = version_json.get("assets", "")
    asset_index = version_json.get("assetIndex") or {}
    if asset_index.get("id"):
        asset_index_id = asset_index["id"]

    # 令牌
    uid = offline_uuid(username)
    tokens = {
        "auth_player_name": username,
        "version_name": vid,
        "game_directory": game_dir,
        "game_dir": game_dir,
        "assets_root": assets_root,
        "assets_index_name": asset_index_id,
        "auth_uuid": uid,
        "auth_access_token": "0",
        "auth_session": "token:0:%s" % uid,
        "auth_xuid": "",
        "clientid": str(uuid_mod.uuid4()),
        "user_type": "legacy",
        "version_type": version_json.get("type", "release"),
        "natives_directory": natives_dir,
        "launcher_name": APP_NAME,
        "launcher_version": config.get("launcher_version") or __version__,
        "classpath": classpath,
        "classpath_separator": os.pathsep,
        "resolution_width": str(int(width)),
        "resolution_height": str(int(height)),
    }

    features = {"is_demo_user": bool(demo), "has_custom_resolution": False}

    # JVM 参数
    jvm_args = []
    if version_json.get("arguments", {}).get("jvm"):
        jvm_args = _flatten(version_json["arguments"]["jvm"], features, os_info)
    else:
        jvm_args = ["-Djava.library.path=" + natives_dir]
    jvm_args = [_substitute(a, tokens) for a in jvm_args]

    # 日志配置参数（如 -Dlog4j.configurationFile=<path>）
    logging_client = version_json.get("logging", {}).get("client") or {}
    if logging_client.get("argument") and logging_client.get("file", {}).get("id"):
        log_path = os.path.join(game_dir, "assets", "log_configs",
                                logging_client["file"]["id"])
        if os.path.isfile(log_path):
            arg = logging_client["argument"].replace("${path}", log_path)
            jvm_args.append(arg)
    # 兼容老版本 jvm 参数里的 ${log4j_configuration_file}
    if os.path.isfile(plan.get("logging_local", "")):
        tokens["log4j_configuration_file"] = plan["logging_local"]
    else:
        tokens["log4j_configuration_file"] = ""
    jvm_args = [_substitute(a, tokens) for a in jvm_args]

    # 内存参数放在最前
    memory_args = ["-Xmx%dM" % max_mem, "-Xms%dM" % min_mem]

    # 确保 classpath 参数存在
    if not any(a.strip() in ("-cp", "-classpath") for a in jvm_args):
        jvm_args += ["-cp", classpath]

    # 游戏参数
    if version_json.get("arguments", {}).get("game"):
        game_args = _flatten(version_json["arguments"]["game"], features, os_info)
    else:
        game_args = (version_json.get("minecraftArguments") or "").split()
    game_args = [_substitute(a, tokens) for a in game_args]

    if server:
        host = server
        game_args += ["--server", host, "--port", str(int(port or 25565))]
    if demo:
        game_args.append("--demo")

    main_class = version_json.get("mainClass") or "net.minecraft.client.main.Main"
    full_args = memory_args + jvm_args + [main_class] + game_args

    # 依赖的库文件是否齐全（不全则提示先 install）
    missing = [j["path"] for j in jars
               if not os.path.isfile(os.path.join(game_dir, "libraries", j["path"].replace("/", os.sep)))]
    if missing:
        log("警告：以下库文件尚未下载，请先执行 install：%s" % missing[0])

    return LaunchSpec(java_exe, full_args, used_major, warn, game_dir, vid)


def launch(spec, dry_run=False, log=None, no_console=False, console_log=None):
    """执行启动。dry_run=True 时只打印命令。

    no_console=True（GUI 用）：不弹出黑色控制台窗口，把游戏输出写入 console_log 文件。
    """
    log = log or (lambda msg: None)
    cmd = [spec.java_exe] + spec.args
    log("启动命令：")
    log("  " + " ".join('"%s"' % a if " " in a else a for a in cmd))
    if dry_run:
        log("[dry-run] 未真正启动")
        return None
    ensure_dir(spec.game_dir)
    kwargs = {}
    if no_console:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if console_log:
            ensure_dir(os.path.dirname(console_log))
            f = open(console_log, "ab", buffering=0)
            kwargs["stdout"] = f
            kwargs["stderr"] = f
            kwargs["close_fds"] = True
            log("游戏输出已写入：%s（不会弹出黑框）" % console_log)
    try:
        proc = subprocess.Popen(cmd, cwd=spec.game_dir, **kwargs)
    except OSError as exc:
        raise RuntimeError("启动失败: %s" % exc)
    log("游戏进程已启动（PID %d），Java %d，等待游戏退出…" % (proc.pid, spec.java_major_used))
    code = proc.wait()
    if no_console and console_log:
        try:
            f.close()
        except Exception:  # noqa: BLE001
            pass
    log("游戏已退出，退出码 %d" % code)
    return code
