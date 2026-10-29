# -*- mode: python ; coding: utf-8 -*-
# Build do PokeNexus (PyInstaller). Gere com:  build.bat
#
# Modo "pasta" (onedir): PokeNexus\PokeNexus.exe + PokeNexus\_internal\.
# O Qt WebEngine (o navegador embutido) é grande e tem um processo auxiliar
# (QtWebEngineProcess.exe); no modo de arquivo único ele seria extraído para uma pasta
# temporária a CADA abertura. Em pasta, abre na hora.
import os
import shutil
import PySide6

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets", "assets"),          # pixel arts e ícone
        ("config.toml", "."),          # configuração padrão (copiada para a pasta de dados)
        ("hunts/bridge.js", "hunts"),  # ponte do Hunt Analyzer com os módulos do jogo
    ],
    # app._build: a versão do build de publicação (só existe quando o Actions ou o build.bat a grava)
    hiddenimports=["websockets", "websockets.asyncio.client"]
                  + (["app._build"] if os.path.isfile(os.path.join("app", "_build.py")) else []),
    hookspath=[],
    runtime_hooks=[],
    excludes=["playwright", "tkinter", "unittest", "pydoc", "test",
              "PySide6.QtOpenGL", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtQuickWidgets",
              "PySide6.QtPositioning", "PySide6.QtTest"],
    noarchive=False,
)


# O PySide6 traz muita coisa que o PokeNexus não usa (QML, 3D, gráficos, mapas, multimídia,
# traduções do Qt em dezenas de idiomas, recursos de depuração do navegador). Fica só o que o
# programa e o QtWebEngineProcess.exe carregam de fato (conferido nos módulos carregados com as
# 4 contas e o Hunt Analyzer abertos), mais o OpenGL por software, que o Qt usa em PCs sem
# driver de vídeo bom.
QT_DLLS = {"Qt6Core", "Qt6Gui", "Qt6Widgets", "Qt6Network", "Qt6OpenGL", "Qt6Positioning",
           "Qt6PrintSupport", "Qt6Qml", "Qt6QmlMeta", "Qt6QmlModels", "Qt6QmlWorkerScript",
           "Qt6Quick", "Qt6QuickWidgets", "Qt6WebChannel", "Qt6WebEngineCore", "Qt6WebEngineWidgets"}
PYSIDE_MODULOS = {"QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtPrintSupport", "QtWebChannel",
                  "QtWebEngineCore", "QtWebEngineWidgets"}
PLUGINS = {"platforms/qwindows.dll", "styles/qmodernwindowsstyle.dll",
           "imageformats/qgif.dll", "imageformats/qico.dll", "imageformats/qjpeg.dll"}
IDIOMAS_NAVEGADOR = ("en-US", "en-GB", "pt-BR", "pt-PT", "es", "es-419")
# Recursos só da versão de depuração do Qt e o painel visual do DevTools (o PokeNexus fala com
# a página pelo protocolo do DevTools, que não usa estes arquivos).
RECURSOS_FORA = ("qtwebengine_devtools_resources.pak", "qtwebengine_devtools_resources.debug.pak",
                 "qtwebengine_resources.debug.pak", "v8_context_snapshot.debug.bin")


def manter(entry):
    destino = entry[0].replace("\\", "/")
    nome = destino.rsplit("/", 1)[-1]
    # Qt uses the ICU implementation provided by Windows. Build environments that
    # expose Poppler on PATH can make PyInstaller collect Poppler's private ICU by
    # mistake (versioned exports), causing WinError 127 while importing QtCore.
    if nome.casefold() == "icuuc.dll" or (nome.casefold().startswith("icudt")
                                           and nome.casefold().endswith(".dll")):
        return False
    if destino in ("libcrypto-3-x64.dll", "libssl-3-x64.dll"):
        return False                  # OpenSSL do plugin de TLS do Qt (o navegador tem o próprio)
    if not destino.startswith("PySide6/"):
        return True
    sub = destino[len("PySide6/"):]
    if sub.startswith("qml/"):
        return False
    if sub.startswith("translations/"):
        if sub.startswith("translations/qtwebengine_locales/"):
            return nome.removesuffix(".pak") in IDIOMAS_NAVEGADOR
        return False
    if sub.startswith("plugins/"):
        return sub[len("plugins/"):] in PLUGINS
    if sub.startswith("resources/"):
        return nome not in RECURSOS_FORA and not nome.endswith((".debug.pak", ".debug.bin"))
    if "/" not in sub:
        base = nome.rsplit(".", 1)[0]
        if nome.startswith("Qt6") and nome.endswith(".dll"):
            return base in QT_DLLS
        if nome.endswith(".pyd") and nome.startswith("Qt"):
            return base in PYSIDE_MODULOS
    return True


a.datas = [e for e in a.datas if manter(e)]
a.binaries = [e for e in a.binaries if manter(e)]
# Python, Windows, and PySide6 can provide different MSVC runtime revisions.
# Mixing PySide's VCRUNTIME with system MSVCP/CONCRT can also break QtCore loading
# ("The specified procedure could not be found"), so bundle PySide's full set.
PYSIDE_DIR = os.path.dirname(PySide6.__file__)
MSVC_RUNTIME = (
    "CONCRT140.dll",
    "MSVCP140.dll",
    "MSVCP140_1.dll",
    "MSVCP140_2.dll",
    "MSVCP140_CODECVT_IDS.dll",
    "VCRUNTIME140.dll",
    "VCRUNTIME140_1.dll",
)
a.binaries = [e for e in a.binaries if os.path.basename(e[0]).casefold()
              not in {n.casefold() for n in MSVC_RUNTIME}]
for nome in MSVC_RUNTIME:
    origem = os.path.join(PYSIDE_DIR, nome.lower())
    if os.path.isfile(origem):
        a.binaries.append((nome, origem, "BINARY"))
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PokeNexus",
    icon="assets/pokenexus.ico",
    console=False,          # sem janela de terminal
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PokeNexus",
)

# The bootloader searches beside the executable before `_internal` is initialized.
# Keep the same complete set at the package root so the Windows loader never combines
# a bundled DLL with a different globally installed revision.
for nome in MSVC_RUNTIME:
    origem = os.path.join(PYSIDE_DIR, nome.lower())
    if os.path.isfile(origem):
        destino = os.path.join(DISTPATH, "PokeNexus", nome)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.copy2(origem, destino)
