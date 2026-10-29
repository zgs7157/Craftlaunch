# -*- coding: utf-8 -*-
"""CraftLaunch Minecraft 启动器 —— 桌面图形版（PCL 风格，tkinter，纯标准库）。

用法：
  python gui.py          # 打开图形界面
  start-gui.bat          # Windows 双击入口（无控制台窗口）

隐藏参数：
  python gui.py --selftest   # 自动构建界面并自检后退出（供验证用）
"""
import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from mc_launcher import APP_NAME, __version__
from mc_launcher import api, install as install_mod, launch as launch_mod
from mc_launcher import loader as loader_mod, resources as res_mod, version as version_mod
from mc_launcher.config import Config
from mc_launcher.utils import get_os_info

LAUNCHER_DIR = os.path.dirname(os.path.abspath(__file__))

# Windows 高分屏适配，避免界面模糊
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# ---------- 主题色（深色，接近 PCL 观感） ----------
BG = "#17181c"
PANEL = "#1f2126"
PANEL2 = "#26282e"
FG = "#e8e8ea"
FG_DIM = "#9aa0a6"
ACCENT = "#3b9eff"
GOOD = "#57c07c"
BAD = "#e06c75"
BORDER = "#33363d"

FONT = ("Segoe UI", 10)
FONT_SM = ("Segoe UI", 9)
FONT_BIG = ("Segoe UI", 13, "bold")


def _java_hint(version_id):
    """按版本号给出要求的 Java 主版本（仅展示用，实际以版本 JSON 为准）。"""
    try:
        parts = version_id.split(".")
        major = int(parts[0])
        if major >= 26:
            return 25
        if major > 1:
            return 21
        minor = int(parts[1]) if len(parts) > 1 else 0
        if minor >= 20:
            return 21
        if minor >= 18:
            return 17
        if minor == 17:
            return 16
        return 8
    except (ValueError, IndexError):
        return "?"


class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.cfg = Config(LAUNCHER_DIR)
        self.q = queue.Queue()
        self.busy = False
        self.versions_cache = []
        self.java_list = []          # [(label, exe_path)]
        self._job = None

        root.title("%s v%s —— Minecraft Java 启动器" % (APP_NAME, __version__))
        root.geometry("1024x680")
        root.minsize(880, 560)
        root.configure(bg=BG)
        self._setup_style()
        self._build_ui()
        self._load_settings_vars()
        self._load_java_list()
        self._log_to_console("界面就绪，正在拉取版本列表…")
        self.root.after(120, self._poll)
        self.refresh_versions_async()

    # ================= 界面 =================
    def _setup_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=BG, foreground=FG, font=FONT,
                        fieldbackground=PANEL2, bordercolor=BORDER, lightcolor=BG, darkcolor=BG)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Dim.TLabel", background=BG, foreground=FG_DIM)
        style.configure("Panel.TLabel", background=PANEL, foreground=FG)
        style.configure("Title.TLabel", background=BG, foreground=FG, font=FONT_BIG)
        style.configure("Accent.TLabel", background=BG, foreground=ACCENT)
        style.configure("Good.TLabel", background=BG, foreground=GOOD)
        style.configure("Bad.TLabel", background=BG, foreground=BAD)
        style.configure("TButton", background=PANEL2, foreground=FG, bordercolor=BORDER,
                        padding=(14, 7), focuscolor=PANEL2)
        style.map("TButton",
                  background=[("active", "#33363d"), ("disabled", "#23252a")],
                  foreground=[("disabled", "#5c6169")])
        style.configure("Accent.TButton", background="#2b6cb0", foreground="#ffffff",
                        bordercolor="#2b6cb0", padding=(18, 9))
        style.map("Accent.TButton",
                  background=[("active", "#3b7fd4"), ("disabled", "#2a3a4a")],
                  foreground=[("disabled", "#8a93a3")])
        style.configure("Nav.TButton", background=PANEL, foreground=FG_DIM,
                        bordercolor=PANEL, padding=(12, 12), font=("Segoe UI", 11))
        style.map("Nav.TButton",
                  background=[("active", PANEL2)],
                  foreground=[("active", FG)])
        style.configure("Treeview", background=PANEL2, fieldbackground=PANEL2,
                        foreground=FG, bordercolor=BORDER, rowheight=28)
        style.configure("Treeview.Heading", background=PANEL2, foreground=FG_DIM,
                        bordercolor=BORDER, font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#2b6cb0")],
                  foreground=[("selected", "#ffffff")])
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL2,
                        bordercolor=PANEL2, lightcolor=ACCENT, darkcolor=ACCENT)
        style.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2,
                        foreground=FG, arrowcolor=FG_DIM)
        style.configure("TEntry", fieldbackground=PANEL2, foreground=FG)
        style.configure("TSpinbox", fieldbackground=PANEL2, foreground=FG, arrowcolor=FG_DIM)
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.configure("TNotebook", background=BG, bordercolor=BORDER)
        style.configure("TNotebook.Tab", background=PANEL, foreground=FG_DIM, padding=(16, 8))
        style.map("TNotebook.Tab", background=[("selected", PANEL2)],
                  foreground=[("selected", FG)])

    def _build_ui(self):
        # ---- 顶栏 ----
        top = ttk.Frame(self.root, style="Panel.TFrame")
        top.pack(side="top", fill="x")
        ttk.Label(top, text="CraftLaunch 启动器", style="Accent.TLabel",
                  font=("Segoe UI", 15, "bold")).pack(side="left", padx=16, pady=10)
        self.top_status = ttk.Label(top, text="", style="Dim.TLabel")
        self.top_status.pack(side="right", padx=16)

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True)

        # ---- 左侧导航 ----
        nav = ttk.Frame(body, style="Panel.TFrame", width=150)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        self._nav_buttons = {}
        for key, label in (("versions", "版本管理"), ("resources", "资源管理"), ("settings", "设置"), ("logs", "运行日志")):
            b = ttk.Button(nav, text=label, style="Nav.TButton",
                           command=lambda k=key: self._switch(k))
            b.pack(fill="x", padx=8, pady=3)
            self._nav_buttons[key] = b

        # ---- 右侧内容区 ----
        self.content = ttk.Frame(body)
        self.content.pack(side="left", fill="both", expand=True)
        self.pages = {}
        self.pages["versions"] = self._build_versions_page(self.content)
        self.pages["resources"] = self._build_resources_page(self.content)
        self.pages["settings"] = self._build_settings_page(self.content)
        self.pages["logs"] = self._build_logs_page(self.content)
        self._switch("versions")

        # ---- 底部操作栏 ----
        bottom = ttk.Frame(self.root, style="Panel.TFrame")
        bottom.pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(bottom, style="Horizontal.TProgressbar", maximum=1000)
        self.progress.pack(side="left", fill="x", expand=True, padx=12, pady=10)
        self.status_label = ttk.Label(bottom, text="就绪", style="Dim.TLabel")
        self.status_label.pack(side="left", padx=12)
        self.btn_launch = ttk.Button(bottom, text="启动游戏", style="Accent.TButton",
                                     command=self.on_launch)
        self.btn_launch.pack(side="right", padx=12, pady=8)
        self.btn_install = ttk.Button(bottom, text="安装所选版本", command=self.on_install)
        self.btn_install.pack(side="right", padx=6, pady=8)

    # ---------- 版本页 ----------
    def _build_versions_page(self, parent):
        page = ttk.Frame(parent)
        toolbar = ttk.Frame(page, style="Panel.TFrame")
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="刷新列表", command=self.refresh_versions_async).pack(side="left", padx=8, pady=8)
        self.filter_var = tk.StringVar(value="全部")
        ttk.Combobox(toolbar, textvariable=self.filter_var, state="readonly", width=12,
                     values=("全部", "正式版", "快照", "远古测试版", "远古抢先版")).pack(side="left", padx=4)
        self.filter_var.trace_add("write", lambda *a: self._refill_tree())
        self.search_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.search_var, width=22).pack(side="left", padx=4)
        self.search_var.trace_add("write", lambda *a: self._refill_tree())
        self.detail_label = ttk.Label(toolbar, text="", style="Dim.TLabel")
        self.detail_label.pack(side="right", padx=12)

        wrap = ttk.Frame(page)
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree = ttk.Treeview(wrap, columns=("id", "type", "date", "java", "status"),
                                 show="headings", selectmode="browse")
        for col, text, w, anchor in (
                ("id", "版本号", 220, "w"),
                ("type", "类型", 110, "center"),
                ("date", "发布时间", 110, "center"),
                ("java", "所需Java", 90, "center"),
                ("status", "状态", 90, "center")):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor=anchor, stretch=(col == "id"))
        self.tree.tag_configure("installed", foreground=GOOD)
        self.tree.tag_configure("notinstalled", foreground=FG_DIM)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self.on_launch())
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        return page

    # ---------- 设置页 ----------
    def _build_settings_page(self, parent):
        page = ttk.Frame(parent)
        form = ttk.Frame(page, style="Panel.TFrame")
        form.pack(fill="x", padx=12, pady=12)

        def row(r, label, widget):
            ttk.Label(form, text=label, style="Panel.TLabel").grid(row=r, column=0, sticky="w", padx=10, pady=7)
            widget.grid(row=r, column=1, sticky="we", padx=10, pady=7)
            return widget

        self.var_game_dir = tk.StringVar()
        e = ttk.Entry(form, textvariable=self.var_game_dir, width=52)
        row(0, "游戏目录", e)
        ttk.Button(form, text="浏览…", command=self._browse_game_dir).grid(row=0, column=2, padx=(0, 10))

        self.var_username = tk.StringVar()
        row(1, "玩家名（离线）", ttk.Entry(form, textvariable=self.var_username, width=30))

        self.var_java = tk.StringVar(value="自动选择")
        jb = ttk.Frame(form, style="Panel.TFrame")
        self.java_combo = ttk.Combobox(jb, textvariable=self.var_java, state="readonly", width=44)
        self.java_combo.pack(side="left")
        ttk.Button(jb, text="重新检测", command=self._load_java_list).pack(side="left", padx=6)
        row(2, "Java 运行时", jb)

        mem = ttk.Frame(form, style="Panel.TFrame")
        self.var_max_mem = tk.IntVar(value=2048)
        self.var_min_mem = tk.IntVar(value=1024)
        ttk.Label(mem, text="最小", style="Panel.TLabel").pack(side="left")
        ttk.Spinbox(mem, from_=256, to=16384, increment=256, textvariable=self.var_min_mem,
                    width=8).pack(side="left", padx=4)
        ttk.Label(mem, text="MB　最大", style="Panel.TLabel").pack(side="left")
        ttk.Spinbox(mem, from_=256, to=16384, increment=256, textvariable=self.var_max_mem,
                    width=8).pack(side="left", padx=4)
        row(3, "内存分配", mem)

        res = ttk.Frame(form, style="Panel.TFrame")
        self.var_width = tk.IntVar(value=854)
        self.var_height = tk.IntVar(value=480)
        ttk.Spinbox(res, from_=320, to=7680, increment=1, textvariable=self.var_width, width=8).pack(side="left")
        ttk.Label(res, text=" × ", style="Panel.TLabel").pack(side="left")
        ttk.Spinbox(res, from_=240, to=4320, increment=1, textvariable=self.var_height, width=8).pack(side="left")
        row(4, "窗口分辨率", res)

        misc = ttk.Frame(form, style="Panel.TFrame")
        self.var_mirror = tk.StringVar(value="auto")
        ttk.Combobox(misc, textvariable=self.var_mirror, state="readonly", width=16,
                     values=("auto", "mojang", "bmclapi")).pack(side="left")
        ttk.Label(misc, text="　下载线程", style="Panel.TLabel").pack(side="left", padx=(14, 0))
        self.var_threads = tk.IntVar(value=8)
        ttk.Spinbox(misc, from_=1, to=32, increment=1, textvariable=self.var_threads, width=6).pack(side="left")
        row(5, "镜像 / 线程", misc)

        btns = ttk.Frame(page)
        btns.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Button(btns, text="保存设置", command=self.save_settings).pack(side="left")
        ttk.Button(btns, text="打开游戏目录", command=self._open_game_dir).pack(side="left", padx=8)
        note = ("· 游戏目录默认 %APPDATA%\\.minecraft，与官方启动器共用；可改成任意新目录独立管理。\n"
                "· 启动器会自动挑满足版本要求的 Java；在列表里选一个具体的 Java 即可固定使用。")
        ttk.Label(page, text=note, style="Dim.TLabel", wraplength=780,
                  justify="left").pack(anchor="w", padx=14, pady=6)
        return page

    # ---------- 资源页（模组 / 光影 / 资源包 + 加载器安装） ----------
    def _build_resources_page(self, parent):
        page = ttk.Frame(parent)

        # 加载器安装区
        lframe = ttk.Frame(page, style="Panel.TFrame")
        lframe.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(lframe, text="模组加载器安装", style="Panel.TLabel").pack(side="left", padx=8)
        self.loader_var = tk.StringVar(value="Fabric")
        self.loader_combo = ttk.Combobox(lframe, textvariable=self.loader_var, state="readonly", width=14,
                                         values=[n for _i, n in loader_mod.available_loaders()])
        self.loader_combo.pack(side="left", padx=4)
        ttk.Label(lframe, text="目标版本", style="Panel.TLabel").pack(side="left", padx=10)
        self.loader_ver_var = tk.StringVar()
        self.loader_ver_combo = ttk.Combobox(lframe, textvariable=self.loader_ver_var, width=20)
        self.loader_ver_combo.pack(side="left", padx=4)
        ttk.Button(lframe, text="安装加载器", command=self.on_install_loader).pack(side="left", padx=8)
        ttk.Button(lframe, text="刷新", command=self.refresh_resources).pack(side="left", padx=4)
        hint = ("装完加载器会在「版本管理」出现新版本（如 fabric-loader-0.19.5-1.21.1），选它启动即可带模组。"
                "模组 jar 放进 mods 文件夹后生效；光影包和资源包放进对应文件夹后，到游戏内「选项 → 资源包/光影」里启用。")
        ttk.Label(page, text=hint, style="Dim.TLabel", wraplength=880,
                  justify="left").pack(anchor="w", padx=14, pady=(0, 6))

        nb = ttk.Notebook(page)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.res_trees = {}
        for key, label, tip in (("mods", "模组 mods", "jar / zip，支持 .disabled 停用"),
                                ("shaders", "光影包 shaderpacks", "zip，游戏内需 Iris / OptiFine"),
                                ("resources", "资源包 resourcepacks", "zip / 文件夹，支持 .disabled 停用")):
            tab = ttk.Frame(nb)
            nb.add(tab, text=label)
            bar = ttk.Frame(tab, style="Panel.TFrame")
            bar.pack(fill="x", padx=4, pady=(6, 4))
            ttk.Button(bar, text="导入文件…", command=lambda k=key: self._res_import(k)).pack(side="left", padx=4)
            ttk.Button(bar, text="打开文件夹", command=lambda k=key: self._res_open(k)).pack(side="left", padx=4)
            ttk.Button(bar, text="启用 / 停用", command=lambda k=key: self._res_toggle(k)).pack(side="left", padx=4)
            ttk.Button(bar, text="删除", command=lambda k=key: self._res_remove(k)).pack(side="left", padx=4)
            ttk.Label(bar, text=tip, style="Dim.TLabel").pack(side="right", padx=8)
            wrap = ttk.Frame(tab)
            wrap.pack(fill="both", expand=True, padx=4, pady=(0, 6))
            tree = ttk.Treeview(wrap, columns=("name", "size", "state"),
                                show="headings", selectmode="browse")
            tree.heading("name", text="名称")
            tree.column("name", width=380, anchor="w", stretch=True)
            tree.heading("size", text="大小")
            tree.column("size", width=90, anchor="center")
            tree.heading("state", text="状态")
            tree.column("state", width=90, anchor="center")
            tree.tag_configure("on", foreground=FG)
            tree.tag_configure("off", foreground=FG_DIM)
            vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            self.res_trees[key] = tree
        return page

    def refresh_resources(self):
        """刷新三个资源列表 + 加载器目标版本下拉。"""
        game_dir = self.cfg.game_dir
        for kind, tree in self.res_trees.items():
            tree.delete(*tree.get_children())
            for it in res_mod.list_items(game_dir, kind):
                tree.insert("", "end", values=(
                    it["name"], res_mod._human_size(it["size"]),
                    "已启用" if it["enabled"] else "已停用"),
                    tags=("on" if it["enabled"] else "off",))
        # 加载器目标版本：本机已装版本（含官方与加载器）+ 允许手输
        installed = [e["id"] for e in api.local_installed_versions(game_dir)]
        self.loader_ver_combo.configure(values=installed)
        cur = self.loader_ver_var.get()
        if not cur or cur not in installed:
            sel = self.tree.selection()
            if sel:
                cur = self.tree.item(sel[0])["values"][0]
            elif installed:
                cur = installed[0]
            self.loader_ver_var.set(cur or "1.21.1")

    def _res_selected(self, kind):
        tree = self.res_trees[kind]
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表里选中一个条目。", parent=self.root)
            return None
        return tree.item(sel[0])["values"][0]

    def _res_import(self, kind):
        files = filedialog.askopenfilenames(parent=self.root,
                                            title="选择要导入的%s文件" % res_mod.CATEGORY_LABELS[kind])
        if not files:
            return
        ok, skipped = res_mod.import_items(self.cfg.game_dir, kind, list(files), log=self.log)
        self.refresh_resources()
        self._set_status("已导入 %d 个，跳过 %d 个" % (ok, skipped))

    def _res_open(self, kind):
        try:
            res_mod.open_dir(self.cfg.game_dir, kind)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("打开失败", str(exc), parent=self.root)

    def _res_toggle(self, kind):
        name = self._res_selected(kind)
        if not name:
            return
        try:
            new = res_mod.toggle_item(self.cfg.game_dir, kind, name)
        except OSError as exc:
            messagebox.showerror("操作失败", str(exc), parent=self.root)
            return
        self.refresh_resources()
        self._set_status("已%s：%s" % ("启用" if not new.endswith(".disabled") else "停用", new))

    def _res_remove(self, kind):
        name = self._res_selected(kind)
        if not name:
            return
        if not messagebox.askyesno("确认删除",
                                   "确定删除「%s」吗？此操作不可撤销。" % name, parent=self.root):
            return
        try:
            res_mod.remove_item(self.cfg.game_dir, kind, name)
        except OSError as exc:
            messagebox.showerror("删除失败", str(exc), parent=self.root)
            return
        self.refresh_resources()
        self._set_status("已删除：%s" % name)

    def on_install_loader(self):
        if self.busy:
            return
        loader_name = self.loader_var.get()
        loader_id = dict((n, i) for i, n in loader_mod.available_loaders()).get(loader_name)
        mc_ver = self.loader_ver_var.get().strip()
        if not loader_id:
            messagebox.showinfo("提示", "加载器源不可用。", parent=self.root)
            return
        if not mc_ver:
            messagebox.showinfo("提示", "请先填写目标版本（如 1.21.1）。", parent=self.root)
            return
        self._run_job("loader", (loader_id, mc_ver))

    # ---------- 日志页 ----------
    def _build_logs_page(self, parent):
        page = ttk.Frame(parent)
        wrap = ttk.Frame(page)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        self.log_text = tk.Text(wrap, bg=PANEL2, fg=FG, insertbackground=FG,
                                font=("Consolas", 9), relief="flat", state="disabled",
                                wrap="word", padx=8, pady=8)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        return page

    # ================= 页面切换 =================
    def _switch(self, key):
        for k, page in self.pages.items():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        for k, b in self._nav_buttons.items():
            b.state(["!pressed"])
        if key == "resources":
            self.refresh_resources()

    # ================= 版本列表 =================
    def refresh_versions_async(self):
        if self.busy:
            return
        self._set_status("正在拉取版本列表…")
        threading.Thread(target=self._fetch_manifest, daemon=True).start()

    def _fetch_manifest(self):
        try:
            manifest = api.get_manifest(self.cfg, LAUNCHER_DIR)
            entries = manifest.get("versions", [])
            latest = manifest.get("latest", {})
            self.versions_cache = sorted(entries, key=lambda e: e.get("releaseTime", ""), reverse=True)
            self.q.put(("manifest_ok", (self.versions_cache, latest)))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("manifest_fail", str(exc)))

    def _refill_tree(self):
        self.tree.delete(*self.tree.get_children())
        ftype = self.filter_var.get()
        keyword = self.search_var.get().strip().lower()
        game_dir = self.cfg.game_dir
        type_map = {"正式版": "release", "快照": "snapshot",
                    "远古测试版": "old_beta", "远古抢先版": "old_alpha"}
        want = type_map.get(ftype)
        manifest_ids = set()
        for e in self.versions_cache:
            if want and e.get("type") != want:
                continue
            vid = e.get("id", "")
            if keyword and keyword not in vid.lower():
                continue
            manifest_ids.add(vid)
            installed = os.path.isfile(os.path.join(game_dir, "versions", vid, "%s.json" % vid))
            t = e.get("releaseTime", "")[:10]
            self.tree.insert("", "end", values=(
                vid, e.get("type", ""), t, _java_hint(vid),
                "已安装" if installed else "未安装"),
                tags=("installed" if installed else "notinstalled",))
        # 本机已装的加载器/本地版本（如 fabric-loader-0.19.5-1.21.1）
        for e in api.local_installed_versions(game_dir):
            vid = e["id"]
            if vid in manifest_ids:
                continue
            if want and want != "release":
                continue
            if keyword and keyword not in vid.lower():
                continue
            vj = api.load_local_version_json(game_dir, vid)
            java = _java_hint((vj or {}).get("inheritsFrom") or vid) if vj else _java_hint(vid)
            self.tree.insert("", "end", values=(vid, "本地", "", java, "已安装"),
                             tags=("installed",))

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            self.detail_label.configure(text="")
            return
        item = self.tree.item(sel[0])
        values = item.get("values") or []
        if len(values) >= 5:
            self.detail_label.configure(
                text="%s · 所需 Java %s · 当前%s" % (values[0], values[3], values[4]))

    # ================= 安装 / 启动 =================
    def _selected_version(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在版本列表里选中一个版本。", parent=self.root)
            return None
        return self.tree.item(sel[0])["values"][0]

    def on_install(self):
        vid = self._selected_version()
        if not vid or self.busy:
            return
        self._run_job("install", vid)

    def on_launch(self):
        vid = self._selected_version()
        if not vid or self.busy:
            return
        self._run_job("launch", vid)

    def _run_job(self, kind, vid):
        self.busy = True
        self.btn_install.state(["disabled"])
        self.btn_launch.state(["disabled"])
        status = {"install": "正在安装 %s…", "launch": "正在启动 %s…",
                  "loader": "正在安装加载器到 %s…"}.get(kind, "处理中 %s…")
        self._set_status(status % (vid if isinstance(vid, str) else vid[1]))
        self.progress.configure(value=0)

        def progress_cb(done, total):
            self.q.put(("progress", done, total))

        def worker():
            try:
                if kind == "loader":
                    loader_id, mc_ver = vid
                    new_id = loader_mod.install(
                        loader_id, mc_ver, self.cfg.game_dir,
                        os.path.join(LAUNCHER_DIR, ".cache", "loaders"),
                        log=self.log, progress_cb=progress_cb)
                    self.q.put(("job_done", "加载器安装完成：%s（到「版本管理」选它启动）" % new_id))
                    return
                manifest = api.get_manifest(self.cfg, LAUNCHER_DIR)
                entry, vj0 = api.resolve_any_version(self.cfg, manifest, vid)

                def _json_loader(v):
                    _e, _j = api.resolve_any_version(self.cfg, manifest, v)
                    return _j
                vj = version_mod.expand_version_json(vid, _json_loader)
                installer = install_mod.Installer(self.cfg, get_os_info(), log=self.log)
                plan = installer.install(entry, vj, progress_cb=progress_cb)
                if kind == "install":
                    self.q.put(("job_done", "安装完成：%s" % vid))
                    return
                spec = launch_mod.build_launch_spec(
                    self.cfg, entry, vj, plan,
                    username=self.var_username.get() or None,
                    max_mem=self.var_max_mem.get(), min_mem=self.var_min_mem.get(),
                    width=self.var_width.get(), height=self.var_height.get(),
                    log=self.log)
                self.q.put(("game_start", (spec.java_major_used, spec.java_exe)))
                console_log = os.path.join(self.cfg.game_dir, "logs", "launcher-game-console.log")
                launch_mod.launch(spec, log=self.log, no_console=True, console_log=console_log)
                self.q.put(("job_done", "游戏已退出"))
            except Exception as exc:  # noqa: BLE001
                self.q.put(("job_fail", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    # ================= 队列轮询 =================
    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log_to_console(msg[1])
                elif kind == "progress":
                    done, total = msg[1], msg[2]
                    if total:
                        self.progress.configure(value=int(done * 1000 / total))
                        self._set_status("%d / %d" % (done, total))
                elif kind == "manifest_ok":
                    _cache, latest = msg[1]
                    self._refill_tree()
                    self._set_status("版本列表已更新 · 最新正式版 %s · 快照 %s" % (
                        latest.get("release"), latest.get("snapshot")))
                elif kind == "manifest_fail":
                    self._set_status("版本列表拉取失败：%s" % msg[1])
                    self._log_to_console("错误：%s" % msg[1])
                elif kind == "game_start":
                    self._set_status("游戏已启动（Java %d），日志见运行日志页" % msg[1][0])
                    self.progress.configure(value=0)
                elif kind == "job_done":
                    self.busy = False
                    self._refill_tree()
                    self._set_status(msg[1])
                    self._enable_buttons()
                elif kind == "job_fail":
                    self.busy = False
                    self._refill_tree()
                    self._set_status("失败")
                    self._log_to_console("错误：%s" % msg[1])
                    messagebox.showerror("操作失败", msg[1], parent=self.root)
                    self._enable_buttons()
        except queue.Empty:
            pass
        except Exception as exc:  # noqa: BLE001 —— 轮询绝不能死
            try:
                self._log_to_console("内部错误：%s" % exc)
            except Exception:
                pass
        self.root.after(120, self._poll)

    def _enable_buttons(self):
        self.btn_install.state(["!disabled"])
        self.btn_launch.state(["!disabled"])

    def _set_status(self, text):
        self.status_label.configure(text=text)
        self.top_status.configure(text=text)

    # ================= 日志 =================
    def log(self, msg):
        """给后台线程用的日志入口（跨线程安全，投递到队列）。"""
        self.q.put(("log", str(msg)))

    def _log_to_console(self, msg):
        line = "[%s] %s\n" % (__import__("datetime").datetime.now().strftime("%H:%M:%S"), msg)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ================= 设置 =================
    def _load_settings_vars(self):
        self.var_game_dir.set(self.cfg.game_dir)
        self.var_username.set(self.cfg.get("username") or "Steve")
        self.var_max_mem.set(int(self.cfg.get("max_memory_mb", 2048)))
        self.var_min_mem.set(int(self.cfg.get("min_memory_mb", 1024)))
        self.var_width.set(int(self.cfg.get("resolution_width", 854)))
        self.var_height.set(int(self.cfg.get("resolution_height", 480)))
        self.var_mirror.set(self.cfg.mirror)
        self.var_threads.set(int(self.cfg.get("download_threads", 8)))

    def save_settings(self):
        try:
            self.cfg.set("game_dir", self.var_game_dir.get().strip())
            self.cfg.set("username", self.var_username.get().strip() or "Steve")
            self.cfg.set("max_memory_mb", max(256, int(self.var_max_mem.get())))
            self.cfg.set("min_memory_mb", max(256, int(self.var_min_mem.get())))
            self.cfg.set("resolution_width", int(self.var_width.get()))
            self.cfg.set("resolution_height", int(self.var_height.get()))
            self.cfg.set("mirror", self.var_mirror.get())
            self.cfg.set("download_threads", max(1, int(self.var_threads.get())))
            exe = self._java_exe_from_selection(self.var_java.get())
            self.cfg.set("java_path", exe or "")
            self.cfg.save()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("设置无效", "请检查填写内容：%s" % exc, parent=self.root)
            return
        self._refill_tree()
        self._set_status("设置已保存")
        self._log_to_console("设置已保存到 config.json")

    def _browse_game_dir(self):
        d = filedialog.askdirectory(initialdir=self.var_game_dir.get(), title="选择游戏目录")
        if d:
            self.var_game_dir.set(d)

    def _open_game_dir(self):
        d = self.var_game_dir.get().strip()
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    def _load_java_list(self):
        self.java_list = [("自动选择（推荐）", "")]
        try:
            for exe, major in sorted(launch_mod.discover_java().items(), key=lambda kv: kv[1]):
                self.java_list.append(("Java %d — %s" % (major, exe), exe))
        except Exception:  # noqa: BLE001
            pass
        labels = [l for l, _ in self.java_list]
        cur = self.var_java.get()
        self.java_combo.configure(values=labels)
        if cur not in labels:
            self.java_combo.set("自动选择（推荐）")
        if len(self.java_list) == 1:
            self._log_to_console("未发现已安装的 Java，请安装 JDK 或手动编辑 config.json 指定 java_path。")

    def _java_exe_from_selection(self, label):
        for l, exe in self.java_list:
            if l == label:
                return exe
        return ""


def main():
    selftest = "--selftest" in sys.argv
    root = tk.Tk()
    app = LauncherApp(root)
    if selftest:
        # 自检：等待版本列表加载完一轮，然后退出
        root.after(3000, _selftest_finish, root, app)
        root.mainloop()
    else:
        root.mainloop()


def _selftest_finish(root, app):
    n = len(app.tree.get_children())
    java_n = len(app.java_list)
    print("SELFTEST OK rows=%d java_candidates=%d" % (n, java_n))
    root.destroy()


if __name__ == "__main__":
    main()
