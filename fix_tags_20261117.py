"""修正标签：1) 清 6 首 FLAC 的 kuwo 字段  2) 去 28 首 MP3 标签值开头的 BOM。
不重编码：MP3 只重写 ID3v2 帧、FLAC 只重写 VORBIS_COMMENT 块。
用法:
  python fix_tags_20261117.py --test   # 往返验证（用备份），不改正式文件
  python fix_tags_20261117.py           # 正式写入
"""
import os, sys, struct, hashlib

ROOT = r'D:\Users\Downloads\Recive\BiliTools'
BAK = r'D:\Users\Documents\Workbuddy_workspace\Recovery\标签修复-20261117'

KUWO_FILES = [
    '卫兰 - 心有不甘.flac', '周慧敏 - 最爱.flac', '周杰伦 - 夜曲.flac',
    '周杰伦 - 黑色毛衣.flac', '周杰伦&Lara梁心颐 - 珊瑚海.flac',
    '周杰伦&林迈可 - 四面楚歌.flac',
]
KUWO_KEYS = {'DESCRIPTION', 'GENRE', 'ALBUM'}
BOM = '\ufeff'


def ss(b):
    return ((b[0] & 0x7f) << 21) | ((b[1] & 0x7f) << 14) | ((b[2] & 0x7f) << 7) | (b[3] & 0x7f)


def enc_ss(n):
    return bytes([(n >> 21) & 0x7f, (n >> 14) & 0x7f, (n >> 7) & 0x7f, n & 0x7f])


# ---------- MP3 / ID3v2 ----------
def id3_parse(data):
    """返回 (ver, [(fid, raw_frame_body), ...], audio_bytes)；无 ID3 返回 (None, [], data)"""
    if data[:3] != b'ID3' or len(data) < 10:
        return None, [], data
    ver = data[3]
    size = ss(data[6:10])
    end = min(10 + size, len(data))
    frames, p = [], 10
    while p + 10 <= end:
        fid = data[p:p + 4]
        if not fid.strip(b'\x00'):
            break
        fsz = ss(data[p + 4:p + 8]) if ver == 4 else struct.unpack('>I', data[p + 4:p + 8])[0]
        if fsz == 0 or p + 10 + fsz > end:
            break
        frames.append((fid.decode('latin-1'), data[p:p + 10 + fsz]))
        p += 10 + fsz
    return ver, frames, data[10 + size:]


def id3_build(ver, frames, audio):
    body = b''.join(raw for _, raw in frames)
    # 重建 ID3v2.3 头（统一用 v3，兼容最好）
    hdr = b'ID3' + bytes([3, 0, 0]) + enc_ss(len(body))
    return hdr + body + audio


def text_frame_decode(raw):
    """raw = 10字节帧头 + 帧体；返回 (编码字节, 文本)"""
    body = raw[10:]
    if not body:
        return None, ''
    enc = body[0]
    codec = {0: 'latin-1', 1: 'utf-16-le', 2: 'utf-16-be', 3: 'utf-8'}.get(enc, 'utf-8')
    txt = body[1:].decode(codec, errors='replace').rstrip('\x00').strip()
    return enc, txt


def text_frame_encode(enc, txt):
    codec = {0: 'latin-1', 1: 'utf-16-le', 2: 'utf-16-be', 3: 'utf-8'}.get(enc, 'utf-8')
    payload = txt.encode(codec, errors='replace') + (b'\x00' if enc == 0 else b'\x00\x00')
    return payload


def strip_bom_text_frame(raw):
    enc, txt = text_frame_decode(raw)
    if enc is None or not txt.startswith(BOM):
        return raw, False
    new_txt = txt.lstrip(BOM)
    header = raw[:10]
    payload = text_frame_encode(enc, new_txt)
    # 更新帧大小（v3: 4字节大端）
    header = header[:4] + struct.pack('>I', len(payload)) + header[8:]
    return header + payload, True


# ---------- FLAC / Vorbis ----------
def flac_parse(data):
    if data[:4] != b'fLaC':
        return None, data
    pos, blocks = 4, []
    while True:
        h = data[pos]
        last, typ = bool(h & 0x80), h & 0x7f
        ln = int.from_bytes(data[pos + 1:pos + 4], 'big')
        blocks.append([typ, last, data[pos + 4:pos + 4 + ln]])
        pos += 4 + ln
        if last:
            break
    return blocks, data[pos:]


def flac_build(blocks, audio):
    out = bytearray(b'fLaC')
    for typ, last, body in blocks:
        out.append((0x80 if last else 0) | typ)
        out += len(body).to_bytes(3, 'big')
        out += body
    return bytes(out) + audio


def vorbis_parse(body):
    p = 0
    vl = int.from_bytes(body[p:p + 4], 'little'); p += 4
    vendor = body[p:p + vl]; p += vl
    cnt = int.from_bytes(body[p:p + 4], 'little'); p += 4
    comments = []
    for _ in range(cnt):
        cl = int.from_bytes(body[p:p + 4], 'little'); p += 4
        comments.append(body[p:p + cl]); p += cl
    return vendor, comments


def vorbis_build(vendor, comments):
    out = struct.pack('<I', len(vendor)) + vendor + struct.pack('<I', len(comments))
    for c in comments:
        out += struct.pack('<I', len(c)) + c
    return out


# ---------- 主处理 ----------
def fix_mp3(data):
    ver, frames, audio = id3_parse(data)
    if ver is None:
        return data, 0
    out, cnt = [], 0
    for fid, raw in frames:
        if fid in ('TIT2', 'TPE1', 'TALB', 'TCON'):
            new, changed = strip_bom_text_frame(raw)
            out.append((fid, new))
            cnt += int(changed)
        else:
            out.append((fid, raw))
    return id3_build(ver, out, audio), cnt


def fix_flac(data, clean_kuwo):
    blocks, audio = flac_parse(data)
    if blocks is None:
        return data, 0
    cnt = 0
    for i, (typ, last, body) in enumerate(blocks):
        if typ != 4:
            continue
        vendor, comments = vorbis_parse(body)
        new = []
        for c in comments:
            if b'=' not in c:
                new.append(c); continue
            k, v = c.split(b'=', 1)
            ku = k.decode('utf-8', 'replace').upper()
            s = v.decode('utf-8', 'replace')
            if clean_kuwo and ku in KUWO_KEYS and 'kuwo' in s.lower():
                cnt += 1
                continue
            if s.startswith(BOM):
                s = s.lstrip(BOM)
                cnt += 1
            new.append(k + b'=' + s.encode('utf-8'))
        blocks[i][2] = vorbis_build(vendor, new)
    return flac_build(blocks, audio), cnt


def audio_md5(data):
    """完整文件 MD5 之外，单独校验音频区字节（排除标签区）"""
    if data[:4] == b'fLaC':
        _, audio = flac_parse(data)
        return hashlib.md5(audio).hexdigest()
    _, _, audio = id3_parse(data)
    return hashlib.md5(audio).hexdigest()


targets = sorted(set(KUWO_FILES) | {f for f in os.listdir(ROOT) if f.lower().endswith('.mp3')})
mode = sys.argv[1] if len(sys.argv) > 1 else ''
total_changed = 0
checked = 0
for f in targets:
    src = os.path.join(ROOT, f)
    bak = os.path.join(BAK, f)
    if not os.path.isfile(src):
        continue
    if not os.path.isfile(bak):
        if f in KUWO_FILES or f.endswith('.mp3'):
            print('备份缺失:', f)
        continue
    orig = open(bak, 'rb').read()
    cur = open(src, 'rb').read()
    if cur != orig:
        # 夜曲已内嵌歌词，备份是内嵌前的；以当前文件为基准
        base = cur
    else:
        base = cur
    before = audio_md5(base)
    if f.lower().endswith('.flac'):
        newdata, cnt = fix_flac(base, f in KUWO_FILES)
    else:
        newdata, cnt = fix_mp3(base)
    after = audio_md5(newdata)
    if before != after:
        print('音频校验失败，跳过:', f)
        continue
    checked += 1
    total_changed += cnt
    if mode == '--test':
        if cnt:
            print('  待改 %d 处: %s' % (cnt, f))
        continue
    if cnt == 0:
        continue
    tmp = src + '.tmp'
    open(tmp, 'wb').write(newdata)
    if audio_md5(open(tmp, 'rb').read()) != before:
        os.remove(tmp)
        print('  写后校验失败:', f)
        continue
    os.replace(tmp, src)
    print('  已修 %d 处: %s' % (cnt, f))

print('\n检查文件数:', checked, '| 修改字段总数:', total_changed, '| 模式:', mode or '正式')
