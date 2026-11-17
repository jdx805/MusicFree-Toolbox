#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把荣耀 MusicFree 缓存里的正确歌词(697c, 57行)内嵌进「打上花火（粤语版）」。
源文件 = 电脑 BiliTools 那份(与手机上同一份 md5=31b31fc2)。
复用 embed_jiayibingding_20261117.py 的容错解析(跳零填充 padding) + USLT 构造。
保留原 TPE1/TIT2/PRIV(XMP) 帧，只新增 USLT；音频字节不动。
"""
import os, struct, json, shutil, hashlib

SRC = r'D:\Users\Downloads\Recive\BiliTools\邓志舜&HungryBaby - 打上花火（粤语版）.mp3'
PHONE_PULLED = r'D:\Users\Documents\Workbuddy_workspace\脚本工具\_dshh_fix\song.mp3'
LYRIC_JSON = r'D:\Users\Documents\Workbuddy_workspace\脚本工具\_dshh_fix\lyric.json'
BAK_DIR = r'D:\Users\Documents\Workbuddy_workspace\Recovery\打上花火歌词内嵌-20261117'
EXPECT_MD5 = '31b31fc2779c'


def _ss(b):
    return ((b[0] & 0x7f) << 21) | ((b[1] & 0x7f) << 14) | ((b[2] & 0x7f) << 7) | (b[3] & 0x7f)


def _es(n):
    return bytes([(n >> 21) & 0x7f, (n >> 14) & 0x7f, (n >> 7) & 0x7f, n & 0x7f])


def _frame_size(b, ver):
    return _ss(b) if ver == 4 else struct.unpack('>I', bytes(b))[0]


def id3_parse(data):
    """返回 (ver, [(fid, raw_frame)...], audio)。raw_frame = 10字节头 + body。跳过零填充。"""
    if data[:3] != b'ID3':
        return None, [], data
    ver = data[3]
    end = 10 + _ss(data[6:10])
    if end > len(data):
        raise ValueError('ID3 长度超出文件')
    p = 10
    frames = []
    while p + 10 <= end:
        fid = data[p:p + 4]
        if not fid.strip(b'\x00'):
            break  # padding
        fsz = _frame_size(data[p + 4:p + 8], ver)
        if fsz == 0 or p + 10 + fsz > end:
            break
        frames.append((fid.decode('latin-1'), bytes(data[p:p + 10 + fsz])))
        p += 10 + fsz
    return ver, frames, bytes(data[end:])


def id3_build(frames, audio, ver=3):
    body = b''.join(raw for _, raw in frames)
    return b'ID3' + bytes([ver, 0, 0]) + _es(len(body)) + body + audio


def make_uslt(lyric):
    """UTF-8(0x03) + 语言chi + 空描述(NUL) + 正文。"""
    payload = b'\x03' + b'chi\x00' + lyric.encode('utf-8')
    return b'USLT' + struct.pack('>I', len(payload)) + b'\x00\x00' + payload


def main():
    lyric = json.load(open(LYRIC_JSON, encoding='utf-8'))['rawLrc']
    assert len(lyric) > 100 and '[00:19.53]' in lyric, '歌词不像正确版，停止'

    # 源文件与手机拉取文件必须一致(防止推错版本)
    src_md5 = hashlib.md5(open(SRC, 'rb').read()).hexdigest()
    ph_md5 = hashlib.md5(open(PHONE_PULLED, 'rb').read()).hexdigest()
    print('源文件 md5=%s' % src_md5[:12])
    print('手机文件 md5=%s' % ph_md5[:12])
    assert src_md5 == ph_md5 and src_md5.startswith(EXPECT_MD5), '源文件与手机不一致，停止'

    d = open(SRC, 'rb').read()
    ver, frames, audio = id3_parse(d)
    audio_before = audio

    # 备份
    os.makedirs(BAK_DIR, exist_ok=True)
    bak = os.path.join(BAK_DIR, os.path.basename(SRC))
    shutil.copy2(SRC, bak)
    print('备份:', bak)

    # 保留原帧(TPE1/TIT2/PRIV)，去掉旧 USLT(本就无)，追加新 USLT
    keep = [(fid, raw) for fid, raw in frames if fid != 'USLT']
    new_frames = keep + [('USLT', make_uslt(lyric))]
    out = id3_build(new_frames, audio_before, ver=3)
    open(SRC, 'wb').write(out)
    print('写入完成: %d -> %d 字节' % (len(d), len(out)))

    # 校验
    ver2, frames2, audio2 = id3_parse(out)
    fm = dict(frames2)
    checks = {
        '音频字节不变': audio2 == audio_before,
        'USLT存在': 'USLT' in fm,
        'USLT编码UTF-8': fm.get('USLT', b'')[10] == 3,
        'USLT语言chi': fm.get('USLT', b'')[11:14] == b'chi',
        '歌词回读一致': fm.get('USLT', b'')[15:].decode('utf-8', 'replace') == lyric,
        'TPE1保留': fm.get('TPE1') == dict(frames).get('TPE1'),
        'TIT2保留': fm.get('TIT2') == dict(frames).get('TIT2'),
        'PRIV保留': fm.get('PRIV') == dict(frames).get('PRIV'),
    }
    print('\n=== 校验 ===')
    for k, v in checks.items():
        print('  %-16s %s' % (k, 'OK' if v else 'FAIL'))
    print('全部通过:', all(checks.values()))
    print('MD5: %s -> %s' % (src_md5, hashlib.md5(open(SRC, 'rb').read()).hexdigest()))
    if not all(checks.values()):
        shutil.copy2(bak, SRC)
        print('校验失败，已从备份还原')


if __name__ == '__main__':
    main()
