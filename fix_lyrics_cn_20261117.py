"""把 4 首歌的内嵌歌词换成与音频一致的版本。
- 群青/无心/LOSER：日文原文(QQ时间轴，已验证对得上音频) + 中文译文(网易云)，双语交替显示
- 嘉宾：QQ 三本目填词的粤语版歌词(Edz 造梦赫兹)，替换原国语版

用法：
  python fix_lyrics_cn_20261117.py --preview   # 只打印结果，不写文件
  python fix_lyrics_cn_20261117.py             # 正式写入(先备份)
"""
import os, sys, json, re, urllib.request, struct, shutil

ROOT = r'D:\Users\Downloads\Recive\BiliTools'
CACHE = r'D:\Users\Documents\Workbuddy_workspace\脚本工具\_lyrics_cache_20261117.json'
BAK = r'D:\Users\Documents\Workbuddy_workspace\Recovery\歌词中文版修正-20261117'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

JP = {
    'YOASOBI - 群青.mp3': '1472480890',
    '小缘 - 无心.mp3': '30284319',
    '米津玄师 - LOSER.mp3': '512359195',
}
YUE_MID = '001E4w8y0dlMsk'
YUE_FILE = '常颖杰 - 嘉宾.mp3'

TS = re.compile(r'^\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]')
META = re.compile(r'^(词|曲|编曲|作词|作曲|填词|原唱|制作人|和声|混音|母带|录音|配唱|监制|乐器|吉他|贝斯|鼓|钢琴|弦乐|OP|制作|翻译水平有限|授权|未经著作权)\s*[：:]|^翻译水平有限')


def sec(line):
    m = TS.match(line)
    if not m:
        return None
    frac = (m.group(3) or '0').ljust(3, '0')[:3]
    return int(m.group(1)) * 60 + int(m.group(2)) + int(frac) / 1000.0


def stamp(s):
    m = int(s // 60)
    sec_ = s % 60
    return '[%02d:%05.2f]' % (m, sec_)


def get(url, headers):
    return opener.open(urllib.request.Request(url, headers=headers), timeout=20).read().decode('utf-8', 'replace')


def netease_tr(sid):
    d = json.loads(get('https://music.163.com/api/song/lyric?id=%s&lv=1&kv=1&tv=-1' % sid,
                       {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://music.163.com/', 'Cookie': 'appver=2.0.2'}))
    out = {}
    for line in (d.get('tlyric', {}).get('lyric', '') or '').splitlines():
        s = sec(line)
        if s is None:
            continue
        txt = TS.sub('', line).strip()
        if not txt or META.match(txt):
            continue
        out.setdefault(round(s, 2), txt)
    return out


def qq_yue(mid):
    u = ('https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg'
         '?songmid=%s&format=json&inCharset=utf-8&outCharset=utf-8&nobase64=1' % mid)
    d = json.loads(get(u, {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://y.qq.com/'}))
    return d.get('lyric', '')


def build_bilingual(qlyric, tr, gap=0.12):
    """按时间把中文译文配对到 QQ 日文行；译文插到对应日文行之后。
    配对规则：译词时间点 t 落在日文行 [t_i, t_{i+1}) 内则归到该行；一行多条译文合并。
    """
    tl = sorted(tr.items())  # [(sec, text)]
    out = []
    lines = qlyric.splitlines()
    # 先收集可锚定的日文行时间点
    idx_t = []
    for i, line in enumerate(lines):
        s = sec(line)
        if s is None:
            continue
        txt = TS.sub('', line).strip()
        # 标题行 / 词曲元信息行不参与配对
        if not txt or META.match(txt):
            continue
        # 标题行「歌名 - 歌手」不参与配对
        if ' - ' in txt and i < 3:
            continue
        idx_t.append((i, s))
    idx_t.sort(key=lambda x: x[1])

    # 译文按时间差最小配对到日文行（网易译词普遍比 QQ 日文早 0~0.6 秒）
    # 排除标题行(前3行且含「 - 」)，避免首句译文配到 00:00 的标题
    anchors = [(i, s) for i, s in idx_t if not (' - ' in TS.sub('', lines[i]).strip() and s < 3)]
    attach = {}  # 日文行号 -> [译文...]
    for ts, txt in tl:
        if not anchors:
            break
        best = min(anchors, key=lambda x: abs(x[1] - ts))
        if abs(best[1] - ts) > 3.0:
            continue  # 时间差过大不配对，避免错位
        attach.setdefault(best[0], []).append((ts, txt))

    for i, line in enumerate(lines):
        out.append(line)
        if i in attach:
            texts = [x[1] for x in sorted(attach[i])]
            # 去重相邻相同译文
            dedup = []
            for t in texts:
                if not dedup or dedup[-1] != t:
                    dedup.append(t)
            anchor = sec(line)
            for k, t in enumerate(dedup):
                # 同一日文行配多条译文时，给一个递增的小偏移，避免全部压在同一秒
                ts = anchor + gap * (k + 1)
                out.append(stamp(ts) + t)
    return '\n'.join(out), len(idx_t), len(tl)


# ---------- ID3 USLT (UTF-8) ----------
def find_id3_end(d):
    if d[:3] != b'ID3':
        return None
    return 10 + (((d[6] & 0x7f) << 21) | ((d[7] & 0x7f) << 14) | ((d[8] & 0x7f) << 7) | (d[9] & 0x7f))


def parse_frames(d, end):
    frames = []
    p = 10
    while p + 10 <= end:
        fid = bytes(d[p:p + 4])
        if not all(65 <= c <= 90 or 48 <= c <= 57 for c in fid):
            break
        sz = struct.unpack('>I', bytes(d[p + 4:p + 8]))[0]
        if sz == 0 or p + 10 + sz > end:
            break
        frames.append((fid, p, sz))
        p += 10 + sz
    return frames


def set_uslt(path, lyric):
    with open(path, 'rb') as f:
        d = bytearray(f.read())
    end = find_id3_end(d)
    if end is None:
        raise RuntimeError('无 ID3 头: ' + path)
    frames = parse_frames(d, end)
    body = b'\x03' + b'eng\x00' + lyric.encode('utf-8')  # enc(1)+lang(3)+desc空串终止(1)+正文
    new = b'USLT' + struct.pack('>I', len(body)) + b'\x00\x00' + body
    hits = [i for i, (f, _, _) in enumerate(frames) if f == b'USLT']
    if hits:
        _, p, sz = frames[hits[0]]
        d[p:p + 10 + sz] = new
    else:
        d[10:10] = new
    with open(path, 'wb') as f:
        f.write(d)


def verify(path, expect):
    with open(path, 'rb') as f:
        d = f.read()
    end = find_id3_end(d)
    for fid, p, sz in parse_frames(d, end):
        if fid == b'USLT':
            return bytes(d[p + 10:p + 10 + sz])[5:].decode('utf-8', 'replace') == expect
    return False


def main():
    preview = '--preview' in sys.argv
    cache = json.load(open(CACHE, encoding='utf-8'))
    results = {}

    print('===== 日语歌：日文原文 + 中文译文(双语) =====')
    for fn, sid in JP.items():
        tr = netease_tr(sid)
        new, nline, ntr = build_bilingual(cache[fn]['lyric'], tr)
        results[fn] = new
        print('\n--- %s：日文锚点%d行 / 网易译文%d条 / 输出%d行 ---' % (fn, nline, ntr, len(new.splitlines())))
        if preview:
            print('\n'.join(new.splitlines()[:22]))
            print('   ...')
            print('\n'.join(new.splitlines()[-10:]))

    print('\n===== 嘉宾：三本目粤语版 =====')
    yue = '\n'.join(l for l in qq_yue(YUE_MID).splitlines() if not l.startswith('[by:'))
    results[YUE_FILE] = yue
    if preview:
        print('共 %d 行' % len(yue.splitlines()))
        print('\n'.join(yue.splitlines()[:18]))

    if preview:
        print('\n[预览模式] 未写任何文件')
        return

    os.makedirs(BAK, exist_ok=True)
    for fn, lyric in results.items():
        path = os.path.join(ROOT, fn)
        bak = os.path.join(BAK, fn)
        if not os.path.exists(bak):
            shutil.copy2(path, bak)
        set_uslt(path, lyric)
        print('%s -> 写入完成 / 回读校验%s' % (fn, '通过' if verify(path, lyric) else '失败'))
    print('\n完成。备份目录:', BAK)


if __name__ == '__main__':
    main()
