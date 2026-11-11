# menu_institucional.py
import logging
from telegram import BotCommand, BotCommandScopeAllPrivateChats

logger = logging.getLogger(__name__)


async def configurar_menu_institucional(app):
    """Configura o menu nativo do Telegram com comandos institucionais."""
    comandos = [
        BotCommand("start", "👋 Iniciar atendimento"),
        BotCommand("cadastrar_nova", "➕ Cadastrar nova regulação"),
        BotCommand("meus_cadastros", "📋 Ver minhas regulações"),
        BotCommand("excluir", "🗑️ Excluir regulação"),
        BotCommand("suporte", "💬 Central de atendimento"),
        BotCommand("privacidade", "🔒 Política de privacidade"),
    ]

    try:
        await app.bot.set_my_commands(
            comandos,
            scope=BotCommandScopeAllPrivateChats(),
        )
        logger.info("✅ Menu institucional configurado com sucesso")
    except Exception as e:
        logger.error(f"Erro ao configurar menu: {e}")
