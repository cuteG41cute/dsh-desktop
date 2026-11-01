#!/usr/bin/env python3
"""探测 WebKit2 4.1 里做右键菜单要用的 API：编辑命令常量、命中测试、编辑器状态。"""
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import WebKit2  # noqa: E402

names = dir(WebKit2)
print('== EDITING 常量:', [n for n in names if 'EDIT' in n.upper()][:30])
print('== EditCommand 枚举:', [n for n in names if n.lower().startswith('editcommand')])
print('== HitTest 相关:', [n for n in names if 'HitTest' in n][:10])
print('== EditorState:', [n for n in names if 'EditorState' in n])
print('== PolicyDecision 类型枚举:', [n for n in names if 'PolicyDecisionType' in n])
try:
    print('== HitTestResult 方法:', [m for m in dir(WebKit2.HitTestResult) if not m.startswith('_')][:20])
except Exception as exc:
    print('  ', exc)
try:
    print('== EditorState props:', [p.name for p in WebKit2.EditorState.list_properties()])
except Exception as exc:
    print('  ', exc)
try:
    print('== WebView 右键相关方法:', [m for m in dir(WebKit2.WebView) if 'context' in m.lower() or 'editor' in m.lower() or 'hit' in m.lower()])
except Exception as exc:
    print('  ', exc)
