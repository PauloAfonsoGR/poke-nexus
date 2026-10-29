"""Economia nativa pelo DOM, com restauração da preferência anterior após reabrir.

Controles conferidos no app.js público 1.375.3 (28/10/2026). O botão chama a
rotina completa do jogo: libera a cena e reduz os eventos de campo no servidor.
Não basta esconder um canvas ou trocar uma classe CSS.
"""

JS_ECONOMIA = """(segundoPlano) => {
  const raiz = document.documentElement;
  const chave = 'pokenexus-economia-anterior';
  const ligado = () => raiz.classList.contains('modo-economia');
  const anterior = localStorage.getItem(chave);
  if (segundoPlano) {
    if (ligado()) return 'mantida';
    const botao = document.querySelector('#hunt-eco');
    if (!botao || botao.disabled) return 'indisponivel';
    if (anterior === null) {
      localStorage.setItem(chave, localStorage.getItem('cfg-economia') === null
        ? 'ausente' : localStorage.getItem('cfg-economia'));
    }
    botao.click();
    if (!ligado()) {
      if (anterior === null) localStorage.removeItem(chave);
      return 'indisponivel';
    }
    return 'ativada';
  }
  if (anterior === null) return 'mantida';
  if (ligado()) {
    const botao = document.querySelector('#eco-sair');
    if (!botao || botao.disabled) return 'indisponivel';
    botao.click();
    if (ligado()) return 'indisponivel';
  }
  if (anterior === 'ausente') localStorage.removeItem('cfg-economia');
  else localStorage.setItem('cfg-economia', anterior);
  localStorage.removeItem(chave);
  return 'restaurada';
}"""
