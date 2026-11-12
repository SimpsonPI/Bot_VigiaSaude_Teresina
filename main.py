from dotenv import load_dotenv
from bot_seguranca import global_error_handler
from handler_admin_metricas import comando_admin_metricas
from telegram.ext import PicklePersistence
from handler_meus_cadastros import callback_verificar_regulacao
from handler_broadcast_cidadao import (
    iniciar_broadcast,
    receber_e_disparar,
    cancelar_broadcast,
    ESCOLHER_TIPO,
    RECEBER_CONTEUDO,
)
from telegram.ext import CallbackQueryHandler, MessageHandler, filters

load_dotenv()

persistence = PicklePersistence(filepath="bot_persistencia.pickle")
# Só DEPOIS os outros imports
from handler_broadcast import conv_broadcast
from admin_panel import comando_painel, callback_painel
from handler_meus_cadastros import comando_meus_cadastros
from handler_meus_cadastros import comando_meus_cadastros, callback_verificar_regulacao
from handler_consultas import (
    comando_verificar_todas,
    iniciar_verificar_especifico,
    processar_verificar_especifico,
)

import logging

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    force=True,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

import os
import json
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import BotCommand, BotCommandScopeAllPrivateChats, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, NetworkError
from handler_privacidade import comando_privacidade

from admin_ia_controller import executar_acao_admin

from handler import (
    comando_verificar_todas,
    conv_cadastro,
    conv_consulta_especifica,
    conv_excluir,
    iniciar_cadastro_manual,
    iniciar_corrigir,
    iniciar_excluir,
    iniciar_verificar_especifico,
    mostrar_email_suporte,
    start,
    configurar_menu_comandos,
    callback_faq_suporte,
    callback_privacidade_voltar,
    callback_abrir_termo_privacidade,
    callback_optout_teaser,
    faq_cadastrar,
    faq_consultar,
    faq_id,
    faq_alterar,
    faq_governo,
)

from handler_gestao import (
    selecionar_regulacao_callback,
    selecionar_campo_callback,
    salvar_novo_valor,
)
from utils import (
    SELECIONAR_REGULACAO,
    SELECIONAR_CAMPO,
    AGUARDAR_NOVO_VALOR,
)
from admin import (
    comando_estatisticas,
    comando_listar_ativos,
    comando_bloquear,
    comando_detalhes,
    comando_aviso,
    comando_menu_admin,
)
from suporte import (
    menu_suporte,
    exibir_resposta_faq,
    iniciar_atendimento_20,
    cancelar_suporte,
    conv_suporte,
    suporte_email,
)

from handler_midia_admin import conv_envio_midia
from handler_enquete_local import (
    conv_criar_enquete,
    receber_voto,
    voto_ja_registrado,
    comando_resultado,
    callback_resultado,
    comando_resultado_detalhado,
    comando_listar_enquetes,
    comando_encerrar,
    comando_apagar_enquete,
)

from autorizacao import verificar_autorizado
from handler_autorizacao import (
    comando_autorizar,
    comando_desautorizar,
    comando_listar_autorizados,
)
from telegram.ext import TypeHandler, ApplicationHandlerStop

logger = logging.getLogger(__name__)


async def erro_global_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    erro = context.error
    if isinstance(erro, (TimedOut, NetworkError)):
        logger.warning(f"⚠️ Timeout de rede: {erro}. Aguardando 5s...")
        await asyncio.sleep(5)
        return
    logger.error(msg="Exceção capturada pelo bot:", exc_info=context.error)


async def post_init(app):
    """Executa tarefas após a inicialização do bot."""

    # 🛑 LIMPA O CACHE DE COMANDOS DO TELEGRAM (Remove o /verificar_todos do menu)
    await app.bot.delete_my_commands()

    from menu_institucional import configurar_menu_institucional

    await configurar_menu_institucional(app)

    # --- CONFIGURAÇÃO DAS TAREFAS AGENDADAS ---
    job_queue = app.job_queue
    if job_queue:
        # 1. Varredura automática de regulações (6h)
        from handler import executar_varredura_automatica

        job_queue.run_repeating(
            executar_varredura_automatica,
            interval=6 * 3600,  # 6 HORAS
            first=180,  # primeira execução 3 min após o boot
        )
        logger.info("✅ Tarefas agendadas: varredura regulações (6h)")

        # 2. ✅ Alertas de consulta (7, 3 e 1 dia) - Roda a cada 24h
        from handler_tarefas import verificar_alertas_consulta

        job_queue.run_repeating(
            verificar_alertas_consulta,
            interval=86400,  # 24 horas
            first=120,  # Roda 2 minutos após o bot ligar
        )
        logger.info("✅ Tarefas agendadas: Alertas de consulta (24h)")

        # 3. Verifica enquetes expiradas a cada 1 minuto
        from handler_enquete_local import verificar_enquetes_expiradas

        # job_queue.run_repeating(
        # verificar_enquetes_expiradas,
        # interval=60,
        # first=30,
        # )
        logger.info("✅ Tarefas agendadas: enquetes expiradas (60s)")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("O TELEGRAM_BOT_TOKEN precisa estar configurado nas variáveis de ambiente.")

    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )

    app = (
        ApplicationBuilder()
        .token(token)
        .request(request)
        .get_updates_request(request)
        .persistence(persistence)  # <-- ADICIONE ESTA LINHA
        .post_init(post_init)
        .build()
    )

    # ═══ MIDDLEWARE DE AUTORIZAÇÃO ═══
    async def verificar_acesso(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return

        # Admin sempre passa
        from config import is_admin

        if is_admin(user.id):
            return

        # Comandos admin sempre passam (pra você conseguir autorizar)
        if update.message and update.message.text:
            if update.message.text.startswith(("/autorizar", "/desautorizar", "/listar_autorizados")):
                return

        if not verificar_autorizado(user.id):
            texto = (
                "🔒 <b>Acesso Restrito</b>\n\n"
                "Este bot está em fase de testes e o acesso é concedido "
                "apenas por autorização.\n\n"
                "Enquanto isso, você pode usar o VigiaSaúde principal:\n"
                "👉 @vigiasaude_bot"
            )
            if update.message:
                await update.message.reply_text(texto, parse_mode="HTML")
            elif update.callback_query:
                await update.callback_query.answer("Acesso restrito", show_alert=True)
                try:
                    await update.callback_query.message.reply_text(texto, parse_mode="HTML")
                except Exception:
                    pass

            raise ApplicationHandlerStop

    # app.add_handler(TypeHandler(Update, verificar_acesso), group=-1)
    # ═══════════════════════════════════
    app.add_error_handler(erro_global_handler)

    conv_corrigir = ConversationHandler(
        entry_points=[
            CommandHandler("corrigir", iniciar_corrigir),
            CallbackQueryHandler(selecionar_regulacao_callback, pattern="^corr_reg_"),
        ],
        states={
            SELECIONAR_REGULACAO: [CallbackQueryHandler(selecionar_regulacao_callback, pattern="^corr_reg_")],
            SELECIONAR_CAMPO: [CallbackQueryHandler(selecionar_campo_callback, pattern="^corr_campo_")],
            AGUARDAR_NOVO_VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, salvar_novo_valor)],
        },
        fallbacks=[CallbackQueryHandler(selecionar_regulacao_callback, pattern="^cancelar_corr$")],
    )

    # ConversationHandlers
    app.add_handler(conv_cadastro)
    #     app.add_handler(conv_consulta_especifica)
    # app.add_handler(conv_corrigir)
    app.add_handler(conv_excluir)
    app.add_handler(conv_envio_midia)
    app.add_handler(conv_criar_enquete)
    app.add_handler(conv_broadcast)

    # Comandos públicos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("iniciar", start))
    # app.add_handler(CommandHandler("menu", start))
    # app.add_handler(CommandHandler("cadastrar_nova", iniciar_cadastro_manual))
    # app.add_handler(CommandHandler("verificar_todos", comando_verificar_todas))
    # app.add_handler(CommandHandler("verificar_especifico", iniciar_verificar_especifico))
    # app.add_handler(CommandHandler("corrigir", iniciar_corrigir))
    app.add_handler(CommandHandler("excluir", iniciar_excluir))
    app.add_handler(CommandHandler("privacidade", comando_privacidade))
    app.add_handler(CommandHandler("suporte", menu_suporte))
    app.add_handler(CommandHandler("meus_cadastros", comando_meus_cadastros))

    # Comandos admin (institucional)
    app.add_handler(CommandHandler("painel", comando_painel))
    app.add_handler(CommandHandler("admin", comando_painel))
    app.add_handler(CommandHandler("menu_admin", comando_painel))
    app.add_handler(CallbackQueryHandler(callback_painel, pattern="^painel_"))
    app.add_handler(CallbackQueryHandler(selecionar_regulacao_callback, pattern="^cancelar_corr$"))
    app.add_handler(CallbackQueryHandler(selecionar_regulacao_callback, pattern="^finalizar_corr$"))
    app.add_handler(CommandHandler("estatisticas", comando_estatisticas))
    app.add_handler(CommandHandler("ativos", comando_listar_ativos))
    app.add_handler(CommandHandler("detalhes", comando_detalhes))
    app.add_handler(CommandHandler("bloquear", comando_bloquear))
    app.add_handler(CommandHandler("aviso", comando_aviso))

    # Enquetes
    app.add_handler(CommandHandler("resultado", comando_resultado))
    app.add_handler(CommandHandler("resultado_detalhado", comando_resultado_detalhado))
    app.add_handler(CommandHandler("listar_enquetes", comando_listar_enquetes))
    app.add_handler(CommandHandler("encerrar", comando_encerrar))
    app.add_handler(CommandHandler("apagar_enquete", comando_apagar_enquete))
    # app.add_handler(CommandHandler("autorizar", comando_autorizar))
    # app.add_handler(CommandHandler("desautorizar", comando_desautorizar))
    app.add_handler(CommandHandler("listar_autorizados", comando_listar_autorizados))
    app.add_handler(CommandHandler("admin_metricas", comando_admin_metricas))
    # Handler IA do admin
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, executar_acao_admin),
        group=1,
    )

    app.add_handler(CallbackQueryHandler(start, pattern="^iniciar$"))

    # FAQ - handlers específicos
    app.add_handler(CallbackQueryHandler(faq_cadastrar, pattern="^faq_cadastrar$"))
    app.add_handler(CallbackQueryHandler(faq_consultar, pattern="^faq_consultar$"))
    app.add_handler(CallbackQueryHandler(faq_id, pattern="^faq_id$"))
    app.add_handler(CallbackQueryHandler(faq_alterar, pattern="^faq_alterar$"))
    app.add_handler(CallbackQueryHandler(faq_governo, pattern="^faq_governo$"))
    app.add_handler(CallbackQueryHandler(iniciar_atendimento_20, pattern="^iniciar_atendimento_20$"))
    app.add_handler(CallbackQueryHandler(cancelar_suporte, pattern="^fechar_menu$"))
    app.add_handler(CallbackQueryHandler(suporte_email, pattern="^suporte_email$"))
    app.add_handler(CallbackQueryHandler(mostrar_email_suporte, pattern="^mostrar_email_suporte$"))
    app.add_handler(CallbackQueryHandler(callback_verificar_regulacao, pattern="^ver_reg_|^verificar_todas_botao$"))
    app.add_handler(conv_suporte)

    # Callbacks de privacidade
    app.add_handler(CallbackQueryHandler(callback_abrir_termo_privacidade, pattern="^abrir_termo_privacidade$"))
    app.add_handler(CallbackQueryHandler(callback_privacidade_voltar, pattern="^privacidade_voltar$"))
    app.add_handler(CallbackQueryHandler(callback_faq_suporte, pattern="^abrir_faq_suporte$"))
    app.add_handler(CallbackQueryHandler(callback_optout_teaser, pattern="^optout_teaser$"))

    # Callbacks de enquete (voto e admin)
    app.add_handler(CallbackQueryHandler(receber_voto, pattern="^voto_\\d+_\\d+$"))
    app.add_handler(CallbackQueryHandler(voto_ja_registrado, pattern="^voto_ja_registrado$"))
    app.add_handler(CallbackQueryHandler(callback_resultado, pattern="^enq_(encerrar|reabrir|apagar|atualizar)_\\d+$"))
    app.add_handler(CallbackQueryHandler(comando_admin_metricas, pattern="^admin_metricas$"))
    conv_broadcast_cidadao = ConversationHandler(
        entry_points=[CallbackQueryHandler(iniciar_broadcast, pattern="^bc_(texto|foto|video)$")],
        states={RECEBER_CONTEUDO: [MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO, receber_e_disparar)]},
        fallbacks=[CommandHandler("cancelar", cancelar_broadcast)],
    )
    app.add_handler(conv_broadcast_cidadao)
    # 📌 Rota para os botões do teclado inline (InlineKeyboard)
    # ─── Servidor HTTP auxiliar ───
    PORT = int(os.environ.get("PORT", "8080"))

    class HealthHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"VigiaSaude Teresina is running!")

        def do_HEAD(self):
            self.send_response(200)
            self.end_headers()

    def run_http_server(port):
        try:
            server = HTTPServer(("0.0.0.0", port), HealthHandler)
            logger.info(f"✅ Servidor HTTP auxiliar rodando na porta {port}")
            server.serve_forever()
        except Exception as e:
            logger.error(f"Erro no servidor HTTP: {e}")

    threading.Thread(target=run_http_server, args=(PORT,), daemon=True).start()

    logger.info("Iniciando o bot VigiaSaude Teresina via polling...")
    app.add_error_handler(global_error_handler)
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
