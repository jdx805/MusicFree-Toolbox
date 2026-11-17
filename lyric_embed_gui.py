#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内嵌歌词工具 · GUI。
流程：选文件夹→选歌→搜索候选(QQ/LRCLIB)→人工点选版本→预览→内嵌(另存,源文件不动)→同步到手机。
复用 lyric_embed_core(获取+写入) / musicfree_sync(推送+缓存+强停重启) / 现有路径配置。
"""
import os, sys, json, threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import lyric_embed_core as core
import musicfree_sync as sync
import lyric_offset_tool as base

FONT = ('Microsoft YaHei', 10)
CFG_PATH = os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
                        else os.path.dirname(os.path.abspath(__file__)), '_embed_gui_config.json')
DEFAULT_OUT_DIR = r'D:\Users\Downloads\Recive\BiliTools_嵌词'


def load_cfg():
    try:
        return json.load(open(CFG_PATH, encoding='utf-8'))
    except Exception:
        return {}


def save_cfg(folder, out, phone):
    d = load_cfg()
    d.update({'folder': folder, 'out': out, 'phone': phone})
    json.dump(d, open(CFG_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)


class App:
    def __init__(self, root, host=None):
        self.root = root
        self.host = host or root
        if host is None:
            root.title('内嵌歌词工具  v1.0')
            root.geometry('980x720')
        cfg = load_cfg()
        self.files = []
        self.cands = []            # 当前候选列表 [{source,key,title,artist,album,duration,...}]
        self.saved_outputs = []    # 上次内嵌另存出来的路径（供同步）
        self._build(cfg)
        self._bind_cfg()
        self.scan()

    # ---------- 界面 ----------
    def _build(self, cfg):
        frm = ttk.Frame(self.host, padding=8)
        frm.grid(row=0, column=0, sticky='nsew')
        self.host.columnconfigure(0, weight=1)
        self.host.rowconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(1, weight=1)
        frm.rowconfigure(4, weight=3)   # 候选区放大
        frm.rowconfigure(11, weight=1)  # 日志区缩小

        # 源文件夹
        ttk.Label(frm, text='歌曲文件夹：', font=FONT).grid(row=0, column=0, sticky='w')
        self.var_folder = tk.StringVar(value=cfg.get('folder') or base.DEFAULT_FOLDER)
        ttk.Entry(frm, textvariable=self.var_folder, font=FONT).grid(row=0, column=1, sticky='ew')
        ttk.Button(frm, text='浏览…', command=self.choose_folder).grid(row=0, column=2, sticky='e')

        # 左：歌曲列表  右：候选列表
        left = ttk.Frame(frm); left.grid(row=1, column=0, columnspan=3, sticky='nsew')
        left.columnconfigure(0, weight=1); left.rowconfigure(1, weight=1)
        ttk.Label(left, text='① 歌曲列表（点选一首）：', font=FONT).grid(row=0, column=0, sticky='w')
        self.listbox = tk.Listbox(left, selectmode='browse', font=FONT, activestyle='dotbox',
                                  exportselection=False)
        self.listbox.grid(row=1, column=0, sticky='nsew')
        self.listbox.bind('<<ListboxSelect>>', self.on_select_song)
        sb1 = ttk.Scrollbar(left, orient='vertical', command=self.listbox.yview)
        sb1.grid(row=1, column=1, sticky='ns'); self.listbox.config(yscrollcommand=sb1.set)
        ttk.Button(left, text='刷新列表', command=self.scan).grid(row=2, column=0, sticky='w', pady=3)

        # 搜索区
        sr = ttk.Frame(frm); sr.grid(row=2, column=0, columnspan=3, sticky='ew', pady=4)
        ttk.Label(sr, text='② 关键词：', font=FONT).pack(side='left')
        self.var_kw = tk.StringVar()
        ttk.Entry(sr, textvariable=self.var_kw, font=FONT, width=28).pack(side='left', padx=(0, 6))
        self.var_src = tk.StringVar(value='ALL')
        ttk.Combobox(sr, textvariable=self.var_src, values=['ALL', 'QQ', 'LRCLIB'],
                     width=8, state='readonly').pack(side='left', padx=(0, 6))
        ttk.Button(sr, text='搜索歌词', command=self.do_search).pack(side='left', padx=(0, 6))
        ttk.Button(sr, text='用选中歌名搜', command=self.fill_kw_from_song).pack(side='left')

        # 候选列表（列表占 0-1 列，滚动条独占第 2 列，避免压住列表）
        ttk.Label(frm, text='③ 候选版本（人工点选，别自动选第一条）：', font=FONT).grid(row=3, column=0, columnspan=3, sticky='w')
        self.cand_box = tk.Listbox(frm, selectmode='browse', font=FONT, height=12, activestyle='dotbox',
                                   exportselection=False)
        self.cand_box.grid(row=4, column=0, columnspan=2, sticky='nsew')
        self.cand_box.bind('<<ListboxSelect>>', self.on_select_cand)
        sb2 = ttk.Scrollbar(frm, orient='vertical', command=self.cand_box.yview)
        sb2.grid(row=4, column=2, sticky='ns'); self.cand_box.config(yscrollcommand=sb2.set)

        # 预览
        ttk.Label(frm, text='④ 歌词预览：', font=FONT).grid(row=5, column=0, columnspan=3, sticky='w', pady=(4, 0))
        self.preview = scrolledtext.ScrolledText(frm, font=FONT, height=6, wrap='word', state='disabled')
        self.preview.grid(row=6, column=0, columnspan=3, sticky='ew')

        # 输出目录
        ttk.Label(frm, text='另存目录（源文件不动）：', font=FONT).grid(row=7, column=0, sticky='w', pady=(4, 0))
        self.var_out = tk.StringVar(value=cfg.get('out') or DEFAULT_OUT_DIR)
        ttk.Entry(frm, textvariable=self.var_out, font=FONT).grid(row=7, column=1, sticky='ew', pady=(4, 0))
        ttk.Button(frm, text='浏览…', command=self.choose_out).grid(row=7, column=2, sticky='e', pady=(4, 0))

        # 手机目录
        ttk.Label(frm, text='手机音乐目录：', font=FONT).grid(row=8, column=0, sticky='w')
        self.var_phone = tk.StringVar(value=cfg.get('phone') or sync.DEFAULT_PHONE_DIR)
        ttk.Entry(frm, textvariable=self.var_phone, font=FONT).grid(row=8, column=1, sticky='ew')
        ttk.Button(frm, text='默认', command=lambda: self.var_phone.set(sync.DEFAULT_PHONE_DIR)).grid(row=8, column=2, sticky='e')

        # 标签勾选
        self.var_tags = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm, text='写入歌手/歌名/专辑标签（从文件名解析）',
                        variable=self.var_tags).grid(row=9, column=0, columnspan=3, sticky='w', pady=3)

        # 动作
        act = ttk.Frame(frm); act.grid(row=10, column=0, columnspan=3, sticky='w', pady=4)
        ttk.Button(act, text='⑤ 内嵌歌词(另存)', command=self.embed_lyric).pack(side='left', padx=(0, 6))
        ttk.Button(act, text='⑥ 同步到手机', command=self.sync_phone).pack(side='left', padx=(0, 6))
        self.var_post = tk.BooleanVar(value=True)
        ttk.Checkbutton(act, text='同步成功后强停并重启MusicFree', variable=self.var_post).pack(side='left', padx=(0, 6))
        ttk.Button(act, text='清空日志', command=self.clear_log).pack(side='left')

        # 日志（默认矮一些，把空间让给候选区）
        self.log = scrolledtext.ScrolledText(frm, font=FONT, wrap='word', height=6, state='disabled')
        self.log.grid(row=11, column=0, columnspan=3, sticky='nsew', pady=(4, 0))

        # 状态
        self.var_status = tk.StringVar(value='就绪')
        ttk.Label(frm, textvariable=self.var_status, font=FONT, foreground='#444').grid(
            row=12, column=0, columnspan=3, sticky='w', pady=(4, 0))

    def _bind_cfg(self):
        for var in (self.var_folder, self.var_out, self.var_phone):
            var.trace_add('write', lambda *_: save_cfg(
                self.var_folder.get().strip(), self.var_out.get().strip(), self.var_phone.get().strip()))

    # ---------- 日志/状态 ----------
    def _log(self, s=''):
        self.log.config(state='normal')
        self.log.insert('end', str(s) + '\n')
        self.log.see('end')
        self.log.config(state='disabled')

    def _status(self, s):
        self.var_status.set(s)

    def _clear_preview(self):
        self.preview.config(state='normal')
        self.preview.delete('1.0', 'end')
        self.preview.config(state='disabled')

    def clear_log(self):
        self.log.config(state='normal'); self.log.delete('1.0', 'end'); self.log.config(state='disabled')

    # ---------- 文件夹/列表 ----------
    def choose_folder(self):
        d = filedialog.askdirectory(initialdir=self.var_folder.get().strip() or base.DEFAULT_FOLDER)
        if d:
            self.var_folder.set(d)
            self.scan()

    def choose_out(self):
        d = filedialog.askdirectory(initialdir=self.var_out.get().strip() or DEFAULT_OUT_DIR)
        if d:
            self.var_out.set(d)

    def scan(self):
        folder = self.var_folder.get().strip() or base.DEFAULT_FOLDER
        try:
            self.files = base.scan_audio_files(folder)
        except Exception as e:
            self.files = []
            self._status('扫描失败: %s' % e)
            return
        self.listbox.delete(0, 'end')
        for p in self.files:
            self.listbox.insert('end', os.path.basename(p))
        self.cands = []
        self.cand_box.delete(0, 'end')
        self._clear_preview()
        self.saved_outputs = []
        self._status('就绪')
        self._log('扫描到 %d 个音频文件：%s' % (len(self.files), folder))

    def on_select_song(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        p = self.files[sel[0]]
        artist, title = core.parse_filename(p)
        self.var_kw.set((title + ' ' + artist).strip())
        self._status('已选：%s（关键词已自动填入，可修改后搜索）' % os.path.basename(p))

    def fill_kw_from_song(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo('提示', '请先在歌曲列表点选一首')
            return
        artist, title = core.parse_filename(self.files[sel[0]])
        self.var_kw.set((title + ' ' + artist).strip())

    # ---------- 搜索 ----------
    def _log_qq_interval(self):
        """把上次 QQ 请求间隔与下限写进日志。"""
        gap, floor = core.qq_interval_info()
        if gap is None:
            self._log('  QQ 拉取间隔：首次请求，无上次记录（下限 %.1fs）' % floor)
        else:
            used = gap < floor
            self._log('  QQ 拉取间隔：距上次 %.2fs（下限 %.1fs，%s；下一次拉取至少间隔 %.1fs）'
                      % (gap, floor, '本次已等待补足' if used else '未触发等待', floor))

    def do_search(self):
        kw = self.var_kw.get().strip()
        if not kw:
            messagebox.showinfo('提示', '请输入关键词，或先点选一首歌')
            return
        src_sel = self.var_src.get()
        sources = ('QQ', 'LRCLIB') if src_sel == 'ALL' else (src_sel,)
        self._status('搜索中…')
        self.cand_box.delete(0, 'end')
        self.cands = []

        def work():
            cands, errs = core.search_all(kw.split()[0], ' '.join(kw.split()[1:]), sources=sources)
            def done():
                self.cands = cands
                self.cand_box.delete(0, 'end')
                for c in cands:
                    tag = '[有轴]' if c.get('has_synced') else ''
                    self.cand_box.insert('end', '%s | %s - %s | %s %s' % (
                        c['source'], c['artist'], c['title'], c['duration'], tag))
                self._status('候选 %d 条（QQ+LRCLIB 按源分组，人工点选）' % len(cands))
                for e in errs:
                    self._log('  搜索警告: ' + e)
                if 'QQ' in sources:
                    self._log_qq_interval()
                if not cands:
                    self._log('  没有候选，换个关键词或换源试试')
            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def on_select_cand(self, event=None):
        sel = self.cand_box.curselection()
        if not sel or sel[0] >= len(self.cands):
            return
        c = self.cands[sel[0]]
        self._status('拉取歌词预览…')
        def work():
            try:
                lrc = core.fetch_lrc(c)
            except Exception as e:
                def fail():
                    self._status('拉取失败: %s' % e)
                    if c['source'] == 'QQ':
                        self._log_qq_interval()
                    self._clear_preview()
                self.root.after(0, fail); return
            def done():
                self._clear_preview()
                self.preview.config(state='normal')
                self.preview.insert('1.0', core.lyric_preview(lrc, 12))
                self.preview.config(state='disabled')
                self._status('预览已就绪：%s - %s（确认后点「内嵌歌词」）' % (c['artist'], c['title']))
                if c['source'] == 'QQ':
                    self._log_qq_interval()
            self.root.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def _get_chosen_lrc(self):
        sel = self.cand_box.curselection()
        if not sel or sel[0] >= len(self.cands):
            messagebox.showinfo('提示', '请先在候选列表点选一个版本')
            return None
        c = self.cands[sel[0]]
        try:
            return core.fetch_lrc(c), c
        except Exception as e:
            messagebox.showerror('拉取失败', str(e))
            return None

    # ---------- 内嵌（另存） ----------
    def embed_lyric(self):
        songs = [self.files[i] for i in self.listbox.curselection() if i < len(self.files)]
        if not songs:
            messagebox.showinfo('提示', '请先在歌曲列表点选一首歌')
            return
        got = self._get_chosen_lrc()
        if not got:
            return
        lrc, cand = got
        out_dir = self.var_out.get().strip() or DEFAULT_OUT_DIR
        os.makedirs(out_dir, exist_ok=True)
        if not messagebox.askyesno('确认内嵌',
                '把「%s - %s」的歌词内嵌到 %d 首歌？\n'
                '歌词来源：%s\n另存到：%s\n源文件不动。\n\n确定吗？'
                % (cand['artist'], cand['title'], len(songs), cand['source'], out_dir)):
            return
        self.saved_outputs = []
        ok_n = fail_n = 0
        for p in songs:
            name = os.path.basename(p)
            out = os.path.join(out_dir, name)
            if os.path.exists(out) and not messagebox.askyesno('文件已存在',
                    '%s 已存在于另存目录，覆盖吗？' % name):
                self._log('  跳过（已存在）: ' + name); continue
            artist, title = core.parse_filename(p)
            tags = ({'title': title, 'artist': artist, 'album': title}
                    if self.var_tags.get() and title else None)
            try:
                r = core.embed(p, out, lrc, tags)
            except Exception as ex:
                r = {'ok': False, 'msg': '%s: %s' % (type(ex).__name__, ex)}
            if r['ok']:
                ok_n += 1
                self.saved_outputs.append(out)
                self._log('  OK   %-38s %s' % (name, r['msg']))
            else:
                fail_n += 1
                self._log('  FAIL %-38s %s' % (name, r['msg']))
                if os.path.exists(out):
                    try: os.remove(out)
                    except OSError: pass
        self._status('内嵌完成：成功 %d，失败 %d' % (ok_n, fail_n))
        self._log('\n内嵌完成：成功 %d，失败 %d。成功的文件已另存，可点「同步到手机」。' % (ok_n, fail_n))

    # ---------- 同步 ----------
    def sync_phone(self):
        if not self.saved_outputs:
            messagebox.showinfo('提示', '请先在上面完成「内嵌歌词」，再同步')
            return
        files = [p for p in self.saved_outputs if os.path.exists(p)]
        if not files:
            messagebox.showinfo('提示', '另存目录里的文件已不存在，请重新内嵌')
            return
        ok, info = sync.check_device()
        if not ok:
            messagebox.showerror('设备检查失败', info)
            return
        phone_dir = self.var_phone.get().strip() or sync.DEFAULT_PHONE_DIR
        do_post = self.var_post.get()
        steps = ('将执行：\n1) push %d 个文件到 %s\n'
                 '2) 按歌词内容定位并覆盖对应歌词缓存\n3) 校验 MD5 + 缓存回读'
                 % (len(files), phone_dir))
        if do_post:
            steps += '\n4) 全部成功后强制停止并重启 MusicFree'
        steps += '\n\n设备 %s\n确定吗？' % info
        if not messagebox.askyesno('确认同步', steps):
            return

        self._status('同步中（推送文件）…')
        res = sync.push_files(files, phone_dir)
        push_fail = 0
        for name, sok, msg in res:
            self._log('  push %-36s %s : %s' % (name, 'OK' if sok else 'FAIL', msg))
            if not sok: push_fail += 1

        self._status('同步中（处理歌词缓存）…')
        cache_fail = 0
        for p in files:
            r = sync.sync_cache_for(p)
            self._log('  缓存 %-34s %s' % (
                os.path.basename(p),
                ('已覆盖' if r['found'] else ('无需(新歌)' if not r['need'] else '失败')) + ' : ' + (r['msg'] or '-')))
            if r['need'] and not r['found']:
                cache_fail += 1

        if do_post:
            if push_fail == 0 and cache_fail == 0:
                self._status('同步中（强停 App）…')
                sok, smsg = sync.force_stop()
                self._log('  强停: ' + smsg)
                if sok:
                    self._status('同步中（重启 App）…')
                    rok, rmsg = sync.restart_app()
                    self._log('  重启: ' + rmsg)
                self._status('同步完成（已强停并重启）')
            else:
                self._status('同步完成：有失败，未强停')
                self._log('  有失败项（push %d / 缓存 %d），跳过强停。' % (push_fail, cache_fail))
        else:
            self._status('同步完成：push失败%d 缓存失败%d' % (push_fail, cache_fail))
        self._log('\n同步完成：push 失败 %d，缓存失败 %d。' % (push_fail, cache_fail))


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
