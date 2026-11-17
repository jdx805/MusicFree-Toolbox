"""修复 fix_lyrics_cn_20261117.py 引入的 ID3 损坏。
根因：原地替换 USLT 帧后未更新 ID3 头部 size，导致后续帧溢出/标签丢失。
做法：从备份读完好文件 -> 解析全部帧 -> 只替换 USLT -> 重新计算 ID3 size -> 写回。
校验：音频数据与备份逐字节一致、TIT2/TPE1 存在、ID3 size 自洽、USLT 内容正确。
"""
import os, struct, hashlib, shutil, json, sys

ROOT = r'D:\Users\Downloads\Recive\BiliTools'
BAK = r'D:\Users\Documents\Workbuddy_workspace\Recovery\歌词中文版修正-20261117'
FILES = ['YOASOBI - 群青.mp3', '小缘 - 无心.mp3', '米津玄师 - LOSER.mp3', '常颖杰 - 嘉宾.mp3']


def dec_synchsafe(b):
    return ((b[0] & 0x7f) << 21) | ((b[1] & 0x7f) << 14) | ((b[2] & 0x7f) << 7) | (b[3] & 0x7f)


def enc_synchsafe(n):
    return bytes([(n >> 21) & 0x7f, (n >> 14) & 0x7f, (n >> 7) & 0x7f, n & 0x7f])


def parse_tag(d):
    """返回 (version, flags, frames[(fid,flags,body)], audio_bytes, ok)"""
    if d[:3] != b'ID3':
        raise ValueError('无 ID3 头')
    ver, flags = d[3], d[4]
    size = dec_synchsafe(d[6:10])
    end = 10 + size
    frames = []
    p = 10
    ok = True
    while p + 10 <= end:
        fid = bytes(d[p:p + 4])
        if not all(65 <= c <= 90 or 48 <= c <= 57 for c in fid):
            ok = False
            break
        fsz = struct.unpack('>I', bytes(d[p + 4:p + 8]))[0]
        fflags = bytes(d[p + 8:p + 10])
        if p + 10 + fsz > end:
            ok = False
            break
        frames.append((fid, fflags, bytes(d[p + 10:p + 10 + fsz])))
        p += 10 + fsz
    if p != end:
        ok = False
    return ver, flags, frames, bytes(d[end:]), ok


def uslt_body(lyric):
    return b'\x03' + b'eng\x00' + lyric.encode('utf-8')


def get_lyric_from_current(path):
    """从当前(损坏)文件中尽力提取 USLT 正文：直接找 USLT 标记。"""
    d = open(path, 'rb').read()
    p = d.find(b'USLT', 10)
    if p < 0:
        raise ValueError('未找到 USLT')
    fsz = struct.unpack('>I', bytes(d[p + 4:p + 8]))[0]
    body = bytes(d[p + 10:p + 10 + fsz])
    # enc(1)+lang(3)+desc终止(1)
    return body[5:].decode('utf-8', 'replace')


def rebuild(path_bak, path_out, lyric):
    ver, flags, frames, audio, ok = parse_tag(open(path_bak, 'rb').read())
    if not ok:
        raise ValueError('备份文件 ID3 解析失败，不可用于修复')
    newframe = (b'USLT', b'\x00\x00', uslt_body(lyric))
    replaced = False
    out_frames = []
    for f in frames:
        if f[0] == b'USLT':
            out_frames.append(newframe)
            replaced = True
        else:
            out_frames.append(f)
    if not replaced:
        out_frames.append(newframe)
    tag = b''.join(fid + struct.pack('>I', len(body)) + fl + body for fid, fl, body in out_frames)
    header = b'ID3' + bytes([ver, flags, 0]) + enc_synchsafe(len(tag))
    with open(path_out, 'wb') as f:
        f.write(header + tag + audio)
    return audio, [f[0].decode('ascii', 'replace') for f in out_frames]


def verify(path, expect_audio, expect_lyric):
    d = open(path, 'rb').read()
    ver, flags, frames, audio, ok = parse_tag(d)
    names = [f[0].decode('ascii', 'replace') for f in frames]
    lyr = ''
    for fid, fl, body in frames:
        if fid == b'USLT':
            lyr = body[5:].decode('utf-8', 'replace')
    return {
        'id3_ok': ok,
        'audio_same': hashlib.md5(audio).hexdigest() == hashlib.md5(expect_audio).hexdigest(),
        'tit2': 'TIT2' in names,
        'tpe1': 'TPE1' in names,
        'uslt_same': lyr == expect_lyric,
        'frames': names,
        'lyric_lines': len([l for l in lyr.splitlines() if l.startswith('[')]),
    }


def main():
    write = '--write' in sys.argv
    for fn in FILES:
        p_cur = os.path.join(ROOT, fn)
        p_bak = os.path.join(BAK, fn)
        lyric = get_lyric_from_current(p_cur)
        print('\n====', fn, '====')
        print(' 提取当前歌词 %d 字，%d 行' % (len(lyric), len(lyric.splitlines())))
        if not write:
            print(' [预览模式，未写文件]')
            continue
        audio, names = rebuild(p_bak, p_cur, lyric)
        r = verify(p_cur, audio, lyric)
        print(' ID3自洽:%s 音频一致:%s TIT2:%s TPE1:%s USLT一致:%s 时间戳%d行' % (
            r['id3_ok'], r['audio_same'], r['tit2'], r['tpe1'], r['uslt_same'], r['lyric_lines']))
        print(' 帧:', ', '.join(r['frames']))


if __name__ == '__main__':
    main()
