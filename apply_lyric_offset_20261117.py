"""把 MusicFree 的歌词偏移固化进歌词时间戳（电脑端源文件）。
数据来自手机 MMKV MediaExtra.本地 的最终 lyricOffset 值。
用法：
  python apply_lyric_offset_20261117.py --preview   # 只预览，不写
  python apply_lyric_offset_20261117.py             # 正式写入(先备份)
"""
import os, sys, re, struct, shutil

ROOT = r'D:\Users\Downloads\Recive\BiliTools'
BAK = r'D:\Users\Documents\Workbuddy_workspace\Recovery\歌词偏移固化-20261117'

# 文件名 -> (偏移秒, 类型)
OFFSETS = {
    '陈一发儿 - 童话镇.mp3': (-8.0, 'mp3'),
    '邓志舜&HungryBaby - 打上花火（粤语版）.mp3': (-7.0, 'mp3'),
    '邓紫棋 - A.I.N.Y. 爱你（重生版）.mp3': (-1.5, 'mp3'),
    '梁咏琪 - 灰姑娘.mp3': (7.0, 'mp3'),
    '林俊杰 - 修炼爱情.mp3': (-2.0, 'mp3'),
    '毛不易 - 消愁.mp3': (-1.5, 'mp3'),
    '朴树 - 平凡之路.mp3': (-1.5, 'mp3'),
    '微醺版 - 雨蝶 (R&B).mp3': (10.0, 'mp3'),
    '赵紫骅 - 可乐.mp3': (3.3, 'mp3'),
    '陈奕迅 - K歌之王.flac': (-1.5, 'flac'),
    '张拾一&鲜芋 - 我用什么把你留住.mp3': (10.0, 'mp3'),
}

TS = re.compile(r'\[(\d{1,2}):(\d{2})\.(\d{1,3})\]')


def shift_lyric(lrc, off):
    """对每行所有时间戳 ±off 秒；钳到 >=0。返回 (新词, 改动行数, 下溢钳行数)。"""
    changed = clamped = 0

    def repl(m):
        nonlocal changed, clamped
        mm, ss, frac = int(m.group(1)), int(m.group(2)), m.group(3)
        cur = mm * 60 + ss + int(frac.ljust(3, '0')[:3]) / 1000.0
        new = cur + off
        if new < 0:
            new = 0
            clamped += 1
        changed += 1
        nmm = int(new // 60)
        nss = new - nmm * 60
        return '[%02d:%05.2f]' % (nmm, nss)

    out = TS.sub(repl, lrc)
    return out, changed, clamped


# ---------- MP3 ID3 ----------
def ds(b):
    return ((b[0] & 0x7f) << 21) | ((b[1] & 0x7f) << 14) | ((b[2] & 0x7f) << 7) | (b[3] & 0x7f)


def es(n):
    return bytes([(n >> 21) & 0x7f, (n >> 14) & 0x7f, (n >> 7) & 0x7f, n & 0x7f])


def parse_mp3(d):
    end = 10 + ds(d[6:10]); p = 10; frames = []
    while p + 10 <= end:
        fid = bytes(d[p:p + 4])
        if not all(65 <= c <= 90 or 48 <= c <= 57 for c in fid):
            raise ValueError('坏帧 @%d' % p)
        sz = struct.unpack('>I', bytes(d[p + 4:p + 8]))[0]
        if p + 10 + sz > end:
            raise ValueError('帧溢出 @%d' % p)
        frames.append([fid, bytes(d[p + 8:p + 10]), bytes(d[p + 10:p + 10 + sz])])
        p += 10 + sz
    if p != end:
        raise ValueError('ID3 不自洽')
    return bytes([d[3], d[4], d[5]]), frames, bytes(d[end:])


def build_mp3(verflags, frames, audio):
    tag = b''.join(f[0] + struct.pack('>I', len(f[2])) + f[1] + f[2] for f in frames)
    return b'ID3' + verflags + es(len(tag)) + tag + audio


def mp3_update(path, off, preview):
    d = open(path, 'rb').read()
    vf, frames, audio = parse_mp3(d)
    idx = next((i for i, f in enumerate(frames) if f[0] == b'USLT'), None)
    if idx is None:
        return '无USLT'
    body = frames[idx][2]
    enc, lang, desc = body[0:1], body[1:4], body[4:5]
    lrc = body[5:].decode('utf-8', 'replace')
    new, changed, clamped = shift_lyric(lrc, off)
    if preview:
        return '偏移%+.1fs 改%d处时间戳 钳零%d' % (off, changed, clamped)
    frames[idx][2] = enc + lang + desc + new.encode('utf-8')
    with open(path, 'wb') as f:
        f.write(build_mp3(vf, frames, audio))
    # 校验
    d2 = open(path, 'rb').read()
    vf2, fr2, au2 = parse_mp3(d2)
    ok_audio = au2 == audio
    ok_lyric = fr2[idx][2][5:].decode('utf-8', 'replace') == new
    return '偏移%+.1fs 改%d处 钳零%d 音频一致:%s 歌词一致:%s' % (
        off, changed, clamped, ok_audio, ok_lyric)


# ---------- FLAC Vorbis ----------
# 铁律：FLAC 歌词必须按「块结构 → Vorbis comment」解析后重建，
# 绝不能用字节级 re.search(b'LYRICS=') 定位——会把文件写坏(膨胀/音频帧丢失)。
def parse_flac(data):
    pos, blocks = 4, []
    while True:
        h = data[pos]; last, typ = bool(h & 0x80), h & 0x7f
        ln = int.from_bytes(data[pos + 1:pos + 4], 'big')
        body = data[pos + 4:pos + 4 + ln]
        blocks.append([typ, last, body]); pos += 4 + ln
        if last:
            break
    return blocks, data[pos:]


def parse_vorbis(body):
    p = 0; vl = int.from_bytes(body[p:p + 4], 'little'); p += 4
    vendor = body[p:p + vl]; p += vl
    cnt = int.from_bytes(body[p:p + 4], 'little'); p += 4
    cs = []
    for _ in range(cnt):
        cl = int.from_bytes(body[p:p + 4], 'little'); p += 4
        cs.append(body[p:p + cl]); p += cl
    return vendor, cs


def build_vorbis(vendor, cs):
    out = struct.pack('<I', len(vendor)) + vendor + struct.pack('<I', len(cs))
    for c in cs:
        out += struct.pack('<I', len(c)) + c
    return out


def serialize_flac(blocks, audio):
    out = bytearray(b'fLaC')
    for typ, last, body in blocks:
        out.append((0x80 if last else 0) | typ)
        out += len(body).to_bytes(3, 'big')
        out += body
    return bytes(out) + audio


def flac_update(path, off, preview):
    d = open(path, 'rb').read()
    blocks, audio = parse_flac(d)
    changed = clamped = 0
    for bi, (typ, last, body) in enumerate(blocks):
        if typ != 4:
            continue
        vendor, cs = parse_vorbis(body)
        ncs = []
        for c in cs:
            if c.startswith(b'LYRICS=') or c.startswith(b'UNSYNCEDLYRICS='):
                key, val = c.split(b'=', 1)
                new, ch, cl = shift_lyric(val.decode('utf-8'), off)
                changed += ch; clamped += cl
                ncs.append(key + b'=' + new.encode('utf-8'))
            else:
                ncs.append(c)
        blocks[bi][2] = build_vorbis(vendor, ncs)
    if preview:
        return '偏移%+.1fs 改%d处时间戳 钳零%d' % (off, changed, clamped)
    nd = serialize_flac(blocks, audio)
    with open(path, 'wb') as f:
        f.write(nd)
    d2 = open(path, 'rb').read()
    b2, a2 = parse_flac(d2)
    ok_audio = (a2 == audio)
    ok_lyric = False
    for typ, last, body in b2:
        if typ == 4:
            v, cs = parse_vorbis(body)
            for c in cs:
                if c.startswith(b'LYRICS='):
                    ok_lyric = bool(re.search(r'\[\d{2}:\d{2}', c.decode('utf-8', 'replace')))
    return '偏移%+.1fs 改%d处 钳零%d 音频一致:%s 歌词一致:%s' % (
        off, changed, clamped, ok_audio, ok_lyric)


def main():
    preview = '--preview' in sys.argv
    print('===== %s =====' % ('预览' if preview else '正式写入'))
    if not preview:
        os.makedirs(BAK, exist_ok=True)
    for fn, (off, kind) in OFFSETS.items():
        path = os.path.join(ROOT, fn)
        if not os.path.exists(path):
            print('%s -> 文件不存在' % fn)
            continue
        if not preview:
            bak = os.path.join(BAK, fn)
            if not os.path.exists(bak):
                shutil.copy2(path, bak)
        r = mp3_update(path, off, preview) if kind == 'mp3' else flac_update(path, off, preview)
        print('%s -> %s' % (fn, r))


if __name__ == '__main__':
    main()
