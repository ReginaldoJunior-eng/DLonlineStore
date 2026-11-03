# -*- coding: utf-8 -*-
"""Estado global do Upseller — vive na memória do processo Django (que fica de
pé o tempo todo, diferente do rerun-por-clique do Streamlit), então um
dicionário de módulo simples já basta como singleton. Substitui o padrão
st.session_state + st.cache_resource do app original.

Rodou headless (--headless=new) por um período curto em 2026-08-02, mas
voltou atrás no mesmo dia: o menu "Exportar" (Pedidos > Enviado), que só abre
com hover de mouse de verdade, parou de funcionar em headless — exatamente o
tipo de bug de hover que já tinha acontecido na versão cloud. Hoje roda com
Chrome de verdade (hover funciona), só que posicionado fora da área visível
da tela (ver upseller/driver.py:criar_driver()), pra não aparecer pra quem
estiver usando o PC sem abrir mão do hover/mouse funcionando direito."""

ESTADO = {
    "driver": None,
    "logado": False,
    "etapa": 0,  # 0=inicial, 1=captcha, 2=codigo email, 3=logado
    "captcha_img_b64": None,
    "erro": None,
    "code_enviado": False,
    # Progresso de tarefas longas (publicar em massa, exportar pedidos, varredura)
    "tarefa": None,  # {"tipo": ..., "rodando": bool, "log": [...], "resultado": {...}}
}


def reset_login():
    ESTADO["driver"] = None
    ESTADO["logado"] = False
    ESTADO["etapa"] = 0
    ESTADO["captcha_img_b64"] = None
    ESTADO["erro"] = None
    ESTADO["code_enviado"] = False
