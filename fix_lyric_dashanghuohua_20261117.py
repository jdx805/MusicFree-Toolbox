# -*- coding: utf-8 -*-
"""把用户提供的正确歌词套用 QQ 音乐时间轴，写入桌面版 mp3（保留 PRIV 帧）。"""
import os, sys, re, shutil, hashlib, importlib.util
sys.stdout.reconfigure(encoding='utf-8')

spec = importlib.util.spec_from_file_location(
    'm', r'D:\Users\Documents\Workbuddy_workspace\脚本工具\embed_lyrics_all_20261117.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

DESK = r'D:\Users\Desktop\邓志舜&HungryBaby - 打上花火（粤语版）.mp3'
BT = os.path.join(m.ROOT, '邓志舜&HungryBaby - 打上花火（粤语版）.mp3')
TXT = r'D:\Users\Desktop\打上火花.txt'
BAK = r'D:\Users\Documents\Workbuddy_workspace\Recovery\歌词修正-打上花火-20261117'
BAKFILE = os.path.join(BAK, os.path.basename(DESK))

# 正确歌词 57 行 → QQ 正文时间轴索引（53 项）的映射
MAP = []
MAP += list(range(0, 17))       # 正确 1-17  → QQ 0-16
MAP += [17, 17]                 # 正确 18,19 → QQ 17（QQ 合并行拆开）
MAP += [18, 19, 20]             # 正确 20-22 → QQ 18-20
MAP += [21, 21]                 # 正确 23,24 → QQ 21（合并行拆开）
MAP += [22, 23]                 # 正确 25,26 → QQ 22-23
MAP += [24, 24]                 # 正确 27,28 → QQ 24（合并行拆开）
MAP += [25, 26, 27]             # 正确 29-31 → QQ 25-27
MAP += list(range(28, 35))      # 正确 32-38 → QQ 28-34
MAP += list(range(35, 42))      # 正确 39-45 → QQ 35-41
MAP += list(range(42, 46))      # 正确 46-49 → QQ 42-45
MAP += list(range(46, 53))      # 正确 50-56 → QQ 46-52
MAP += [52]                     # 正确 57 La~~~ → 套用末句时间


def get_qq_times():
    ver, frames, audio = m.id3_parse(open(BT, 'rb').read())
    raw = [r for fid, r in frames if fid == 'USLT'][0]  # 完整帧：头10字节 + payload
    enc = raw[10]
    codec = {0: 'latin-1', 1: 'utf-16', 2: 'utf-16-be', 3: 'utf-8'}.get(enc, 'utf-8')
    body = raw[10:]
    lyric = (body[4:].decode('utf-8', 'replace').split('\x00', 1)[-1]
             if enc == 3 else body[1:].decode(codec, 'replace'))
    times = []
    for line in lyric.splitlines():
        mm = re.match(r'\[(\d{1,2}):(\d{2})(?:\.(\d+))?\](.*)', line)
        if mm:
            t = (int(mm.group(1)) * 60 + int(mm.group(2)) +
                 (int((mm.group(3) or '0').ljust(2, '0')) / 100))
            times.append(t)
    return times[5:]  # 去掉 5 行元数据（标题/作曲/原词/原唱/填词）


def fmt(t):
    mi = int(t // 60)
    return '[%02d:%05.2f]' % (mi, t - mi * 60)


def build_lyric():
    times = get_qq_times()
    lines = [l.strip() for l in open(TXT, encoding='utf-8').read().splitlines() if l.strip()]
    assert len(times) == 53, 'QQ 时间轴不是 53 项: %d' % len(times)
    assert len(lines) == 57, '正确歌词不是 57 行: %d' % len(lines)
    assert len(MAP) == 57, '映射表不是 57 项: %d' % len(MAP)
    out = [fmt(times[i]) + lines[n] for n, i in enumerate(MAP)]
    return '\n'.join(out) + '\n', lines, times


def audio_md5(data):
    ver, frames, audio = m.id3_parse(data)
    return hashlib.md5(audio).hexdigest()


def verify(original, result, lyric):
    """验证：音频 MD5 不变、其余帧原样保留、USLT 写入正确。"""
    va, fa, aa = m.id3_parse(original)
    vb, fb, ab = m.id3_parse(result)
    oth_a = [(f, r) for f, r in fa if f != 'USLT']
    oth_b = [(f, r) for f, r in fb if f != 'USLT']
    uslt = [r for f, r in fb if f == 'USLT']
    got = ''
    if uslt:
        raw = uslt[0]
        enc = raw[10]
        body = raw[10:]
        got = (body[4:].decode('utf-8', 'replace').split('\x00', 1)[-1]
               if enc == 3 else body[1:].decode('utf-8', 'replace')).rstrip('\x00')
    return {
        'audio_same': hashlib.md5(aa).hexdigest() == hashlib.md5(ab).hexdigest(),
        'other_frames_same': oth_a == oth_b,
        'frame_names': [f for f, _ in fb],
        'uslt_ok': got.strip() == lyric.strip(),
        'uslt_len': len(got),
    }


def main():
    lyric, lines, times = build_lyric()
    data = open(DESK, 'rb').read()
    result, cnt = m.embed_mp3(data, lyric)
    v = verify(data, result, lyric)
    print('歌词行数: %d | QQ时间轴: %d | 时间跨度: %s → %s' %
          (len(lines), len(times), fmt(times[0]), fmt(times[-1])))
    print('帧列表: %s' % v['frame_names'])
    print('音频MD5一致: %s | 其余帧原样: %s | USLT正确: %s (%d字)' %
          (v['audio_same'], v['other_frames_same'], v['uslt_ok'], v['uslt_len']))
    print('\n=== 生成的歌词前 8 行 ===')
    for l in lyric.splitlines()[:8]:
        print('  ' + l)
    print('  ...')
    for l in lyric.splitlines()[-4:]:
        print('  ' + l)

    if '--test' in sys.argv:
        print('\n[测试模式] 未写文件')
        return
    if not (v['audio_same'] and v['other_frames_same'] and v['uslt_ok']):
        print('\n验证未通过，中止')
        return

    os.makedirs(BAK, exist_ok=True)
    if not os.path.exists(BAKFILE):
        shutil.copy2(DESK, BAKFILE)
        print('\n已备份: %s' % BAKFILE)
    else:
        print('\n备份已存在，跳过: %s' % BAKFILE)
    tmp = DESK + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(result)
    v2 = verify(data, open(tmp, 'rb').read(), lyric)
    if v2['audio_same'] and v2['other_frames_same'] and v2['uslt_ok']:
        os.replace(tmp, DESK)
        print('写入完成: %s' % DESK)
        final = verify(open(BAKFILE, 'rb').read(), open(DESK, 'rb').read(), lyric)
        print('最终复核: 音频一致=%s 其余帧一致=%s USLT正确=%s' %
              (final['audio_same'], final['other_frames_same'], final['uslt_ok']))
    else:
        os.remove(tmp)
        print('临时文件复核失败，未替换')


if __name__ == '__main__':
    main()
