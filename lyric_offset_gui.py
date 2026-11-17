#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内嵌歌词偏移工具 —— GUI 版（tkinter，标准库，无新依赖）

架构：核心逻辑全部来自 lyric_offset_tool.py（MP3/FLAC 解析、偏移、读写、校验），
      本文件只负责界面与交互；后期若要换 Qt/Web，只需替换本文件，核心不动。

偏移语义：正数 = 歌词提前，负数 = 歌词延后（与命令行版一致）。

运行：python 脚本工具/lyric_offset_gui.py
"""
import os
import sys
import json
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import lyric_offset_tool as core
import musicfree_sync as sync

FONT = ('Microsoft YaHei', 10)
DEFAULT_OUT_DIR = r'D:\Users\Downloads\Recive\BiliTools_改时间戳'
CFG_PATH = os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
                        else os.path.dirname(os.path.abspath(__file__)), '_offset_gui_config.json')


def load_cfg():
    """读取上次保存的三个路径；缺项用默认值。"""
    cfg = {'folder': core.DEFAULT_FOLDER, 'out': DEFAULT_OUT_DIR, 'phone': sync.DEFAULT_PHONE_DIR}
    try:
        if os.path.exists(CFG_PATH):
            cfg.update(json.load(open(CFG_PATH, encoding='utf-8')))
    except Exception:
        pass
    return cfg


def save_cfg(folder, out, phone):
    try:
        json.dump({'folder': folder, 'out': out, 'phone': phone},
                  open(CFG_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    except Exception:
        pass


class App:
    def __init__(self, root, host=None):
        self.root = root
        self.host = host or root
        if host is None:
            root.title('内嵌歌词偏移工具')
            root.geometry('780x580')
        self.files = []            # 当前扫描到的文件绝对路径（全量）
        self.shown = []            # 搜索过滤后当前列表显示的文件绝对路径（选择/预览/保存都基于它）
        self.previews = []         # [(path, analyze_result)]
        self.preview_offset = None
        self.preview_paths = []    # 预览时的选择（绝对路径），保存前校验
        self.saved_outputs = []    # 上次「保存」另存出来的文件路径（供同步用）
        self.cfg = load_cfg()
        self._build()
        self._bind_cfg_trace()
        self._bind_search()
        self.scan()

    # ---------- 界面搭建 ----------
    def _build(self):
        frm = ttk.Frame(self.host, padding=10)
        frm.grid(row=0, column=0, sticky='nsew')
        self.host.columnconfigure(0, weight=1)
        self.host.rowconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(6, weight=1)
        frm.rowconfigure(11, weight=2)

        # 源文件夹
        ttk.Label(frm, text='源文件夹：', font=FONT).grid(row=0, column=0, sticky='w', pady=(0, 4))
        self.var_folder = tk.StringVar(value=self.cfg['folder'])
        ttk.Entry(frm, textvariable=self.var_folder, font=FONT).grid(row=0, column=1, sticky='ew', pady=(0, 4))
        ttk.Button(frm, text='浏览…', command=self.choose_folder).grid(row=0, column=2, sticky='e', pady=(0, 4))

        # 另存目录（改后文件写这里，源文件不动）
        ttk.Label(frm, text='另存目录（改后文件）：', font=FONT).grid(row=1, column=0, sticky='w', pady=(0, 4))
        self.var_out = tk.StringVar(value=self.cfg['out'])
        ttk.Entry(frm, textvariable=self.var_out, font=FONT).grid(row=1, column=1, sticky='ew', pady=(0, 4))
        ttk.Button(frm, text='浏览…', command=self.choose_out).grid(row=1, column=2, sticky='e', pady=(0, 4))

        # 手机目标目录
        ttk.Label(frm, text='手机音乐目录：', font=FONT).grid(row=2, column=0, sticky='w', pady=(0, 4))
        self.var_phone = tk.StringVar(value=self.cfg['phone'])
        ttk.Entry(frm, textvariable=self.var_phone, font=FONT).grid(row=2, column=1, columnspan=2, sticky='ew', pady=(0, 4))

        # 搜索栏
        ttk.Label(frm, text='搜索：', font=FONT).grid(row=3, column=0, sticky='w', pady=(6, 2))
        self.var_search = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_search, font=FONT).grid(row=3, column=1, sticky='ew', pady=(6, 2))
        self.var_regex = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text='正则', variable=self.var_regex).grid(row=3, column=2, sticky='e', pady=(6, 2))
        self.var_search_info = tk.StringVar(value='')
        ttk.Label(frm, textvariable=self.var_search_info, font=FONT, foreground='#888').grid(
            row=4, column=0, columnspan=3, sticky='w')

        # 文件列表
        ttk.Label(frm, text='歌曲列表（Ctrl / Shift 多选）：', font=FONT).grid(row=5, column=0, columnspan=3, sticky='nw')
        lf = ttk.Frame(frm)
        lf.grid(row=6, column=0, columnspan=3, sticky='nsew')
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(lf, selectmode='extended', font=FONT, activestyle='dotbox')
        self.listbox.grid(row=0, column=0, sticky='nsew')
        sb = ttk.Scrollbar(lf, orient='vertical', command=self.listbox.yview)
        sb.grid(row=0, column=1, sticky='ns')
        self.listbox.config(yscrollcommand=sb.set)

        # 列表操作
        ops = ttk.Frame(frm)
        ops.grid(row=7, column=0, columnspan=3, sticky='w', pady=4)
        ttk.Button(ops, text='刷新列表', command=self.scan).pack(side='left', padx=(0, 6))
        ttk.Button(ops, text='全选(当前筛选)', command=self._select_all).pack(side='left', padx=(0, 6))
        ttk.Button(ops, text='取消全选', command=lambda: self.listbox.selection_clear(0, 'end')).pack(side='left')

        # 偏移输入
        ttk.Label(frm, text='偏移秒数（正数=歌词提前，负数=延后）：', font=FONT).grid(row=8, column=0, columnspan=2, sticky='w')
        self.var_off = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_off, font=FONT, width=12).grid(row=8, column=2, sticky='e')

        # 同步后动作勾选（强停+自动重启 一并动作，默认开启）
        post = ttk.Frame(frm)
        post.grid(row=9, column=0, columnspan=3, sticky='w')
        self.var_post_restart = tk.BooleanVar(value=True)
        ttk.Checkbutton(post, text='同步全部成功后强制停止并重启 MusicFree', variable=self.var_post_restart).pack(side='left')

        # 动作：预览 / 保存 / 同步到手机（独立按钮）/ 清空
        act = ttk.Frame(frm)
        act.grid(row=10, column=0, columnspan=3, sticky='w', pady=4)
        ttk.Button(act, text='预览', command=self.preview).pack(side='left', padx=(0, 6))
        ttk.Button(act, text='保存(另存)', command=self.save).pack(side='left', padx=(0, 6))
        ttk.Button(act, text='同步到手机', command=self.sync_phone).pack(side='left', padx=(0, 6))
        ttk.Button(act, text='清空日志', command=self.clear_log).pack(side='left')

        # 日志
        self.log = scrolledtext.ScrolledText(frm, font=FONT, wrap='word', state='disabled')
        self.log.grid(row=11, column=0, columnspan=3, sticky='nsew', pady=(4, 0))

        # 状态
        self.var_status = tk.StringVar(value='就绪')
        ttk.Label(frm, textvariable=self.var_status, font=FONT, foreground='#444').grid(
            row=12, column=0, columnspan=3, sticky='w', pady=(4, 0))

    # ---------- 路径记忆 ----------
    def _bind_cfg_trace(self):
        """三个路径变量任一变化即写盘，下次启动作为默认值。"""
        def changed(*_):
            save_cfg(self.var_folder.get().strip(), self.var_out.get().strip(), self.var_phone.get().strip())
        for v in (self.var_folder, self.var_out, self.var_phone):
            v.trace_add('write', changed)

    # ---------- 搜索过滤 ----------
    def _bind_search(self):
        """输入或勾选变化时即时重筛；用 trace 覆盖键盘输入、粘贴、清空。"""
        self.var_search.trace_add('write', lambda *_: self.apply_filter())
        self.var_regex.trace_add('write', lambda *_: self.apply_filter())

    def apply_filter(self):
        """按关键词/正则过滤 self.files -> self.shown，并重建列表显示。"""
        q = self.var_search.get().strip()
        use_re = self.var_regex.get()
        pat = None
        if use_re and q:
            try:
                pat = re.compile(q, re.IGNORECASE)
                self.var_search_info.set('')
            except re.error as e:
                # 正则写错：不崩、不动列表，只提示
                self.var_search_info.set('正则无效：%s' % e)
                return
        else:
            self.var_search_info.set('')

        if q:
            if use_re:
                self.shown = [p for p in self.files if pat.search(os.path.basename(p)) or pat.search(p)]
            else:
                low = q.lower()
                self.shown = [p for p in self.files
                              if low in os.path.basename(p).lower() or low in p.lower()]
        else:
            self.shown = list(self.files)

        self.listbox.delete(0, 'end')
        for p in self.shown:
            self.listbox.insert('end', os.path.basename(p))
        self.var_search_info.set('匹配 %d / %d' % (len(self.shown), len(self.files)))

    def _select_all(self):
        """全选只作用于当前筛选出来的项。"""
        self.listbox.selection_clear(0, 'end')
        if self.shown:
            self.listbox.select_set(0, len(self.shown) - 1)

    # ---------- 日志/状态 ----------
    def _log(self, s=''):
        self.log.config(state='normal')
        self.log.insert('end', s + '\n')
        self.log.see('end')
        self.log.config(state='disabled')

    def _status(self, s):
        self.var_status.set(s)
        self.root.update_idletasks()

    def clear_log(self):
        self.log.config(state='normal')
        self.log.delete('1.0', 'end')
        self.log.config(state='disabled')

    # ---------- 操作 ----------
    def choose_folder(self):
        d = filedialog.askdirectory(initialdir=self.var_folder.get().strip() or core.DEFAULT_FOLDER)
        if d:
            self.var_folder.set(d)
            self.scan()

    def choose_out(self):
        d = filedialog.askdirectory(initialdir=self.var_out.get().strip() or DEFAULT_OUT_DIR)
        if d:
            self.var_out.set(d)

    def scan(self):
        try:
            self.files = core.scan_audio_files(self.var_folder.get().strip() or core.DEFAULT_FOLDER)
        except Exception as e:
            messagebox.showerror('错误', str(e))
            return
        self.apply_filter()
        self.previews = []
        self._status('就绪')
        self._log('扫描到 %d 个音频文件：%s' % (len(self.files), self.var_folder.get().strip() or core.DEFAULT_FOLDER))

    def _selected(self):
        # 只从当前筛选后的 shown 取，索引与列表框严格一一对应
        return [self.shown[i] for i in self.listbox.curselection() if i < len(self.shown)]

    def _get_offset(self):
        try:
            return float(self.var_off.get().strip())
        except ValueError:
            messagebox.showwarning('输入错误', '偏移必须是数字，例如 7 或 -2.5')
            return None

    def preview(self):
        picks = self._selected()
        if not picks:
            messagebox.showinfo('提示', '请先在列表里选择歌曲（Ctrl / Shift 多选）')
            return
        off = self._get_offset()
        if off is None:
            return
        self._status('分析中…')
        self.clear_log()
        self._log('预览：用户偏移 %+g 秒（正数=提前）→ 时间戳 %+g 秒'
                  % (off, core.user_to_timestamp_delta(off)))
        self.previews = []
        self.preview_offset = off
        self.preview_paths = [os.path.abspath(p) for p in picks]
        ok_n = 0
        for p in picks:
            r = core.analyze(p, off)
            self.previews.append((p, r))
            if r['ok']:
                ok_n += 1
                self._log('  %-42s [%s] 改%d处 钳零%d'
                          % (r['file'], r['kind'], r['changed'], r['clamped']))
                self._log('      原: %s' % r['old_first'])
                self._log('      新: %s' % r['new_first'])
            else:
                self._log('  %s  预览失败: %s' % (r['file'], r['error']))
        self._status('预览完成：%d / %d 首可保存' % (ok_n, len(picks)))

    def _write_as(self, src, out_dir, new_lrc):
        """读源文件 -> 用 new_lrc 重建 -> 写到 out_dir；源文件不动。返回 (out_path, ok, msg)。"""
        name = os.path.basename(src)
        out = os.path.join(out_dir, name)
        try:
            info, _, kind = core.read_embedded_lyric(src)
            audio_before = info['audio']
            data = core.mp3_write(info, new_lrc) if kind == 'mp3' else core.flac_write(info, new_lrc)
            os.makedirs(out_dir, exist_ok=True)
            with open(out, 'wb') as f:
                f.write(data)
            # 校验：写后重新解析，音频字节不变 + 歌词=预期
            info2, lrc2, _ = core.read_embedded_lyric(out)
            ok = (info2['audio'] == audio_before and lrc2 == new_lrc)
            return out, ok, 'OK' if ok else '校验失败（音频或歌词不符）'
        except Exception as e:
            return out, False, '%s: %s' % (type(e).__name__, e)

    def save(self):
        if not self.previews:
            messagebox.showinfo('提示', '请先点「预览」')
            return
        if self._get_offset() is None:
            return
        if [os.path.abspath(p) for p in self._selected()] != self.preview_paths:
            messagebox.showinfo('提示', '歌曲选择已改动，请重新点「预览」后再保存')
            return
        out_dir = self.var_out.get().strip()
        if not out_dir:
            messagebox.showwarning('提示', '请填写「另存目录」')
            return
        saveable = [(p, r) for p, r in self.previews if r['ok'] and r['changed'] > 0]
        if not saveable:
            messagebox.showinfo('提示', '没有可保存的歌曲')
            return
        # 检查同名覆盖
        exists = [os.path.basename(p) for p, _ in saveable if os.path.exists(os.path.join(out_dir, os.path.basename(p)))]
        tip = '将把 %d 首改后歌曲另存到：\n%s\n源文件保持不变。\n' % (len(saveable), out_dir)
        if exists:
            tip += '\n注意：%d 个同名文件会被覆盖：%s\n' % (len(exists), '、'.join(exists[:5]))
        tip += '\n确定保存吗？'
        if not messagebox.askyesno('确认另存', tip):
            return

        self._status('另存中…')
        self._log('\n另存目录（源文件不动）: ' + out_dir)
        ok_n = fail_n = 0
        self.saved_outputs = []
        for p, r in saveable:
            out, ok, msg = self._write_as(p, out_dir, r['new_lrc'])
            if ok:
                ok_n += 1
                self.saved_outputs.append(out)
                self._log('  OK   %-38s 改%d处 钳零%d 校验:%s -> %s'
                          % (r['file'], r['changed'], r['clamped'], msg, os.path.basename(out)))
            else:
                fail_n += 1
                self._log('  FAIL %-38s %s' % (r['file'], msg))
        self._status('另存完成：成功 %d，失败 %d' % (ok_n, fail_n))
        self._log('\n另存完成：成功 %d，失败 %d。需要推到手机请点「同步到手机」。' % (ok_n, fail_n))

    def sync_phone(self):
        """独立同步按钮：校验 adb -> push 另存文件 -> 按内容定位并删除缓存 -> 汇总。"""
        ok, info = sync.check_device()
        if not ok:
            messagebox.showerror('设备检查失败', info)
            return
        # 优先用本次另存的文件；没有则提示先保存
        files = [f for f in self.saved_outputs if os.path.exists(f)]
        if not files:
            messagebox.showinfo('提示', '没有可同步的文件，请先点「保存(另存)」')
            return
        phone_dir = self.var_phone.get().strip() or sync.DEFAULT_PHONE_DIR
        do_restart = self.var_post_restart.get()
        steps = ('将执行：\n1) push %d 个文件到手机 %s\n2) 按歌词内容定位并删除对应歌词缓存（先备份到本地）\n'
                 '3) 校验 MD5 + 删除确认' % (len(files), phone_dir))
        if do_restart:
            steps += '\n4) 全部成功后强制停止并重启 MusicFree'
        steps += '\n\n设备 %s\n确定吗？' % info
        if not messagebox.askyesno('确认同步', steps):
            return

        self._status('同步中（push 文件）…')
        self._log('\n===== 同步到手机 %s =====' % info)
        res = sync.push_files(files, phone_dir)
        for name, ok, msg in res:
            self._log('  push %-38s %s : %s' % (name, 'OK' if ok else 'FAIL', msg))

        self._status('同步中（处理歌词缓存）…')
        self._log('--- 歌词缓存 ---')
        cache_fail = 0
        for f in files:
            r = sync.sync_cache_for(f)
            self._log('  cache %-36s %s' % (r['file'], r['msg']))
            if r['need'] and not r['ok']:
                cache_fail += 1
        push_fail = sum(1 for _, ok, _ in res if not ok)
        self._log('\n同步完成：push 失败 %d，缓存失败 %d' % (push_fail, cache_fail))

        # 同步后动作：仅当全部成功且勾选时才强停+重启（一并动作）
        if do_restart:
            if push_fail == 0 and cache_fail == 0:
                self._status('同步中（强制停止 App）…')
                sok, smsg = sync.force_stop()
                self._log('  强停: ' + smsg)
                if sok:
                    self._status('同步中（重启 App）…')
                    rok, rmsg = sync.restart_app()
                    self._log('  重启: ' + rmsg)
                self._status('同步完成（已强停并重启）' if sok else '同步完成（强停失败）')
            else:
                self._status('同步完成：有失败，未强停重启')
                self._log('  有失败项（push %d / 缓存 %d），按设置跳过强停重启。' % (push_fail, cache_fail))
        else:
            self._status('同步完成：push失败%d 缓存失败%d' % (push_fail, cache_fail))
            self._log('  按设置不重启；你可在手机上强停重启 App 验证。')


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
