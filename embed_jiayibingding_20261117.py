#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给「李佳薇 - 甲乙丙丁粤语版.mp3」内嵌歌词+标签，并校验。
复用 embed_lyrics_all_20261117.py 的 ID3 解析/USLT 构造（能处理零填充 padding）。
"""
import os, struct, json, shutil, hashlib

SRC = r'D:\Users\Downloads\Recive\李佳薇 - 甲乙丙丁粤语版.mp3'
LYRIC_JSON = r'D:\Users\Documents\Workbuddy_workspace\脚本工具\_qq_lyric_jiayibingding_yue.json'
BAK_DIR = r'D:\Users\Documents\Workbuddy_workspace\Recovery\甲乙丙丁歌词-20261117'

TITLE = '甲乙丙丁 (粤语版)'
ARTIST = '李佳薇'
ALBUM = '甲乙丙丁 (粤语版)'


def _ss(b):
    return ((b[0] & 0x7f) << 21) | ((b[1] & 0x7f) << 14) | ((b[2] & 0x7f) << 7) | (b[3] & 0x7f)


def _es(n):
    return bytes([(n >> 21) & 0x7f, (n >> 14) & 0x7f, (n >> 7) & 0x7f, n & 0x7f])


def id3_parse(data):
    """返回 (ver, [(fid, raw_frame)...], audio)。raw_frame = 10字节头 + body。
    能跳过全零 padding。"""
    if data[:3] != b'ID3':
        return None, [], data
    ver = data[3]
    size = _ss(data[6:10])
    end = 10 + size
    if end > len(data):
        raise ValueError('ID3 长度超出文件')
    p = 10
    frames = []
    while p + 10 <= end:
        fid = data[p:p + 4]
        if not fid.strip(b'\x00'):
            break  # padding
        fsz = _es_size(data[p + 4:p + 8], ver)
        if fsz == 0 or p + 10 + fsz > end:
            break
        frames.append((fid.decode('latin-1'), bytes(data[p:p + 10 + fsz])))
        p += 10 + fsz
    return ver, frames, bytes(data[end:])


def _es_size(b, ver):
    if ver == 4:
        return _ss(b)
    return struct.unpack('>I', bytes(b))[0]


def id3_build(frames, audio):
    body = b''.join(raw for _, raw in frames)
    return b'ID3' + bytes([3, 0, 0]) + _es(len(body)) + body + audio


def frame_text(fid, text):
    """ID3v2.3 文本帧：UTF-8(0x03) + 文本。fid 为 str。"""
    payload = b'\x03' + text.encode('utf-8')
    return fid.encode('latin-1') + struct.pack('>I', len(payload)) + b'\x00\x00' + payload


def make_uslt(lyric):
    """UTF-8(0x03) + 语言chi + 空描述(NUL) + 正文。"""
    payload = b'\x03' + b'chi\x00' + lyric.encode('utf-8')
    return b'USLT' + struct.pack('>I', len(payload)) + b'\x00\x00' + payload


def read_back(data):
    """回读校验：解析 audio + 各帧文本。"""
    ver, frames, audio = id3_parse(data)
    out = {'audio_len': len(audio), 'frames': {}}
    for fid, raw in frames:
        body = raw[10:]
        if fid == 'USLT':
            out['frames'][fid] = {'enc': body[0], 'lang': body[1:4].decode('latin1'),
                                  'lyric': body[5:].decode('utf-8', 'replace')}
        elif fid in ('TIT2', 'TPE1', 'TALB'):
            out['frames'][fid] = body[1:].decode('utf-8', 'replace')
        else:
            out['frames'][fid] = len(body)
    return out


def main():
    lyric = json.load(open(LYRIC_JSON, encoding='utf-8'))['lyric']
    d = open(SRC, 'rb').read()
    md5_before = hashlib.md5(d).hexdigest()

    ver, frames, audio = id3_parse(d)
    audio_before = audio  # 音频原字节，用于校验不变

    # 备份原文件
    os.makedirs(BAK_DIR, exist_ok=True)
    bak = os.path.join(BAK_DIR, os.path.basename(SRC))
    shutil.copy2(SRC, bak)
    print('备份:', bak)

    # 重建帧：保留原帧(PRIV XMP)，去掉旧 TIT2/TPE1/TALB/USLT，写新的
    keep = [(fid, raw) for fid, raw in frames if fid not in ('TIT2', 'TPE1', 'TALB', 'USLT')]
    new_frames = [
        ('TIT2', frame_text('TIT2', TITLE)),
        ('TPE1', frame_text('TPE1', ARTIST)),
        ('TALB', frame_text('TALB', ALBUM)),
        ('USLT', make_uslt(lyric)),
    ] + keep
    out = id3_build(new_frames, audio_before)
    open(SRC, 'wb').write(out)
    print('写入完成: %d -> %d 字节' % (len(d), len(out)))

    # 校验
    rb = read_back(out)
    checks = {
        '音频字节不变': rb['audio_len'] == len(audio_before),
        'USLT存在': 'USLT' in rb['frames'],
        'USLT编码UTF-8': rb['frames'].get('USLT', {}).get('enc') == 3,
        'USLT语言chi': rb['frames'].get('USLT', {}).get('lang') == 'chi',
        '歌词回读一致': rb['frames'].get('USLT', {}).get('lyric') == lyric,
        'TIT2正确': rb['frames'].get('TIT2') == TITLE,
        'TPE1正确': rb['frames'].get('TPE1') == ARTIST,
        'TALB正确': rb['frames'].get('TALB') == ALBUM,
        'PRIV保留': 'PRIV' in rb['frames'],
    }
    print('\n=== 校验 ===')
    for k, v in checks.items():
        print('  %-16s %s' % (k, 'OK' if v else 'FAIL'))
    print('全部通过:', all(checks.values()))
    print('MD5: %s -> %s' % (md5_before, hashlib.md5(open(SRC, 'rb').read()).hexdigest()))
    if not all(checks.values()):
        shutil.copy2(bak, SRC)
        print('校验失败，已从备份还原')


if __name__ == '__main__':
    main()
