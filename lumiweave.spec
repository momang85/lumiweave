# -*- mode: python ; coding: utf-8 -*-
# LumiWeave — PyInstaller 打包为单一 exe
# 构建: pyinstaller lumiweave.spec
# 输出: dist/lumiweave.exe

import os, sys, glob as _glob
from pathlib import Path

try:
    ROOT = Path(SPECPATH)
except NameError:
    ROOT = Path(os.getcwd())

os.chdir(str(ROOT))

# 收集所有需要打包的数据文件
datas = []
# agent_store JSON
for f in _glob.glob('builder/backend/agent_store/*.json'):
    datas.append((f, os.path.dirname(f)))
# runtime config example
datas.append(('builder/backend/runtime_config.example.json', 'builder/backend'))
# frontend built files
for f in _glob.glob('builder/frontend/dist/**/*', recursive=True):
    if os.path.isfile(f):
        rel = os.path.relpath(os.path.dirname(f), 'builder/frontend')
        datas.append((f, f'builder/frontend/{rel}'))
# agent YAML files
for f in _glob.glob('agents/*.yaml'):
    datas.append((f, 'agents'))

a = Analysis(
    ['lumiweave/launcher.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'uvicorn', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http',
        'fastapi', 'starlette', 'pydantic',
        'openai', 'anthropic', 'google.generativeai',
        'yaml', 'rich', 'json',
        'shared', 'shared.agent_dispatcher', 'shared.agent_memory',
        'shared.session_manager', 'shared.ir_models', 'shared.rate_limiter',
        'shared.adapters', 'shared.adapters.openai_adapter',
        'shared.adapters.deepseek_adapter', 'shared.adapters.base_adapter',
        'shared.adapter_registry',
        'runner', 'runner.tool_handlers', 'runner.runner',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='lumiweave',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='lumiweave.ico' if os.path.exists('lumiweave.ico') else None,
)
