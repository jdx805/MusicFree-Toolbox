#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""音乐工具箱 —— 内嵌歌词 / 歌词偏移 / 入库体检 三合一

三个页签复用现有模块，各自的配置与行为完全不变：
  内嵌歌词 -> lyric_embed_gui.App（配置 _embed_gui_config.json）
  歌词偏移 -> lyric_offset_gui.App（配置 _offset_gui_config.json）
  入库体检 -> musicfree_check（配置 _check_ignore.json，报告存 体检报告\\）

原有的三个独立 bat 仍可单独使用，本程序只是多一个统一入口。
"""
import os
import sys
import io
import contextlib
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

HERE = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
        else os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import lyric_embed_gui
import lyric_offset_gui
import musicfree_check

FONT = ('Microsoft YaHei', 10)


class CheckTab:
    """把命令行的体检工具包成一个页签；结果直接显示在页内。"""

    def __init__(self, root, host):
        self.root = root
        frm = ttk.Frame(host, padding=10)
        frm.pack(fill='both', expand=True)
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(3, weight=1)

        ttk.Label(frm, text='扫描目录：', font=FONT).grid(row=0, column=0, sticky='w', pady=(0, 6))
        self.var_dir = tk.StringVar(value=musicfree_check.DEFAULT_DIR)
        ttk.Entry(frm, textvariable=self.var_dir, font=FONT).grid(row=0, column=1, sticky='ew', pady=(0, 6))
        ttk.Button(frm, text='浏览…', command=self.choose_dir).grid(row=0, column=2, sticky='e', pady=(0, 6))

        tip = '入库（推手机 / 交给 MusicFree 扫描）之前跑一次。只读，不改文件。\n检查：容器与扩展名不符 / 无内嵌歌词 / 标签为空 / 文件名规范。纯音乐登记在 _check_ignore.json。'
        ttk.Label(frm, text=tip, font=FONT, foreground='#555').grid(row=1, column=0, columnspan=3, sticky='w', pady=(0, 8))

        self.btn = ttk.Button(frm, text='开始体检', command=self.run)
        self.btn.grid(row=2, column=0, columnspan=3, sticky='w', pady=(0, 6))

        self.text = scrolledtext.ScrolledText(frm, font=('Consolas', 10), wrap='none', state='disabled')
        self.text.grid(row=3, column=0, columnspan=3, sticky='nsew')

    def choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.var_dir.get() or HERE)
        if d:
            self.var_dir.set(d)

    def run(self):
        folder = self.var_dir.get().strip()
        if not os.path.isdir(folder):
            messagebox.showinfo('提示', '目录不存在：%s' % folder)
            return
        self.btn.config(state='disabled')
        self.text.config(state='normal')
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', '体检中…\n')
        self.text.config(state='disabled')

        def work():
            buf = io.StringIO()
            old_argv = sys.argv
            try:
                sys.argv = ['musicfree_check.py', folder]
                with contextlib.redirect_stdout(buf):
                    musicfree_check.main()
            except Exception as e:
                buf.write('体检出错：%s\n' % e)
            finally:
                sys.argv = old_argv
            result = buf.getvalue()
            self.root.after(0, lambda: self.done(result))

        threading.Thread(target=work, daemon=True).start()

    def done(self, text):
        self.text.config(state='normal')
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', text)
        self.text.config(state='disabled')
        self.btn.config(state='normal')


def main():
    root = tk.Tk()
    root.title('音乐工具箱 —— 内嵌歌词 / 歌词偏移 / 入库体检')
    root.geometry('1120x800')

    nb = ttk.Notebook(root)
    nb.pack(fill='both', expand=True, padx=4, pady=4)

    tab_embed = ttk.Frame(nb)
    tab_offset = ttk.Frame(nb)
    tab_check = ttk.Frame(nb)
    nb.add(tab_embed, text='① 内嵌歌词')
    nb.add(tab_offset, text='② 歌词偏移')
    nb.add(tab_check, text='③ 入库体检')

    lyric_embed_gui.App(root, tab_embed)
    lyric_offset_gui.App(root, tab_offset)
    CheckTab(root, tab_check)

    root.mainloop()


if __name__ == '__main__':
    main()
