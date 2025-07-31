# build.py

from PyInstaller.__main__ import run
pyinstaller_args = [
    '--onefile',
    '--windowed',
    '--name=Justice4all',
    '--icon=NONE',
    '--upx-dir=.', 
    '--exclude-module=PyQt5.QtDesigner',
    '--exclude-module=PyQt5.QtNetwork',
    '--exclude-module=PyQt5.QtOpenGL',
    '--exclude-module=PyQt5.QtMultimedia',
    '--exclude-module=PyQt5.QtMultimediaWidgets',
    '--exclude-module=PyQt5.QtPrintSupport',
    '--exclude-module=PyQt5.QtQuick',
    '--exclude-module=PyQt5.QtSql',
    '--exclude-module=PyQt5.QtSvg',
    '--exclude-module=PyQt5.QtTest',
    '--exclude-module=PyQt5.QtWebChannel',
    '--exclude-module=PyQt5.QtWebEngine',
    '--exclude-module=PyQt5.QtWebEngineCore',
    '--exclude-module=PyQt5.QtWebEngineWidgets',
    '--exclude-module=PyQt5.QtWebKit',
    '--exclude-module=PyQt5.QtWebKitWidgets',
    '--exclude-module=PyQt5.QtXml',
    '--exclude-module=PyQt5.QtXmlPatterns',
    

    'Justice4all.py'
]

if __name__ == '__main__':
    run(pyinstaller_args)
    print("\n\nСборка завершена! Исполняемый файл находится в папке 'dist'.")
