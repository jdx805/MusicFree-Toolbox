# -*- coding: utf-8 -*-
"""二次验证：对第一轮 NONE 的歌用纯歌名搜索，过滤 UP 主 mid；
同时输出已命中的标题供人工核对。"""
import json, re, sys, time, random, urllib.request, urllib.parse

sys.stdout.reconfigure(encoding='utf-8')
MID = '3493093607213343'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
COOKIE = 'buvid3=F0B4CC60-48CF-B11C-1D33-A2F6547E45FF40719infoc'
P = r'D:\Users\Documents\Workbuddy_workspace\脚本工具\_bili_match_result_20261116.json'

def norm(s):
    s = re.sub(r'[（(][^)）]*[)）]', '', s or '')
    return re.sub(r'[\s·・・:：\-—_!！?？\'’“”"\.,，。/\\\[\]【】《》|]+', '', s).lower()

def clean(t): return re.sub(r'<[^>]+>', '', t or '')
def brackets(t): return re.findall(r'[《〈「]([^》〉」]{1,60})[》〉」]', t)
def fetch(kw, retry=3):
    url = 'https://api.bilibili.com/x/web-interface/search/type?' + urllib.parse.urlencode({'search_type':'video','keyword':kw,'page':1})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers={'User-Agent':UA,'Referer':'https://www.bilibili.com/','Cookie':COOKIE})
            with op.open(req, timeout=15) as r: d = json.loads(r.read().decode('utf-8'))
            if d.get('code')==0: return d.get('data',{}).get('result',[]) or []
            if d.get('code') in (-799,-412): time.sleep(3+i*3)
        except Exception: time.sleep(2+i*2)
    return None

data = json.load(open(P, encoding='utf-8'))
print('=== 已命中 23 首标题（核对用）===')
for r in data:
    if r['hit']:
        h=r['hit']
        print('%3d %-28s | %s | %s' % (r['no'], r['song'], h['bvid'], h['title'][:70]))

print('\n=== NONE 二次验证 ===')
for r in data:
    if r['hit']: continue
    song=r['song']; kw=re.sub(r'[（(][^)）]*[)）]','',song).strip()
    vlist=fetch(kw)
    cands=[]
    if vlist is not None:
        for v in vlist:
            if str(v.get('mid'))!=MID: continue
            t=clean(v.get('title')); bs=brackets(t)
            if any(norm(b)==norm(song) for b in bs) or (norm(kw) and norm(kw) in norm(t)):
                islive=bool(re.search(r'live|现场|演唱会',t,re.I))
                if r['live_only'] and not islive: continue
                cands.append({'bvid':v.get('bvid'),'title':t,'live':islive})
    if cands:
        r['hit']=cands[0]
        r['hit']['all']=[dict(c) for c in cands if c is not r['hit']]
        r['verify']='round2'
        print('%3d FOUND %s | %s | %s' % (r['no'], cands[0]['bvid'], song, cands[0]['title'][:60]))
    else:
        print('%3d NONE  %s | %s' % (r['no'], song, r['artist']))
    json.dump(data, open(P,'w',encoding='utf-8'), ensure_ascii=False, indent=1)
    time.sleep(random.uniform(0.8,1.5))

found=[r for r in data if r['hit']]
print('\n=== FINAL FOUND %d / MISSING %d ===' % (len(found), len(data)-len(found)))
