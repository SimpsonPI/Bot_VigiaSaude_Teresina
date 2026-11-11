# handler_consultas.py
import asyncio
import logging
import re
from html import escape
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from rate_limiter import consultar_com_limite
from database import supabase
from scraper import consultar_status_fms

logger = logging.getLogger(__name__)

CONSULTAR_ID = 1

DISCLAIMER_TEXTO = (
    "Serviço independente de monitoramento. Não possuímos vínculo oficial com a FMS ou Prefeitura de Teresina."
)


# ═══════════════════════════════════════════════
# FUNÇÕES AUXILIARES
# ═══════════════════════════════════════════════


def emoji_por_status(status: str | None) -> str:
    """Retorna o emoji correspondente ao status da regulação."""
    if not status:
        return "⚪"
    s = str(status).strip().lower()

    if "vencid" in s or "expirad" in s:
        return "🔵"
    if "reativ" in s:
        return "🟣"
    if "cancel" in s:
        return "🔴"
    if "agend" in s:
        return "🟢"
    if "fila" in s or "aguard" in s or "marcad" in s or "informada" in s:
        return "🟡"

    return "⚪"


def _mascarar_nome_custom(nome: str) -> str:
    """Retorna: Primeiro nome + iniciais. Ex: 'João Silva Santos' -> 'João S. S.'"""
    if not nome or str(nome).lower() in ["none", "não informado", ""]:
        return "Não informado"
    partes = nome.strip().split()
    if len(partes) <= 1:
        return partes[0].capitalize()

    primeiro = partes[0].capitalize()
    iniciais = [f"{p[0].upper()}." for p in partes[1:]]
    return f"{primeiro} {' '.join(iniciais)}"


def _mascarar_sus_custom(sus: str) -> str:
    """Retorna: 3 primeiros + 3 últimos."""
    s = str(sus).strip()
    if len(s) < 6:
        return s
    return f"{s[:3]}{'*' * 5}{s[-3:]}"


def _montar_msg_html(
    num_reg: str,
    resultado: dict,
    reg_db=None,
    titulo: str = "📋 <b>STATUS DA REGULAÇÃO</b>",
) -> str:
    cartao_sus_raw = ""
    nome_paciente_raw = ""
    cbo = "Não informado"
    procedimento = "Não informado"

    if reg_db and isinstance(reg_db, dict):
        cartao_sus_raw = reg_db.get("numero_sus") or reg_db.get("cartao_sus") or ""
        nome_paciente_raw = reg_db.get("nome_paciente") or ""
        cbo = reg_db.get("cbo") or cbo
        procedimento = reg_db.get("procedimento") or procedimento

    nome_exibicao = _mascarar_nome_custom(nome_paciente_raw)
    cartao_sus_exibicao = _mascarar_sus_custom(cartao_sus_raw) if cartao_sus_raw else "Não informado"

    if isinstance(resultado, dict) and resultado.get("sucesso"):
        situacao = resultado.get("situacao") or "Informada no portal"
        posicao = resultado.get("posicao_fila") or "Não informada"
        previsao = resultado.get("previsao_atendimento") or "Não informada"
        alerta = resultado.get("alerta_fms") or resultado.get("alerta")
        data_consulta = resultado.get("data_consulta")
        estabelecimento = resultado.get("estabelecimento")
        endereco = resultado.get("endereco")
        telefone = resultado.get("telefone")
    else:
        situacao = "Não encontrada / Indisponível"
        posicao = "Não informada"
        previsao = "Não informada"
        alerta = resultado.get("mensagem") if isinstance(resultado, dict) else None
        data_consulta = None
        estabelecimento = None
        endereco = None
        telefone = None

    linhas = [
        titulo,
        "",
        f"<b>ID Regulação:</b> <code>{escape(str(num_reg))}</code>",
        f"<b>Cartão SUS:</b> <code>{escape(str(cartao_sus_exibicao))}</code>",
        f"<b>Paciente:</b> {escape(str(nome_exibicao))}",
        f"<b>Especialidade:</b> {escape(str(cbo).upper())}",
        f"<b>Procedimento:</b> {escape(str(procedimento).upper())}",
        f"<b>Status:</b> {escape(str(situacao))}",
        f"<b>Posição:</b> {escape(str(posicao))}",
    ]

    if data_consulta or estabelecimento:
        linhas.append(f"<b>Previsão:</b> {escape(str(previsao))}")
        linhas.append("")
        linhas.append("📅 <b>DADOS DO AGENDAMENTO</b>")
        if data_consulta:
            linhas.append(f"• <b>Data/Hora:</b> {escape(str(data_consulta))}")
        if estabelecimento:
            linhas.append(f"• <b>Local:</b> {escape(str(estabelecimento))}")
        if endereco:
            linhas.append(f"• <b>Endereço:</b> {escape(str(endereco))}")
        if telefone:
            linhas.append(f"• <b>Telefone:</b> {escape(str(telefone))}")

        if alerta and str(alerta).strip():
            linhas.append("")
            linhas.append(f"⚠️ <b>AVISO DO PORTAL:</b>\n<i>{escape(str(alerta.strip()))}</i>")
    else:
        linhas.append(f"<b>Previsão:</b> {escape(str(previsao))}")
        if alerta and str(alerta).strip():
            linhas.append("")
            linhas.append(f"⚠️ <b>Mensagem do Portal:</b>\n<i>{escape(str(alerta).strip())}</i>")

    if DISCLAIMER_TEXTO:
        linhas.append("")
        linhas.append(f"ℹ️ <i>{DISCLAIMER_TEXTO.strip()}</i>")

    return "\n".join(linhas)


async def enviar_resposta(update: Update, texto: str, parse_mode="HTML", reply_markup=None):
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(texto, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception:
            await update.callback_query.message.reply_text(texto, parse_mode=parse_mode, reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(texto, parse_mode=parse_mode, reply_markup=reply_markup)


# ═══════════════════════════════════════════════
# COMANDO: VERIFICAR TODAS
# ═══════════════════════════════════════════════


async def comando_verificar_todas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🔒 Bloqueio de plano expirado
    from handler import verificar_plano_ativo, enviar_alerta_plano_expirado

    user_id = update.effective_user.id
    ativo, info = verificar_plano_ativo(user_id)
    if not ativo:
        await enviar_alerta_plano_expirado(update, context)
        return

        # 🆕 LIMITE DIÁRIO + INTERVALO
    from verificacao_limite import pode_verificar, registrar_verificacao
    from config import is_admin

    chat_id = str(user_id)

    # Bypass total para o Admin: ignora limite e tempo de espera
    if is_admin(user_id):
        pode = True
        motivo = ""
        restantes = 999
    else:
        pode, motivo, restantes = pode_verificar(chat_id, "todas")

    if not pode:
        if motivo.startswith("intervalo:"):
            segundos = int(motivo.split(":")[1])
            await update.message.reply_text(
                f"⏳ <b>Aguarde um pouco!</b>\n\n"
                f"Você fez uma verificação há pouco tempo. "
                f"Tente novamente em <b>{segundos} segundos</b>.",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                "⏳ <b>Limite diário de verificações completas atingido!</b>\n\n"
                "Você já usou suas <b>3 verificações completass</b> de hoje.\n\n"
                "💡 <i>Alternativas:</i>\n"
                "• O bot continua monitorando automaticamente a cada 6h 🕐\n"
                "• Volte amanhã para mais 3 verificações completass",
                parse_mode="HTML",
            )
        return

    # ✅ Busca as regulações do usuário
    try:
        res = supabase.table("VigiaSaude_Teresina").select("*").eq("chat_id", user_id).execute()
        regulacoes = res.data if res.data else []
    except Exception as e:
        logger.error(f"Erro ao buscar regulações no Supabase: {e}")
        regulacoes = []

    if not regulacoes:
        await update.message.reply_text(
            "ℹ️ <b>Você não possui nenhuma regulação cadastrada.</b>\nUse o menu para cadastrar.",
            parse_mode="HTML",
        )
        return

    # Marca como usada
    registrar_verificacao(chat_id, "todas")
    # Define o alvo (message ou callback)
    msg_alvo = update.message if update.message else update.callback_query.message

    # Envia mensagem de carregamento
    total_regs = len(regulacoes)
    msg_carregando = f"🔄 Consultando <b>{total_regs}</b> regulação(ões) na FMS... Por favor, aguarde."
    if update.callback_query:
        try:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(msg_carregando, parse_mode="HTML")
        except Exception:
            await update.message.reply_text(msg_carregando, parse_mode="HTML")
    elif update.message:
        await update.message.reply_text(msg_carregando, parse_mode="HTML")

    relatorios = []

    # Dispara verificação em BACKGROUND
    asyncio.create_task(_verificar_todas_bg(regulacoes, msg_alvo, restantes))


async def _verificar_todas_bg(regulacoes, msg_alvo, restantes):
    """Roda a verificação de N regulações em background."""
    relatorios = []
    for reg in regulacoes:
        num_reg = reg.get("numero_reg")
        if not num_reg:
            continue
        try:
            resultado = await asyncio.wait_for(consultar_com_limite(num_reg), timeout=30)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout FMS {num_reg}")
            resultado = {"sucesso": False, "mensagem": "Tempo limite excedido"}
        except Exception as e:
            logger.error(f"Erro FMS {num_reg}: {e}")
            resultado = {"sucesso": False}

        msg_html = _montar_msg_html(num_reg, resultado, reg)
        relatorios.append(msg_html)

    try:
        if relatorios:
            mensagem_final = "\n\n➖➖➖➖➖➖➖➖➖➖\n\n".join(relatorios)
            if len(mensagem_final) <= 4096:
                await msg_alvo.reply_text(mensagem_final, parse_mode="HTML")
            else:
                for relatorio in relatorios:
                    await msg_alvo.reply_text(relatorio, parse_mode="HTML")

            restantes_agora = max(0, restantes - 1)
            await msg_alvo.reply_text(
                f"<i>📊 Verificações completas restantes hoje: <b>{restantes_agora}/3</b></i>",
                parse_mode="HTML",
            )
        else:
            await msg_alvo.reply_text(
                "⚠️ Não foi possível recuperar os dados no momento.",
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"Erro em _verificar_todas_bg: {e}")


# ═══════════════════════════════════════════════
# COMANDO: VERIFICAR ESPECÍFICO
# ═══════════════════════════════════════════════


async def iniciar_verificar_especifico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user_id = update.effective_user.id

        # 1. Mensagem de carregamento
        msg_carregando = None
        if update.message:
            msg_carregando = await update.message.reply_text("⏳ Consultando suas regulações, aguarde...")
        elif update.callback_query:
            await update.callback_query.answer("Carregando...")
            msg_carregando = await update.callback_query.message.reply_text(
                "⏳ Consultando suas regulações, aguarde..."
            )

        # 2. Consulta no Supabase
        res = supabase.table("VigiaSaude_Teresina").select("*").eq("chat_id", user_id).execute()
        regulacoes = res.data if res.data else []

        if not regulacoes:
            msg_sem_dados = "⚠️ Nenhuma regulação cadastrada encontrada para o seu usuário."
            if msg_carregando:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=msg_carregando.message_id,
                    text=msg_sem_dados,
                )
            return ConversationHandler.END

        # 3. Monta botões
        teclado_botoes = []
        for reg in regulacoes:
            num_reg = reg.get("numero_reg")
            nome_bruto = reg.get("nome_paciente", "")
            cbo = reg.get("cbo", "")
            status_reg = reg.get("status_anterior_cidadao") or ""

            cbo_str = f" ({cbo.strip().upper()})" if cbo and str(cbo).strip().upper() not in ["NONE", "N/A", ""] else ""
            emoji = emoji_por_status(status_reg)
            rotulo_botao = f"{emoji} {num_reg} - {_mascarar_nome_custom(nome_bruto)}{cbo_str}"

            teclado_botoes.append([InlineKeyboardButton(rotulo_botao, callback_data=f"ver_esp_{num_reg}")])

        teclado_botoes.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_ver_esp")])
        reply_markup = InlineKeyboardMarkup(teclado_botoes)

        # 4. Contador de restantes (usa função que ignora intervalo)
        from verificacao_limite import restantes_reais

        restantes_esp = restantes_reais(str(user_id), "especifico")

        # 5. Menu com legenda colorida
        # 5. Menu com legenda colorida
        from verificacao_limite import _eh_admin as _check_admin

        eh_admin = _check_admin(str(user_id))

        if eh_admin:
            rodape = "👑 <b>Admin</b> · sem limite\n🕐 <i>Monitoramento automático a cada 6h</i>"
        else:
            rodape = f"📊 <b>Específicas hoje:</b> {restantes_esp}/10\n🕐 <i>Monitoramento automático a cada 6h</i>"

        msg = (
            "🔍 <b>Selecione qual regulação verificar</b>\n"
            "<i>Ou digite o ID abaixo:</i>\n\n"
            "━━━━━━━━━━━━━━━\n"
            "🎨 <b>LEGENDA DE STATUS</b>\n"
            "━━━━━━━━━━━━━━━\n\n"
            "🟢 <b>Agendada</b> · vá à UBS assinar e carimbar\n"
            "🟡 <b>Em fila</b> · aguarde, monitorando\n"
            "🔵 <b>Vencida</b> · revalidação atrasada\n"
            "🔴 <b>Cancelada</b> · procure a UBS\n"
            "🟣 <b>Revalidar</b> · procure a UBS antes dos 60 dias\n"
            "⚪ <b>Sem status</b> · portal não informou\n\n"
            "💡 <i>Fique de olho nas 🟡 Em fila!</i>\n\n"
            "━━━━━━━━━━━━━━━\n"
            f"{rodape}"
        )

        # 6. Substitui o carregamento pelo menu final
        if msg_carregando:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=msg_carregando.message_id,
                text=msg,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        context.user_data["_em_fluxo_admin"] = "verificar"
        return CONSULTAR_ID

    except Exception as e:
        logger.error(f"Erro em iniciar_verificar_especifico: {e}")
        context.user_data.pop("_em_fluxo_admin", None)
        return ConversationHandler.END


async def processar_verificar_especifico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa o clique/digitação da consulta específica."""
    try:
        user_id = update.effective_user.id

        # 🔒 Bloqueio de plano expirado
        from handler import verificar_plano_ativo, enviar_alerta_plano_expirado

        ativo, info = verificar_plano_ativo(user_id)
        if not ativo:
            await enviar_alerta_plano_expirado(update, context)
            return ConversationHandler.END

        # Identifica o número da regulação (callback ou texto)
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            num_reg = query.data.replace("ver_esp_", "").replace("corr_reg_", "").strip()
            msg_alvo = query.message
        elif update.message:
            num_reg = update.message.text.strip()
            msg_alvo = update.message
        else:
            context.user_data.pop("_em_fluxo_admin", None)
            return ConversationHandler.END

        # 🆕 LIMITE DIÁRIO + INTERVALO
        from verificacao_limite import pode_verificar, registrar_verificacao

        chat_id = str(user_id)
        pode, motivo, restantes = pode_verificar(chat_id, "especifico")

        if not pode:
            if motivo.startswith("intervalo:"):
                segundos = int(motivo.split(":")[1])
                await msg_alvo.reply_text(
                    f"⏳ <b>Aguarde {segundos} segundos</b> para fazer outra verificação.",
                    parse_mode="HTML",
                )
            else:
                await msg_alvo.reply_text(
                    "⏳ <b>Limite diário de verificações específicas atingido!</b>\n\n"
                    "Você já usou suas <b>10 verificações específicas</b> de hoje.\n\n"
                    "💡 <i>Aguarde até meia-noite para novas verificações.</i>",
                    parse_mode="HTML",
                )
            context.user_data.pop("_em_fluxo_admin", None)
            return ConversationHandler.END

        # Marca como usada
        registrar_verificacao(chat_id, "especifico")

        # Mensagem de carregamento
        msg_carregando = f"🔄 Consultando a regulação <b>{num_reg}</b> na FMS... Por favor, aguarde."
        await msg_alvo.reply_text(msg_carregando, parse_mode="HTML")

        # Dispara verificação em BACKGROUND (não bloqueia o bot)
        asyncio.create_task(_verificar_especifico_bg(num_reg, user_id, msg_alvo, restantes))

        return ConversationHandler.END

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Erro em processar_verificar_especifico: {e}")
        try:
            alvo = update.effective_message
            if alvo:
                await alvo.reply_text("⚠️ Ocorreu um erro ao consultar esta regulação. Tente novamente mais tarde.")
        except Exception:
            pass
    finally:
        context.user_data.pop("_em_fluxo_admin", None)

    return ConversationHandler.END


async def _verificar_especifico_bg(num_reg, user_id, msg_alvo, restantes):
    """Roda a consulta FMS em background e envia o resultado quando chegar."""
    try:
        try:
            resultado = await asyncio.wait_for(consultar_com_limite(num_reg), timeout=30)
        except asyncio.TimeoutError:
            await msg_alvo.reply_text(
                "⏳ <b>O portal FMS está demorando para responder.</b>\n\nTente novamente em alguns minutos.",
                parse_mode="HTML",
            )
            return

        # Busca dados complementares
        try:
            res_db = supabase.table("VigiaSaude_Teresina").select("*").eq("numero_reg", num_reg).execute()
            reg_data = res_db.data[0] if res_db.data else {}
        except Exception:
            reg_data = {}

        # Envia a mensagem final
        msg_html = _montar_msg_html(num_reg, resultado, reg_data)
        await msg_alvo.reply_text(msg_html, parse_mode="HTML")

        # Atualiza status_anterior_cidadao
        try:
            if isinstance(resultado, dict) and resultado.get("sucesso"):
                status_novo = (resultado.get("situacao") or "Informada no portal").strip()
                supabase.table("VigiaSaude_Teresina").update({"status_anterior_cidadao": status_novo}).eq(
                    "numero_reg", num_reg
                ).eq("chat_id", str(user_id)).execute()
        except Exception as e:
            logger.error(f"Erro ao atualizar status_anterior_cidadao: {e}")

        # Contador final
        restantes_agora = max(0, restantes - 1)
        await msg_alvo.reply_text(
            f"<i>📊 Verificações específicas restantes hoje: <b>0/0</b></i>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Erro em _verificar_especifico_bg: {e}")
