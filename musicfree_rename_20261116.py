# -*- coding: utf-8 -*-
"""BiliTools 歌曲整理：重命名 + 重写 ID3 标签，供 MusicFree 识别。
用法: python musicfree_rename_20261116.py [--test]
源定位：根目录文件名精确匹配；子目录用 BV 号前缀定位唯一 mp3（避免空格细节差异）。
源文件清理：优先移到备份保留区；失败则留在原地并记录，不中断整体流程。
"""
import os, sys, hashlib, struct

sys.stdout.reconfigure(encoding='utf-8')

SRC_ROOT = r'D:\Users\Downloads\Recive\BiliTools'
BAK_ROOT = r'D:\Users\Documents\Workbuddy_workspace\Recovery\BiliTools-20261116'
BATCH = 8

# (源键: 根文件名或BV号, 目标文件名, title, artist, album)
MAP = [
    ('下雨天.mp3', '南拳妈妈 - 下雨天.mp3', '下雨天', '南拳妈妈', '优の良曲南搞小孩'),
    ('不将就.mp3', '李荣浩 - 不将就.mp3', '不将就', '李荣浩', '有理想'),
    ('九九八十一.mp3', '乐正绫&洛天依 - 九九八十一.mp3', '九九八十一', '乐正绫&洛天依', ''),
    ('你曾这样问过（Cover 周深）.mp3', '群星 - 你曾这样问过.mp3', '你曾这样问过', '群星', ''),
    ('别害怕.mp3', '罗震环 - 别害怕.mp3', '别害怕', '罗震环', '爱情公寓4 电视剧原声带'),
    ('可乐.mp3', '赵紫骅 - 可乐.mp3', '可乐', '赵紫骅', ''),
    ('我好想你.mp3', '苏打绿 - 我好想你.mp3', '我好想你', '苏打绿', '我好想你'),
    ('无心.mp3', '小缘 - 无心.mp3', '无心', '小缘', ''),
    ('海屿你-Crabbit.mp3', 'Crabbit - 海屿你.mp3', '海屿你', 'Crabbit', ''),
    ('王上-我的一个道姑朋友.mp3', '王上 - 我的一个道姑朋友.mp3', '我的一个道姑朋友', '王上', ''),
    ('粤语版-打上花火.mp3', '邓志舜&HungryBaby - 打上花火（粤语版）.mp3', '打上花火（粤语版）', '邓志舜&HungryBaby', ''),
    ('那些年.mp3', '胡夏 - 那些年.mp3', '那些年', '胡夏', '那些年，我们一起追的女孩'),
    ('钟无艳.mp3', '谢安琪 - 钟无艳.mp3', '钟无艳', '谢安琪', ''),
    ('闹够了没有.mp3', '赖伟锋 - 闹够了没有.mp3', '闹够了没有', '赖伟锋', '写给年少回不去的爱'),
    ('陈一发儿 - 童话镇.mp3', '陈一发儿 - 童话镇.mp3', '童话镇', '陈一发儿', '童话镇'),
    ('面具.mp3', '许廷铿 - 面具.mp3', '面具', '许廷铿', '蓝调'),
    ('BV118411B7XU', '杨丞琳 - 雨爱.mp3', '雨爱', '杨丞琳', ''),
    ('BV118411w7Pa', 'YOASOBI - 群青.mp3', '群青', 'YOASOBI', ''),
    ('BV12c411E7Sw', '张芸京 - 偏爱.mp3', '偏爱', '张芸京', '仙剑奇侠传'),
    ('BV13J4m1j7tK', '陈奕迅 - 孤独患者.mp3', '孤独患者', '陈奕迅', '陈奕迅'),
    ('BV17K4y1w7NQ', '毛不易 - 无名的人.mp3', '无名的人', '毛不易', '毛不易'),
    ('BV1824y1T7cD', '李常超 - 盗墓笔记·十年人间.mp3', '盗墓笔记·十年人间', '李常超', ''),
    ('BV1d94y1r7PW', '陈韵若&陈每文 - 爱的回归线.mp3', '爱的回归线', '陈韵若&陈每文', '爱情公寓3'),
    ('BV1F84y147KS', '林俊杰 - 修炼爱情.mp3', '修炼爱情', '林俊杰', '林俊杰'),
    ('BV1h24y1778a', '青鸟飞鱼 - 此生不换.mp3', '此生不换', '青鸟飞鱼', '仙剑奇侠传'),
    ('BV1HH4y1o7Ue', '邓紫棋 - 唯一.mp3', '唯一', '邓紫棋', '邓紫棋'),
    ('BV1Lo4y1F7Fg', '米津玄师 - LOSER.mp3', 'LOSER', '米津玄师', ''),
    ('BV1n24y1V7a6', '陈奕迅 - 富士山下.mp3', '富士山下', '陈奕迅', '陈奕迅'),
    ('BV1UM4y187WJ', '毛不易 - 消愁.mp3', '消愁', '毛不易', '毛不易'),
    ('BV1vD4y1J7fX', '柳爽 - 漠河舞厅.mp3', '漠河舞厅', '柳爽', ''),
    ('BV1y14y1Q77v', '邓紫棋 - 多远都要在一起.mp3', '多远都要在一起', '邓紫棋', '邓紫棋'),
    ('BV1y8411i7Dd', '邓紫棋 - 泡沫.mp3', '泡沫', '邓紫棋', '邓紫棋'),
]


def synchsafe(n):
    return bytes([(n >> 21) & 0x7f, (n >> 14) & 0x7f, (n >> 7) & 0x7f, n & 0x7f])


def unsynchsafe(b):
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def parse_tag(data):
    ver, frames, taglen = 0, [], 0
    if len(data) >= 10 and data[:3] == b'ID3':
        ver = data[3]
        taglen = 10 + unsynchsafe(data[6:10])
        if taglen <= len(data):
            body, pos = data[10:taglen], 0
            while pos + 10 <= len(body):
                fid = body[pos:pos + 4]
                if not fid.strip(b'\x00'):
                    break
                fsz = unsynchsafe(body[pos + 4:pos + 8]) if ver == 4 else struct.unpack('>I', body[pos + 4:pos + 8])[0]
                if fsz <= 0 or pos + 10 + fsz > len(body):
                    break
                frames.append((fid, body[pos + 8:pos + 10], body[pos + 10:pos + 10 + fsz]))
                pos += 10 + fsz
    has_v1 = len(data) >= 128 and data[-128:-125] == b'TAG'
    return ver, frames, taglen, has_v1


def audio_part(data):
    _, _, taglen, has_v1 = parse_tag(data)
    return data[taglen:len(data) - 128 if has_v1 else len(data)]


def audio_md5(data):
    return hashlib.md5(audio_part(data)).hexdigest()


def text_frame(fid, text):
    payload = b'\x01' + b'\xff\xfe' + text.encode('utf-16-le')
    return fid + struct.pack('>I', len(payload)) + b'\x00\x00' + payload


def build_file(data, title, artist, album):
    _, frames, _, _ = parse_tag(data)
    audio = audio_part(data)
    keep = [(fid, fl, pl) for fid, fl, pl in frames if fid not in (b'TIT2', b'TPE1', b'TALB', b'TSSE')]
    new = [text_frame(b'TIT2', title), text_frame(b'TPE1', artist)]
    if album:
        new.append(text_frame(b'TALB', album))
    body = b''.join(new + [fid + struct.pack('>I', len(pl)) + fl + pl for fid, fl, pl in keep])
    return b'ID3\x03\x00\x00' + synchsafe(len(body)) + body + audio


def read_fields(path):
    with open(path, 'rb') as f:
        data = f.read()
    _, frames, _, _ = parse_tag(data)
    out = {}
    for fid, _, pl in frames:
        if fid in (b'TIT2', b'TPE1', b'TALB') and len(pl) > 1:
            enc = pl[0]
            try:
                if enc == 1:
                    out[fid] = pl[3:].decode('utf-16-le', errors='replace').rstrip('\x00')
                elif enc == 3:
                    out[fid] = pl[1:].decode('utf-8', errors='replace').rstrip('\x00')
                else:
                    out[fid] = pl[1:].decode('latin-1', errors='replace').rstrip('\x00')
            except Exception:
                out[fid] = '<decode error>'
    return out, audio_md5(data)


def find_src(key):
    direct = os.path.join(SRC_ROOT, key)
    if os.path.isfile(direct):
        return direct
    if key.startswith('BV'):
        for d in os.listdir(SRC_ROOT):
            if d.startswith(key):
                sub = os.path.join(SRC_ROOT, d)
                if os.path.isdir(sub):
                    mp3s = [os.path.join(sub, f) for f in os.listdir(sub) if f.lower().endswith('.mp3')]
                    if len(mp3s) == 1:
                        return mp3s[0]
    return None


def test_mode():
    src = os.path.join(BAK_ROOT, '下雨天.mp3')
    with open(src, 'rb') as f:
        data = f.read()
    before = audio_md5(data)
    out = build_file(data, '下雨天', '南拳妈妈', '优の良曲南搞小孩')
    tmp = os.path.join(os.path.dirname(__file__), '_id3_roundtrip_test.mp3')
    with open(tmp, 'wb') as f:
        f.write(out)
    fields, after = read_fields(tmp)
    os.replace(tmp, os.path.join(BAK_ROOT, '_校验用临时文件.tmp'))
    print('TEST 音频MD5不变:', before == after, '| 标签:', fields)


def run_mode():
    if not os.path.isdir(BAK_ROOT):
        print('备份不存在，中止'); return
    targets = [m[1] for m in MAP]
    if len(set(targets)) != 32:
        print('目标名重复，中止'); return
    keep = os.path.join(BAK_ROOT, '被替换的原文件')
    os.makedirs(keep, exist_ok=True)

    ok, leftovers = 0, []
    for n, (key, dst_name, title, artist, album) in enumerate(MAP, 1):
        dst = os.path.join(SRC_ROOT, dst_name)
        tmp = dst + '.tmp'
        src = find_src(key)
        if src is None:
            if os.path.exists(dst):
                fields, _ = read_fields(dst)
                if fields.get(b'TIT2') == title and fields.get(b'TPE1') == artist:
                    ok += 1; print(f'[{n}/32] 已完成:', dst_name); continue
            print(f'[{n}/32] 源缺失且目标无效:', key); continue
        if os.path.abspath(src) == os.path.abspath(dst):
            fields, _ = read_fields(dst)
            if fields.get(b'TIT2') == title and fields.get(b'TPE1') == artist:
                ok += 1; print(f'[{n}/32] 已完成:', dst_name); continue
        with open(src, 'rb') as f:
            data = f.read()
        expect_md5 = audio_md5(data)
        with open(tmp, 'wb') as f:
            f.write(build_file(data, title, artist, album))
        fields, got_md5 = read_fields(tmp)
        if fields.get(b'TIT2') != title or fields.get(b'TPE1') != artist or got_md5 != expect_md5:
            os.replace(tmp, os.path.join(keep, f'_校验失败_{n}.tmp'))
            print(f'[{n}/32] 失败:', key, fields); continue
        os.replace(tmp, dst)
        if os.path.abspath(src) != os.path.abspath(dst):
            try:
                os.rename(src, os.path.join(keep, f'{n:02d}_' + os.path.basename(src)))
            except OSError as e:
                leftovers.append((src, str(e)))
                print(f'[{n}/32] 目标已生成，源留在原地(占用):', os.path.basename(src))
        ok += 1
        print(f'[{n}/32] OK:', dst_name)
        if n % BATCH == 0:
            print(f'-- 进度 {n}/32 --')
    print('成功总数:', ok, '/', len(MAP))
    print('根目录 mp3 数:', len([f for f in os.listdir(SRC_ROOT) if f.lower().endswith('.mp3')]))
    if leftovers:
        print('需后续清理的源文件:', len(leftovers))
        for p, e in leftovers:
            print('  ', p, '|', e)


if __name__ == '__main__':
    if '--test' in sys.argv:
        test_mode()
    else:
        run_mode()
