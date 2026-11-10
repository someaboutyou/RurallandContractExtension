# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules
root = Path.cwd() / '..' / 'runtime' / 'windows' / 'python'
binaries = [(str(root/'Library'/'bin'/'tcl86t.dll'), '.'), (str(root/'Library'/'bin'/'tk86t.dll'), '.')]
datas = [('UI/startup.ico','UI'), (str(root/'Library'/'lib'/'tcl8.6'),'tcl8.6'), (str(root/'Library'/'lib'/'tk8.6'),'tk8.6')]
a = Analysis(['launcher.py'], pathex=['.'], binaries=binaries, datas=datas, hiddenimports=collect_submodules('tkinter'))
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, name='RurallandLauncher', icon='UI/startup.ico', console=False)