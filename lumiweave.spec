# -*- mode: python ; coding: utf-8 -*-
# LumiWeave — PyInstaller 打包为单一 exe
# 构建: pyinstaller lumiweave.spec
# 输出: dist/lumiweave.exe

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent

a = Analysis(
    ['lumiweave/launcher.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        ('builder/backend/agent_store/*.json', 'builder/backend/agent_store'),
        ('builder/backend/runtime_config.json', 'builder/backend'),
        ('builder/frontend/dist/**/*', 'builder/frontend/dist'),
        ('agents/*.yaml', 'agents'),
        ('shared/**/*.py', 'shared'),
        ('runner/**/*.py', 'runner'),
        ('builder/backend/**/*.py', 'builder/backend'),
        ('builder/backend/static/**/*', 'builder/backend/static'),
    ],
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
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
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
