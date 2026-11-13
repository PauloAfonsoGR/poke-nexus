"""PokeNexus - ponto de entrada.

Usuário final: dois cliques em PokeNexus.exe (gerado por build.bat).
Desenvolvimento: .venv\\Scripts\\python.exe main.py
"""
import sys
import traceback

# O Qt WebEngine precisa ser configurado e importado ANTES de criar o QApplication.
from browser.web_host import WebHost, setup_environment

DEVTOOLS_PORT = setup_environment()

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.config import APP_NAME, DATA_DIR, LOGS_DIR, load_config, prepare_data_dir  # noqa: E402
from app.gui import MainWindow  # noqa: E402
from app.instancia import Instancia  # noqa: E402
from app.manager import Manager  # noqa: E402


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    # Uma cópia só por pasta de dados (app/instancia.py). Se já há uma aberta (talvez escondida na bandeja),
    # ela mostra a janela e esta fecha aqui, antes de criar página, perfil ou conta.
    instancia = Instancia(DATA_DIR)
    if not instancia.abrir():
        return 0
    # O X deixa o programa na bandeja (MainWindow.closeEvent): fechar ou esconder janelas nunca encerra
    # sozinho. Fechar de verdade é só pelo MainWindow.sair() (bandeja: Sair, fim de sessão, atualizador).
    app.setQuitOnLastWindowClosed(False)
    try:
        prepare_data_dir()
        cfg, accounts = load_config()
    except Exception as e:
        QMessageBox.critical(None, APP_NAME, f"Não consegui ler a configuração (config.toml):\n\n{e}")
        return 1
    for a in accounts:
        a.profile_dir.mkdir(parents=True, exist_ok=True)

    web = WebHost(DEVTOOLS_PORT)
    manager = Manager(cfg, accounts, web)
    manager.start()
    win = MainWindow(manager, web)
    instancia.saindo = lambda: win._encerrando
    instancia.mostrar.connect(win.restaurar)
    win.showMaximized()
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            (LOGS_DIR / "crash.log").write_text(traceback.format_exc(), encoding="utf-8")
        finally:
            raise
