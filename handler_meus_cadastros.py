from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import supabase
import asyncio
import html

# ⚠️ Mantenha os imports exatamente como estão no seu projeto
from scraper import consultar_status_fms
from config import is_admin


# ==============================================================================
# FUNÇÃO 1: COMANDO /meus_cadastros
# ==============================================================================
async def comando_meus_cadastros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    NOME_TABELA = "VigiaSaude_Teresina"

    try:
        res = supabase.table("VigiaSaude_Teresina").select("*").eq("chat_id", str(user_id)).execute()
        registros = res.data if res.data else []
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao buscar suas regulações: {e}")
        return

    if not registros:
        await update.message.reply_text("📭 Você ainda não tem regulações cadastradas.")
        return

    msg = "<b>📋 Suas Regulações Cadastradas:</b>\n\n"
    botoes = []

    for i, r in enumerate(registros, 1):
        numero_reg = r.get("numero_reg", "S/N")
        nome = r.get("nome_paciente") or "Não informado"
        especialidade = r.get("cbo") or "Não informada"
        procedimento = r.get("procedimento") or "Não informado"
        status = str(r.get("status_anterior") or "").lower()

        cor = (
            "🟢"
            if "agend" in status
            else "🟡"
            if "fila" in status
            else "🔵"
            if "venc" in status
            else "🔴"
            if "cancel" in status
            else "⚪"
        )

        msg += (
            f"<b>{i}. ID: {cor} <code>{numero_reg}</code></b>\n"
            f"👤 Paciente: {html.escape(nome)}\n"
            f"🩺 Especialidade: {html.escape(especialidade)}\n"
            f"📋 Procedimento: {html.escape(procedimento)}\n\n"
        )

        nome_curto = nome[:12] + "..." if len(nome) > 12 else nome
        botoes.append(
            [InlineKeyboardButton(f"🔍 Verificar {nome_curto} ({numero_reg})", callback_data=f"ver_reg_{numero_reg}")]
        )

    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(botoes))


# ==============================================================================
# FUNÇÃO 2: CALLBACK DOS BOTÕES (SEM ERRO DE DICT)
# ==============================================================================
async def callback_verificar_regulacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data
    NOME_TABELA = "VigiaSaude_Teresina"

    if data.startswith("ver_reg_"):
        numero_reg = data.replace("ver_reg_", "")
        agora = datetime.now(timezone.utc)

        try:
            # 1. Busca no banco
            res_db = (
                supabase.table("VigiaSaude_Teresina")
                .select("*")
                .eq("chat_id", str(user_id))
                .eq("numero_reg", numero_reg)
                .execute()
            )

            if not res_db.data:
                await query.edit_message_text("❌ Regulação não encontrada.")
                return

            dados_db = res_db.data[0]
            ultima_verif_str = dados_db.get("ultima_verificacao")

            # 2. Trava de 2 horas (com exceção para o Admin)
            if not is_admin(user_id) and ultima_verif_str:
                ultima_verif = datetime.fromisoformat(ultima_verif_str.replace("Z", "+00:00"))
                tempo_decorrido = agora - ultima_verif

                if tempo_decorrido < timedelta(hours=2):
                    tempo_restante = timedelta(hours=2) - tempo_decorrido
                    minutos_restantes = int(tempo_restante.total_seconds() // 60)

                    await query.edit_message_text(
                        f"⏳ <b>Aguarde um pouco!</b>\n\nTente novamente em <b>{minutos_restantes} minutos</b>.",
                        parse_mode="HTML",
                    )
                    return

            # 3. Atualiza a hora no banco
            supabase.table("VigiaSaude_Teresina").update({"ultima_verificacao": agora.isoformat()}).eq(
                "chat_id", str(user_id)
            ).eq("numero_reg", numero_reg).execute()

            # 4. Avisa que está consultando
            await query.edit_message_text(f"⏳ <b>Consultando a regulação {numero_reg}...</b>", parse_mode="HTML")

            # 5. Consulta real no site
            sus_paciente = dados_db.get("numero_sus") or dados_db.get("sus") or ""
            resultado_fms = await consultar_status_fms(numero_reg, sus_paciente)

            # 🎨 SALVA O STATUS NO BANCO (Agora a coluna existe!)
            # ... código anterior ...
            sus_paciente = dados_db.get("numero_sus") or dados_db.get("sus") or ""
            resultado_fms = await consultar_status_fms(numero_reg, sus_paciente)

            # 🎨 SALVA O STATUS, DATA E LOCAL NO BANCO (Para as cores e os alertas)
            if isinstance(resultado_fms, dict) and not resultado_fms.get("erro"):
                situacao_site = resultado_fms.get("situacao") or "Não encontrada"
                data_consulta_site = resultado_fms.get("data_consulta")
                estabelecimento = resultado_fms.get("estabelecimento")
                endereco = resultado_fms.get("endereco")

                update_data = {"status_anterior": situacao_site}

                # Adiciona os campos extras se o scraper retornar
                if data_consulta_site:
                    update_data["data_consulta"] = data_consulta_site
                if estabelecimento:
                    update_data["estabelecimento"] = estabelecimento
                if endereco:
                    update_data["endereco"] = endereco

                supabase.table("VigiaSaude_Teresina").update(update_data).eq("chat_id", str(user_id)).eq(
                    "numero_reg", numero_reg
                ).execute()

            # 🎨 AQUI: SALVA A COR NO BANCO DE DADOS
            if isinstance(resultado_fms, dict) and not resultado_fms.get("erro"):
                situacao_site = resultado_fms.get("situacao") or "Não encontrada"
                # Atualiza a coluna status_anterior
                supabase.table("VigiaSaude_Teresina").update({"status_anterior": situacao_site}).eq(
                    "chat_id", str(user_id)
                ).eq("numero_reg", numero_reg).execute()

            # ... (resto do código que monta o texto_final e envia a mensagem) ...

            # 6. Monta o layout do print manualmente (evita o erro do dict)
            if isinstance(resultado_fms, dict) and resultado_fms.get("erro"):
                texto_final = f"❌ <b>Erro na consulta:</b> {resultado_fms.get('erro')}"
            else:
                # Tenta pegar os dados do dicionário que o scraper retornou
                situacao = resultado_fms.get("situacao") or "Não encontrada"
                posicao = resultado_fms.get("posicao_fila") or "Não informada"
                previsao = resultado_fms.get("previsao_atendimento") or "Não informada"

                # Formata o SUS mascarado
                sus_mascarado = sus_paciente[:3] + "****" + sus_paciente[-3:] if len(sus_paciente) > 6 else sus_paciente

                texto_final = (
                    f"📋 <b>STATUS DA REGULAÇÃO</b>\n\n"
                    f"<b>ID Regulação:</b> <code>{numero_reg}</code>\n"
                    f"<b>Cartão SUS:</b> <code>{sus_mascarado}</code>\n"
                    f"<b>Paciente:</b> {html.escape(dados_db.get('nome_paciente') or 'Não informado')}\n"
                    f"<b>Especialidade:</b> {html.escape(dados_db.get('cbo') or 'Não informada')}\n"
                    f"<b>Procedimento:</b> {html.escape(dados_db.get('procedimento') or 'Não informado')}\n"
                    f"<b>Status:</b> {situacao}\n"
                    f"<b>Posição:</b> {posicao}\n"
                    f"<b>Previsão:</b> {previsao}\n\n"
                    f"ℹ️ <i>Serviço independente de monitoramento. Não possuímos vínculo oficial com a FMS ou Prefeitura de Teresina.</i>"
                )

            # 7. Envia
            await query.edit_message_text(texto_final, parse_mode="HTML")

        except Exception as e:
            await query.edit_message_text(
                f"❌ <b>Erro ao consultar.</b>\n\nDetalhe: <code>{e}</code>", parse_mode="HTML"
            )
