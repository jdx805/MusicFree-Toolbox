#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MusicFree 手机同步模块（供 lyric_offset_gui.py 调用）

职责：
  1. 把改后文件 push 到手机音乐目录
  2. 遍历手机 lyric/cache，按歌词内容定位目标缓存，用改后内嵌歌词覆盖 rawLrc
  3. 双重校验（push 文件 MD5、缓存内容回读）

设计要点（脱离 AI 的关键）：
  - 缓存按「歌词正文文字」匹配，不依赖 sha256 文件名 → 换手机哈希变了也能定位
  - 覆盖缓存而非删除 → 避免 App 从在线源拉回旧词
  - 新机无缓存时不报错，提示「首次播放会生成新缓存」即可
  - 全部只读 adb 采集 + 显式 push，不做界面点击

不依赖 lyric_offset_tool 以外的第三方库。
"""
import os
import re
import sys
import json
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


def _run(*args, timeout=60):
    """执行 adb 命令，返回 (returncode, stdout, stderr)，统一 UTF-8。"""
    p = subprocess.run([ADB] + list(args), capture_output=True, timeout=timeout)
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


def _cache_write(name, raw_lrc):
    """用新 rawLrc 覆盖手机缓存：写临时 json -> push -> 回读校验。"""
    fd, tmp = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'rawLrc': raw_lrc}, f, ensure_ascii=False)
        rc, out, err = _run('push', tmp, '%s/%s' % (CACHE_DIR, name))
        if rc != 0:
            return False, 'push 失败: ' + (err or out).strip()
        back = _cache_read(name)
        if back != raw_lrc:
            return False, '回读不一致'
        return True, 'OK'
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def force_stop():
    """强制停止 MusicFree（清掉内存里驻留的旧歌词对象）。返回 (ok, msg)。"""
    rc, out, err = _run('shell', 'am force-stop %s' % PACKAGE)
    return (rc == 0, '已强制停止 %s' % PACKAGE if rc == 0 else '强停失败: ' + (err or out).strip())


def restart_app():
    """拉起 MusicFree 到前台。用 monkey 按包名启动，跨版本不需知道入口 Activity。"""
    rc, out, err = _run('shell', 'monkey -p %s -c android.intent.category.LAUNCHER 1' % PACKAGE)
    return (rc == 0 and 'Events injected' in out,
            '已启动 %s' % PACKAGE if rc == 0 and 'Events injected' in out
            else '启动失败: ' + ((err or out).strip() or 'rc=%d' % rc))


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
    """为单个改后文件定位并覆盖手机缓存。
    返回 dict: found / need / ok / msg / cache_name
      - found: 找到缓存并已覆盖
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
    best = None
    for name in names:
        raw = _cache_read(name)
        if not raw:
            continue
        # 严格：去时间戳后文字完全一致；宽松：前 12 句正文一致
        if _norm(raw) == new_norm:
            best = (name, raw, 'strict')
            break
        if _lyric_texts(raw)[:12] == new_texts[:12] and new_texts:
            best = (name, raw, 'text')
    if best is None:
        r['need'] = False
        r['msg'] = '手机无对应歌词缓存（首次播放会从内嵌生成新缓存，无需处理）'
        return r
    name, _, how = best
    r['found'] = True
    r['need'] = True
    r['cache_name'] = name
    ok, msg = _cache_write(name, new_lrc)
    r['ok'] = ok
    r['msg'] = '%s匹配 %s -> %s' % ('严格' if how == 'strict' else '正文', name[:12], msg)
    return r
