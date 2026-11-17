# -*- coding: utf-8 -*-
"""整理 BiliTools\新增 目录：按「歌手 - 歌名」重命名 + 重写 title/artist 标签。
支持 mp3(ID3v2.3) 与 flac(Vorbis comment)，纯标准库。
用法: python musicfree_rename_新增_20261116.py [--test]
"""
import os, sys, struct, hashlib, shutil
sys.stdout.reconfigure(encoding='utf-8')

SRC = r'D:\Users\Downloads\Recive\BiliTools\新增'
BAK = r'D:\Users\Documents\Workbuddy_workspace\Recovery\BiliTools新增-20261116'
KEEP = os.path.join(BAK, '被替换的原文件')
BATCH = 10

# (源文件名, 目标文件名, title, artist)
MAP = [
 ('GQ.mp3','Lola Coca - GQ.mp3','GQ','Lola Coca'),
 ('Tango - 方大同.flac','方大同 - Tango.flac','Tango','方大同'),
 ('en (王翊恩)《嚣张》百万豪装录音棚大声听.mp3','王翊恩 - 嚣张.mp3','嚣张','王翊恩'),
 ('《情深深雨濛濛》R&B.mp3','微醺版 - 情深深雨濛濛 (R&B).mp3','情深深雨濛濛 (R&B)','微醺版'),
 ('《雨蝶》微醺版R&B.mp3','微醺版 - 雨蝶 (R&B).mp3','雨蝶 (R&B)','微醺版'),
 ('『4K无损』离岸~苏晗★就各自参一半 不让你为难 你不用装冷淡 我没想纠缠★.mp3','苏晗 - 离岸.mp3','离岸','苏晗'),
 ('【4K修复丨吴彦祖出演】杨千嬅 - 飞女正传 MV.mp3','杨千嬅 - 飞女正传.mp3','飞女正传','杨千嬅'),
 ('【Hi-Res无损】郭采洁_杨坤《答案》“爱就像蓝天白云 晴空万里 突然暴风雨”_ 音乐可视化 _ 动态歌词.flac','杨坤&郭采洁 - 答案.flac','答案','杨坤&郭采洁'),
 ('【平凡之路注定不平凡！高考加油！】朴树《平凡之路》百万豪装录音棚大声听.mp3','朴树 - 平凡之路.mp3','平凡之路','朴树'),
 ('【张杰】按下随身听，一起穿越到《想见你想见你想见你》纯享舞台.mp3','张杰 - 想见你想见你想见你 (Live).mp3','想见你想见你想见你 (Live)','张杰'),
 ('不谓侠 - 萧忆情Alex.flac','萧忆情Alex - 不谓侠.flac','不谓侠','萧忆情Alex'),
 ('东风破 - 周杰伦.flac','周杰伦 - 东风破.flac','东风破','周杰伦'),
 ('以父之名 - 周杰伦.flac','周杰伦 - 以父之名.flac','以父之名','周杰伦'),
 ('任贤齐《天涯（《笑傲江湖》片尾曲）》百万豪装录音棚大声听.mp3','任贤齐 - 天涯.mp3','天涯','任贤齐'),
 ('兰亭序 - 周杰伦.flac','周杰伦 - 兰亭序.flac','兰亭序','周杰伦'),
 ('命硬.mp3','侧田 - 命硬.mp3','命硬','侧田'),
 ('嘉宾 - 粤语.mp3','常颖杰 - 嘉宾.mp3','嘉宾','常颖杰'),
 ('四面楚歌 - 周杰伦&林迈可.flac','周杰伦&林迈可 - 四面楚歌.flac','四面楚歌','周杰伦&林迈可'),
 ('在百万豪装录音棚大声听 AGA《孤雏》【Hi-res】.flac','AGA - 孤雏.flac','孤雏','AGA'),
 ('在百万豪装录音棚大声听 古巨基《必杀技》【Hi-res】.mp3','古巨基 - 必杀技.mp3','必杀技','古巨基'),
 ('在百万豪装录音棚大声听 周柏豪《够钟》【Hi-res】.flac','周柏豪 - 够钟.flac','够钟','周柏豪'),
 ('在百万豪装录音棚大声听 我不是药神ost 张杰&张碧晨《只要平凡》【Hi-res】.flac','张杰&张碧晨 - 只要平凡.flac','只要平凡','张杰&张碧晨'),
 ('在百万豪装录音棚大声听 李常超《盗墓笔记·十年人间》【Hi-res】.mp3','李常超 - 盗墓笔记·十年人间.mp3','盗墓笔记·十年人间','李常超'),
 ('在百万豪装录音棚大声听 李荣浩 《年少有为》【Hi-res】.flac','李荣浩 - 年少有为.flac','年少有为','李荣浩'),
 ('在百万豪装录音棚大声听 李荣浩 《老街》【Hi-res】.flac','李荣浩 - 老街.flac','老街','李荣浩'),
 ('在百万豪装录音棚大声听 李荣浩《不将就》【Hi-res】.flac','李荣浩 - 不将就.flac','不将就','李荣浩'),
 ('在百万豪装录音棚大声听 李荣浩《麻雀》【Hi-res】.flac','李荣浩 - 麻雀.flac','麻雀','李荣浩'),
 ('在百万豪装录音棚大声听 杨千嬅《少女的祈祷》【Hi-res】.mp3','杨千嬅 - 少女的祈祷.mp3','少女的祈祷','杨千嬅'),
 ('在百万豪装录音棚大声听 杨千嬅《野孩子》【Hi-res】.flac','杨千嬅 - 野孩子.flac','野孩子','杨千嬅'),
 ('在百万豪装录音棚大声听 林宥嘉《说谎》【Hi-res】.mp3','林宥嘉 - 说谎.mp3','说谎','林宥嘉'),
 ('在百万豪装录音棚大声听 梁静茹《情歌》【Hi-res】.flac','梁静茹 - 情歌.flac','情歌','梁静茹'),
 ('在百万豪装录音棚大声听 牛奶咖啡《明天，你好》【Hi-res】.mp3','牛奶咖啡 - 明天，你好.mp3','明天，你好','牛奶咖啡'),
 ('在百万豪装录音棚大声听 萧忆情Alex《不谓侠》【Hi-res】.mp3','萧忆情Alex - 不谓侠.mp3','不谓侠','萧忆情Alex'),
 ('在百万豪装录音棚大声听 陈奕迅《K歌之王》【Hi-res】.flac','陈奕迅 - K歌之王.flac','K歌之王','陈奕迅'),
 ('在百万豪装录音棚大声听 陈小春《相依为命》【Hi-res】.mp3','陈小春 - 相依为命.mp3','相依为命','陈小春'),
 ('在百万豪装录音棚大声听柳爽《漠河舞厅》【Hi-res】.mp3','柳爽 - 漠河舞厅.mp3','漠河舞厅','柳爽'),
 ('在百万豪装录音棚大声听谢安琪《喜帖街》【Hi-res】.flac','谢安琪 - 喜帖街.flac','喜帖街','谢安琪'),
 ('在百万豪装录音棚大声听邓紫棋《光年之外》【Hi-res】.flac','邓紫棋 - 光年之外.flac','光年之外','邓紫棋'),
 ('夜曲 - 周杰伦.flac','周杰伦 - 夜曲.flac','夜曲','周杰伦'),
 ('夜的第七章 - 周杰伦&潘儿.flac','周杰伦&潘儿 - 夜的第七章.flac','夜的第七章','周杰伦&潘儿'),
 ('女声开口惊艳!!校园神级合唱《我用什么把你留住》所以生命璀璨如歌.mp3','张拾一&鲜芋 - 我用什么把你留住.mp3','我用什么把你留住','张拾一&鲜芋'),
 ('张宇《囚鸟》百万豪装录音棚大声听【Hi-res】.mp3','张宇 - 囚鸟.mp3','囚鸟','张宇'),
 ('心有不甘 - 卫兰.flac','卫兰 - 心有不甘.flac','心有不甘','卫兰'),
 ('悟空.mp3','戴荃 - 悟空 (Live).mp3','悟空 (Live)','戴荃'),
 ('我的一个道姑朋友 - 以冬.mp3','以冬 - 我的一个道姑朋友.mp3','我的一个道姑朋友','以冬'),
 ('最爱 - 周慧敏.flac','周慧敏 - 最爱.flac','最爱','周慧敏'),
 ('李荣浩《李白》百万豪装录音棚大声听.mp3','李荣浩 - 李白.mp3','李白','李荣浩'),
 ('杨丞琳-搁浅【蒙面歌王】.mp3','杨丞琳 - 搁浅 (Live).mp3','搁浅 (Live)','杨丞琳'),
 ('杨千嬅《可惜我是水瓶座》百万豪装录音棚大声听.mp3','杨千嬅 - 可惜我是水瓶座.mp3','可惜我是水瓶座','杨千嬅'),
 ('梁咏琪 - 灰姑娘.mp3','梁咏琪 - 灰姑娘.mp3','灰姑娘','梁咏琪'),
 ('梁静茹《会呼吸的痛》百万豪装录音棚大声听.mp3','梁静茹 - 会呼吸的痛.mp3','会呼吸的痛','梁静茹'),
 ('残酷游戏 - 卫兰.flac','卫兰 - 残酷游戏.flac','残酷游戏','卫兰'),
 ('水星记-郭顶.mp3','郭顶 - 水星记.mp3','水星记','郭顶'),
 ('灵风 - 阳光开朗大男孩.mp3','灵风 - 阳光开朗大男孩.mp3','阳光开朗大男孩','灵风'),
 ('珊瑚海 - 周杰伦&Lara梁心颐.flac','周杰伦&Lara梁心颐 - 珊瑚海.flac','珊瑚海','周杰伦&Lara梁心颐'),
 ('空心 - 哦漏.mp3','哦漏 - 空心.mp3','空心','哦漏'),
 ('说书人 - 暗杠&寅子.mp3','暗杠&寅子 - 说书人.mp3','说书人','暗杠&寅子'),
 ('邓垚 - 诀别书.mp3','邓垚 - 诀别书.mp3','诀别书','邓垚'),
 ('邓紫棋《A.I.N.Y. 爱你（G.E.M. 重生版）》百万豪装录音棚大声听.mp3','邓紫棋 - A.I.N.Y. 爱你（重生版）.mp3','A.I.N.Y. 爱你（重生版）','邓紫棋'),
 ('青山黛玛 - 留在我身边.mp3','青山黛玛&SoulJa - 留在我身边.mp3','留在我身边','青山黛玛&SoulJa'),
 ('黑色毛衣 - 周杰伦.flac','周杰伦 - 黑色毛衣.flac','黑色毛衣','周杰伦'),
]

def ss(b): return ((b[0]&0x7f)<<21)|((b[1]&0x7f)<<14)|((b[2]&0x7f)<<7)|(b[3]&0x7f)
def enc_ss(n): return bytes([(n>>21)&0x7f,(n>>14)&0x7f,(n>>7)&0x7f,n&0x7f])
def md5(b): return hashlib.md5(b).hexdigest()

# ---------- MP3 / ID3 ----------
def mp3_strip(data):
    if data[:3]==b'ID3' and len(data)>=10:
        data=data[10+ss(data[6:10]):]
    if len(data)>=128 and data[-128:-125]==b'TAG':
        data=data[:-128]
    return data

def mp3_audio_md5(data):
    return md5(mp3_strip(data))

def mp3_build(data,title,artist):
    data=mp3_strip(data)
    frames=b''
    for fid,txt in ((b'TIT2',title),(b'TPE1',artist)):
        if not txt: continue
        payload=b'\x03'+txt.encode('utf-8')
        frames+=fid+struct.pack('>I',len(payload))+b'\x00\x00'+payload
    size=len(frames)+1024
    return b'ID3\x03\x00\x00'+enc_ss(size)+frames+b'\x00'*1024+data

def mp3_read(data):
    out={}
    if data[:3]!=b'ID3' or len(data)<10: return out
    ver=data[3]; p=10; end=10+ss(data[6:10])
    while p+10<=end and p+10<=len(data):
        fid=data[p:p+4]
        if not fid.strip(b'\x00'): break
        sz=ss(data[p+4:p+8]) if ver==4 else struct.unpack('>I',data[p+4:p+8])[0]
        if sz==0 or p+10+sz>len(data): break
        if fid in (b'TIT2',b'TPE1'):
            raw=data[p+10:p+10+sz]
            if raw:
                codec={0:'latin-1',1:'utf-16-le',2:'utf-16-be',3:'utf-8'}.get(raw[0],'utf-8')
                out[fid]=raw[1:].decode(codec,errors='replace').rstrip('\x00').strip()
        p+=10+sz
    return out

# ---------- FLAC / Vorbis comment ----------
def flac_blocks(data):
    assert data[:4]==b'fLaC', 'not flac'
    pos=4; blocks=[]; last=False
    while not last and pos+4<=len(data):
        h=data[pos]; last=bool(h&0x80); typ=h&0x7f
        ln=int.from_bytes(data[pos+1:pos+4],'big')
        blocks.append([typ,data[pos+4:pos+4+ln]])
        pos+=4+ln
    return blocks, data[pos:]

def flac_audio_md5(data):
    _,audio=flac_blocks(data)
    return md5(audio)

def flac_build(data,title,artist):
    blocks,audio=flac_blocks(data)
    vidx=next((i for i,b in enumerate(blocks) if b[0]==4),None)
    if vidx is not None:
        b=blocks[vidx][1]
        vl=int.from_bytes(b[0:4],'little'); vendor=b[4:4+vl]; p=4+vl
        cnt=int.from_bytes(b[p:p+4],'little'); p+=4
        comments=[]
        for _ in range(cnt):
            cl=int.from_bytes(b[p:p+4],'little'); p+=4
            comments.append(b[p:p+cl]); p+=cl
    else:
        vendor=b''; comments=[]
    drop=(b'TITLE=',b'ARTIST=')
    keep=[c for c in comments if not c.upper().startswith(drop)]
    new=[]
    for k,v in ((b'TITLE',title),(b'ARTIST',artist)):
        if v: new.append(k+b'='+v.encode('utf-8'))
    cs=keep+new
    body=len(vendor).to_bytes(4,'little')+vendor+len(cs).to_bytes(4,'little')
    for c in cs: body+=len(c).to_bytes(4,'little')+c
    if vidx is not None:
        blocks[vidx][1]=body
    else:
        ins=1 if blocks and blocks[0][0]==0 else 0
        blocks.insert(ins,[4,body])
    out=bytearray(b'fLaC')
    n=len(blocks)
    for i,(t,b) in enumerate(blocks):
        out.append((0x80 if i==n-1 else 0)|t)
        out+=len(b).to_bytes(3,'big')+b
    return bytes(out)+audio

def flac_read(data):
    blocks,_=flac_blocks(data)
    b=next((x[1] for x in blocks if x[0]==4),None)
    if not b: return {}
    vl=int.from_bytes(b[0:4],'little'); p=4+vl
    cnt=int.from_bytes(b[p:p+4],'little'); p+=4
    out={}
    for _ in range(cnt):
        cl=int.from_bytes(b[p:p+4],'little'); p+=4
        s=b[p:p+cl].decode('utf-8',errors='replace'); p+=cl
        if '=' in s:
            k,v=s.split('=',1)
            if k.upper() in ('TITLE','ARTIST'): out[k.upper()]=v
    return out

def audio_md5(path_or_bytes):
    data=path_or_bytes if isinstance(path_or_bytes,bytes) else open(path_or_bytes,'rb').read()
    return flac_audio_md5(data) if data[:4]==b'fLaC' else mp3_audio_md5(data)

def build_file(data,title,artist):
    return flac_build(data,title,artist) if data[:4]==b'fLaC' else mp3_build(data,title,artist)

def read_fields(path_or_bytes):
    data=path_or_bytes if isinstance(path_or_bytes,bytes) else open(path_or_bytes,'rb').read()
    if data[:4]==b'fLaC':
        f=flac_read(data); return f.get('TITLE'),f.get('ARTIST')
    f=mp3_read(data); return f.get(b'TIT2'),f.get(b'TPE1')

def test_mode():
    ok=0; fail=[]
    for src,dst,title,artist in MAP:
        p=os.path.join(BAK,src)
        if not os.path.isfile(p): fail.append((src,'备份缺文件')); continue
        data=open(p,'rb').read()
        expect=audio_md5(data)
        out=build_file(data,title,artist)
        t,a=read_fields(out)
        if t!=title or a!=artist or audio_md5(out)!=expect:
            fail.append((src,'标签=%r/%r 音频一致=%s'%(t,a,audio_md5(out)==expect)))
        else: ok+=1
    print('往返测试通过:',ok,'/',len(MAP))
    for x in fail: print('  失败:',x)
    return not fail

def run_mode():
    os.makedirs(KEEP,exist_ok=True)
    targets=[m[1] for m in MAP]
    if len(set(targets))!=len(MAP): print('目标名重复，中止'); return
    ok=0; skip=0
    for i in range(0,len(MAP),BATCH):
        batch=MAP[i:i+BATCH]
        print('--- 第 %d 批（%d 首）---'%(i//BATCH+1,len(batch)))
        for src,dst,title,artist in batch:
            sp=os.path.join(SRC,src); dp=os.path.join(SRC,dst); tmp=dp+'.tmp'
            # 已完成：目标存在且标签正确
            if not os.path.exists(sp):
                if os.path.isfile(dp):
                    t,a=read_fields(dp)
                    if t==title and a==artist:
                        ok+=1; skip+=1; print('  已完成:',dst); continue
                # 源文件可能已在保留区
                kp=os.path.join(KEEP,src)
                if os.path.isfile(kp): sp=kp
                else: print('  源文件缺失:',src); continue
            try:
                data=open(sp,'rb').read()
                expect=audio_md5(data)
                with open(tmp,'wb') as f: f.write(build_file(data,title,artist))
                t,a=read_fields(tmp)
                if t!=title or a!=artist or audio_md5(tmp)!=expect:
                    os.remove(tmp); print('  校验失败:',src); continue
                if os.path.exists(dp): os.remove(dp)
                os.replace(tmp,dp)
                # 源移到保留区（不删除）
                if os.path.normcase(sp)!=os.path.normcase(dp) and os.path.isfile(sp):
                    kp=os.path.join(KEEP,src)
                    if not os.path.exists(kp): shutil.move(sp,kp)
                ok+=1; print('  OK:',dst)
            except Exception as e:
                print('  异常:',src,'|',type(e).__name__,str(e)[:80])
        print('  累计 %d/%d'%(ok,i+len(batch)))
    print('完成:',ok,'/',len(MAP),'（其中已完成跳过',skip,'）')
    print('目录内音频数:',len([f for f in os.listdir(SRC) if f.lower().endswith(('.mp3','.flac'))]))

if __name__=='__main__':
    if '--test' in sys.argv:
        test_mode()
    else:
        run_mode()
