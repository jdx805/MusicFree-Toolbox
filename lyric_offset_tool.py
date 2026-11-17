#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内嵌歌词偏移工具（命令行交互版，后期可加 GUI）

流程：选文件夹 -> 选歌曲(可多选) -> 输入偏移秒数 -> 预览 -> 确认保存(先备份后写入并校验)

偏移语义（已按用户拍板）：
    用户输入的秒数沿用 MusicFree App 习惯 —— 正数 = 歌词提前，负数 = 歌词延后。
    歌词提前 = 时间戳减小，所以写入文件时对时间戳加的是 -user_offset。
    转换只发生在 user_to_timestamp_delta() 一处，避免历史性的方向搞反。

架构（便于后期加 GUI）：
    【核心层】纯函数，GUI 可直接调用，不碰 input/print：
        scan_audio_files / analyze / apply_offset / shift_lyric
        read_embedded_lyric / write_embedded_lyric
    【交互层】仅本文件末尾 interactive_main()，加 GUI 时替换这一段即可，核心不动。

用法：
    python lyric_offset_tool.py            # 进入交互
    python lyric_offset_tool.py --test     # 纯函数自检（不读写任何文件）
"""
import os
import re
import sys
import shutil
import struct
from datetime import datetime

DEFAULT_FOLDER = r'D:\Users\Downloads\Recive\BiliTools'
RECOVERY_ROOT = r'D:\Users\Documents\Workbuddy_workspace\Recovery'
AUDIO_EXT = ('.mp3', '.flac')

# 时间戳：[mm:ss] / [mm:ss.x] / [mm:ss.xx] / [mm:ss.xxx]
TS_RE = re.compile(r'\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]')


# ============================================================
# 核心层：时间戳
# ============================================================
def user_to_timestamp_delta(user_offset):
    """用户语义(正数=歌词提前) -> 时间戳增量。歌词提前=时间戳减小。"""
    return -float(user_offset)


def shift_lyric(lrc, delta_sec):
    """对所有时间戳加 delta_sec 秒（整数毫秒运算，避免浮点误差）。
    保留每处原始小数位数；负时间戳钳到 00:00 并计数。
    返回 (新歌词, 改动数, 钳零数)。
    """
    delta_ms = int(round(float(delta_sec) * 1000))
    changed = 0
    clamped = 0

    def repl(m):
        nonlocal changed, clamped
        mm, ss = int(m.group(1)), int(m.group(2))
        frac_raw = m.group(3)
        digits = len(frac_raw) if frac_raw else 0
        ms = (mm * 60 + ss) * 1000 + int((frac_raw or '0').ljust(3, '0')[:3])
        new_ms = ms + delta_ms
        if new_ms < 0:
            new_ms = 0
            clamped += 1
        changed += 1
        total_s, rem_ms = divmod(new_ms, 1000)
        nmm, nss = divmod(total_s, 60)
        if digits == 0:
            return '[%02d:%02d]' % (nmm, nss)
        if digits == 1:
            return '[%02d:%02d.%d]' % (nmm, nss, rem_ms // 100)
        if digits == 2:
            return '[%02d:%02d.%02d]' % (nmm, nss, rem_ms // 10)
        return '[%02d:%02d.%03d]' % (nmm, nss, rem_ms)

    return TS_RE.sub(repl, lrc), changed, clamped


def first_timestamp_line(lrc):
    """取第一句带时间戳的歌词行，用于预览「原 -> 新」；无则取第一行非空。"""
    for line in lrc.splitlines():
        if TS_RE.search(line):
            return line
    for line in lrc.splitlines():
        if line.strip():
            return line
    return '(无歌词)'


# ============================================================
# 核心层：MP3 / ID3 USLT
# ============================================================
def _ds(b):
    return ((b[0] & 0x7f) << 21) | ((b[1] & 0x7f) << 14) | ((b[2] & 0x7f) << 7) | (b[3] & 0x7f)


def _es(n):
    return bytes([(n >> 21) & 0x7f, (n >> 14) & 0x7f,
                  (n >> 7) & 0x7f, n & 0x7f])


def parse_mp3(d):
    """返回 (verflags, frames[[fid,flags,body],...], audio_bytes)。结构不自洽则抛错。"""
    if d[:3] != b'ID3':
        raise ValueError('无 ID3 头')
    end = 10 + _ds(d[6:10])
    if end > len(d):
        raise ValueError('ID3 长度超出文件')
    p = 10
    frames = []
    while p + 10 <= end:
        fid = bytes(d[p:p + 4])
        if not all(65 <= c <= 90 or 48 <= c <= 57 for c in fid):
            raise ValueError('坏帧标识 @%d' % p)
        sz = struct.unpack('>I', bytes(d[p + 4:p + 8]))[0]
        if p + 10 + sz > end:
            raise ValueError('帧越界 @%d' % p)
        frames.append([fid, bytes(d[p + 8:p + 10]), bytes(d[p + 10:p + 10 + sz])])
        p += 10 + sz
    if p != end:
        raise ValueError('ID3 不自洽 (p=%d end=%d)' % (p, end))
    return bytes([d[3], d[4], d[5]]), frames, bytes(d[end:])


def build_mp3(verflags, frames, audio):
    tag = b''.join(f[0] + struct.pack('>I', len(f[2])) + f[1] + f[2] for f in frames)
    return b'ID3' + verflags + _es(len(tag)) + tag + audio


def _split_uslt(body):
    """USLT body = enc(1)+lang(3)+desc(NUL结尾)+正文；desc 可能非空，按 NUL 切。"""
    enc, lang = body[0:1], body[1:4]
    rest = body[4:]
    nul = rest.find(b'\x00')
    if nul < 0:
        raise ValueError('USLT 缺 desc 终止符')
    return enc, lang, rest[:nul + 1], rest[nul + 1:]


def mp3_read(d):
    vf, frames, audio = parse_mp3(d)
    idx = next((i for i, f in enumerate(frames) if f[0] == b'USLT'), None)
    if idx is None:
        raise ValueError('无内嵌歌词(USLT)')
    enc, lang, desc, lyric_b = _split_uslt(frames[idx][2])
    lrc = lyric_b.decode('utf-8', 'replace')
    return {'vf': vf, 'frames': frames, 'audio': audio, 'idx': idx,
            'enc': enc, 'lang': lang, 'desc': desc, 'lrc': lrc}


def mp3_write(info, new_lrc):
    frames = info['frames']
    frames[info['idx']][2] = info['enc'] + info['lang'] + info['desc'] + new_lrc.encode('utf-8')
    return build_mp3(info['vf'], frames, info['audio'])


# ============================================================
# 核心层：FLAC / Vorbis comment
# 铁律：必须按块结构+Vorbis comment 解析重建，禁止字节级 re.search(b'LYRICS=')
# ============================================================
def parse_flac(data):
    if data[:4] != b'fLaC':
        raise ValueError('非 FLAC 文件')
    pos, blocks = 4, []
    while True:
        if pos + 4 > len(data):
            raise ValueError('FLAC 块头越界')
        h = data[pos]
        last, typ = bool(h & 0x80), h & 0x7f
        ln = int.from_bytes(data[pos + 1:pos + 4], 'big')
        body = data[pos + 4:pos + 4 + ln]
        if len(body) != ln:
            raise ValueError('FLAC 块体越界')
        blocks.append([typ, last, body])
        pos += 4 + ln
        if last:
            break
    return blocks, data[pos:]


def parse_vorbis(body):
    p = 0
    vl = int.from_bytes(body[p:p + 4], 'little'); p += 4
    vendor = body[p:p + vl]; p += vl
    cnt = int.from_bytes(body[p:p + 4], 'little'); p += 4
    cs = []
    for _ in range(cnt):
        cl = int.from_bytes(body[p:p + 4], 'little'); p += 4
        cs.append(body[p:p + cl]); p += cl
    return vendor, cs


def build_vorbis(vendor, cs):
    out = bytearray(struct.pack('<I', len(vendor)) + vendor + struct.pack('<I', len(cs)))
    for c in cs:
        out += struct.pack('<I', len(c)) + c
    return bytes(out)


def serialize_flac(blocks, audio):
    out = bytearray(b'fLaC')
    for typ, last, body in blocks:
        out.append((0x80 if last else 0) | typ)
        out += len(body).to_bytes(3, 'big')
        out += body
    return bytes(out) + audio


def flac_read(d):
    blocks, audio = parse_flac(d)
    hits = []
    for bi, (typ, last, body) in enumerate(blocks):
        if typ != 4:
            continue
        vendor, cs = parse_vorbis(body)
        for ci, c in enumerate(cs):
            if c.startswith(b'LYRICS=') or c.startswith(b'UNSYNCEDLYRICS='):
                key, val = c.split(b'=', 1)
                hits.append((bi, ci, key, val.decode('utf-8', 'replace')))
    if not hits:
        raise ValueError('无内嵌歌词(LYRICS)')
    return {'blocks': blocks, 'audio': audio, 'hits': hits, 'lrc': hits[0][3]}


def flac_write(info, new_lrc):
    blocks = [list(b) for b in info['blocks']]
    # 同一 Vorbis 块内可能有多个歌词字段，按原 key 分组改写
    by_block = {}
    for bi, ci, key, _ in info['hits']:
        by_block.setdefault(bi, []).append((ci, key))
    for bi, items in by_block.items():
        typ, last, body = blocks[bi]
        vendor, cs = parse_vorbis(body)
        cs = [bytes(c) for c in cs]
        for ci, key in items:
            cs[ci] = key + b'=' + new_lrc.encode('utf-8')
        blocks[bi][2] = build_vorbis(vendor, cs)
    return serialize_flac(blocks, info['audio'])


# ============================================================
# 核心层：统一读写入口 + 对外 API
# ============================================================
def read_embedded_lyric(path):
    """返回 (info_dict, lrc_text, kind)；kind in {'mp3','flac'}。"""
    d = open(path, 'rb').read()
    ext = os.path.splitext(path)[1].lower()
    if ext == '.mp3':
        info = mp3_read(d)
        return info, info['lrc'], 'mp3'
    if ext == '.flac':
        info = flac_read(d)
        return info, info['lrc'], 'flac'
    raise ValueError('不支持的格式: ' + ext)


def _verify(path, expected_lrc, audio_before):
    """写入后校验：结构自洽 + 音频字节不变 + 歌词==预期。"""
    d = open(path, 'rb').read()
    ext = os.path.splitext(path)[1].lower()
    if ext == '.mp3':
        vf, frames, audio = parse_mp3(d)
        idx = next((i for i, f in enumerate(frames) if f[0] == b'USLT'), None)
        if idx is None:
            return False, '校验失败: 写后无 USLT'
        _, _, _, lyric_b = _split_uslt(frames[idx][2])
        got = lyric_b.decode('utf-8', 'replace')
    else:
        blocks, audio = parse_flac(d)
        got = None
        for typ, last, body in blocks:
            if typ == 4:
                _, cs = parse_vorbis(body)
                for c in cs:
                    if c.startswith(b'LYRICS=') or c.startswith(b'UNSYNCEDLYRICS='):
                        got = c.split(b'=', 1)[1].decode('utf-8', 'replace')
                        break
        if got is None:
            return False, '校验失败: 写后无歌词'
    if audio != audio_before:
        return False, '校验失败: 音频字节变化'
    if got != expected_lrc:
        return False, '校验失败: 歌词不符'
    return True, 'OK'


def analyze(path, user_offset):
    """只读预览：返回该文件偏移后的信息字典，不写文件。"""
    r = {'file': os.path.basename(path), 'ok': False, 'error': None}
    try:
        info, lrc, kind = read_embedded_lyric(path)
        delta = user_to_timestamp_delta(user_offset)
        new, changed, clamped = shift_lyric(lrc, delta)
        audio = info['audio'] if kind == 'mp3' else info['audio']
        r.update(ok=True, kind=kind, delta=delta, lrc=lrc, new_lrc=new,
                 changed=changed, clamped=clamped,
                 old_first=first_timestamp_line(lrc),
                 new_first=first_timestamp_line(new))
    except Exception as e:
        r['error'] = '%s: %s' % (type(e).__name__, e)
    return r


def apply_offset(path, user_offset, backup_dir):
    """执行写入：先备份 -> 写入 -> 校验；失败从备份回滚。"""
    r = {'file': os.path.basename(path), 'ok': False, 'error': None,
         'backup': None, 'verify': None}
    tmp = analyze(path, user_offset)
    if not tmp['ok']:
        r['error'] = tmp['error']
        return r
    if tmp['changed'] == 0:
        r['error'] = '无时间戳可改（可能无歌词或格式异常）'
        return r
    os.makedirs(backup_dir, exist_ok=True)
    bak = os.path.join(backup_dir, tmp['file'])
    try:
        shutil.copy2(path, bak)
        r['backup'] = bak
        info, _, kind = read_embedded_lyric(path)
        audio_before = info['audio']
        if kind == 'mp3':
            out = mp3_write(info, tmp['new_lrc'])
        else:
            out = flac_write(info, tmp['new_lrc'])
        with open(path, 'wb') as f:
            f.write(out)
        ok, msg = _verify(path, tmp['new_lrc'], audio_before)
        r['verify'] = msg
        r['ok'] = ok
        r['changed'] = tmp['changed']
        r['clamped'] = tmp['clamped']
        if not ok:
            shutil.copy2(bak, path)
            r['error'] = '校验未过，已回滚: ' + msg
    except Exception as e:
        r['error'] = '%s: %s' % (type(e).__name__, e)
        if r['backup'] and os.path.exists(r['backup']):
            try:
                shutil.copy2(r['backup'], path)
                r['error'] += '（已回滚）'
            except Exception:
                pass
    return r


def scan_audio_files(folder):
    """扫描文件夹内 mp3/flac，返回排序后的绝对路径列表。"""
    if not os.path.isdir(folder):
        raise ValueError('文件夹不存在: ' + folder)
    return sorted(
        os.path.join(folder, f) for f in os.listdir(folder)
        if f.lower().endswith(AUDIO_EXT) and os.path.isfile(os.path.join(folder, f))
    )


# ============================================================
# 交互层（后期加 GUI 时替换这一段）
# ============================================================
def interactive_main():
    print('=' * 56)
    print(' 内嵌歌词偏移工具  |  正数=歌词提前  负数=歌词延后')
    print('=' * 56)

    # 1) 选文件夹
    folder = input('1) 歌曲文件夹（回车用默认）\n   [%s]\n   > ' % DEFAULT_FOLDER).strip()
    folder = folder or DEFAULT_FOLDER
    try:
        files = scan_audio_files(folder)
    except Exception as e:
        print('错误:', e)
        return
    if not files:
        print('该文件夹没有 mp3/flac 文件。')
        return

    # 2) 选歌曲
    print('\n2) 选择歌曲（找到 %d 个音频文件）' % len(files))
    for i, p in enumerate(files, 1):
        print('  [%d] %s' % (i, os.path.basename(p)))
    sel = input('   输入编号，逗号分隔（如 1,3,5）或 all 全选，q 退出\n   > ').strip().lower()
    if sel == 'q':
        return
    if sel == 'all':
        picked = files
    else:
        picked = []
        for tok in re.split(r'[,\s]+', sel):
            if tok.isdigit() and 1 <= int(tok) <= len(files):
                picked.append(files[int(tok) - 1])
        picked = list(dict.fromkeys(picked))  # 去重保序
    if not picked:
        print('未选中任何文件。')
        return
    print('   已选 %d 首' % len(picked))

    # 3) 输入偏移
    raw = input('\n3) 偏移秒数（正数=提前，负数=延后，如 7 / -2.5）\n   > ').strip()
    try:
        user_offset = float(raw)
    except ValueError:
        print('偏移必须是数字。')
        return

    # 4) 预览
    print('\n4) 预览（偏移 %+g 秒，实际写入时间戳 %+g 秒）' % (user_offset, user_to_timestamp_delta(user_offset)))
    previews = [analyze(p, user_offset) for p in picked]
    for r in previews:
        if r['ok']:
            print('  - %s [%s] 改%d处 钳零%d' % (r['file'], r['kind'], r['changed'], r['clamped']))
            print('      原: %s' % r['old_first'])
            print('      新: %s' % r['new_first'])
        else:
            print('  - %s 预览失败: %s' % (r['file'], r['error']))
    okp = [r for r in previews if r['ok'] and r['changed'] > 0]
    if not okp:
        print('\n没有可保存的歌曲。')
        return

    # 5) 确认保存
    confirm = input('\n5) 保存以上 %d 首？输入 y 确认，其他键取消\n   > ' % len(okp)).strip().lower()
    if confirm != 'y':
        print('已取消，未改动任何文件。')
        return

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_dir = os.path.join(RECOVERY_ROOT, '歌词偏移工具-' + stamp)
    print('\n备份目录:', backup_dir)
    results = []
    for p in picked:
        r = apply_offset(p, user_offset, backup_dir)
        results.append(r)
        if r['ok']:
            print('  OK   %s  改%d处 钳零%d 校验:%s' % (r['file'], r['changed'], r['clamped'], r['verify']))
        else:
            print('  FAIL %s  %s' % (r['file'], r['error']))

    ok_n = sum(1 for r in results if r['ok'])
    fail_n = len(results) - ok_n
    print('\n完成：成功 %d，失败 %d。备份在 %s' % (ok_n, fail_n, backup_dir))
    if fail_n:
        print('失败项可从备份目录对应文件 cp 回去回滚。')


# ============================================================
# 纯函数自检
# ============================================================
def self_test():
    d = user_to_timestamp_delta(7)
    assert abs(d - (-7.0)) < 1e-9, d
    new, ch, cl = shift_lyric('[00:01.49]test\n[00:00.30]x\n[00:05]y', d)
    # 保留各处原始小数位数：两位/两位/零位
    assert new == '[00:00.00]test\n[00:00.00]x\n[00:00]y' and ch == 3 and cl == 3, (new, ch, cl)
    # 延后（用户负数）
    new, ch, cl = shift_lyric('[01:02.345]a', user_to_timestamp_delta(-2.5))
    assert new == '[01:04.845]a' and ch == 1 and cl == 0, (new, ch, cl)
    # 毫秒不溢出
    new, ch, cl = shift_lyric('[00:00.999]a', user_to_timestamp_delta(-0.001))
    assert new == '[00:01.000]a', new
    # synchsafe 往返
    for n in (0, 127, 128, 300, 137709, 1000000):
        b = _es(n)
        assert _ds(b) == n, (n, b)
    print('自检通过：语义换算 / 时间戳平移 / 钳零 / 精度 / synchsafe 均正常')


if __name__ == '__main__':
    if '--test' in sys.argv:
        self_test()
    else:
        interactive_main()
