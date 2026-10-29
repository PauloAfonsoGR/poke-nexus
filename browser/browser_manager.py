"""Sessões das contas: uma página embutida (Qt WebEngine) por conta.

Cada conta tem o seu perfil persistente em <dados>/profiles/conta_XX/web (cookies,
LocalStorage e login próprios). Nada é compartilhado entre contas.
"""
import asyncio
import itertools
from pathlib import Path

from app.config import Account
from browser.cdp import CdpPage
from browser.web_host import WebHost


class BrowserManager:
    def __init__(self, web: WebHost, zoom: float = 1.0):
        self.web = web
        self.zoom = zoom
        self.shutting_down = False
        self.background = False
        self._seq = itertools.count(1)

    @staticmethod
    def web_dir(acc: Account) -> Path:
        return acc.profile_dir / "web"

    async def open_page(self, acc: Account) -> CdpPage:
        """Abre a página da conta e conecta o DevTools nela (monitoramento + automação)."""
        # Endereço único para achar ESTA página no DevTools (só letras e números: o Chromium
        # não reescreve).
        marker = f"about:blank#pokeidle-conta{acc.index + 1}-{next(self._seq)}"
        await asyncio.wrap_future(self.web.open(acc.index, str(self.web_dir(acc)), marker, self.zoom))
        return await CdpPage.attach(self.web.port, marker)

    async def open_login_page(self, acc: Account, url: str):
        """Abre o jogo SEM conectar o DevTools: uma página comum, só para a pessoa entrar
        na conta (reserva, para o caso de a verificação de login não passar com o
        monitoramento ligado)."""
        await asyncio.wrap_future(self.web.open(acc.index, str(self.web_dir(acc)), url, self.zoom))

    async def close_page(self, acc: Account, page: CdpPage | None):
        if page:
            try:
                await asyncio.wait_for(page.close(), 5)
            except Exception:
                pass
        # Ao sair do programa quem fecha as páginas é a própria interface (close_all).
        if not self.shutting_down:
            await asyncio.wrap_future(self.web.close(acc.index))
