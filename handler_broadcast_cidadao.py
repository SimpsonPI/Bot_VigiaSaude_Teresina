import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import supabase
from config import is_admin  # Importa a função de admin

logger = logging.getLogger(__name__)

ESCOLHER_TIPO, RECEBER_CONTEUDO = range(2)


async def iniciar_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tipo = query.data.replace("bc_", "")
    context.user_data["bc_tipo"] = tipo
    context.user_data["_em_fluxo_admin"] = "broadcast"  # 🛑 AVISA A IA PARA FICAR QUIETA

    if tipo == "texto":
        await query.edit_message_text(
            "📝 <b>Modo Texto</b>\n\nDigite a mensagem que deseja enviar para todos os usuários:", parse_mode="HTML"
        )
    elif tipo == "foto":
        await query.edit_message_text(
            "📸 <b>Modo Imagem</b>\n\nEnvie a imagem agora (com legenda opcional):", parse_mode="HTML"
        )
    elif tipo == "video":
        await query.edit_message_text(
            "🎥 <b>Modo Vídeo</b>\n\nEnvie o vídeo agora (com legenda opcional):", parse_mode="HTML"
        )

    return RECEBER_CONTEUDO


async def receber_e_disparar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tipo = context.user_data.get("bc_tipo")
    msg = update.message

    # Remove o bloqueio da IA agora que já recebemos a mensagem
    context.user_data.pop("_em_fluxo_admin", None)

    await msg.reply_text("⏳ Buscando usuários e iniciando o disparo... Por favor, aguarde.")

    try:
        res = supabase.table("VigiaSaude_Teresina").select("chat_id").execute()
        chat_ids = list(set([str(r.get("chat_id")) for r in res.data if r.get("chat_id")]))

        # 🚫 FILTRO: Remove o ID do Admin da lista (para você não receber)
        chat_ids = [cid for cid in chat_ids if not is_admin(int(cid))]

    except Exception as e:
        logger.error(f"Erro ao buscar chat_ids: {e}")
        await msg.reply_text("❌ Erro ao buscar usuários no banco.")
        return ConversationHandler.END

    if not chat_ids:
        await msg.reply_text("❌ Nenhum usuário encontrado (ou apenas o Admin estava cadastrado).")
        return ConversationHandler.END

    enviados = 0
    falhas = 0

    for cid in chat_ids:
        try:
            if tipo == "texto":
                # 📢 ADICIONA O TÍTULO AQUI
                texto_com_rotulo = f"📢 <b>Aviso VigiaSaúde Teresina:</b>\n\n{msg.text}"
                await context.bot.send_message(chat_id=cid, text=texto_com_rotulo, parse_mode="HTML")

            elif tipo == "foto" and msg.photo:
                # 📢 ADICIONA O TÍTULO NA LEGENDA DA FOTO
                legenda = f"📢 <b>Aviso VigiaSaúde Teresina:</b>\n\n{msg.caption or ''}"
                await context.bot.send_photo(
                    chat_id=cid, photo=msg.photo[-1].file_id, caption=legenda, parse_mode="HTML"
                )

            elif tipo == "video" and msg.video:
                # 📢 ADICIONA O TÍTULO NA LEGENDA DO VÍDEO
                legenda = f"📢 <b>Aviso VigiaSaúde Teresina:</b>\n\n{msg.caption or ''}"
                await context.bot.send_video(chat_id=cid, video=msg.video.file_id, caption=legenda, parse_mode="HTML")

            enviados += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            falhas += 1
            logger.error(f"Erro ao enviar para {cid}: {e}")

    await msg.reply_text(
        f"✅ <b>Disparo concluído!</b>\n\n📬 Mensagens enviadas: {enviados}\n❌ Falhas (bloqueio/inativo): {falhas}",
        parse_mode="HTML",
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancelar_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Disparo cancelado.")
    return ConversationHandler.END
