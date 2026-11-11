import os
import logging
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Configuração do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Lista de IDs de administradores autorizados
ADMIN_IDS = [5242040324]  # Seu ID de admin


def eh_admin(user_id: int) -> bool:
    """Verifica se o usuário é administrador."""
    return user_id in ADMIN_IDS


async def comando_estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Visão geral de usuários, planos e cadastros de regulações."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    try:
        res_assinaturas = supabase.table("assinaturas").select("*", count="exact").execute()
        total_assinaturas = res_assinaturas.count if hasattr(res_assinaturas, "count") else len(res_assinaturas.data)

        res_ativos = supabase.table("assinaturas").select("tipo_plano", count="exact").eq("status", "ativo").execute()
        total_ativos = res_ativos.count if hasattr(res_ativos, "count") else len(res_ativos.data)

        res_regulacoes = supabase.table("VigiaSaude_Teresina").select("*", count="exact").execute()
        total_regulacoes = res_regulacoes.count if hasattr(res_regulacoes, "count") else len(res_regulacoes.data)

        texto = (
            "📊 <b>ESTATÍSTICAS GERAIS</b>\n\n"
            f"👥 <b>Total de Usuários (assinaturas):</b> {total_assinaturas}\n"
            f"✅ <b>Assinaturas Ativas:</b> {total_ativos}\n"
            f"📋 <b>Total de Cadastros de Regulação:</b> {total_regulacoes}\n"
        )
        await update.message.reply_text(texto, parse_mode="HTML")
    except Exception as e:
        logger.error(f"[ADMIN] Erro ao executar estatísticas: {e}")
        await update.message.reply_text("❌ Erro ao calcular estatísticas.")


async def comando_listar_ativos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        return
    try:
        # Busca os últimos cadastros na tabela do Teresina
        res = (
            supabase.table("VigiaSaude_Teresina")
            .select("chat_id, nome_paciente, numero_sus")
            .order("id", desc=True)
            .limit(10)
            .execute()
        )
        registros = res.data

        if not registros:
            await update.message.reply_text("ℹ️ Nenhum cadastro encontrado no sistema.")
            return

        texto = "📋 <b>Últimos Cadastros Realizados:</b>\n\n"
        for r in registros:
            texto += f"👤 <b>{r.get('nome_paciente')}</b>\n"
            texto += f"🆔 Chat ID: <code>{r.get('chat_id')}</code>\n"
            texto += f"💳 SUS: {r.get('numero_sus')}\n\n"

        await update.message.reply_text(texto, parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao buscar cadastros: {e}")


async def comando_bloquear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Altera o status de um usuário para banido/bloqueado no banco."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Uso correto:</b> <code>/bloquear &lt;TELEGRAM_ID&gt;</code>",
            parse_mode="HTML",
        )
        return

    target_id = context.args[0].strip()

    try:
        supabase.table("assinaturas").update({"status": "bloqueado", "tipo_plano": "bloqueado"}).eq(
            "chat_id", str(target_id)
        ).execute()

        await update.message.reply_text(
            f"🚫 <b>CONFIRMAÇÃO:</b> O usuário <code>{target_id}</code> foi bloqueado com sucesso.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"[ADMIN] Erro ao bloquear usuário: {e}")
        await update.message.reply_text(f"❌ Erro ao bloquear no banco de dados: {e}")


async def comando_detalhes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Busca e exibe as regulações de um usuário específico pelo ID do Telegram."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Uso correto:</b> <code>/detalhes &lt;TELEGRAM_ID&gt;</code>",
            parse_mode="HTML",
        )
        return

    target_id = context.args[0].strip()

    try:
        # 🔄 Busca na tabela correta do Teresina
        response = supabase.table("VigiaSaude_Teresina").select("*").eq("chat_id", target_id).execute()
        dados = response.data

        if not dados:
            await update.message.reply_text(
                f"ℹ️ Nenhuma regulação encontrada para o ID <code>{target_id}</code>.",
                parse_mode="HTML",
            )
            return

        # ─── Monta a mensagem com as regulações encontradas ───
        texto = f"🔍 <b>Regulações do Usuário</b>\n🆔 <code>{target_id}</code>\n\n"

        for i, reg in enumerate(dados, 1):
            texto += (
                f"<b>{i}. Paciente:</b> {reg.get('nome_paciente') or '—'}\n"
                f"🆔 <b>ID Regulação:</b> <code>{reg.get('numero_reg')}</code>\n"
                f"🏥 <b>Procedimento:</b> {reg.get('procedimento') or '—'}\n"
                f"📊 <b>Status:</b> {reg.get('status_anterior_cidadao') or 'Não verificado'}\n"
                "───────────────────\n"
            )

        await update.message.reply_text(texto, parse_mode="HTML")

    except Exception as e:
        logger.error(f"[ADMIN] Erro ao buscar detalhes do usuário {target_id}: {e}")
        await update.message.reply_text("❌ Erro ao consultar dados do usuário.")


async def comando_dar_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Concede um plano específico com validade em dias para um usuário."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ <b>Uso correto:</b> <code>/dar_plano &lt;ID&gt; &lt;plano&gt; &lt;dias&gt;</code>\n"
            "<i>Exemplo:</i> <code>/dar_plano 123456789 pro 30</code>",
            parse_mode="HTML",
        )
        return

    target_id = context.args[0].strip()
    nome_plano = context.args[1].strip().lower()

    try:
        dias = int(context.args[2])
    except ValueError:
        await update.message.reply_text("❌ O número de dias precisa ser um valor inteiro.")
        return

    data_inicio = datetime.now(timezone.utc)
    data_vencimento = data_inicio + timedelta(days=dias)

    try:
        supabase.table("assinaturas").upsert(
            {
                "chat_id": str(target_id),
                "tipo_plano": nome_plano,
                "status": "ativo",
                "limite_ids": 999,
                "data_inicio": data_inicio.isoformat(),
                "data_vencimento": data_vencimento.isoformat(),
            },
            on_conflict="chat_id",
        ).execute()

        await update.message.reply_text(
            f"✅ <b>Plano Concedido com Sucesso!</b>\n\n"
            f"• <b>Usuário ID:</b> <code>{target_id}</code>\n"
            f"• <b>Novo Plano:</b> {nome_plano}\n"
            f"• <b>Validade:</b> {dias} dias (Até {data_vencimento.strftime('%d/%m/%Y')})",
            parse_mode="HTML",
        )

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎁 <b>Seu plano foi atualizado!</b>\n\n"
                f"Você agora possui acesso ao plano <b>{nome_plano.upper()}</b> válido por {dias} dias. Aproveite!",
                parse_mode="HTML",
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"[ADMIN] Erro ao atribuir plano personalizado: {e}")
        await update.message.reply_text(f"❌ Erro ao atualizar plano no banco: {e}")


async def comando_cortesia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Concede acesso VIP/Cortesia ilimitada para um usuário."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Uso correto:</b>\n"
            "<code>/cortesia 123456789</code>\n\n"
            "<i>Digite o ID numérico, sem os símbolos &lt; &gt;.</i>",
            parse_mode="HTML",
        )
        return

    target_id = context.args[0].strip()
    try:
        supabase.table("assinaturas").upsert(
            {
                "chat_id": str(target_id),
                "tipo_plano": "cortesia",
                "status": "ativo",
                "data_inicio": datetime.now(timezone.utc).isoformat(),
                "data_vencimento": None,
            },
            on_conflict="chat_id",
        ).execute()

        await update.message.reply_text(
            f"🎁 Cortesia aplicada com sucesso para o ID <code>{target_id}</code>.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"[ADMIN] Erro ao dar cortesia: {e}")
        await update.message.reply_text(f"❌ Erro ao conceder cortesia: {e}")


async def comando_remover_cortesia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a cortesia de um usuário, deixando-o neutro (sem plano, sem degustação)."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Uso correto: <code>/remover_cortesia &lt;TELEGRAM_ID&gt;</code>",
            parse_mode="HTML",
        )
        return

    target_id = context.args[0].strip()

    try:
        # Verifica se o usuário existe
        res = supabase.table("assinaturas").select("*").eq("chat_id", str(target_id)).execute()
        if not res.data:
            # Se não existe, cria um registro neutro com trava de degustação
            supabase.table("assinaturas").insert(
                {
                    "chat_id": str(target_id),
                    "tipo_plano": None,
                    "status": None,
                    "usou_degustacao": True,
                }
            ).execute()
        else:
            # Atualiza para estado neutro, mantendo a trava de degustação
            supabase.table("assinaturas").update(
                {
                    "tipo_plano": None,
                    "status": None,
                    "data_inicio": None,
                    "data_vencimento": None,
                    "limite_ids": None,
                    "usou_degustacao": True,
                }
            ).eq("chat_id", str(target_id)).execute()

        await update.message.reply_text(
            f"✅ Cortesia removida do ID <code>{target_id}</code>. Usuário agora está neutro.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"[ADMIN] Erro ao remover cortesia: {e}")
        await update.message.reply_text(f"❌ Erro ao remover cortesia: {e}")


async def comando_retirar_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retira o plano de um usuário, deixando-o neutro (sem plano, com trava de degustação)."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Uso correto: /retirar_plano <ID>")
        return

    target_id = context.args[0].strip()

    try:
        # Verifica se existe registro
        res = supabase.table("assinaturas").select("*").eq("chat_id", str(target_id)).execute()
        if not res.data:
            # Se não existe, cria um registro neutro com trava de degustação
            supabase.table("assinaturas").insert(
                {
                    "chat_id": str(target_id),
                    "tipo_plano": None,
                    "status": None,
                    "usou_degustacao": True,
                }
            ).execute()
        else:
            # Atualiza para estado neutro, mantendo a trava de degustação
            supabase.table("assinaturas").update(
                {
                    "tipo_plano": None,
                    "status": None,
                    "data_inicio": None,
                    "data_vencimento": None,
                    "limite_ids": None,
                    "usou_degustacao": True,
                }
            ).eq("chat_id", str(target_id)).execute()

        await update.message.reply_text(f"✅ Plano retirado do usuário {target_id}. Usuário agora está neutro.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao retirar plano: {e}")


async def comando_retirar_degustacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retira o acesso à degustação de um usuário (impede de usar novamente)."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Uso correto: /retirar_degustacao <ID>")
        return

    target_id = context.args[0].strip()

    try:
        # Verifica se existe registro
        res = supabase.table("assinaturas").select("*").eq("chat_id", str(target_id)).execute()
        if not res.data:
            # Cria registro neutro com trava de degustação
            supabase.table("assinaturas").insert(
                {
                    "chat_id": str(target_id),
                    "tipo_plano": None,
                    "status": None,
                    "usou_degustacao": True,
                }
            ).execute()
        else:
            # Atualiza para neutro e trava degustação
            supabase.table("assinaturas").update(
                {
                    "usou_degustacao": True,
                    "tipo_plano": None,
                    "status": None,
                    "data_inicio": None,
                    "data_vencimento": None,
                    "limite_ids": None,
                }
            ).eq("chat_id", str(target_id)).execute()

        await update.message.reply_text(f"✅ Degustação retirada do usuário {target_id}. Usuário agora está neutro.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao retirar degustação: {e}")


async def comando_aviso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia uma mensagem de broadcast (aviso em massa) para todos os usuários cadastrados."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text(
            "⚠️ <b>Uso correto:</b> <code>/aviso &lt;Sua mensagem aqui&gt;</code>",
            parse_mode="HTML",
        )
        return

    mensagem_broadcast = " ".join(context.args)
    if not mensagem_broadcast:
        await update.message.reply_text("⚠️ Digite a mensagem após o comando. Ex: /aviso Olá, pessoal!")
        return

    try:
        # 🔄 CORREÇÃO: Busca na tabela correta do Teresina
        response = supabase.table("VigiaSaude_Teresina").select("chat_id").execute()
        registros = response.data

        if not registros:
            await update.message.reply_text("ℹ️ Nenhum usuário encontrado para enviar o aviso.")
            return

        # 🧹 CORREÇÃO: Remove chat_ids duplicados (para não mandar 2x pro mesmo usuário)
        chat_ids_unicos = list(set(str(reg.get("chat_id")) for reg in registros if reg.get("chat_id")))
        # 🚫 FILTRO: Remove o ID do Admin da lista de envio
        from config import is_admin

        chat_ids_unicos = [cid for cid in chat_ids_unicos if not is_admin(int(cid))]

        await update.message.reply_text(f"🚀 Iniciando envio de aviso para {len(chat_ids_unicos)} usuários únicos...")

        enviados = 0
        falhas = 0

        for chat_id in chat_ids_unicos:
            try:
                # Aqui adicionamos o rótulo no topo da mensagem
                texto_com_rotulo = f"📢 <b>Aviso VigiaSaúde Teresina:</b>\n\n{mensagem_broadcast}"

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=texto_com_rotulo,  # <-- Usa o texto com o rótulo
                    parse_mode="HTML",
                )
                enviados += 1
                await asyncio.sleep(0.05)  # 🛡️ Previne bloqueio do Telegram
            except Exception as e:
                falhas += 1

        await update.message.reply_text(f"✅ Envio concluído!\n\n📬 Enviados: {enviados}\n❌ Falhas: {falhas}")

    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao buscar usuários: {e}")


async def comando_menu_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redireciona para o painel interativo."""
    from admin_panel import comando_painel

    await comando_painel(update, context)
