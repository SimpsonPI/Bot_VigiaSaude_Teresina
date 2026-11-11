from telegram import Update
from telegram.ext import ContextTypes


async def executar_comando_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Roteia o clique do botão inline para a função real do comando."""
    query = update.callback_query
    await query.answer()
    cmd = query.data

    # Importa as funções reais
    from handler import start, iniciar_cadastro_manual, comando_privacidade
    from handler_consultas import comando_verificar_todas
    from handler_meus_cadastros import comando_meus_cadastros
    from suporte import menu_suporte

    # 1. Apaga a mensagem com os botões inline para limpar a tela
    try:
        await query.message.delete()
    except Exception:
        pass

    # 2. Mapeia o callback para o comando de texto real
    comando_texto = cmd.replace("cmd_", "/")

    # 3. Simula a mensagem de texto que as funções esperam
    # (Isso resolve o erro do 'NoneType')
    if not update.message:
        update.message = query.message
    update.message.text = comando_texto
    update.message.from_user = query.from_user

    # 4. Roda a função correspondente
    if cmd == "cmd_start":
        await start(update, context)
    elif cmd == "cmd_cadastrar_nova":
        await iniciar_cadastro_manual(update, context)
    elif cmd == "cmd_meus_cadastros":
        await comando_meus_cadastros(update, context)
    elif cmd == "cmd_suporte":
        await menu_suporte(update, context)
    elif cmd == "cmd_privacidade":
        await comando_privacidade(update, context)
