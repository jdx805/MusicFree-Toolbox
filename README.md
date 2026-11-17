# MusicFree工具箱

面向 [MusicFree](https://github.com/maotoumao/MusicFree)（Android 本地音乐播放器）的歌词与入库处理工具集。

一个窗口，三个页签：**内嵌歌词**、**歌词偏移**、**入库体检**。

解决的问题很具体——MusicFree 走本地内嵌歌词路线时，会遇到三类反复踩的坑：

| 症状 | 真实原因 | 本工具箱的解法 |
|---|---|---|
| 播不了，但系统播放器能播 | 扩展名与真实容器不符（`.mp3` 实为 MP4/AAC） | 入库体检提前拦截 |
| 能播但没歌词 | 文件里没有内嵌歌词 / App 库记录残缺 | 内嵌歌词工具补词 |
| 有歌词但时间轴错位 | 内嵌 LRC 时间戳不准 | 歌词偏移工具整体平移 |
| 改了文件、手机仍不生效 | App 把旧路径绑成了旧状态 | 体检 + README 里的判据说明 |

## 功能

### ① 内嵌歌词

- 从 QQ 音乐 / LRCLIB 搜索候选版本，**人工点选**（不自动选第一条，避免版本选错）
- 预览前 12 行确认无误后，写入 MP3 的 ID3 `USLT` 帧或 FLAC 的 Vorbis `LYRICS`
- 另存到指定目录，源文件不动
- 可选一键 `adb push` 到手机，并强停重启 MusicFree

### ② 歌词偏移

- 整体平移内嵌 LRC 的时间戳，正数＝歌词提前，负数＝延后
- 支持正则/关键词搜索歌曲列表
- 源文件不动、另存新目录；单曲可单独设置偏移量
- 内置备份与回滚

### ③ 入库体检

入库手机前跑一次，**全程只读**，检查项：

- 扩展名与真实容器不符（严重，会导致播不了）
- MP3 帧结构不连续（严重，文件本身损坏）
- 无内嵌歌词
- 标题 / 歌手标签为空（会导致 App 库记录残缺）
- 文件名不符合「歌手 - 歌名」规范

报告写在 `体检报告/` 下，不污染音乐目录。纯音乐可在 `_check_ignore.json` 里登记忽略。

## 快速开始

本仓库**只提供脚本**，不包含打包好的 exe；需要 exe 请按文末「本地打包 exe」自行生成。

### 源码运行（推荐）

```bash
# 依赖：Python 3.9+（实测 3.13），无任何第三方 pip 包
python music_toolbox.py
```

Windows 下直接双击 `启动音乐工具箱.bat`——三个工具都在同一个窗口的三个页签里。

### 首次使用

不需要手工建配置文件——界面里选一次文件夹、另存目录、手机目录，退出时自动记住，写在 `%APPDATA%\MusicFree工具箱\config.json`。

不复制也能用，程序会用内置默认值，并在你第一次选完路径后自动保存。

## 依赖

| 项 | 说明 |
|---|---|
| Python 3.9+ | exe 版本已内置，无需安装 |
| tkinter | Python 标准库，随 Python 安装 |
| 第三方 pip 包 | **无** |
| adb | 仅「同步到手机」功能需要；需手机开启 USB 调试，**查找规则见下** |
| ffmpeg | 仅人工修复畸形音频时用到，工具运行不依赖 |

### adb 路径

程序不会四处搜 adb，规则是固定的（`musicfree_sync.py` 的 `_find_adb()`）：

| 运行形态 | 查找顺序 |
|---|---|
| 源码（`python music_toolbox.py`） | **只用** `D:\Program Files\platform-tools\adb.exe`，不搜 PATH |
| 打包 exe | ① exe 同目录的 `adb.exe` → ② PATH 里的 `adb` → ③ 兜底 `D:\Program Files\platform-tools\adb.exe` |

源码态这条路径是**硬编码**的：换机器或 platform-tools 装在别处，必须改 `musicfree_sync.py` 第 40 行，否则「同步到手机」会提示 `adb 不存在: D:\Program Files\platform-tools\adb.exe`。

用 exe 则不必改代码：把 `adb.exe` 连同 `AdbWinApi.dll`、`AdbWinUsbApi.dll` 放到 exe 旁边即可。

## 关键判据

这些是排查过程中验证过的硬结论：

**1. MusicFree 按扩展名选解码器，不嗅探容器。**
系统播放器会嗅探，所以会出现「别的播放器能播、MusicFree 播不了」。
判据：`ffprobe -show_format 文件` 看 `format_name`。若是 `.mp3` 但实际为 MP4/AAC（常见于下载工具的 DASH 音频被改名），需重新编码为真 MP3。

**2. 换完文件仍没歌词 → 查 App 库记录是否残缺。**
MusicFree 的本地库记录（MMKV `musicByPath`）若 `duration=0`、`artist` 为空，说明 App 从未成功解析过该文件，此时歌词、封面、歌名全都不会对。
**治法：换一个全新未用过的文件名 → 重新扫描 → 建立新记录。**

**3. 旧路径一旦被记成「无词」，救不回来。**
覆盖文件、清除库记录、移走重扫、按官方规则写 `local_lrc`——四种办法均无效（重扫会把记录还原）。
**唯一解仍是换全新文件名重扫。**

**4. 歌词缓存优先级高于内嵌歌词。**
改了内嵌歌词但手机不变，多半是 App 读到了旧缓存快照。缓存位置：
`/sdcard/Android/data/fun.upup.musicfree/files/lyric/cache/`
缓存文件名是哈希，无法从歌名推断，只能按歌词正文内容定位。

**这条缓存可以直接删。** 实测（2026-11-17）：某首歌缓存缺失时播放，App 会用**文件内嵌**重建缓存，新缓存 `rawLrc` 与内嵌 MD5 完全一致（当时手机在线，排除离线偏置）。所以处理旧词的正确做法是「删缓存让它重建」，而不是改缓存内容——前提是文件内嵌已经是正确版本；内嵌为空则删完仍无词。

**5. 时间戳偏移方向容易搞反。**
本工具约定：**正数＝歌词提前（变快），负数＝延后（变慢）**。

**6. 不要用 `monkey` 启动 App——它会顺手把自动旋转打开。**
`monkey -p <包名> -c android.intent.category.LAUNCHER 1` 会在系统里注册一个名为 `Monkey touch` 的虚拟触摸设备，触发 WindowManager 的「Display reconfigured」，ColorOS 的旋转锁（`OplusRotationLockTile`）随之把 `accelerometer_rotation` 写成 1。
logcat 判据（按时间顺序，间隔约 40 ms）：`New device … 'Monkey touch'` → `Display reconfigured outside of a transition` → `notifyForSettingsChange … accelerometer_rotation, value: 1`。
本工具重启 MusicFree 一律用 `am start -n <包名>/.MainActivity`，不创建虚拟输入设备，无此副作用。

## 目录结构

```
20261117音乐工具箱/
├── music_toolbox.py         # 三合一入口
├── lyric_embed_gui.py       # 页签①：内嵌歌词
├── lyric_offset_gui.py      # 页签②：歌词偏移
├── musicfree_check.py       # 页签③：入库体检
├── lyric_embed_core.py      # 歌词搜索/拉取/写入核心
├── lyric_offset_tool.py     # MP3/FLAC 标签读写与时间戳平移核心
├── musicfree_sync.py        # adb 同步、缓存清理、强停重启
├── toolbox_config.py        # 统一配置读写（存 %APPDATA%，不落程序目录）
├── _check_ignore.json       # 体检忽略名单（纯音乐）
├── 启动音乐工具箱.bat        # 一键启动
├── 音乐工具箱-使用说明.md
├── 内嵌歌词工具-使用说明.md
├── 歌词偏移工具-使用说明.md
├── 音乐入库前体检-使用说明.md
└── 体检报告/                 # 体检输出
```

### 配置存在哪里

路径记忆（文件夹 / 另存目录 / 手机目录）写在：

```
%APPDATA%\MusicFree工具箱\config.json
```

一个文件两节，`embed` 对应页签①，`offset` 对应页签②：

```json
{
  "embed":  {"folder": "...", "out": "...", "phone": "/sdcard/MusicFree/"},
  "offset": {"folder": "...", "out": "...", "phone": "/sdcard/Music/"}
}
```

所以 exe 拷到任何目录都不会在它旁边生成配置文件。早期版本留下的 `_embed_gui_config.json`、`_offset_gui_config.json` 会在首次读取时自动迁入新文件，旧文件不再写入，可直接删除。

## 本地打包 exe

仓库不提交二进制产物，需要时自己在本地生成：

```bash
pip install pyinstaller
pyinstaller -w -F --clean -n "音乐工具箱" music_toolbox.py
```

产物在 `dist/音乐工具箱.exe`，约 10 MB。打包后：

1. 把 `_check_ignore.json` 复制到 exe 同目录（体检忽略名单）
2. 如需「同步到手机」，把 `adb.exe` 连同 `AdbWinApi.dll`、`AdbWinUsbApi.dll` 一起放到 exe 同目录（或把 platform-tools 加入 PATH）

单文件模式首次启动会有 1–2 秒解压，属正常现象。**路径设置写在 `%APPDATA%\MusicFree工具箱\config.json`**（不在 exe 旁边）；体检报告仍写在 exe 所在目录的 `体检报告\`。

## 说明

- 歌词来源为第三方公开接口，仅供个人学习与本地使用，请勿用于分发。
- 「歌词偏移」「入库体检」不会修改源文件；「内嵌歌词」默认另存新目录。
- 同步功能会向手机写入文件并强停重开 MusicFree，请确认目标目录后再执行。

## 许可

个人自用工具，未做通用化适配。按需取用。
