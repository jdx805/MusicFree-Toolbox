"""只读诊断：4 首歌的 ID3 标签与 USLT 歌词当前状态。不写任何文件。"""
import os, struct, hashlib, re

ROOT = r'D:\Users\Downloads\Recive\BiliTools'
FILES = ['YOASOBI - 群青.mp3', '小缘 - 无心.mp3', '米津玄师 - LOSER.mp3', '常颖杰 - 嘉宾.mp3']

def dec_ss(b):
    return ((b[0]&0x7f)<<21)|((b[1]&0x7f)<<14)|((b[2]&0x7f)<<7)|(b[3]&0x7f)

def decode_txt(body):
    enc = body[0] if body else 0
    rest = body[1:]
    try:
        if enc == 0:
            return rest.decode('latin-1', 'replace')
        if enc == 1:
            return rest.decode('utf-16', 'replace')
        if enc == 2:
            return rest.decode('utf-16-be', 'replace')
        if enc == 3:
            return rest.decode('utf-8', 'replace')
    except Exception as e:
        return '<decode err %s>' % e
    return '?'

for fn in FILES:
    p = os.path.join(ROOT, fn)
    d = open(p, 'rb').read()
    print('\n========', fn, '========')
    print(' size=%d md5=%s' % (len(d), hashlib.md5(d).hexdigest()))
    if d[:3] != b'ID3':
        print(' !! 无 ID3 头'); continue
    ver, flags = d[3], d[4]
    size = dec_ss(d[6:10]); end = 10 + size
    print(' ID3v2.%d.%d tag_size=%d end=%d' % (ver, d[5], size, end))
    p2 = 10; frames = []; ok = True
    while p2 + 10 <= end:
        fid = bytes(d[p2:p2+4])
        if not all(65<=c<=90 or 48<=c<=57 for c in fid):
            ok = False; print(' !! 非帧标识 @%d: %r' % (p2, fid)); break
        fsz = struct.unpack('>I', bytes(d[p2+4:p2+8]))[0]
        fflag = bytes(d[p2+8:p2+10])
        if p2+10+fsz > end:
            ok = False; print(' !! 帧越界 @%d sz=%d' % (p2, fsz)); break
        body = bytes(d[p2+10:p2+10+fsz])
        frames.append((fid.decode('ascii','replace'), fflag, body))
        p2 += 10 + fsz
    print(' 帧(%d): %s  [解析%s]' % (len(frames), ', '.join(f[0] for f in frames), 'OK' if ok and p2==end else '异常 p2=%d end=%d'%(p2,end)))
    for fid, fl, body in frames:
        if fid in ('TIT2','TPE1','TALB'):
            print('  %s = %r' % (fid, decode_txt(body)))
        if fid == 'USLT':
            enc = body[0]; lang = body[1:4].decode('latin-1','replace')
            desc = body[4:].split(b'\x00',1)[0]
            lyric = body[5:].decode('utf-8', 'replace')
            lines = [l for l in lyric.splitlines() if l.startswith('[')]
            cn = len(re.findall(r'[\u4e00-\u9fff]', lyric))
            jp = len(re.findall(r'[\u3040-\u30ff]', lyric))
            print('  USLT enc=%d lang=%r desc=%r' % (enc, lang, desc))
            print('    歌词字节=%d 时间戳行=%d 中文字符=%d 日文假名=%d' % (len(lyric.encode('utf-8')), len(lines), cn, jp))
            print('    前6行:', ' | '.join(lyric.splitlines()[:6]))
