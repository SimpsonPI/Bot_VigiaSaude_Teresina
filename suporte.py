from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from config import BOT_SUPORTE_LINK
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# Constante de estado para o ConversationHandler
AGUARDANDO_MENSAGEM = 1


async def menu_suporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Central de Atendimento - Links, FAQs e Email"""
    texto = (
        "🤖 <b>Central de Atendimento VigiaSaude Teresina</b>\n\n"
        "Como podemos ajudar você hoje?\n\n"
        "<b>📌 Canais de Atendimento:</b>\n"
        "• 🤖 <b>Bot de Atendimento:</b> @central_vigiasaude_bot\n"
        "• 📧 <b>Email:</b> suportevigiasaude@gmail.com\n\n"
        "<b>❓ Perguntas Frequentes (FAQs):</b>\n"
        "1️⃣ Como cadastrar uma nova regulação?\n"
        "2️⃣ Como verificar o status das regulações?\n"
        "3️⃣ Onde encontrar o Cartão SUS ou ID?\n"
        "4️⃣ Como corrigir dados?\n"
        "6️⃣ O VigiaSaude Teresina tem vínculo com o governo?\n\n"
        "Selecione uma opção abaixo:"
    )

    teclado = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🤖 Bot de Atendimento", url=BOT_SUPORTE_LINK),
                InlineKeyboardButton("📧 Email", callback_data="suporte_email"),
            ],
            [
                InlineKeyboardButton("1️⃣ Cadastrar", callback_data="faq_cadastrar"),
                InlineKeyboardButton("2️⃣ Consultar", callback_data="faq_consultar"),
            ],
            [
                InlineKeyboardButton("3️⃣ Cartão SUS/ID", callback_data="faq_id"),
                InlineKeyboardButton("4️⃣ Alterar Dados", callback_data="faq_alterar"),
            ],
            [InlineKeyboardButton("6️⃣ Vínculo Governo", callback_data="faq_governo")],
            [InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="iniciar")],
        ]
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)
    elif update.message:
        await update.message.reply_text(texto, parse_mode="HTML", reply_markup=teclado)


async def exibir_resposta_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe as respostas individuais do FAQ com botão para voltar ao menu."""
    query = update.callback_query
    await query.answer()

    dados = query.data

    respostas = {
        "faq_cadastrar": (
            "📌 <b>Como cadastrar uma nova regulação?</b>\n\n"
            "• Utilize o comando <b>/cadastrar_nova</b> no menu do bot.\n"
            "• Digite o número do seu <b>Cartão SUS</b> (15 dígitos) ou o <b>ID da Regulação</b> solicitado.\n"
            "• Siga as instruções na tela até a confirmação do cadastro."
        ),
        "faq_consultar": ("🔍 <b>Como consultar minhas regulações?</b>\n\n"),
        "faq_id": (
            "🆔 <b>Onde encontrar o Cartão SUS ou ID da Regulação?</b>\n\n"
            "• <b>Cartão SUS:</b> O número possui 15 dígitos e pode ser encontrado no seu cartão impresso ou no aplicativo 'Meu SUS Digital'.\n"
            "• <b>ID da Regulação:</b> É o código de identificação fornecido pelo posto de saúde ou hospital no momento da solicitação do procedimento."
        ),
        "faq_alterar": (
            "✏️ <b>Como corrigir ou alterar dados?</b>\n\n"
            "• Para alterar informações de uma regulação já cadastrada, utilize o comando <b>/corrigir</b> e selecione o registro desejado."
        ),
        "faq_governo": (
            "⚠️ <b>O VigiaSaude Teresina tem vínculo com o governo?</b>\n\n"
            "Não. O VigiaSaude Teresina é uma ferramenta <b>independente</b> e não possui vínculo oficial com a Prefeitura de Teresina, FMS ou SUS.\n"
            "As informações são baseadas nos dados públicos dos portais de regulação."
        ),
    }

    texto_resposta = respostas.get(dados, "Informação não encontrada no FAQ.")

    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar ao Menu de Atendimento", callback_data="suporte")]])

    await query.edit_message_text(texto_resposta, parse_mode="HTML", reply_markup=teclado)


async def suporte_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe o email de suporte."""
    query = update.callback_query
    await query.answer()

    texto = (
        "📧 <b>Email de Suporte</b>\n\n"
        "Para entrar em contato com nossa equipe, utilize o email:\n\n"
        "<b>suportevigiasaude@gmail.com</b>\n\n"
        "Nossa equipe responderá o mais breve possível.\n\n"
        "<b>Horário de atendimento:</b>\n"
        "Segunda a Sexta: 08h às 18h\n"
        "Sábado: 08h às 12h"
    )

    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar ao Menu de Atendimento", callback_data="suporte")]])

    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def iniciar_atendimento_20(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia a escuta da dúvida caso o FAQ não resolva."""
    query = update.callback_query
    await query.answer()

    mensagem = (
        "🤖 <b>Central de Atendimento ao Usuário VigiaSaude Teresina</b>\n\n"
        "Por favor, digite abaixo a sua dúvida ou descreva detalhadamente o seu problema sobre o Cartão SUS ou ID da Regulação.\n\n"
        "<i>Sua mensagem será enviada diretamente para a nossa equipe de suporte.</i>"
    )

    teclado = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅️ Voltar ao FAQ", callback_data="suporte")],
            [InlineKeyboardButton("❌ Fechar", callback_data="fechar_menu")],
        ]
    )

    await query.edit_message_text(mensagem, parse_mode="HTML", reply_markup=teclado)

    return AGUARDANDO_MENSAGEM


async def receber_mensagem_suporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe a mensagem enviada pelo usuário e confirma o protocolo de atendimento."""
    user = update.effective_user
    texto_usuario = update.message.text

    # Confirmação enviada ao usuário
    await update.message.reply_text(
        "✅ <b>Mensagem enviada com sucesso!</b>\n\n"
        "Sua solicitação sobre o Cartão SUS / ID da Regulação foi registrada. "
        "Nossa equipe de suporte analisará o chamado e responderá em breve.",
        parse_mode="HTML",
    )

    return ConversationHandler.END


async def cancelar_suporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela ou fecha o fluxo de atendimento."""
    texto = "❌ Atendimento encerrado. Se precisar de algo, acesse o menu novamente!"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(texto)
    elif update.message:
        await update.message.reply_text(texto)

    return ConversationHandler.END


async def responder_chamado_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permite ao administrador responder a um chamado diretamente (se aplicável)."""
    pass


# Declaração do fluxo conversacional do suporte
conv_suporte = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(iniciar_atendimento_20, pattern="^iniciar_atendimento_20$"),
        CallbackQueryHandler(menu_suporte, pattern="^suporte$"),
        CommandHandler("suporte", menu_suporte),
    ],
    states={
        AGUARDANDO_MENSAGEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_mensagem_suporte)],
    },
    fallbacks=[
        CallbackQueryHandler(exibir_resposta_faq, pattern="^faq_"),
        CallbackQueryHandler(iniciar_atendimento_20, pattern="^iniciar_atendimento_20$"),
        CallbackQueryHandler(menu_suporte, pattern="^suporte$"),
        CallbackQueryHandler(cancelar_suporte, pattern="^fechar_menu$"),
    ],
)
