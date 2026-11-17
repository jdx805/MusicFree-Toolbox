"""全量内嵌歌词：MP3 写 ID3v2 USLT，FLAC 写 Vorbis LYRICS/UNSYNCEDLYRICS。
判据：歌名精确匹配（归一化后相等）才接受，歌手不作为否决（歌词随歌名走）。
用法：
  python embed_lyrics_all_20261117.py --probe   # 只统计覆盖率，抓歌词存缓存，不写文件
  python embed_lyrics_all_20261117.py --test    # 用备份做往返验证，不写正式文件
  python embed_lyrics_all_20261117.py           # 正式写入
"""
import os, sys, json, re, time, struct, urllib.request, urllib.parse, unicodedata, hashlib

ROOT = r'D:\Users\Downloads\Recive\BiliTools'
PLAYLIST = r'D:\Users\Documents\Workbuddy_workspace\脚本工具\_qq_playlist_9381017819.json'
CACHE = r'D:\Users\Documents\Workbuddy_workspace\脚本工具\_lyrics_cache_20261117.json'
BAK = r'D:\Users\Documents\Workbuddy_workspace\Recovery\歌词全量-20261117'
LYRIC_KEYS = ('LYRICS', 'UNSYNCEDLYRICS', 'LYRIC')
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://y.qq.com/'})
    return opener.open(req, timeout=15).read().decode('utf-8', 'replace')


def norm(s):
    s = unicodedata.normalize('NFKC', str(s or ''))
    s = re.sub(r'\s*[\(（][^)）]*[)）]\s*$', '', s)  # 去结尾版本括号
    return re.sub(r'\s+', '', s).lower()


def parse_name(f):
    stem = os.path.splitext(f)[0]
    parts = re.split(r'\s+-\s+', stem, maxsplit=1)
    return (parts[1], parts[0]) if len(parts) == 2 else (stem, '')


def load_playlist_mids():
    d = json.load(open(PLAYLIST, encoding='utf-8'))
    sl = d['data']['cdlist'][0]['songlist']
    by = {}
    for x in sl:
        n = norm(x.get('songname'))
        if n and n not in by:
            by[n] = (x.get('songmid'), x.get('songname'))
    return by


def search_mid(song, artist):
    q = urllib.parse.quote((song + ' ' + artist).strip())
    url = 'https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w=%s&format=json&n=10' % q
    try:
        d = json.loads(http_get(url))
        songs = (d.get('data') or {}).get('song', {}).get('list') or []
        target = norm(song)
        for s in songs:
            if norm(s.get('songname')) == target and s.get('songmid'):
                return s['songmid']
    except Exception as e:
        print('    搜索失败:', e)
    return None


def fetch_lyric(mid):
    url = ('https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg'
           '?songmid=%s&format=json&inCharset=utf-8&outCharset=utf-8&nobase64=1' % mid)
    try:
        d = json.loads(http_get(url))
        if d.get('retcode') != 0:
            return '', 'retcode=%s' % d.get('retcode')
        lc = d.get('lyric') or ''
        if not lc.strip():
            return '', '空歌词'
        # 必须含时间戳行才算真歌词（排除纯「纯音乐，请欣赏」）
        if not re.search(r'\[\d{1,2}:\d{2}(?:\.\d+)?\]', lc):
            return '', '无时间戳(纯音乐?)'
        return lc, ''
    except Exception as e:
        return '', 'ERR:%s' % e


def probe():
    files = sorted(f for f in os.listdir(ROOT) if f.lower().endswith(('.mp3', '.flac')))
    pl = load_playlist_mids()
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding='utf-8'))
    stats = {'pl': 0, 'search': 0, 'ok': 0, 'nolrc': 0, 'nomid': 0}
    for i, f in enumerate(files, 1):
        song, artist = parse_name(f)
        if f in cache and cache[f].get('lyric'):
            stats['ok'] += 1
            continue
        n = norm(song)
        mid, src = pl.get(n, (None, ''))
        if mid:
            stats['pl'] += 1
            src = '歌单'
        else:
            mid = search_mid(song, artist)
            time.sleep(0.3)
            if mid:
                stats['search'] += 1
                src = '搜索'
        if not mid:
            stats['nomid'] += 1
            cache[f] = {'song': song, 'artist': artist, 'mid': '', 'lyric': '', 'err': '未找到songmid'}
            print('%2d %-40s 无mid' % (i, f[:40]))
            continue
        lc, err = fetch_lyric(mid)
        time.sleep(0.3)
        cache[f] = {'song': song, 'artist': artist, 'mid': mid, 'src': src, 'lyric': lc, 'err': err}
        if lc:
            stats['ok'] += 1
        else:
            stats['nolrc'] += 1
        print('%2d %-40s mid=%s %s %s' % (i, f[:40], mid, src, ('OK %d字' % len(lc)) if lc else ('✗ ' + err)))
        json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n=== 覆盖统计 ===')
    print('总歌曲:', len(files), '| 歌单命中:', stats['pl'], '| 搜索命中:', stats['search'])
    print('有歌词:', stats['ok'], '| 无歌词:', stats['nolrc'], '| 无 mid:', stats['nomid'])
    print('缓存:', CACHE)


# ---------- ID3v2 ----------
def ss(b):
    return ((b[0] & 0x7f) << 21) | ((b[1] & 0x7f) << 14) | ((b[2] & 0x7f) << 7) | (b[3] & 0x7f)


def enc_ss(n):
    return bytes([(n >> 21) & 0x7f, (n >> 14) & 0x7f, (n >> 7) & 0x7f, n & 0x7f])


def id3_parse(data):
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
    hdr = b'ID3' + bytes([3, 0, 0]) + enc_ss(len(body))
    return hdr + body + audio


def make_uslt(lyric):
    payload = b'\x03' + b'chi\x00' + lyric.encode('utf-8')  # UTF-8, 语言chi, 空描述
    return b'USLT' + struct.pack('>I', len(payload)) + b'\x00\x00' + payload


def embed_mp3(data, lyric):
    ver, frames, audio = id3_parse(data)
    if ver is None:
        # 无 ID3：在音频前造一个
        return id3_build(3, [('USLT', make_uslt(lyric))], data), 1
    out, cnt = [], 0
    for fid, raw in frames:
        if fid == 'USLT':
            out.append(('USLT', make_uslt(lyric)))
            cnt += 1
        else:
            out.append((fid, raw))
    if cnt == 0:
        out.append(('USLT', make_uslt(lyric)))
        cnt = 1
    return id3_build(ver, out, audio), cnt


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


def embed_flac(data, lyric):
    blocks, audio = flac_parse(data)
    if blocks is None:
        return data, 0
    cnt = 0
    for i, (typ, last, body) in enumerate(blocks):
        if typ != 4:
            continue
        vendor, comments = vorbis_parse(body)
        new = [c for c in comments
               if b'=' not in c or c.split(b'=', 1)[0].decode('utf-8', 'replace').upper() not in LYRIC_KEYS]
        lb = lyric.encode('utf-8')
        new.append(b'LYRICS=' + lb)
        new.append(b'UNSYNCEDLYRICS=' + lb)
        blocks[i][2] = vorbis_build(vendor, new)
        cnt = 1
    return flac_build(blocks, audio), cnt


def audio_md5(data):
    if data[:4] == b'fLaC':
        _, a = flac_parse(data)
        return hashlib.md5(a).hexdigest()
    _, _, a = id3_parse(data)
    return hashlib.md5(a).hexdigest()


def run(mode):
    cache = json.load(open(CACHE, encoding='utf-8'))
    targets = {f: c for f, c in cache.items() if c.get('lyric')}
    print('待写入:', len(targets), '| 模式:', mode)
    if mode == '--test':
        if not os.path.isdir(BAK):
            print('备份不存在，无法测试'); return
        ok = 0
        for f, c in targets.items():
            p = os.path.join(BAK, f)
            if not os.path.isfile(p):
                print('  备份缺失:', f); continue
            orig = open(p, 'rb').read()
            newdata, _ = embed_flac(orig, c['lyric']) if f.lower().endswith('.flac') else embed_mp3(orig, c['lyric'])
            same = audio_md5(orig) == audio_md5(newdata)
            ok += same
            if not same:
                print('  音频校验失败:', f)
        print('往返测试通过:', ok, '/', len(targets))
        return
    # 正式写入
    os.makedirs(BAK, exist_ok=True)
    done = 0
    for f, c in sorted(targets.items()):
        src = os.path.join(ROOT, f)
        bak = os.path.join(BAK, f)
        if not os.path.isfile(src):
            print('  源文件缺失:', f); continue
        if not os.path.isfile(bak):
            import shutil
            shutil.copy2(src, bak)
        orig = open(src, 'rb').read()
        before = audio_md5(orig)
        newdata, _ = embed_flac(orig, c['lyric']) if f.lower().endswith('.flac') else embed_mp3(orig, c['lyric'])
        if audio_md5(newdata) != before:
            print('  音频校验失败，跳过:', f); continue
        tmp = src + '.tmp'
        open(tmp, 'wb').write(newdata)
        if audio_md5(open(tmp, 'rb').read()) != before:
            os.remove(tmp); print('  写后校验失败:', f); continue
        os.replace(tmp, src)
        done += 1
    print('正式写入完成:', done, '/', len(targets))


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == '--probe':
        probe()
    else:
        run(mode)
