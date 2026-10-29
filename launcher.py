# -*- coding: utf-8 -*-
"""CraftLaunch Minecraft Java 版启动器（离线版）命令行入口。

用法示例：
  python launcher.py versions                 # 查看可安装版本
  python launcher.py install 1.21.1           # 安装指定版本
  python launcher.py launch 26.3 --username Steve  # 启动游戏（缺文件会自动补装）
  python launcher.py status                   # 环境自检
"""
import argparse
import datetime
import os
import sys

from mc_launcher import APP_NAME, __version__
from mc_launcher import api, install as install_mod, launch as launch_mod, version as version_mod
from mc_launcher.config import Config
from mc_launcher.utils import fmt_size, get_os_info

LAUNCHER_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LAUNCHER_DIR, "launcher.log")


def _setup_logging():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    import logging

    logger = logging.getLogger("craftlaunch")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
    return logger


def log(msg, logger=None, quiet=False):
    line = str(msg)
    if not quiet:
        print(line)
    if logger:
        logger.info(line)


def _load_config():
    return Config(LAUNCHER_DIR)


def cmd_versions(args):
    cfg = _load_config()
    manifest = api.get_manifest(cfg, LAUNCHER_DIR, force=args.refresh)
    latest = manifest.get("latest", {})
    print("最新正式版：%s    最新快照：%s" % (latest.get("release"), latest.get("snapshot")))
    allowed = {"release", "snapshot", "old_beta", "old_alpha"} if args.type == "all" else {args.type}
    rows = [e for e in manifest.get("versions", []) if e.get("type") in allowed]
    rows.sort(key=lambda e: e.get("releaseTime", ""), reverse=True)
    limit = args.limit or len(rows)
    label = "全部类型" if args.type == "all" else args.type
    print("共 %d 个%s版本（显示前 %d 个）：" % (len(rows), label, min(limit, len(rows))))
    print("%-18s %-10s %s" % ("版本号", "类型", "发布时间"))
    for e in rows[:limit]:
        t = e.get("releaseTime", "")
        try:
            t = datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
        except ValueError:
            pass
        installed = ""
        if os.path.isfile(os.path.join(cfg.game_dir, "versions", e["id"], "%s.json" % e["id"])):
            installed = " [已安装]"
        print("%-18s %-10s %s%s" % (e["id"], e.get("type"), t, installed))


def cmd_status(args):
    cfg = _load_config()
    os_info = get_os_info()
    print("== 环境自检 ==")
    print("Python: %s" % sys.version.split()[0])
    print("系统: %s / %s" % (os_info["name"], os_info["arch"]))
    print("游戏目录: %s" % cfg.game_dir)
    print("镜像策略: %s（auto=官方优先+镜像兜底）" % cfg.mirror)
    java = launch_mod.discover_java()
    if java:
        print("发现的 Java：")
        for exe, major in sorted(java.items(), key=lambda kv: kv[1]):
            print("  Java %-3d %s" % (major, exe))
    else:
        print("未发现任何 Java（请安装 Adoptium Temurin）")
    installed = []
    ver_dir = os.path.join(cfg.game_dir, "versions")
    if os.path.isdir(ver_dir):
        for name in sorted(os.listdir(ver_dir)):
            if os.path.isfile(os.path.join(ver_dir, name, "%s.json" % name)):
                installed.append(name)
    if installed:
        print("已安装版本：%s" % ", ".join(installed))
    else:
        print("已安装版本：无（使用 install 命令安装）")


def cmd_config(args):
    cfg = _load_config()
    print("配置文件：%s" % cfg.path)
    for k, v in cfg.data.items():
        print("  %s = %s" % (k, v))


def cmd_install(args):
    cfg = _load_config()
    logger = _setup_logging()
    log("== 安装 %s ==" % args.version, logger)
    manifest = api.get_manifest(cfg, LAUNCHER_DIR, force=args.refresh)
    entry, version_json = api.resolve_any_version(cfg, manifest, args.version)
    version_json = version_mod.expand_version_json(
        args.version, lambda v: api.resolve_any_version(cfg, manifest, v)[1])
    if args.game_dir:
        cfg.set("game_dir", args.game_dir, save=False)
    log("版本：%s（%s），游戏目录：%s" % (entry["id"], entry.get("type"), cfg.game_dir), logger)
    required = api.version_required_java(version_json)
    log("该版本要求 Java %d" % required, logger)
    installer = install_mod.Installer(cfg, get_os_info(), log=lambda m: log(m, logger))
    plan = installer.install(
        entry, version_json,
        skip_assets=args.skip_assets,
        skip_libraries=args.skip_libraries,
        force=args.force,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        print("\n== 干跑计划 ==")
        print("客户端 jar：%s" % plan["jar"])
        print("库文件：%d 个，共 %s" % (len(plan["libraries"]), fmt_size(sum(int(l.get("size") or 0) for l in plan["libraries"]))))
        print("natives：%d 个" % len(plan["natives"]))
        if plan["asset_index"]:
            print("资源索引：%s（%s）" % (plan["asset_index"].get("id"), fmt_size(plan["asset_index"].get("size", 0))))
        return
    if not args.skip_assets:
        print("\n安装完成：%s" % entry["id"])
    else:
        print("\n安装完成（已跳过资源下载，launch 时会自动补齐）：%s" % entry["id"])
    if args.skip_assets:
        print("提示：跳过资源后首次 launch 仍会补下资源（约数百 MB）。")


def cmd_launch(args):
    cfg = _load_config()
    logger = _setup_logging()
    if args.game_dir:
        cfg.set("game_dir", args.game_dir, save=False)
    if args.java:
        cfg.set("java_path", args.java, save=False)
    log("== 启动 %s（离线模式，玩家名：%s）==" % (args.version, args.username or cfg.get("username")), logger)
    manifest = api.get_manifest(cfg, LAUNCHER_DIR)
    entry, version_json = api.resolve_any_version(cfg, manifest, args.version)
    version_json = version_mod.expand_version_json(
        args.version, lambda v: api.resolve_any_version(cfg, manifest, v)[1])
    required = api.version_required_java(version_json)

    # 确保已安装（缺什么补什么）
    installer = install_mod.Installer(cfg, get_os_info(), log=lambda m: log(m, logger))
    plan = installer.install(entry, version_json, skip_assets=False, force=args.force)
    if plan.get("logging_local"):
        _ensure_logging(cfg, version_json, plan)

    spec = launch_mod.build_launch_spec(
        cfg, entry, version_json, plan,
        username=args.username, max_mem=args.max_mem, min_mem=args.min_mem,
        width=args.width, height=args.height, server=args.server, port=args.port,
        demo=args.demo, log=lambda m: log(m, logger),
    )
    if spec.warning:
        log("提示：%s" % spec.warning, logger)
    log("使用 Java %d：%s" % (spec.java_major_used, spec.java_exe), logger)
    log("游戏目录：%s" % spec.game_dir, logger)
    launch_mod.launch(spec, dry_run=args.dry_run, log=lambda m: log(m, logger))


def _ensure_logging(cfg, version_json, plan):
    """启动前确保日志配置文件就位。"""
    import os as _os
    if _os.path.isfile(plan.get("logging_local", "")):
        return
    logging_file = (version_json.get("logging") or {}).get("client", {}).get("file")
    if logging_file and logging_file.get("url"):
        from mc_launcher import network
        _os.makedirs(_os.path.dirname(plan["logging_local"]), exist_ok=True)
        network.download_file(logging_file["url"], plan["logging_local"],
                              sha1=logging_file.get("sha1"), size=logging_file.get("size"),
                              mirror_mode=cfg.mirror)


def build_parser():
    p = argparse.ArgumentParser(
        prog="launcher.py",
        description="%s —— Minecraft Java 版离线启动器 v%s" % (APP_NAME, __version__),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--version", action="version", version="%s %s" % (APP_NAME, __version__))
    sub = p.add_subparsers(dest="command", required=True)

    pv = sub.add_parser("versions", help="列出可安装的官方版本")
    pv.add_argument("--type", choices=["release", "snapshot", "old_beta", "old_alpha", "all"],
                    default="release", help="版本类型过滤（默认 release）")
    pv.add_argument("--limit", type=int, default=None, help="最多显示条数")
    pv.add_argument("--refresh", action="store_true", help="强制刷新版本清单")
    pv.set_defaults(func=cmd_versions)

    pi = sub.add_parser("install", help="下载并安装一个版本")
    pi.add_argument("version", help="版本号（如 1.21.1），或用 latest / latest-release / latest-snapshot")
    pi.add_argument("--game-dir", help="指定游戏目录（覆盖配置文件）")
    pi.add_argument("--dry-run", action="store_true", help="只打印下载计划，不实际下载")
    pi.add_argument("--skip-assets", action="store_true", help="跳过资源文件下载（体积最大）")
    pi.add_argument("--skip-libraries", action="store_true", help="跳过 jar 与库文件下载")
    pi.add_argument("--force", action="store_true", help="强制重新下载并重解压 natives")
    pi.add_argument("--refresh", action="store_true", help="强制刷新版本清单")
    pi.set_defaults(func=cmd_install)

    pl = sub.add_parser("launch", help="启动游戏（缺文件自动补装）")
    pl.add_argument("version", help="版本号或 latest")
    pl.add_argument("--username", help="离线玩家名（默认取配置）")
    pl.add_argument("--game-dir", help="指定游戏目录（覆盖配置文件）")
    pl.add_argument("--java", help="指定 java.exe 路径（覆盖配置）")
    pl.add_argument("--max-mem", type=int, help="最大堆内存 MB")
    pl.add_argument("--min-mem", type=int, help="最小堆内存 MB")
    pl.add_argument("--width", type=int, help="窗口宽度")
    pl.add_argument("--height", type=int, help="窗口高度")
    pl.add_argument("--server", help="启动后直连服务器（host:port 或仅 host）")
    pl.add_argument("--port", type=int, default=25565, help="配合 --server 的端口")
    pl.add_argument("--demo", action="store_true", help="以演示模式启动")
    pl.add_argument("--dry-run", action="store_true", help="只打印启动命令，不真正启动")
    pl.add_argument("--force", action="store_true", help="强制重新下载缺失文件")
    pl.set_defaults(func=cmd_launch)

    ps = sub.add_parser("status", help="环境自检（Java/游戏目录/已安装版本）")
    ps.set_defaults(func=cmd_status)

    pc = sub.add_parser("config", help="查看配置文件内容")
    pc.set_defaults(func=cmd_config)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except LookupError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        sys.exit(2)
    except (RuntimeError, OSError, ValueError) as exc:
        print("错误：%s" % exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
