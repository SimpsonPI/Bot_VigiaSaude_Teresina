import logging
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.ext import ContextTypes
from config import BOT_SUPORTE_LINK

logger = logging.getLogger(__name__)


def obter_menu_principal():
    """Remove qualquer teclado persistente da tela do usuário."""
    return ReplyKeyboardRemove()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal do /start ou /iniciar."""
    user = update.effective_user
    nome = user.first_name or "Usuário"

    mensagem = (
        f"👋 Olá, <b>{nome}</b>! É um prazer ter você aqui ao <b>VigiaSaude Teresina</b>.\n\n"
        f"🆔 <b>Seu ID do Telegram:</b> <code>{user.id}</code>\n\n"
        "Acesse todas as opções e comandos diretamente pelo menu nativo do Telegram "
        "(botão <b>[/]</b> ao lado da barra de digitação)."
    )


teclado_suporte = InlineKeyboardMarkup([[InlineKeyboardButton("📚 Instruções de Uso", callback_data="suporte")]])
await update.message.reply_text(
    "💡 <i>Precisa de ajuda com o VigiaSaúde?</i>", reply_markup=teclado_suporte, parse_mode="HTML"
)


async def comando_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde ao comando de ajuda com o script da Central de Atendimento."""
    script_atendimento = (
        "🤖 <b>Central de Atendimento Automatizado — VigiaSaude Teresina</b>\n\n"
        "Seja bem-vindo(a) ao suporte do VigiaSaude Teresina! Nosso sistema automatizado está pronto "
        "para auxiliar você com rapidez e precisão.\n\n"
        "📌 <b>O que você pode fazer por aqui?</b>\n"
        "• Consultar o status das suas regulações ativas.\n"
        "• Obter orientações sobre a consulta via Cartão SUS ou ID da Regulação.\n"
        "• Notificar divergências ou solicitar suporte técnico no sistema.\n\n"
        "💡 <b>Como iniciar?</b>\n"
        "Acesse nossa central dedicada abaixo para ser atendido pelo nosso assistente:"
    )

    teclado = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🤖 Central de Atendimento ao Usuário VigiaSaude Teresina",
                    url="https://t.me/VigiaSaude_Atendimento_ao_Usuario",
                )
            ]
        ]
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(script_atendimento, parse_mode="HTML", reply_markup=teclado)
    else:
        await update.message.reply_text(script_atendimento, parse_mode="HTML", reply_markup=teclado)


async def callback_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde ao clique no botão Ajuda com o script da Central de Atendimento."""
    query = update.callback_query
    await query.answer()

    script_atendimento = (
        "🤖 <b>Central de Atendimento Automatizado — VigiaSaude Teresina</b>\n\n"
        "Seja bem-vindo(a) ao suporte do VigiaSaude Teresina! Nosso sistema automatizado está pronto "
        "para auxiliar você com rapidez e precisão.\n\n"
        "📌 <b>O que você pode fazer por aqui?</b>\n"
        "• Consultar o status das suas regulações ativas.\n"
        "• Obter orientações sobre a consulta via Cartão SUS ou ID da Regulação.\n"
        "• Notificar divergências ou solicitar suporte técnico no sistema.\n\n"
        "💡 <b>Como iniciar?</b>\n"
        "Acesse nossa central dedicada abaixo para ser atendido pelo nosso assistente:"
    )

    teclado = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🤖 Central de Atendimento ao Usuário VigiaSaude Teresina",
                    url="https://t.me/VigiaSaude_Atendimento_ao_Usuario",
                )
            ],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="voltar_inicio")],
        ]
    )

    await query.edit_message_text(script_atendimento, parse_mode="HTML", reply_markup=teclado)
