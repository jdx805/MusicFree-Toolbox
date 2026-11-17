#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内嵌歌词工具 · 核心层（纯函数，无界面）。
源层：QQ音乐搜索/歌词、LRCLIB 搜索/歌词；写入层：MP3 容错 ID3(新增/替换 USLT)、FLAC Vorbis。
写入后可校验：音频字节不变 + 歌词回读一致 + 结构自洽。
不改动 lyric_offset_tool.py（已验证的偏移工具），独立模块避免回归。
"""
import os, re, json, struct, ssl, time, threading, urllib.request, urllib.parse

# 复用已验证的 FLAC 块解析（纯函数，无副作用）
import lyric_offset_tool as base

CTX = ssl._create_unverified_context()
UA = {'User-Agent': 'Mozilla/5.0'}
QQ_SEARCH = 'https://c.y.qq.com/soso/fcgi-bin/client_search_cp'
QQ_LYRIC = 'https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg'
LRCLIB_SEARCH = 'https://lrclib.net/api/search'
LRCLIB_GET = 'https://lrclib.net/api/get'

# ---- QQ 请求节流 ----
# 实测：搜索 0.4~0.9s、歌词 0.1~0.2s；0.3s 间隔连打 8 次未限流。
# 取 1.5s 下限留安全余量，避免短时间连续搜索/拉取被判异常。
QQ_MIN_INTERVAL = 1.5
_qq_lock = threading.Lock()
_qq_last_ts = None      # 上一次 QQ 请求时间戳
_qq_last_gap = None     # 上次请求与再上一次的间隔（秒）


def _qq_throttle():
    """QQ 请求前调用：记录间隔，不足下限则等待。返回本次等待秒数。"""
    global _qq_last_ts, _qq_last_gap
    with _qq_lock:
        now = time.time()
        wait = 0.0
        if _qq_last_ts is not None:
            gap = now - _qq_last_ts
            _qq_last_gap = gap
            if gap < QQ_MIN_INTERVAL:
                wait = QQ_MIN_INTERVAL - gap
                time.sleep(wait)
        _qq_last_ts = time.time()
        return wait


def qq_interval_info():
    """返回 (上次 QQ 请求间隔秒数或 None, 强制下限秒数)。供界面写日志。"""
    with _qq_lock:
        return _qq_last_gap, QQ_MIN_INTERVAL


# ==================== 网络层 ====================
def _get(url, referer=None, timeout=15):
    h = dict(UA)
    if referer:
        h['Referer'] = referer
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=h), timeout=timeout, context=CTX
    ).read().decode('utf-8', 'replace')


def qq_search(keyword, n=10):
    """返回 [{mid,title,artist,album,duration,source:'QQ'}]。"""
    _qq_throttle()
    q = urllib.parse.quote(keyword)
    url = '%s?w=%s&format=json&n=%d&p=1' % (QQ_SEARCH, q, n)
    d = json.loads(_get(url, referer='https://y.qq.com/'))
    songs = (d.get('data') or {}).get('song', {}).get('list', []) or []
    out = []
    for s in songs:
        mid = s.get('songmid') or ''
        if not mid:
            continue
        out.append({
            'source': 'QQ', 'key': mid,
            'title': s.get('songname') or '',
            'artist': '/'.join(a.get('name', '') for a in (s.get('singer') or [])),
            'album': (s.get('albumname') or ''),
            'duration': s.get('interval') or '',
        })
    return out


def qq_lyric(mid):
    """返回明文带时间戳 LRC（nobase64=1）。失败抛错。"""
    _qq_throttle()
    url = (QQ_LYRIC + '?songmid=%s&format=json&inCharset=utf-8'
           '&outCharset=utf-8&nobase64=1' % mid)
    d = json.loads(_get(url, referer='https://y.qq.com/'))
    lyric = d.get('lyric', '') or ''
    if d.get('retcode') not in (0, '0', None) or not lyric:
        raise ValueError('QQ 无歌词 (retcode=%s)' % d.get('retcode'))
    return lyric


def lrclib_search(track, artist=''):
    """返回 [{id,title,artist,album,duration,source:'LRCLIB',has_synced}]。"""
    q = urllib.parse.quote((track + ' ' + artist).strip())
    url = LRCLIB_SEARCH + '?q=' + q
    arr = json.loads(_get(url))
    out = []
    for x in arr:
        oid = x.get('id')
        if not oid:
            continue
        out.append({
            'source': 'LRCLIB', 'key': oid,
            'title': x.get('trackName') or '',
            'artist': x.get('artistName') or '',
            'album': x.get('albumName') or '',
            'duration': ('%ds' % x['duration']) if x.get('duration') else '',
            'has_synced': bool(x.get('syncedLyrics')),
        })
    return out


def lrclib_get(oid):
    # 实测：/api/get?id=xxx 返回 400；正确端点是 /api/get/<id>
    d = json.loads(_get(LRCLIB_GET + '/' + urllib.parse.quote(str(oid))))
    lrc = d.get('syncedLyrics') or d.get('plainLyrics') or ''
    if not lrc:
        raise ValueError('LRCLIB 无歌词')
    return lrc


def fetch_lrc(cand):
    """按候选条目拉取歌词正文。"""
    if cand['source'] == 'QQ':
        return qq_lyric(cand['key'])
    if cand['source'] == 'LRCLIB':
        return lrclib_get(cand['key'])
    raise ValueError('未知来源: ' + str(cand.get('source')))


def search_all(title, artist='', sources=('QQ', 'LRCLIB')):
    """聚合搜索，单源失败不影响另一源。返回候选列表。"""
    out, errs = [], []
    kw = (title + ' ' + artist).strip() or title
    if 'QQ' in sources:
        try:
            out += qq_search(kw)
        except Exception as e:
            errs.append('QQ: %s' % e)
    if 'LRCLIB' in sources:
        try:
            out += lrclib_search(title, artist)
        except Exception as e:
            errs.append('LRCLIB: %s' % e)
    return out, errs


def parse_filename(path):
    """从「歌手 - 歌名.ext」解析 (歌手, 歌名)。失败返回 ('','')。"""
    name = os.path.splitext(os.path.basename(path))[0]
    m = re.split(r'\s+-\s+', name, maxsplit=1)
    if len(m) == 2 and m[0].strip() and m[1].strip():
        return m[0].strip(), m[1].strip()
    return '', name.strip()


def lyric_preview(lrc, n=6):
    """取前 n 条带时间戳的行做预览。"""
    lines = [l for l in lrc.splitlines() if re.match(r'^\[\d{1,2}:\d{2}', l)]
    return '\n'.join(lines[:n]) if lines else '\n'.join(lrc.splitlines()[:n])


# ==================== 写入层：MP3 容错 ID3 ====================
def _ss(b):
    return ((b[0] & 0x7f) << 21) | ((b[1] & 0x7f) << 14) | ((b[2] & 0x7f) << 7) | (b[3] & 0x7f)


def _es(n):
    return bytes([(n >> 21) & 0x7f, (n >> 14) & 0x7f, (n >> 7) & 0x7f, n & 0x7f])


def _frame_size(b, ver):
    return _ss(b) if ver == 4 else struct.unpack('>I', bytes(b))[0]


def id3_parse_tolerant(d):
    """容错解析：能跳过零填充 padding（B站下载的怪 ID3）。
    返回 (ver, [[fid,flags,body],...], audio_bytes)。"""
    if d[:3] != b'ID3':
        return 3, [], bytes(d)
    ver = d[3]
    end = 10 + _ss(d[6:10])
    if end > len(d):
        raise ValueError('ID3 长度超出文件')
    p, frames = 10, []
    while p + 10 <= end:
        fid = bytes(d[p:p + 4])
        if not fid.strip(b'\x00'):
            break  # padding 开始
        sz = _frame_size(d[p + 4:p + 8], ver)
        if sz == 0 or p + 10 + sz > end:
            break
        frames.append([fid.decode('latin-1'), bytes(d[p + 8:p + 10]),
                       bytes(d[p + 10:p + 10 + sz])])
        p += 10 + sz
    return ver, frames, bytes(d[end:])


def id3_build(ver, frames, audio):
    body = b''
    for fid, flags, b in frames:
        sz = _es(len(b)) if ver == 4 else struct.pack('>I', len(b))
        body += fid.encode('latin-1') + sz + flags + b
    return b'ID3' + bytes([ver, 0, 0]) + _es(len(body)) + body + audio


def _frame_text(fid, text):
    return (fid, b'\x00\x00', b'\x03' + text.encode('utf-8'))


def _make_uslt(lrc):
    """UTF-8(0x03) + 语言chi + 空描述(NUL) + 正文。"""
    return ('USLT', b'\x00\x00', b'\x03' + b'chi\x00' + lrc.encode('utf-8'))


def _read_uslt(frames):
    """从 frames 里回读 USLT 正文；无则 None。"""
    for fid, _, body in frames:
        if fid == 'USLT' and len(body) >= 5:
            rest = body[4:]
            nul = rest.find(b'\x00')
            if nul >= 0:
                return rest[nul + 1:].decode('utf-8', 'replace')
    return None


# ==================== 写入层：FLAC Vorbis ====================
def _flac_set_lyric(d, lrc, tags=None):
    blocks, audio = base.parse_flac(d)
    found = False
    for bi, (typ, last, body) in enumerate(blocks):
        if typ != 4:
            continue
        vendor, cs = base.parse_vorbis(body)
        cs = [bytes(c) for c in cs]

        def setkey(key, val):
            nonlocal cs
            hit = False
            for i, c in enumerate(cs):
                if c.startswith(key.encode() + b'='):
                    cs[i] = key.encode() + b'=' + val.encode('utf-8')
                    hit = True
            if not hit:
                cs.append(key.encode() + b'=' + val.encode('utf-8'))

        setkey('LYRICS', lrc)
        setkey('UNSYNCEDLYRICS', lrc)
        for k in ('TITLE', 'ARTIST', 'ALBUM'):
            if tags and tags.get(k):
                setkey(k, tags[k])
        blocks[bi][2] = base.build_vorbis(vendor, cs)
        found = True
        break
    if not found:
        raise ValueError('FLAC 无 Vorbis comment 块')
    return base.serialize_flac(blocks, audio), audio


def _flac_read_lyric(d):
    blocks, audio = base.parse_flac(d)
    for typ, last, body in blocks:
        if typ != 4:
            continue
        vendor, cs = base.parse_vorbis(body)
        for c in cs:
            if c.startswith(b'LYRICS=') or c.startswith(b'UNSYNCEDLYRICS='):
                return c.split(b'=', 1)[1].decode('utf-8', 'replace')
    return None


# ==================== 统一对外 API ====================
def embed(src, dst, lrc, tags=None):
    """把歌词写入 src，另存到 dst（源文件不动）。
    tags: {'title':..,'artist':..,'album':..} 可选，仅当为 None 时不写标签。
    返回 {'ok':bool,'kind':..,'msg':..}。写入后校验音频不变+歌词回读一致。"""
    tags = tags or {}
    d = open(src, 'rb').read()
    ext = os.path.splitext(src)[1].lower()
    if ext == '.mp3':
        ver, frames, audio = id3_parse_tolerant(d)
        audio_before = audio
        # 去掉旧歌词/标签帧，写新的；保留其它帧（如 PRIV XMP 水印）
        drop = {'USLT'}
        if tags.get('title'):
            drop.add('TIT2')
        if tags.get('artist'):
            drop.add('TPE1')
        if tags.get('album'):
            drop.add('TALB')
        frames = [f for f in frames if f[0] not in drop]
        if tags.get('title'):
            frames.insert(0, _frame_text('TIT2', tags['title']))
        if tags.get('artist'):
            frames.insert(0, _frame_text('TPE1', tags['artist']))
        if tags.get('album'):
            frames.insert(0, _frame_text('TALB', tags['album']))
        frames.append(_make_uslt(lrc))
        out = id3_build(ver if ver in (3, 4) else 3, frames, audio)
        open(dst, 'wb').write(out)

        rb = open(dst, 'rb').read()
        v2, f2, a2 = id3_parse_tolerant(rb)
        checks = {
            '音频字节不变': a2 == audio_before,
            '歌词回读一致': _read_uslt(f2) == lrc,
        }
        for key, fid in (('title', 'TIT2'), ('artist', 'TPE1'), ('album', 'TALB')):
            if tags.get(key):
                bs = [f[2] for f in f2 if f[0] == fid]
                checks['标签%s' % fid] = bool(bs) and bs[0][1:].decode('utf-8', 'replace') == tags[key]
        kind = 'mp3'
    elif ext == '.flac':
        out, audio_before = _flac_set_lyric(d, lrc, tags)
        open(dst, 'wb').write(out)
        rb = open(dst, 'rb').read()
        _, a2 = base.parse_flac(rb)
        checks = {'音频字节不变': a2 == audio_before, '歌词回读一致': _flac_read_lyric(rb) == lrc}
        kind = 'flac'
    else:
        return {'ok': False, 'kind': '', 'msg': '不支持的格式: ' + ext}

    ok = all(checks.values())
    msg = '; '.join('%s:%s' % (k, 'OK' if v else 'FAIL') for k, v in checks.items())
    return {'ok': ok, 'kind': kind, 'msg': msg}


def self_test():
    """纯函数自检：USLT 构造/回读、容错解析跳 padding、文件名解析。"""
    # 文件名
    assert parse_filename('YOASOBI - 群青.mp3') == ('YOASOBI', '群青')
    assert parse_filename('无分隔符.mp3')[0] == ''
    # 容错解析：合法帧 + padding + audio
    tag = (b'TIT2' + struct.pack('>I', 4) + b'\x00\x00' + b'\x03abc'
           + b'\x00' * 20)
    d = b'ID3' + bytes([3, 0, 0]) + _es(len(tag)) + tag + b'AUDIO\xff\xfb'
    ver, frames, audio = id3_parse_tolerant(d)
    assert ver == 3 and audio == b'AUDIO\xff\xfb' and frames[0][0] == 'TIT2'
    # USLT 往返
    lrc = '[00:01.00]hello\n[00:03.50]world'
    out = id3_build(3, [_make_uslt(lrc)], b'AUDIO')
    ver2, f2, a2 = id3_parse_tolerant(out)
    assert _read_uslt(f2) == lrc and a2 == b'AUDIO'
    assert b'chi' in f2[0][2][:4]
    print('lyric_embed_core self_test: OK')


if __name__ == '__main__':
    self_test()
