# -*- coding: utf-8 -*-
"""用 wbi 签名接口拉取 UP 主全部投稿视频，按发布时间倒序，输出 bvid->行号。"""
import json, sys, time, urllib.request, urllib.parse, hashlib, re, random

sys.stdout.reconfigure(encoding='utf-8')
MID = '3493093607213343'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
COOKIE = 'buvid3=F0B4CC60-48CF-B11C-1D33-A2F6547E45FF40719infoc'
OUT = r'D:\Users\Documents\Workbuddy_workspace\脚本工具\_bili_space_index_20261116.json'

MIXIN = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]

def get(url, referer='https://www.bilibili.com/'):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={'User-Agent':UA,'Referer':referer,'Cookie':COOKIE})
    with op.open(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))

def mixin_key(img, sub):
    s = img + sub
    return ''.join(s[i] for i in MIXIN)[:32]

def sign(params, img, sub):
    params = dict(params)
    params['wts'] = int(time.time())
    clean = {k: ''.join(c for c in str(v) if c.isalnum() or c in '-_.:') for k,v in params.items()}
    query = urllib.parse.urlencode(sorted(clean.items()))
    w_rid = hashlib.md5((query + mixin_key(img, sub)).encode()).hexdigest()
    return query + '&w_rid=' + w_rid

nav = get('https://api.bilibili.com/x/web-interface/nav')
wbi = (nav.get('data') or {}).get('wbi_img') or {}
img_url = wbi.get('img_url',''); sub_url = wbi.get('sub_url','')
if not img_url or not sub_url:
    print('取 wbi key 失败:', nav.get('code'), nav.get('message')); sys.exit(1)
img_key = re.sub(r'\.[^.]+$','',img_url.rsplit('/',1)[-1])
sub_key = re.sub(r'\.[^.]+$','',sub_url.rsplit('/',1)[-1])
print('wbi key ok')

allv = []
pn = 1
while True:
    qs = sign({'mid':MID,'ps':100,'pn':pn,'order':'pubdate','order_sort':0,'platform':'web'}, img_key, sub_key)
    url = 'https://api.bilibili.com/x/space/wbi/arc/search?' + qs
    d = get(url, 'https://space.bilibili.com/%s/video' % MID)
    if d.get('code') != 0:
        print('pn', pn, '失败', d.get('code'), d.get('message'))
        time.sleep(4)
        if pn <= 1: sys.exit(1)
        break
    vlist = ((d.get('data') or {}).get('list') or {}).get('vlist') or []
    if not vlist:
        print('pn', pn, '空页，结束'); break
    allv.extend(vlist)
    print('pn', pn, 'got', len(vlist), '累计', len(allv), flush=True)
    json.dump([{'bvid':v.get('bvid'),'title':v.get('title'),'created':v.get('created')} for v in allv],
              open(OUT,'w',encoding='utf-8'), ensure_ascii=False, indent=1)
    if len(vlist) < 100: break
    pn += 1
    time.sleep(random.uniform(1.0, 2.0))

# 按发布时间倒序（B站空间默认），编号从 1 开始
allv.sort(key=lambda v: v.get('created') or 0, reverse=True)
idx = {v.get('bvid'): i+1 for i,v in enumerate(allv)}
json.dump({'total':len(allv),'index':idx,
           'list':[{'bvid':v.get('bvid'),'title':v.get('title'),'created':v.get('created'),'no':i+1} for i,v in enumerate(allv)]},
          open(OUT,'w',encoding='utf-8'), ensure_ascii=False, indent=1)
print('TOTAL', len(allv))
