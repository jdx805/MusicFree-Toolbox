# -*- coding: utf-8 -*-
"""音乐入库前体检（只读）

扫一个目录里的音频文件，提前报出会导致 MusicFree 出问题的四类毛病：
  1. 扩展名与真实容器不符  -> 播不了（GQ 教训）
  2. 无内嵌歌词            -> 没歌词（纯音乐可在 _check_ignore.json 里忽略）
  3. 标题/歌手标签缺失     -> App 库记录残缺，歌词封面全不会对（GQ 教训）

已作废的旧判据：曾认为「歌词缺 [ti:] 行就不显示」，但《空心》无 ti 却正常出词
（缓存正文首行即时间戳行），说明缺 ti 不是失败的充分条件，故不再告警。

用法：
  python musicfree_check.py [目录]       默认 D:\\Users\\Downloads\\Recive\\BiliTools
  结果同时写入 脚本工具\\体检报告\\体检报告-YYYYMMDD-HHmm.txt
全程只读，不修改任何文件。
"""

import os
import sys
import datetime

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

HERE = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
        else os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

DEFAULT_DIR = r'D:\Users\Downloads\Recive\BiliTools'
AUDIO_EXT = {'.mp3', '.flac', '.m4a', '.aac', '.wav', '.ogg', '.opus', '.wma'}

# MP3 码率表（Layer III），单位 kbps；索引 0 与 15 为非法
BR_V1L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
BR_V2L3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]
SR_MAP = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}

EXT_OF_CONTAINER = {'MP4': {'.m4a', '.mp4', '.aac'}, 'FLAC': {'.flac'},
                    'OGG': {'.ogg', '.opus'}, 'WAV': {'.wav'}, 'MP3': {'.mp3'}}
CONTAINER_CN = {'MP4': 'MP4/M4A', 'FLAC': 'FLAC', 'OGG': 'OGG', 'WAV': 'WAV', 'MP3': 'MP3'}


def strip_id3(d):
    """剥掉 ID3v2 头，返回剩余数据。"""
    if len(d) >= 10 and d[:3] == b'ID3':
        sz = ((d[6] & 0x7f) << 21) | ((d[7] & 0x7f) << 14) | ((d[8] & 0x7f) << 7) | (d[9] & 0x7f)
        return d[10 + sz:]
    return d


def sniff_container(body):
    """按魔数判真实容器，返回 (容器名, 细节) 或 (None, None)。"""
    if len(body) >= 12 and body[4:8] == b'ftyp':
        brand = body[8:12].decode('latin-1', 'replace').strip()
        return 'MP4', 'MP4/M4A 容器 (brand=%s)' % brand
    if body[:4] == b'fLaC':
        return 'FLAC', 'FLAC 容器'
    if body[:4] == b'OggS':
        return 'OGG', 'OGG 容器'
    if body[:4] == b'RIFF' and body[8:12] == b'WAVE':
        return 'WAV', 'WAV 容器'
    return None, None


def _mp3_hdr(body, pos):
    """校验 pos 处是否合法 MP3 帧头，返回帧长；非法返 0。"""
    if pos + 4 > len(body):
        return 0
    if body[pos] != 0xFF or (body[pos + 1] & 0xE0) != 0xE0:
        return 0
    b1, b2 = body[pos + 1], body[pos + 2]
    ver = (b1 >> 3) & 0x03
    layer = (b1 >> 1) & 0x03
    br_i = (b2 >> 4) & 0x0F
    sr_i = (b2 >> 2) & 0x03
    pad = (b2 >> 1) & 0x01
    if ver == 1 or layer == 0 or br_i == 0 or br_i == 15 or sr_i == 3:
        return 0
    if ver == 3:
        br = BR_V1L3[br_i] * 1000
        sr = SR_MAP[3][sr_i]
        return int(144 * br / sr) + pad
    br = BR_V2L3[br_i] * 1000
    sr = SR_MAP[ver][sr_i]
    return int(72 * br / sr) + pad


def mp3_scan(body, limit=200, head=8192):
    """从起点（允许少量填充）连续跟帧，返回 (连续帧数, 断点次数)。

    真 MP3 的帧首尾相接，不该出现断点；伪文件（如 MP4 换了 .mp3 名）
    会在一帧之后就断，靠这个区分。
    """
    n = len(body)
    pos = None
    for i in range(max(1, min(n - 3, head))):
        if _mp3_hdr(body, i):
            pos = i
            break
    if pos is None:
        return 0, 99
    count = 0
    gaps = 0
    while pos + 4 <= n and count < limit:
        flen = _mp3_hdr(body, pos)
        if flen:
            pos += flen
            count += 1
            continue
        gaps += 1
        nxt = pos + 1
        found = None
        while nxt + 4 <= n and nxt - pos < 4096:
            if _mp3_hdr(body, nxt):
                found = nxt
                break
            nxt += 1
        if found is None:
            break
        pos = found
    return count, gaps


def read_tags_and_lyric(path, body):
    """返回 (tags字典, 歌词文本)；失败返回 ({}, '')。"""
    tags, lrc = {}, ''
    try:
        import lyric_embed_core as core
        data = open(path, 'rb').read()
        if body[:4] == b'fLaC':
            import lyric_offset_tool as lot
            info, lrc, kind = lot.read_embedded_lyric(path)
            lrc = lrc or ''
            return tags, lrc
        ver, frames, audio = core.id3_parse_tolerant(data)
        for fid, fl, b in frames:
            if fid in ('TIT2', 'TPE1', 'TALB'):
                try:
                    tags[fid] = b[1:].decode('utf-8', 'replace')
                except Exception:
                    tags[fid] = ''
        lrc = core._read_uslt(frames) or ''
    except Exception:
        pass
    return tags, lrc


def load_ignore():
    """读取纯音乐忽略名单；文件不存在或格式错误时返回空配置。"""
    p = os.path.join(HERE, '_check_ignore.json')
    try:
        import json
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def check_file(path, ignore=None):
    """体检单个文件，返回问题列表 [(级别, 类别, 说明)]。"""
    ignore = ignore or {}
    no_lyric_ignore = ignore.get('no_lyric', [])
    issues = []
    base = os.path.splitext(os.path.basename(path))[0]
    ext = os.path.splitext(path)[1].lower()
    try:
        raw = open(path, 'rb').read(1 << 20)
    except Exception as e:
        return [('严重', '读取失败', str(e))]
    if len(raw) < 12:
        return [('严重', '文件异常', '文件过小或为空')]

    body = strip_id3(raw)
    container, detail = sniff_container(body)

    if container is None:
        frames, gaps = mp3_scan(body)
        if frames >= 50 and gaps <= 1:
            container, detail = 'MP3', 'MP3 流（连续 %d 帧）' % frames
        else:
            issues.append(('严重', '不是有效音频',
                           '帧结构不连续（连续帧=%d，断点=%d），既非 MP3 也非已知容器' % (frames, gaps)))
            return issues

    # 1. 扩展名与容器是否匹配
    if ext not in EXT_OF_CONTAINER.get(container, set()):
        issues.append(('严重', '扩展名与容器不符',
                       '扩展名 %s，实际是 %s；MusicFree 按扩展名选解码器会播不了' % (ext, detail)))

    # 2/3 标签与歌词
    tags, lrc = read_tags_and_lyric(path, body)
    if container in ('MP3', 'FLAC'):
        is_pure_music = any(k in base for k in no_lyric_ignore)
        if not lrc.strip():
            if not is_pure_music:
                issues.append(('提示', '无内嵌歌词', '为空；需用内嵌歌词工具补，纯音乐请在 _check_ignore.json 里登记'))
        # 注：不检查 [ti:]。已验证《空心》无 ti 也正常出词，旧判据作废。
        if container == 'MP3':
            for fid, name in (('TIT2', '标题'), ('TPE1', '歌手')):
                if not tags.get(fid, '').strip():
                    issues.append(('提示', '标签缺失', '%s(%s) 为空 → App 库记录会残缺' % (name, fid)))

    # 文件名规范（下载环节常见）
    if ' - ' not in base:
        issues.append(('提示', '文件名不规范', '缺「歌手 - 歌名」格式'))
    return issues


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    if not os.path.isdir(target):
        print('目录不存在: %s' % target)
        return 2

    files = []
    for root, dirs, names in os.walk(target):
        for nm in names:
            if os.path.splitext(nm)[1].lower() in AUDIO_EXT:
                files.append(os.path.join(root, nm))
    files.sort()

    lines = []
    def out(s=''):
        print(s)
        lines.append(s)

    out('=' * 62)
    out('音乐入库前体检（只读）')
    out('目录: %s' % target)
    out('时间: %s' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    out('文件: %d 个音频' % len(files))
    out('=' * 62)

    results = []
    ignore = load_ignore()
    for p in files:
        issues = check_file(p, ignore)
        if issues:
            results.append((p, issues))

    order = {'严重': 0, '提示': 1}
    groups = {'严重': [], '提示': []}
    for p, issues in results:
        worst = min(issues, key=lambda x: order.get(x[0], 9))[0]
        groups[worst].append((p, issues))

    for level in ('严重', '提示'):
        items = groups[level]
        if not items:
            continue
        out('')
        out('【%s】%d 个' % (level, len(items)))
        out('-' * 62)
        for p, issues in items:
            rel = os.path.relpath(p, target)
            out('  %s' % rel)
            for lv, cat, msg in issues:
                out('      · %s：%s' % (cat, msg))

    ok = len(files) - len(results)
    out('')
    out('=' * 62)
    out('通过 %d 个 / 有问题 %d 个 / 共 %d 个' % (ok, len(results), len(files)))
    if results:
        out('')
        out('处置参考：')
        out('  扩展名与容器不符 → 先剥 ID3，再用 ffmpeg 转真 MP3：')
        out('    ffmpeg -i "输入.m4a" -c:a libmp3lame -b:a 192k -ar 48000 "输出.mp3"')
        out('  无内嵌歌词 → 用「启动内嵌歌词工具.bat」补词（纯音乐请登记到 _check_ignore.json）')
        out('  标签缺失 → 重写 TIT2/TPE1；否则手机端库记录会残缺，换了文件也不生效')
        out('  换完文件仍没词 → 多半是旧路径被 App 记成无词状态，换个全新文件名重扫')
    out('=' * 62)

    rpt_dir = os.path.join(HERE, '体检报告')
    try:
        os.makedirs(rpt_dir, exist_ok=True)
    except Exception:
        rpt_dir = HERE
    rpt = os.path.join(rpt_dir, '体检报告-%s.txt' % datetime.datetime.now().strftime('%Y%m%d-%H%M'))
    try:
        with open(rpt, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        print('\n报告已保存: %s' % rpt)
    except Exception as e:
        print('\n报告保存失败: %s' % e)
    return 0


if __name__ == '__main__':
    sys.exit(main())
