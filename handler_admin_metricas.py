from telegram import Update
from telegram.ext import ContextTypes
from database import supabase

# SEUS IDs DE ADMIN
IDS_ADMIN = [5242040324, 5444152614]


async def comando_admin_metricas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id  # <--- LINHA ADICIONADA AQUI

    # 1. Verificação de Segurança
    if user_id not in IDS_ADMIN:
        return

    # 2. Trata se veio de botão ou de texto
    if update.callback_query:
        await update.callback_query.answer()
        msg_carregando = await update.callback_query.message.reply_text("⏳ Buscando métricas no banco de dados...")
    else:
        msg_carregando = await update.message.reply_text("⏳ Buscando métricas no banco de dados...")

    try:
        # Busca todos os registros para calcular
        res = supabase.table("VigiaSaude_Teresina").select("chat_id").execute()
        registros = res.data

        if not registros:
            await msg_carregando.edit_text("📊 O banco de dados está vazio. Nenhum usuário ainda.")
            return

        # Calcula usuários únicos
        usuarios_unicos = len(set(str(r.get("chat_id")) for r in registros))
        total_regulacoes = len(registros)

        texto_metricas = (
            "📊 <b>PAINEL DO CRIADOR - VIGIASAÚDE TERESINA</b>\n\n"
            f"👥 <b>Usuários únicos no bot:</b> {usuarios_unicos}\n"
            f"📋 <b>Regulações cadastradas:</b> {total_regulacoes}\n\n"
            f"📈 <i>Média de regulação por usuário: {total_regulacoes / usuarios_unicos:.1f}</i>\n\n"
            "🚀 <i>Continue divulgando! Seu trabalho está chegando às pessoas.</i>"
        )

        await msg_carregando.edit_text(texto_metricas, parse_mode="HTML")

    except Exception as e:
        await msg_carregando.edit_text(f"❌ Erro ao buscar métricas: {e}")
