import sys
from distutils.core import setup
from Cython.Build import cythonize
from PyInstaller.__main__ import run

# Сначала компилируем в C
setup(
    ext_modules=cythonize("Justice4all.py", compiler_directives={'language_level': "3"}),
    script_args=["build_ext", "--inplace"]
)

# Затем собираем в exe с PyInstaller
pyinstaller_args = [
    '--onefile',
    '--windowed',
    '--name=Justice4all',
    '--icon=NONE',
    'Justice4all.py'
]

run(pyinstaller_args)