"""修复 11-17 修 BOM 时的 bug：28 个 MP3 的 TIT2/TPE1/TALB 帧丢失 enc 字节导致乱码。
做法：从「修标签前」备份原样取回这 3 类帧（UTF-16 的 ff fe 是合法 BOM，必须保留），
      保留当前文件里的 USLT 歌词帧，重建 ID3v2.3。不重编码音频。
用法:
  python fix_bom_damage_20261117.py --test
  python fix_bom_damage_20261117.py
"""
import os, sys, struct, hashlib

ROOT = r'D:\Users\Downloads\Recive\BiliTools'
BAK = r'D:\Users\Documents\Workbuddy_workspace\Recovery\标签修复-20261117'
TEXT_FRAMES = ('TIT2', 'TPE1', 'TALB')


def ss(b):
    return ((b[0] & 0x7f) << 21) | ((b[1] & 0x7f) << 14) | ((b[2] & 0x7f) << 7) | (b[3] & 0x7f)


def enc_ss(n):
    return bytes([(n >> 21) & 0x7f, (n >> 14) & 0x7f, (n >> 7) & 0x7f, n & 0x7f])


def parse(data):
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


def build(ver, frames, audio):
    body = b''.join(r for _, r in frames)
    return b'ID3' + bytes([3, 0, 0]) + enc_ss(len(body)) + body + audio


def bad_frame(body):
    """帧体首字节必须是编码标识 0..3，否则视为损坏"""
    return not body or body[0] not in (0, 1, 2, 3)


def decode_frame(body):
    if not body or body[0] not in (0, 1, 2, 3):
        return '<损坏>'
    enc = body[0]
    codec = {0: 'latin-1', 1: 'utf-16', 2: 'utf-16-be', 3: 'utf-8'}.get(enc, 'utf-8')
    return body[1:].decode(codec, errors='replace').rstrip('\x00').strip('\ufeff').strip()


def fix(cur_data, bak_data):
    _, cur_frames, audio = parse(cur_data)
    _, bak_frames, _ = parse(bak_data)
    bmap = dict(bak_frames)
    out, restored = [], 0
    for fid, raw in cur_frames:
        if fid in TEXT_FRAMES and bad_frame(raw[10:]):
            if fid in bmap and not bad_frame(bmap[fid][10:]):
                out.append((fid, bmap[fid]))
                restored += 1
                continue
        out.append((fid, raw))
    return build(3, out, audio), restored


def audio_md5(data):
    _, _, a = parse(data)
    return hashlib.md5(a).hexdigest()


def uslt_of(data):
    _, frames, _ = parse(data)
    for fid, raw in frames:
        if fid == 'USLT':
            return raw
    return None


mode = sys.argv[1] if len(sys.argv) > 1 else ''
targets, total = [], 0
for f in sorted(os.listdir(ROOT)):
    if not f.lower().endswith('.mp3'):
        continue
    bp = os.path.join(BAK, f)
    if not os.path.isfile(bp):
        continue
    cur = open(os.path.join(ROOT, f), 'rb').read()
    bak = open(bp, 'rb').read()
    _, cf, _ = parse(cur)
    need = [fid for fid, raw in cf if fid in TEXT_FRAMES and bad_frame(raw[10:])]
    if not need:
        continue
    newdata, cnt = fix(cur, bak)
    # 校验：音频不变、歌词帧不变、恢复后的文本帧可正常解码
    checks = []
    checks.append(('音频MD5', audio_md5(cur) == audio_md5(newdata)))
    checks.append(('歌词帧保留', uslt_of(cur) == uslt_of(newdata)))
    _, nf, _ = parse(newdata)
    for fid, raw in nf:
        if fid in TEXT_FRAMES:
            checks.append((fid + '可解码', not bad_frame(raw[10:]) and bool(decode_frame(raw[10:]))))
    ok = all(v for _, v in checks)
    targets.append(f)
    total += cnt
    if not ok:
        print('校验失败，跳过:', f, checks)
        continue
    if mode == '--test':
        sample = [(fid, decode_frame(raw[10:])) for fid, raw in nf if fid in TEXT_FRAMES][:2]
        print('  可修 %d 帧: %s | 样本=%s' % (cnt, f, sample))
    else:
        tmp = os.path.join(ROOT, f + '.tmp')
        open(tmp, 'wb').write(newdata)
        vdata = open(tmp, 'rb').read()
        if audio_md5(vdata) != audio_md5(cur) or uslt_of(vdata) != uslt_of(cur):
            os.remove(tmp)
            print('  写后校验失败:', f)
            continue
        os.replace(tmp, os.path.join(ROOT, f))
        print('  已修 %d 帧: %s' % (cnt, f))

print('\n受影响文件:', len(targets), '| 恢复帧总数:', total, '| 模式:', mode or '正式')
