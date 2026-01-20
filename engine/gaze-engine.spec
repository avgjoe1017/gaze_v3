# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Gaze Engine.

This bundles the Python engine with all ML dependencies into a single executable.
Run with: pyinstaller gaze-engine.spec
"""

import sys
import os
from pathlib import Path

# Determine platform suffix for output naming
if sys.platform == 'win32':
    PLATFORM_SUFFIX = 'x86_64-pc-windows-msvc'
    EXE_EXT = '.exe'
elif sys.platform == 'darwin':
    import platform
    arch = platform.machine()
    if arch == 'arm64':
        PLATFORM_SUFFIX = 'aarch64-apple-darwin'
    else:
        PLATFORM_SUFFIX = 'x86_64-apple-darwin'
    EXE_EXT = ''
else:
    PLATFORM_SUFFIX = 'x86_64-unknown-linux-gnu'
    EXE_EXT = ''

# Hidden imports for ML packages that PyInstaller doesn't detect automatically
hidden_imports = [
    # Torch core
    'torch',
    'torch._C',
    'torch._dynamo',
    'torch._inductor',
    'torch.utils',
    'torch.utils.cpp_extension',
    'torch.utils.data',
    'torch.nn',
    'torch.nn.functional',
    'torch.autograd',

    # Whisper
    'whisper',
    'whisper.tokenizer',
    'whisper.model',
    'whisper.audio',
    'whisper.decoding',

    # OpenCLIP
    'open_clip',
    'open_clip.model',
    'open_clip.tokenizer',
    'open_clip.factory',

    # Torchvision detection
    'torchvision',
    'torchvision._C',
    'torchvision.ops',
    'torchvision.models',
    'torchvision.models.detection',
    'torchvision.transforms',
    'torchvision.transforms._presets',

    # FAISS
    'faiss',
    'faiss.swigfaiss',

    # Image/Video processing
    'PIL',
    'PIL.Image',
    'cv2',
    'numpy',

    # FastAPI and web stack
    'fastapi',
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.websockets',
    'uvicorn.lifespan',
    'starlette',
    'pydantic',
    'pydantic.fields',
    'pydantic_core',

    # Async and networking
    'websockets',
    'httpx',
    'aiosqlite',
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',

    # Misc utilities
    'tiktoken',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
    'regex',
    'tqdm',
    'yaml',

    # Standard library modules sometimes missed
    'encodings',
    'encodings.utf_8',
    'encodings.ascii',
    'multiprocessing',
]

# Collect data files needed by packages
datas = []

# Try to collect package data for ML models
try:
    import whisper
    whisper_path = Path(whisper.__file__).parent
    datas.append((str(whisper_path / 'assets'), 'whisper/assets'))
except ImportError:
    pass

try:
    import tiktoken
    tiktoken_path = Path(tiktoken.__file__).parent
    if (tiktoken_path / 'registry.json').exists():
        datas.append((str(tiktoken_path / 'registry.json'), 'tiktoken'))
except ImportError:
    pass

# Binary files to include
binaries = []

# Analysis block
a = Analysis(
    ['src/engine/main.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude optional JIT tooling pulled in by local env (not used at runtime).
        'numba',
        'llvmlite',
        # Exclude GUI packages not needed
        'tkinter',
        'matplotlib',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        # Exclude test packages
        'pytest',
        'unittest',
        # Exclude dev tools
        'IPython',
        'jupyter',
        'notebook',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f'gaze-engine-{PLATFORM_SUFFIX}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for server logging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
