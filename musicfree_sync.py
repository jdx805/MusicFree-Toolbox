#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MusicFree 手机同步模块（供 lyric_offset_gui.py 调用）

职责：
  1. 把改后文件 push 到手机音乐目录
  2. 遍历手机 lyric/cache，按歌词内容定位目标缓存，**备份到本地后删除**该缓存
  3. 双重校验（push 文件 MD5、删除后确认缓存已不存在）

设计要点（脱离 AI 的关键）：
  - 缓存按「歌词正文文字」匹配，不依赖 sha256 文件名 → 换手机哈希变了也能定位
  - 删除而非覆盖：实测（2026-11-17）缓存缺失时 App 用文件内嵌重建，新缓存 rawLrc 与内嵌 MD5 全等
    → 删除更简单，且不必构造 json；前提是文件内嵌已是正确版本，内嵌为空则删后无词
  - 删除前先 pull 到本地「歌词缓存备份/时间戳/」，可回滚
  - 新机无缓存时不报错，提示「首次播放会生成新缓存」即可
  - 全部只读 adb 采集 + 显式 push/删除，不做界面点击

不依赖 lyric_offset_tool 以外的第三方库。
"""
import os
import re
import sys
import json
import time
import hashlib
import subprocess
import tempfile

import lyric_offset_tool as core


def _find_adb():
    """打包态优先 exe 同目录的 adb.exe，其次 PATH；源码态维持原绝对路径不变。"""
    if getattr(sys, 'frozen', False):
        local = os.path.join(os.path.dirname(sys.executable), 'adb.exe')
        if os.path.isfile(local):
            return local
        import shutil
        found = shutil.which('adb')
        if found:
            return found
    return r'D:\Program Files\platform-tools\adb.exe'


ADB = _find_adb()
DEFAULT_PHONE_DIR = '/sdcard/Music/'
PACKAGE = 'fun.upup.musicfree'
CACHE_DIR = '/sdcard/Android/data/%s/files/lyric/cache' % PACKAGE
TS = core.TS_RE


def _base_dir():
    """配置/备份的落点：打包态用 exe 所在目录，源码态用脚本所在目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# 删除缓存前的本地备份根目录；每次进程启动一个时间戳子目录
BACKUP_ROOT = os.path.join(_base_dir(), '歌词缓存备份')
RUN_TS = time.strftime('%Y%m%d-%H%M%S')


# Windows 下 subprocess 默认会给每个子进程新开控制台窗口，在 GUI 里表现为黑窗一闪而过。
# 一次同步会调十几次 adb，必须彻底隐藏：creationflags + startupinfo 双保险。
_NO_WINDOW = 0
_STARTUPINFO = None
if os.name == 'nt':
    _NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
    _STARTUPINFO = subprocess.STARTUPINFO()
    _STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _STARTUPINFO.wShowWindow = subprocess.SW_HIDE


def _run(*args, timeout=60):
    """执行 adb 命令，返回 (returncode, stdout, stderr)，统一 UTF-8。
    Windows 下隐藏子进程控制台窗口，避免界面里黑窗闪烁。"""
    p = subprocess.run([ADB] + list(args), capture_output=True, timeout=timeout,
                       creationflags=_NO_WINDOW, startupinfo=_STARTUPINFO)
    dec = lambda b: b.decode('utf-8', 'replace').replace('\r', '')
    return p.returncode, dec(p.stdout), dec(p.stderr)


def check_device():
    """返回 (ok, msg)。要求恰好一台设备在线。"""
    if not os.path.exists(ADB):
        return False, 'adb 不存在: ' + ADB
    rc, out, err = _run('devices')
    lines = [l for l in out.splitlines() if l.strip() and not l.startswith('List of devices')]
    dev = [l for l in lines if l.split()[-1:] == ['device']]
    if not dev:
        return False, '没有已授权的设备（确认数据线 + USB调试 + 允许本机调试）'
    if len(dev) > 1:
        return False, '检测到 %d 台设备，请只连一台' % len(dev)
    return True, dev[0].split()[0]


def _md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _lyric_texts(lrc):
    """提取歌词正文文字（去时间戳行、去元信息），用于按内容匹配缓存。"""
    out = []
    for line in lrc.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith('[') and not TS.match(s):   # [ti:] [ar:] 等元信息
            continue
        txt = TS.sub('', s).strip()
        if txt:
            out.append(txt)
    return out


def _norm(lrc):
    """归一化：去时间戳 + 去所有空白，用于全文严格比对。"""
    return re.sub(r'\s+', '', TS.sub('', lrc))


def _cache_list():
    """列出手机缓存目录里的 .json 文件名。"""
    rc, out, err = _run('shell', 'ls -1 "%s/"' % CACHE_DIR)
    if rc != 0:
        return [], '列缓存目录失败: ' + (err or out).strip()
    return [l.strip() for l in out.splitlines() if l.strip().endswith('.json')], None


def _cache_read(name):
    """pull 单条缓存到临时文件，返回 rawLrc 字符串。"""
    fd, tmp = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    try:
        rc, out, err = _run('pull', '%s/%s' % (CACHE_DIR, name), tmp)
        if rc != 0:
            return None
        d = json.load(open(tmp, encoding='utf-8'))
        return d.get('rawLrc', '')
    except Exception:
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _cache_delete(name):
    """先备份到本地，再删除手机缓存；App 下次播放会从文件内嵌重建。
    返回 (ok, msg)。删除后回读目录确认真的不存在。
    """
    # 1) 备份（失败也继续删，但会在 msg 里标出来）
    backed = False
    try:
        d = os.path.join(BACKUP_ROOT, RUN_TS)
        os.makedirs(d, exist_ok=True)
        rc, out, err = _run('pull', '%s/%s' % (CACHE_DIR, name), os.path.join(d, name))
        backed = (rc == 0)
    except Exception:
        backed = False

    # 2) 删除：普通 shell 先试，权限不足再用 su 兜底
    rc, out, err = _run('shell', 'rm -f "%s/%s"' % (CACHE_DIR, name))
    if rc != 0:
        _run('shell', 'su -c "rm -f \'%s/%s\'"' % (CACHE_DIR, name))

    # 3) 回读确认
    names, lerr = _cache_list()
    if lerr:
        return False, '删除后无法确认: ' + lerr
    if name in names:
        return False, '删除失败（缓存仍在，可能缺写权限）'
    return True, '已删除' + ('（已备份）' if backed else '（备份失败）')


def force_stop():
    """强制停止 MusicFree（清掉内存里驻留的旧歌词对象）。返回 (ok, msg)。"""
    rc, out, err = _run('shell', 'am force-stop %s' % PACKAGE)
    return (rc == 0, '已强制停止 %s' % PACKAGE if rc == 0 else '强停失败: ' + (err or out).strip())


def restart_app():
    """拉起 MusicFree 到前台。返回 (ok, msg)。

    必须用 `am start` 显式启动入口 Activity，绝不能用 monkey：
    monkey 会在系统里注册一个名为 'Monkey touch' 的虚拟触摸设备，触发
    WindowManager 的「Display reconfigured」，ColorOS 的旋转锁逻辑
    （OplusRotationLockTile）会顺势把 accelerometer_rotation 写成 1，
    表现为「每次同步完成后手机的自动旋转被悄悄打开」。
    2026-11-18 01:58 logcat 实证：
      EventHub: New device id=25 name='Monkey touch' classes=TOUCH
      WindowManager: Display reconfigured outside of a transition
      SettingsProvider: notifyForSettingsChange ... accelerometer_rotation, value: 1
    """
    rc, out, err = _run('shell', 'am start -n %s/.MainActivity' % PACKAGE)
    if rc == 0 and 'Error' not in (out + err):
        return True, '已启动 ' + PACKAGE

    # 入口 Activity 万一改名：动态解析一次再启动（仍不用 monkey）
    rc2, out2, _ = _run('shell', 'cmd package resolve-activity --brief '
                                 '-c android.intent.category.LAUNCHER %s' % PACKAGE)
    comp = ''
    if rc2 == 0:
        for line in out2.splitlines():
            s = line.strip()
            if '/' in s and ' ' not in s:
                comp = s
    if comp:
        rc3, out3, err3 = _run('shell', 'am start -n %s' % comp)
        if rc3 == 0 and 'Error' not in (out3 + err3):
            return True, '已启动 %s（解析入口）' % comp
        err = err3 or out3
    return False, '启动失败: ' + ((err or out).strip() or 'rc=%d' % rc)


def push_files(local_paths, phone_dir):
    """push 多个文件到手机目录，逐个校验 MD5。返回 [(文件名, ok, msg), ...]。"""
    phone_dir = phone_dir.rstrip('/') + '/'
    res = []
    for p in local_paths:
        name = os.path.basename(p)
        rc, out, err = _run('push', p, phone_dir + name)
        if rc != 0:
            res.append((name, False, 'push 失败: ' + (err or out).strip()))
            continue
        fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(name)[1])
        os.close(fd)
        try:
            rc2, _, _ = _run('pull', phone_dir + name, tmp)
            ok = rc2 == 0 and _md5(tmp) == _md5(p)
            res.append((name, ok, 'MD5 一致' if ok else 'MD5 不一致'))
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    return res


def sync_cache_for(local_path):
    """为单个改后文件定位并删除手机缓存（备份后删除，App 下次播放从内嵌重建）。
    返回 dict: found / need / ok / msg / cache_name
      - found: 找到缓存并已删除
      - need=False: 手机没有对应缓存（首次播放会生成新缓存），非错误
    """
    r = {'file': os.path.basename(local_path), 'found': False, 'need': False,
         'ok': False, 'msg': '', 'cache_name': None}
    try:
        _, new_lrc, _ = core.read_embedded_lyric(local_path)
    except Exception as e:
        r['msg'] = '读内嵌歌词失败: %s' % e
        return r
    new_norm = _norm(new_lrc)
    new_texts = _lyric_texts(new_lrc)
    names, err = _cache_list()
    if err:
        r['msg'] = err
        return r
    strict, loose = [], []
    for name in names:
        raw = _cache_read(name)
        if not raw:
            continue
        # 严格：去时间戳后文字完全一致；宽松：前 12 句正文一致
        if _norm(raw) == new_norm:
            strict.append(name)
        elif new_texts and _lyric_texts(raw)[:12] == new_texts[:12]:
            loose.append(name)
    targets, how = (strict, '严格') if strict else (loose, '正文')
    if not targets:
        r['need'] = False
        r['msg'] = '手机无对应歌词缓存（首次播放会从内嵌生成新缓存，无需处理）'
        return r
    r['found'] = True
    r['need'] = True
    r['cache_name'] = targets[0]
    msgs, all_ok = [], True
    for name in targets:
        ok, msg = _cache_delete(name)
        all_ok = all_ok and ok
        msgs.append('%s %s' % (name[:12], msg))
    r['ok'] = all_ok
    r['msg'] = '%s匹配 %d 条 -> %s' % (how, len(targets), '；'.join(msgs))
    return r
