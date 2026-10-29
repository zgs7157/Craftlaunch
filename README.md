# CraftLaunch Minecraft Java 版启动器（离线版）

一个用 **Python 标准库**（零第三方依赖）写成的《我的世界》Java 版启动器：拉取官方版本、下载游戏本体、自动挑 Java、一键离线启动。支持 1.8 ~ 最新版（含快照）全部官方版本。

> 本启动器与 Mojang / Microsoft 无任何隶属关系，仅调用官方公开接口（BMCLAPI 镜像可选）。

---

## 功能特性

- ✅ 官方版本清单：release / snapshot / old_beta / old_alpha 全量版本
- ✅ 一键安装：客户端 jar、全部库文件、natives（原生库）、资源文件、日志配置
- ✅ 离线模式启动：无需正版账号，自动生成离线 UUID 与令牌
- ✅ 自动发现 Java：从 PATH / JAVA_HOME / 常见安装目录找到并匹配版本要求（1.17+ 用 Java 17，1.20.5+ 用 Java 21，26.x 用 Java 25，老版本用 Java 8）
- ✅ 新旧两种启动参数格式全兼容：新版 `arguments.jvm/game` 与老版 `minecraftArguments`
- ✅ 镜像兜底：官方源失败自动切换 BMCLAPI 国内镜像（`mirror: auto`），也可强制官方或镜像
- ✅ 断点续传思维：已下载且 SHA1 校验通过的文件自动跳过
- ✅ 多线程并行下载（默认 8 线程）
- ✅ SHA1 完整性校验 + zip-slip 防护 + 临时文件原子替换
- ✅ 版本继承（inheritsFrom）支持：可启动 Fabric / Forge 等加载器版本
- ✅ 一键安装模组加载器：自动拉取 Fabric / Forge 官方安装器并装好（联网）
- ✅ 模组 / 光影包 / 资源包管理：导入、启用停用（`.disabled`）、删除、打开文件夹

## 环境要求

| 依赖 | 说明 |
|---|---|
| Python | 3.9+（本机已验证 3.13） |
| Java | 按目标版本要求安装（见下表），没有对应版本时启动器会明确提示 |

| 游戏版本 | 要求 Java |
|---|---|
| 26.x（最新） | 25 |
| 1.20.5 ~ 1.25.x | 21 |
| 1.18 ~ 1.20.4 | 17 |
| 1.17 | 16 |
| 1.16.5 及更早 | 8 |

> 官方 Java 下载（免费，选择 Temurin）：<https://adoptium.net/>

## 快速开始

```bat
:: 1. 查看可安装版本（默认只看正式版）
python launcher.py versions

:: 2. 安装最新正式版（首次约下载 300~700MB，看版本）
python launcher.py install latest

:: 3. 启动游戏（离线模式；缺资源文件会自动补下）
python launcher.py launch latest --username Steve
```

或者直接双击 **`start.bat`**，它会以 UTF-8 编码调用 `launcher.py`，参数照常写在后面（例如 `start.bat launch 1.21.1`）。

---

## 桌面图形版（PCL 风格）

除了命令行，还带一个图形界面版（深色主题，左侧导航 + 版本管理 + 资源管理 + 设置 + 日志），双击 **`start-gui.bat`** 即可打开（无控制台窗口）：

- **版本管理**：全量版本列表（可筛选正式版/快照/远古版本、搜索），显示已安装状态与所需 Java，一键安装 / 双击启动；本机已装的加载器版本（如 `fabric-loader-0.19.5-1.21.1`）也会显示
- **资源管理**：模组（mods）/ 光影包（shaderpacks）/ 资源包（resourcepacks）三个页签，可导入文件、打开文件夹、启用/停用、删除；顶部可一键安装 Fabric / Forge 模组加载器
- **启动**：底部大按钮直接启动所选版本，安装与启动都有实时进度条和日志
- **设置**：游戏目录（浏览选择）、离线玩家名、Java 运行时（自动检测所有已装 JDK）、内存分配、窗口分辨率、镜像与下载线程，保存即生效
- **运行日志**：实时显示下载/启动日志，便于排查

```bat
python gui.py                 :: 命令行方式打开图形界面
python gui.py --selftest      :: 自检模式（自动构建界面后退出，用于验证）
```

> 图形界面基于 Python 自带的 tkinter，需要完整版 Python（`python.org` 安装包自带）。`start-gui.bat` 会自动挑选带 tkinter 的 Python（优先常见安装路径，再依次尝试 `pyw` / `pythonw` / `python`）；如果提示找不到 Python，请安装 Python 3.9+。
>
> 从图形界面启动游戏时**不会弹出黑色控制台窗口**，游戏的标准输出/错误会实时写入 `<游戏目录>\logs\launcher-game-console.log`；启动失败时先看启动器的「运行日志」页或该文件。

## 模组 / 光影包 / 资源包

三者都通过图形界面的「资源管理」页操作（文件放在游戏目录下，与官方启动器共用）：

| 类别 | 目录 | 说明 |
|---|---|---|
| 模组 | `<游戏目录>\mods` | 需要先装 Fabric 或 Forge 加载器，`.jar` 放进文件夹即生效 |
| 光影包 | `<游戏目录>\shaderpacks` | 一般是 `.zip`，游戏内需配合 Iris（Fabric 模组）或 OptiFine 使用 |
| 资源包 | `<游戏目录>\resourcepacks` | 支持 `.zip` 或文件夹，游戏内「选项 → 资源包」启用 |

- **导入**：点「导入文件…」多选本地文件复制进去（同名会跳过并提示）。
- **启用 / 停用**：切换 `.disabled` 后缀（Minecraft 官方机制，停用的不会加载）。
- **删除 / 打开文件夹**：删除前有确认框；打开文件夹便于手动管理。

### 一键安装模组加载器

在「资源管理」页顶部选加载器（**Fabric / Forge**）和目标版本（如 `1.21.1`），点「安装加载器」：

1. 从官方元数据（`meta.fabricmc.net` / `maven.minecraftforge.net`）获取最新稳定版本；
2. 下载官方安装器（缓存到 `.cache/loaders/`，已存在则跳过）；
3. 用本机 Java 无头运行安装器，装好后在「版本管理」出现新版本（Fabric 形如 `fabric-loader-0.19.5-1.21.1`，Forge 形如 `1.21.1-forge`）；
4. 选中新版本点「启动游戏」即可带加载器进游戏，再把模组 jar 导入 `mods` 文件夹。

> 加载器版本继承原版（`inheritsFrom`），启动器会自动展开合并原版 jar、参数、资源；原版文件齐备时无需额外下载。
>
> 命令行也可启动加载器版本：`python launcher.py launch fabric-loader-0.19.5-1.21.1`。

## 命令行用法

### `versions` —— 查看版本

```bat
python launcher.py versions                    :: 只看正式版
python launcher.py versions --type all         :: 全部类型（含快照/远古测试版）
python launcher.py versions --type snapshot --limit 20
python launcher.py versions --refresh          :: 强制刷新清单缓存
```

### `install` —— 安装版本

```bat
python launcher.py install 1.21.1
python launcher.py install latest-snapshot
python launcher.py install 1.21.1 --game-dir "D:\MC"     :: 指定游戏目录（仅本次生效）
python launcher.py install 1.21.1 --skip-assets          :: 先不下载资源（体积最大）
python launcher.py install 1.21.1 --dry-run              :: 只打印下载计划，不下
python launcher.py install 1.21.1 --force                :: 强制重下 + 重解压 natives
```

### `launch` —— 启动游戏

```bat
python launcher.py launch 1.21.1
python launcher.py launch 1.21.1 --username 史蒂夫        :: 自定义离线玩家名
python launcher.py launch 1.21.1 --max-mem 4096           :: 分配 4GB 内存
python launcher.py launch 1.21.1 --server mc.example.com:25565  :: 启动后直连服务器
python launcher.py launch 1.21.1 --width 1280 --height 720
python launcher.py launch 1.21.1 --java "C:\path\to\java.exe"   :: 指定 Java
python launcher.py launch 1.21.1 --dry-run                :: 只打印启动命令，不启动
```

> `launch` 会自动检查并补齐缺失文件（首次会补下资源文件），所以装完直接 `launch` 即可。

### `status` / `config`

```bat
python launcher.py status     :: 环境自检：Java、游戏目录、已安装版本
python launcher.py config     :: 查看 config.json 内容
```

## 配置文件 `config.json`

首次运行自动生成在启动器根目录，可直接用记事本修改：

```json
{
  "game_dir": "%APPDATA%\\.minecraft",   // 游戏数据目录（可改成任意路径）
  "username": "Steve",                    // 默认离线玩家名
  "java_path": "",                        // 指定 java.exe 则优先用它（留空=自动发现）
  "min_memory_mb": 1024,                  // 最小堆内存
  "max_memory_mb": 2048,                  // 最大堆内存
  "resolution_width": 854,
  "resolution_height": 480,
  "download_threads": 8,
  "mirror": "auto",                       // auto | mojang | bmclapi
  "launcher_name": "CraftLaunch",
  "launcher_version": "1.0.0",
  "manifest_cache_ttl_minutes": 30
}
```

- `game_dir`：默认 `%APPDATA%\.minecraft`，与官方启动器共用目录；想独立管理就改成新路径（如 `D:\MC`）。
- `mirror`：`auto` 官方优先、失败自动走 BMCLAPI；国内网络慢时可设 `bmclapi` 让镜像优先。
- 命令行参数（`--game-dir`、`--java` 等）只对本次运行生效，不会写回配置文件。

## 目录结构

```
minecraft-java-launcher/
├── launcher.py            # 命令行入口
├── gui.py                 # 桌面图形版入口（tkinter，PCL 风格）
├── start.bat              # Windows 一键启动脚本（命令行）
├── start-gui.bat          # Windows 图形版启动脚本（无控制台窗口）
├── config.json            # 配置文件（首次运行自动生成）
├── launcher.log           # 运行日志（自动生成）
├── .cache/                # 版本清单缓存（自动生成）
├── mc_launcher/           # 核心包
│   ├── __init__.py
│   ├── config.py          # 配置读写
│   ├── network.py         # 下载 / 镜像兜底 / 重试 / 校验
│   ├── api.py             # 版本清单、版本 JSON、资源索引、本地版本扫描
│   ├── version.py         # 版本继承（inheritsFrom）展开合并
│   ├── install.py         # 安装：jar / 库 / natives / 资源
│   ├── launch.py          # Java 发现、启动命令构建、进程拉起
│   ├── loader.py          # 模组加载器安装（Fabric / Forge）
│   ├── resources.py       # 模组 / 光影 / 资源包文件管理
│   └── utils.py           # 规则求值、离线 UUID、SHA1 等
├── README.md
└── LICENSE                # MIT
```

游戏数据目录（默认 `.minecraft`）内的布局与官方启动器一致：

```
<game_dir>/
├── versions/<版本>/        # 版本 JSON、客户端 jar、natives
├── libraries/              # 全部库文件（含 natives jar）
├── assets/
│   ├── indexes/            # 资源索引
│   ├── objects/            # 资源文件（按 SHA1 前两位分目录）
│   └── log_configs/        # log4j 配置文件
└── saves/ mods/ ...        # 你的存档、模组等（由游戏自行创建）
```

## 工作原理

1. 从 `piston-meta.mojang.com` 拉取版本清单（本地缓存 30 分钟）→ 找到目标版本的 `version.json`。
2. 加载器版本（Fabric / Forge，带 `inheritsFrom`）先按继承链展开合并：库文件父级在前子级在后、JVM/游戏参数拼接、主类与资源等以子级为准。
3. 解析 `version.json`：库文件按 `rules`（系统/特性）过滤，natives 按「分类器名称 + 系统架构」精确选择，兼容新旧两种格式；只有 Maven 坐标（`name` + 仓库 `url`）的库自动合成下载地址。
4. 并行下载：客户端 jar（继承版本放父版本目录）→ 库文件 → 资源索引 → 资源对象，全部做 SHA1 校验。
5. 解压 natives（仅 `.dll/.so/.dylib/.jnilib/.cfg`，带 zip-slip 防护）到 `versions/<版本>/natives`。
6. 生成启动命令：`-Xmx/-Xms` → JVM 参数（含 `-cp`、`-Djava.library.path` 等令牌替换）→ 主类 → 游戏参数（离线令牌：`auth_player_name`、离线 UUID、`accessToken=0`）。
7. 找到匹配版本要求的 Java，`Popen` 拉起游戏进程（GUI 模式无控制台窗口，输出写入日志文件）。

## 常见问题

**Q：下载很慢 / 一直失败？**
A：把 `config.json` 里的 `mirror` 改成 `"bmclapi"`（国内镜像优先）；或在命令行 `install` 前先设好。资源文件最大（数百 MB），耐心等或换网络环境。

**Q：提示找不到 Java？**
A：安装对应版本的 JDK（见环境要求表）。已装但没找到，就在 `config.json` 里把 `java_path` 写成 `java.exe` 的完整路径。

**Q：提示"未找到精确匹配 Java X，改用 Java Y"？**
A：高版本 JDK 能向下兼容部分版本（如用 21 跑 1.20.x），但老版本（≤1.16.5）必须用 Java 8，新版必须用 17/21/25，否则会启动崩溃。装上精确版本即可消除提示。

**Q：内存不足（OOM）？**
A：用 `--max-mem` 调大堆内存，或确认电脑剩余内存足够（默认 2GB，一般够用）。

**Q：启动后黑屏 / 闪退？**
A：先跑 `launcher.py launch <版本> --dry-run` 看命令是否正常；再看 `launcher.log` 与游戏崩溃报告（`<game_dir>/crash-reports/`）。常见原因是 Java 版本不匹配或显卡驱动过旧。

**Q：这是离线模式，能进服务器吗？**
A：能进「允许离线模式（正版验证关闭）」的服务器（如局域网联机、部分公益服）。需要正版验证的服务器请用官方启动器登录正版账号。

## 已知限制

- 仅支持 Windows（代码中 Java 搜索路径按 Windows 编写）；macOS/Linux 需自行调整 `launch.py` 的 `_JAVA_ROOTS`。
- 不支持正版微软账号登录（离线模式）。
- 极远古版本（≤1.6）若库文件为 `.pack.xz` 格式，需要 JDK 8 自带的 `unpack200` 工具，本启动器会跳过并告警。
- 不内置 Java 下载（出于安全考虑，只使用本机已安装的 Java）。
- 加载器暂不支持 NeoForge：其官方仓库 `maven.neoforged.net` 在部分网络环境不可达；Fabric 与 Forge 已完整支持。
- Forge 官方安装器只装到默认目录 `%APPDATA%\.minecraft`（与官方启动器一致）；若游戏目录改到了别处，装完的 Forge 版本仍会出现在默认目录，需把游戏目录切回默认目录使用。

## 安全说明

- 所有文件只从 **Mojang 官方域名**（或你显式配置的 BMCLAPI 镜像）下载，下载后做 SHA1 完整性校验。
- 本项目不会执行任何来历不明的脚本，不会上传你的任何数据。
- 使用第三方镜像源时，请自行评估镜像方可信度。

## 许可

MIT License，见 [LICENSE](LICENSE)。游戏本体与相关资源版权归 Mojang AB / Microsoft 所有。
