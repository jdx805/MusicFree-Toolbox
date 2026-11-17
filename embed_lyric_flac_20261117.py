"""给单个 FLAC 内嵌 LRC 歌词（Vorbis LYRICS + UNSYNCEDLYRICS）。
用法：
  python embed_lyric_flac_20261117.py --test   # 只做往返验证，不写原文件
  python embed_lyric_flac_20261117.py          # 备份后正式写入
设计：不重编码，只改 VORBIS_COMMENT 块；校验音频帧字节 MD5 与原文件一致。
"""
import os, sys, struct, hashlib, shutil

FLAC = r'D:\Users\Downloads\Recive\BiliTools\周杰伦 - 夜曲.flac'
LYRIC_TXT = r'D:\Users\Documents\Workbuddy_workspace\脚本工具\_qq_lyric_yequ.txt'
BAK = r'D:\Users\Documents\Workbuddy_workspace\Recovery\歌词验证-20261117\周杰伦 - 夜曲.flac.bak'
LYRIC_KEYS = ('LYRICS', 'UNSYNCEDLYRICS', 'LYRIC')


def parse_flac(data):
    if data[:4] != b'fLaC':
        raise ValueError('不是 FLAC 文件')
    pos, blocks = 4, []
    while True:
        if pos + 4 > len(data):
            raise ValueError('metadata 截断')
        h = data[pos]
        last, typ = bool(h & 0x80), h & 0x7f
        ln = int.from_bytes(data[pos + 1:pos + 4], 'big')
        body = data[pos + 4:pos + 4 + ln]
        if len(body) != ln:
            raise ValueError('block 截断')
        blocks.append((typ, last, body))
        pos += 4 + ln
        if last:
            break
    return blocks, data[pos:]


def parse_vorbis(body):
    p = 0
    vl = int.from_bytes(body[p:p + 4], 'little'); p += 4
    vendor = body[p:p + vl]; p += vl
    cnt = int.from_bytes(body[p:p + 4], 'little'); p += 4
    comments = []
    for _ in range(cnt):
        cl = int.from_bytes(body[p:p + 4], 'little'); p += 4
        comments.append(body[p:p + cl]); p += cl
    return vendor, comments


def build_vorbis(vendor, comments):
    out = struct.pack('<I', len(vendor)) + vendor + struct.pack('<I', len(comments))
    for c in comments:
        out += struct.pack('<I', len(c)) + c
    return out


def serialize(blocks, audio):
    out = bytearray(b'fLaC')
    for typ, last, body in blocks:
        out.append((0x80 if last else 0) | typ)
        out += len(body).to_bytes(3, 'big')
        out += body
    out += audio
    return bytes(out)


def is_lyric_key(c):
    return c.split(b'=', 1)[0].decode('utf-8', 'replace').upper() in LYRIC_KEYS


def make(orig, lyric_text):
    blocks, audio = parse_flac(orig)
    out_blocks, done = [], False
    for typ, last, body in blocks:
        if typ == 4 and not done:
            vendor, comments = parse_vorbis(body)
            keep = [c for c in comments if not is_lyric_key(c)]
            lb = lyric_text.encode('utf-8')
            keep.append(b'LYRICS=' + lb)
            keep.append(b'UNSYNCEDLYRICS=' + lb)
            out_blocks.append((4, last, build_vorbis(vendor, keep)))
            done = True
        else:
            out_blocks.append((typ, last, body))
    if not done:
        raise ValueError('FLAC 无 VORBIS_COMMENT 块，本脚本不处理')
    return serialize(out_blocks, audio), audio


def verify(orig, newdata, lyric_text):
    ob, oa = parse_flac(orig)
    nb, na = parse_flac(newdata)
    if hashlib.md5(oa).hexdigest() != hashlib.md5(na).hexdigest():
        return False, '音频帧 MD5 变化（音频被破坏）'

    def comments_of(blocks):
        for typ, last, body in blocks:
            if typ == 4:
                return parse_vorbis(body)[1]
        return None

    oc, nc = comments_of(ob), comments_of(nb)
    if oc is None or nc is None:
        return False, '缺 VORBIS_COMMENT 块'
    # 原有非歌词标签必须逐字节保留
    if [c for c in oc if not is_lyric_key(c)] != [c for c in nc if not is_lyric_key(c)]:
        return False, '原有标签被改动'
    got = None
    for c in nc:
        if c.upper().startswith(b'LYRICS='):
            got = c.split(b'=', 1)[1].decode('utf-8', 'replace')
            break
    if got != lyric_text:
        return False, 'LYRICS 读回不符'
    return True, '音频帧 MD5 一致；原有标签保留；LYRICS %d 字' % len(got)


lyric = open(LYRIC_TXT, encoding='utf-8').read()
orig = open(FLAC, 'rb').read()
newdata, _ = make(orig, lyric)
ok, msg = verify(orig, newdata, lyric)
print('往返验证:', ok, '|', msg)
print('大小: %d -> %d (+%d 字节)' % (len(orig), len(newdata), len(newdata) - len(orig)))
if not ok:
    sys.exit(1)

if len(sys.argv) > 1 and sys.argv[1] == '--test':
    print('测试模式：未写原文件')
    sys.exit(0)

os.makedirs(os.path.dirname(BAK), exist_ok=True)
if os.path.exists(BAK):
    print('备份已存在，不覆盖:', BAK)
else:
    shutil.copy2(FLAC, BAK)
    print('已备份:', BAK)

tmp = FLAC + '.tmp'
open(tmp, 'wb').write(newdata)
ok2, msg2 = verify(orig, open(tmp, 'rb').read(), lyric)
if not ok2:
    os.remove(tmp)
    print('临时文件复验失败:', msg2)
    sys.exit(1)
os.replace(tmp, FLAC)
print('已写入歌词:', FLAC)
