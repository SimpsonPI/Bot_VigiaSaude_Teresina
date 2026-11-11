import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from config import EMAIL_SUPORTE, BOT_SUPORTE_USERNAME, BOT_SUPORTE_LINK

logger = logging.getLogger(__name__)

# Definindo os estados da conversação
MENU_PRINCIPAL = 0


async def iniciar_atendimento(update: Update, context):
    """Passo 1: Recebe a mensagem inicial, dá boas-vindas e exibe o menu de opções."""
    if update.message and update.message.from_user.is_bot:
        return

    user_nome = update.effective_user.first_name or "Usuário"

    teclado = [
        [InlineKeyboardButton("1️⃣ Como consultar minha regulação?", callback_data="opcao_1")],
        [InlineKeyboardButton("2️⃣ Prazos para exames e consultas", callback_data="opcao_2")],
        [InlineKeyboardButton("3️⃣ Problemas de acesso à plataforma", callback_data="opcao_3")],
        [InlineKeyboardButton("👤 Falar com Atendimento Personalizado", callback_data="personalizado")],
    ]
    reply_markup = InlineKeyboardMarkup(teclado)

    texto_boas_vindas = (
        f"Olá, <b>{user_nome}</b>! Seja bem-vinda(o) ao suporte do VigiaSaude Teresina.\n\n"
        "Para agilizar o seu atendimento, escolha uma das opções abaixo clicando em um dos botões:\n\n"
        f'📧 <b>E-mail:</b> <a href="mailto:{EMAIL_SUPORTE}">{EMAIL_SUPORTE}</a>\n'
        f'🤖 <b>Atendimento:</b> <a href="{BOT_SUPORTE_LINK}">{BOT_SUPORTE_USERNAME}</a>'
    )

    if update.message:
        await update.message.reply_text(
            texto_boas_vindas,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    return MENU_PRINCIPAL


async def tratar_escolha_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    dados = query.data

    teclado_voltar = [
        [
            InlineKeyboardButton("⬅️ Voltar ao Menu", callback_data="voltar_menu"),
            InlineKeyboardButton("👤 Atendimento Personalizado", callback_data="personalizado"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(teclado_voltar)

    if dados == "opcao_1":
        resposta = (
            "📌 <b>Como consultar sua regulação:</b>\n\n"
            "Você pode acompanhar o status da sua regulação diretamente pelo menu principal do VigiaSaude Teresina inserindo o seu cartão SUS ou CPF."
        )
    elif dados == "opcao_2":
        resposta = (
            "📌 <b>Prazos para exames e consultas:</b>\n\n"
            "Os prazos variam conforme a prioridade médica definida na rede pública. Casos urgentes são priorizados pela central de regulação do estado."
        )
    elif dados == "opcao_3":
        resposta = (
            "📌 <b>Problemas de acesso:</b>\n\n"
            "Caso esteja com falhas para entrar, tente redefinir sua senha na tela de login ou limpe os dados de navegação do seu aplicativo.\n\n"
            f'Se persistir, contate-nos via e-mail: <a href="mailto:{EMAIL_SUPORTE}">{EMAIL_SUPORTE}</a>'
        )
    elif dados == "voltar_menu":
        return await iniciar_atendimento_callback(query)
    elif dados == "personalizado" or dados == "transbordo" or dados == "iniciar_atendimento_20":
        # Aciona o transbordo e muda para o estado que aguarda a mensagem do usuário
        from suporte import AGUARDANDO_MENSAGEM

        await query.edit_message_text(
            text="🎧 <b>Atendimento Personalizado VigiaSaude Teresina</b>\n\n"
            "Escreva abaixo a sua dúvida ou demanda para que nossa equipe receba por aqui:",
            parse_mode="HTML",
        )
        return AGUARDANDO_MENSAGEM
    else:
        resposta = "Opção inválida."

    await query.edit_message_text(
        text=resposta,
        reply_markup=reply_markup,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    return MENU_PRINCIPAL


async def iniciar_atendimento_callback(query):
    """Auxiliar para reiniciar o menu via callback."""
    teclado = [
        [InlineKeyboardButton("1️⃣ Como consultar minha regulação?", callback_data="opcao_1")],
        [InlineKeyboardButton("2️⃣ Prazos para exames e consultas", callback_data="opcao_2")],
        [InlineKeyboardButton("3️⃣ Problemas de acesso à plataforma", callback_data="opcao_3")],
        [InlineKeyboardButton("👤 Falar com Atendimento Personalizado", callback_data="personalizado")],
    ]
    await query.edit_message_text(
        text="Escolha uma das opções abaixo:",
        reply_markup=InlineKeyboardMarkup(teclado),
        parse_mode="HTML",
    )
    return MENU_PRINCIPAL


async def receber_mensagem_suporte(update, context):
    user = update.effective_user
    texto_usuario = update.message.text
    CANAL_SUPORTE_ID = -1004479965268

    try:
        # Envia a demanda do usuário direto para o seu canal do Telegram
        await context.bot.send_message(
            chat_id=CANAL_SUPORTE_ID,
            text=(
                f"🚨 <b>NOVO CHAMADO DE SUPORTE</b>\n\n"
                f"• <b>Usuário:</b> {user.full_name} (@{user.username or 'Sem username'})\n"
                f"• <b>ID do Telegram:</b> <code>{user.id}</code>\n\n"
                f"• <b>Mensagem do usuário:</b>\n{texto_usuario}"
            ),
            parse_mode="HTML",
        )

        # Confirma para o usuário
        await update.message.reply_text(
            "✅ Sua mensagem foi enviada com sucesso! Em breve nossa equipe retornará por aqui."
        )
    except Exception as e:
        print(f"Erro ao enviar para o canal: {e}")

    return ConversationHandler.END
