# -*- coding: utf-8 -*-
"""从 QQ 音乐歌单选中的 42 首，匹配 B 站 UP 主 JLRS-LeoFM 的视频。
现场版歌曲只接受标题含 Live/现场 的视频。
输出 JSON 到脚本工具目录，供后续生成下载清单。
"""
import json, re, sys, time, random, urllib.request, urllib.parse, os

sys.stdout.reconfigure(encoding='utf-8')

MID = '3493093607213343'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
COOKIE = 'buvid3=F0B4CC60-48CF-B11C-1D33-A2F6547E45FF40719infoc'
OUT = r'D:\Users\Documents\Workbuddy_workspace\脚本工具\_bili_match_result_20261116.json'

# (编号, 歌名原文, 歌手, 是否只接受现场版)
SEL = [
 (1,'죽을 만큼 아파서 (死一样的痛苦)','MC梦、Mellow',False),
 (3,'答案','杨坤、郭采洁',False),
 (4,'最爱','周慧敏',False),
 (8,'そばにいるね (留在我身边)','青山黛玛、SoulJa',False),
 (9,'够钟','周柏豪',False),
 (10,'会呼吸的痛','梁静茹',False),
 (18,'野孩子','杨千嬅',False),
 (20,'搁浅 (Live)','杨丞琳',True),
 (21,'平凡之路','朴树',False),
 (29,'孤雏','AGA',False),
 (30,'GQ','Lola Coca',False),
 (31,'A.I.N.Y.','G.E.M.邓紫棋',False),
 (32,'Tango','方大同',False),
 (33,'特别的人','方大同',False),
 (35,'凄美地','郭顶',False),
 (37,'水星记','郭顶',False),
 (38,'必杀技','古巨基',False),
 (40,'给未来的自己','梁静茹',False),
 (41,'陀飞轮','陈奕迅',False),
 (43,'离岸','苏晗',False),
 (45,'只要平凡','张杰、张碧晨',False),
 (47,'年少有为','李荣浩',False),
 (51,'老街','李荣浩',False),
 (54,'答应不爱你','郑中基',False),
 (55,'可惜我是水瓶座','杨千嬅',False),
 (56,'我不是伟人','陈小春',False),
 (57,'光年之外','G.E.M.邓紫棋',False),
 (60,'嚣张','en (王翊恩)',False),
 (62,'说书人','暗杠、寅子',False),
 (64,'悟空 (Live)','戴荃',True),
 (70,'想见你想见你想见你 (Live)','张杰',True),
 (72,'天涯','任贤齐',False),
 (73,'越难越爱 (粤语)','吴若希',False),
 (81,'囍帖街','谢安琪',False),
 (92,'命硬','侧田',False),
 (94,'我很快乐','刘惜君',False),
 (98,'飞女正传','杨千嬅',False),
 (102,'K歌之王 (粤语)','陈奕迅',False),
 (108,'李白','李荣浩',False),
 (109,'情歌','梁静茹',False),
 (115,'三人游','方大同',False),
 (116,'残酷游戏','卫兰',False),
]

def norm(s):
    s = re.sub(r'[（(][^)）]*[)）]', '', s or '')
    s = re.sub(r'[\s·・・:：\-—_!！?？\'’“”"\.,，。/\\\[\]【】《》|]+', '', s)
    return s.lower()

def core(s):
    return re.sub(r'[（(][^)）]*[)）]', '', s or '').strip()

def clean_title(t):
    return re.sub(r'<[^>]+>', '', t or '')

def extract_song_in_brackets(title):
    # 匹配《...》或「...」或〈...〉
    m = re.findall(r'[《〈「]([^》〉」]{1,60})[》〉」]', title)
    return m

def fetch(keyword, retry=3):
    url = 'https://api.bilibili.com/x/web-interface/search/type?' + urllib.parse.urlencode({
        'search_type': 'video', 'keyword': keyword, 'page': 1
    })
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': 'https://www.bilibili.com/', 'Cookie': COOKIE})
            with opener.open(req, timeout=15) as r:
                d = json.loads(r.read().decode('utf-8'))
            if d.get('code') == 0:
                return d.get('data', {}).get('result', []) or []
            if d.get('code') in (-799, -412):
                time.sleep(3 + i * 3)
        except Exception as e:
            time.sleep(2 + i * 2)
    return None

results = []
for idx, (no, song, artist, live_only) in enumerate(SEL, 1):
    kw = core(song) + ' 百万豪装录音棚'
    vlist = fetch(kw)
    hit = None
    if vlist is not None:
        cands = []
        for v in vlist:
            if str(v.get('mid')) != MID:
                continue
            title = clean_title(v.get('title'))
            brackets = extract_song_in_brackets(title)
            # 歌名匹配：书名号内的歌名 或 标题直接包含核心歌名
            name_ok = any(norm(b) == norm(song) for b in brackets) or (norm(core(song)) and norm(core(song)) in norm(title))
            if not name_ok:
                continue
            is_live = bool(re.search(r'live|现场|演唱会|LIVE', title, re.I))
            cands.append({'bvid': v.get('bvid'), 'title': title, 'live': is_live, 'mid': str(v.get('mid'))})
        if live_only:
            cands = [c for c in cands if c['live']]
        if cands:
            hit = cands[0]
            hit['all'] = [dict(c) for c in cands if c is not hit]
    rec = {'no': no, 'song': song, 'artist': artist, 'live_only': live_only, 'keyword': kw, 'hit': hit}
    results.append(rec)
    flag = ('OK  ' + hit['bvid']) if hit else 'NONE'
    print('[%2d/%d] %-4s %s | %s' % (idx, len(SEL), flag, song, artist), flush=True)
    json.dump(results, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    time.sleep(random.uniform(0.8, 1.6))

found = [r for r in results if r['hit']]
missing = [r for r in results if not r['hit']]
print('=== DONE ===', flush=True)
print('FOUND', len(found), 'MISSING', len(missing), flush=True)
