#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工具箱统一配置存储（不落在程序目录）

位置：%APPDATA%\\MusicFree工具箱\\config.json
结构：{"embed": {...}, "offset": {...}} —— 两个页签各占一节，共用一个文件

为什么不用 exe 旁边的 _*_config.json：
  单文件 exe 拷到哪里都干净，改设置不会在旁边生成新文件。

旧版散落文件的迁移：
  exe/脚本目录若还留着 _embed_gui_config.json、_offset_gui_config.json，
  首次读取新配置缺失时会把它们的内容搬进新文件（旧文件保留，自行删除即可）。
"""
import os
import sys
import json

APP_NAME = 'MusicFree工具箱'
LEGACY_NAMES = {
    'embed': '_embed_gui_config.json',
    'offset': '_offset_gui_config.json',
}


def cfg_dir():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    return os.path.join(base, APP_NAME)


CFG_PATH = os.path.join(cfg_dir(), 'config.json')


def _program_dir():
    """旧配置的所在地：打包态是 exe 目录，源码态是脚本目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _read_all():
    try:
        with open(CFG_PATH, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load(section, defaults=None):
    """读某节配置；缺项用 defaults 补齐。新文件不存在时尝试从旧文件迁移。"""
    cfg = dict(defaults or {})
    data = _read_all()
    if isinstance(data.get(section), dict):
        cfg.update(data[section])
        return cfg

    name = LEGACY_NAMES.get(section)
    if name:
        legacy = os.path.join(_program_dir(), name)
        if os.path.exists(legacy):
            try:
                with open(legacy, encoding='utf-8') as f:
                    old = json.load(f)
                if isinstance(old, dict) and old:
                    cfg.update(old)
                    save(section, cfg)
            except Exception:
                pass
    return cfg


def save(section, values):
    """写某节配置（先读全量再合并，不覆盖另一节）。成功返回 True。"""
    data = _read_all()
    data[section] = dict(values)
    try:
        os.makedirs(cfg_dir(), exist_ok=True)
        tmp = CFG_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CFG_PATH)
        return True
    except Exception:
        try:
            os.remove(CFG_PATH + '.tmp')
        except OSError:
            pass
        return False
