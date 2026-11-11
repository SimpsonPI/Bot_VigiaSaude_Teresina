# handler_enquete_local.py
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from admin import eh_admin
from enquetes_storage import (
    criar_enquete,
    obter_enquete,
    registrar_voto,
    listar_enquetes,
    encerrar_enquete,
    reabrir_enquete,
    apagar_enquete,
    apagar_todas,
    calcular_resultado,
    salvar_mensagem,
    obter_mensagens,
    definir_prazo,
    obter_enquetes_expiradas,
    tempo_restante,
    limpar_mensagens,  # ← NOVOS
)
from database import supabase

logger = logging.getLogger(__name__)

# Estados
AGUARDANDO_PERGUNTA = 1
AGUARDANDO_OPCOES = 2
AGUARDANDO_DESTINO = 3
AGUARDANDO_PRAZO = 4
AGUARDANDO_CONFIRMACAO = 5


# ═══════════════════════════════════════════════════════════
# CRIAÇÃO DA ENQUETE
# ═══════════════════════════════════════════════════════════


async def iniciar_criacao_enquete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        if update.callback_query:
            await update.callback_query.answer("⛔ Acesso restrito.", show_alert=True)
        else:
            await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return ConversationHandler.END

    for k in ("enq_pergunta", "enq_opcoes", "enq_destinos"):
        context.user_data.pop(k, None)

    texto = (
        "📊 <b>Criar Enquete</b>\n\n"
        "Digite a <b>pergunta</b>:\n\n"
        "<i>Ex: Qual sua principal dificuldade no VigiaSaúde?</i>\n\n"
        "Para cancelar, use /cancelar."
    )

    # Se veio de um botão do painel, avisa o Telegram e edita a mensagem
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(texto, parse_mode="HTML")
    else:
        await update.message.reply_text(texto, parse_mode="HTML")

    context.user_data["_em_fluxo_admin"] = "enquete"
    return AGUARDANDO_PERGUNTA


async def receber_pergunta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pergunta = update.message.text.strip()
    if len(pergunta) < 5 or len(pergunta) > 300:
        await update.message.reply_text("❌ A pergunta deve ter entre 5 e 300 caracteres. Tente novamente:")
        return AGUARDANDO_PERGUNTA

    context.user_data["enq_pergunta"] = pergunta

    await update.message.reply_text(
        "✅ Pergunta salva.\n\n"
        "Agora envie as <b>opções</b>, uma por linha (mín. 2, máx. 10):\n\n"
        "<i>Exemplo:</i>\n<code>Cadastrar\nCorrigir\nExcluir\nInformações do bot</code>",
        parse_mode="HTML",
    )
    return AGUARDANDO_OPCOES


async def receber_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    linhas = [l.strip() for l in update.message.text.split("\n") if l.strip()]
    if len(linhas) < 2 or len(linhas) > 10:
        await update.message.reply_text("❌ Envie entre 2 e 10 opções, uma por linha:")
        return AGUARDANDO_OPCOES
    for opt in linhas:
        if len(opt) > 100:
            await update.message.reply_text(f'❌ A opção "{opt[:30]}..." excede 100 caracteres:')
            return AGUARDANDO_OPCOES

    context.user_data["enq_opcoes"] = linhas

    await update.message.reply_text(
        f"✅ {len(linhas)} opções salvas.\n\n"
        "📨 Para quem deseja enviar?\n\n"
        "• Digite o <b>ID do chat</b>\n"
        "• Ou digite <b>todos</b> para enviar a todos os usuários.",
        parse_mode="HTML",
    )
    return AGUARDANDO_DESTINO


async def receber_destino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    destino = update.message.text.strip().lower()

    if destino == "todos":
        try:
            res = supabase.table("VigiaSaude_Teresina").select("chat_id").execute()
            chat_ids = list(set(str(r["chat_id"]) for r in res.data if r.get("chat_id")))
        except Exception as e:
            logger.error(f"Erro ao buscar chat_ids: {e}")
            await update.message.reply_text("❌ Erro ao buscar lista de usuários.")
            return ConversationHandler.END
        if not chat_ids:
            await update.message.reply_text("⚠️ Nenhum usuário cadastrado.")
            return ConversationHandler.END
        context.user_data["enq_destinos"] = chat_ids
        alvo = f"<b>TODOS</b> ({len(chat_ids)} usuários)"
    else:
        try:
            chat_id_unico = str(int(destino))
        except ValueError:
            await update.message.reply_text("❌ ID inválido. Envie um número ou <b>todos</b>.", parse_mode="HTML")
            return AGUARDANDO_DESTINO
        context.user_data["enq_destinos"] = [chat_id_unico]
        alvo = f"ID <code>{chat_id_unico}</code>"

    # Agora pergunta o PRAZO
    teclado = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⏱️ 5 min", callback_data="prazo_300"),
                InlineKeyboardButton("⏱️ 15 min", callback_data="prazo_900"),
                InlineKeyboardButton("⏱️ 30 min", callback_data="prazo_1800"),
            ],
            [
                InlineKeyboardButton("⏰ 1 hora", callback_data="prazo_3600"),
                InlineKeyboardButton("⏰ 6 horas", callback_data="prazo_21600"),
                InlineKeyboardButton("🌙 24 horas", callback_data="prazo_86400"),
            ],
            [
                InlineKeyboardButton("📅 3 dias", callback_data="prazo_259200"),
                InlineKeyboardButton("📅 7 dias", callback_data="prazo_604800"),
            ],
            [
                InlineKeyboardButton("♾️ Sem prazo (não expira)", callback_data="prazo_none"),
            ],
        ]
    )

    await update.message.reply_text(
        f"✅ Destino salvo: {alvo}\n\n"
        "⏱️ Agora escolha o <b>prazo de duração</b> da enquete:\n\n"
        "<i>Após o prazo, a mensagem será removida automaticamente dos chats.</i>",
        parse_mode="HTML",
        reply_markup=teclado,
    )
    return AGUARDANDO_PRAZO


async def receber_prazo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "prazo_none":
        context.user_data["enq_prazo_segundos"] = None
        contexto_prazo = "♾️ Sem prazo (não expira automaticamente)"
    else:
        try:
            segundos = int(data.split("_")[1])
            context.user_data["enq_prazo_segundos"] = segundos
            if segundos < 3600:
                contexto_prazo = f"⏱️ {segundos // 60} minuto(s)"
            elif segundos < 86400:
                contexto_prazo = f"⏰ {segundos // 3600} hora(s)"
            else:
                contexto_prazo = f"📅 {segundos // 86400} dia(s)"
        except Exception:
            await query.edit_message_text("❌ Prazo inválido.")
            return ConversationHandler.END

    context.user_data["enq_prazo_texto"] = contexto_prazo

    pergunta = context.user_data.get("enq_pergunta")
    opcoes = context.user_data.get("enq_opcoes", [])
    destinos = context.user_data.get("enq_destinos", [])
    preview = "\n".join(f"  {i + 1}. {o}" for i, o in enumerate(opcoes))

    alvo = f"{len(destinos)} usuário(s)" if len(destinos) > 1 else f"ID <code>{destinos[0]}</code>"

    teclado = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirmar", callback_data="enq_confirmar"),
                InlineKeyboardButton("❌ Cancelar", callback_data="enq_cancelar"),
            ]
        ]
    )

    await query.edit_message_text(
        "📋 <b>Confirmação Final</b>\n\n"
        f"• <b>Pergunta:</b> {pergunta}\n"
        f"• <b>Opções:</b>\n{preview}\n"
        f"• <b>Destino:</b> {alvo}\n"
        f"• <b>Prazo:</b> {contexto_prazo}\n\n"
        "⚠️ <i>Após o prazo, a mensagem será removida automaticamente.</i>\n\n"
        "Confirma?",
        parse_mode="HTML",
        reply_markup=teclado,
    )
    return AGUARDANDO_CONFIRMACAO  # ← MUDE DE ConversationHandler.END PARA ISSO


async def confirmar_criacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pergunta = context.user_data.get("enq_pergunta")
    opcoes = context.user_data.get("enq_opcoes")
    destinos = context.user_data.get("enq_destinos") or []
    prazo_seg = context.user_data.get("enq_prazo_segundos")

    if not pergunta or not opcoes or not destinos:
        context.user_data.pop("_em_fluxo_admin", None)
        await query.edit_message_text("❌ Dados incompletos.")
        return ConversationHandler.END

    enquete_id = criar_enquete(pergunta, opcoes, str(update.effective_user.id))

    # Define o prazo
    if prazo_seg is not None:
        definir_prazo(enquete_id, prazo_seg)

    admin_id_str = str(update.effective_user.id)
    if admin_id_str not in destinos:
        destinos.append(admin_id_str)

    await query.edit_message_text(f"📤 Enviando enquete #{enquete_id} para {len(destinos)} usuário(s)...")

    # Envia
    enviados = 0
    falhas = 0
    for chat_id in destinos:
        try:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=mensagem_inicial_enquete(obter_enquete(enquete_id)),
                parse_mode="HTML",
                reply_markup=construir_teclado(enquete_id, opcoes, None),
            )
            salvar_mensagem(enquete_id, chat_id, msg.message_id)
            enviados += 1
        except Exception as e:
            falhas += 1
            logger.error(f"Erro ao enviar enquete para {chat_id}: {e}")

    prazo_info = f"\n⏱️ Prazo: <b>{context.user_data.get('enq_prazo_texto', '—')}</b>" if prazo_seg else ""

    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=(
            f"✅ <b>Enquete #{enquete_id} enviada!</b>\n\n"
            f"• Enviadas: {enviados}\n"
            f"• Falhas: {falhas}"
            f"{prazo_info}\n\n"
            f"📊 Ver resultado: <code>/resultado {enquete_id}</code>\n"
            f"📋 Encerrar: <code>/encerrar {enquete_id}</code>\n"
            f"🗑️ Apagar: <code>/apagar_enquete {enquete_id}</code>"
        ),
        parse_mode="HTML",
    )

    for k in (
        "enq_pergunta",
        "enq_opcoes",
        "enq_destinos",
        "enq_prazo_segundos",
        "enq_prazo_texto",
    ):
        context.user_data.pop(k, None)

    return ConversationHandler.END


async def cancelar_criacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Criação cancelada.")
    elif update.message:
        await update.message.reply_text("❌ Criação cancelada.")
    for k in (
        "enq_pergunta",
        "enq_opcoes",
        "enq_destinos",
        "enq_prazo_segundos",
        "enq_prazo_texto",
    ):
        context.user_data.pop(k, None)
    context.user_data.pop("_em_fluxo_admin", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════
# VOTAÇÃO
# ═══════════════════════════════════════════════════════════


async def receber_voto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    partes = query.data.split("_")
    enquete_id = int(partes[1])
    opcao_idx = int(partes[2])

    ok, msg = registrar_voto(enquete_id, str(user.id), user.first_name or "Usuário", opcao_idx)

    if not ok:
        await query.answer(msg, show_alert=True)
        return

    enquete = obter_enquete(enquete_id)
    opcoes = enquete.get("opcoes", [])
    opcao_escolhida = opcoes[opcao_idx] if opcao_idx < len(opcoes) else "?"

    await query.answer(f"✅ Voto registrado: {opcao_escolhida}", show_alert=False)

    # Atualiza imediatamente a mensagem para o usuário
    await atualizar_uma_mensagem(
        bot=context.bot,
        enquete=enquete,
        chat_id=str(user.id),
        message_id=query.message.message_id,
        voto_usuario_idx=opcao_idx,
    )


async def voto_ja_registrado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("⚠️ Você já votou nesta enquete!", show_alert=True)


# ═══════════════════════════════════════════════════════════
# RESULTADO
# ═══════════════════════════════════════════════════════════


async def comando_resultado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Uso: <code>/resultado &lt;ID&gt;</code>", parse_mode="HTML")
        return

    try:
        enquete_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID inválido.")
        return

    enquete = obter_enquete(enquete_id)
    if not enquete:
        await update.message.reply_text(f"❌ Enquete #{enquete_id} não encontrada.")
        return

    r = calcular_resultado(enquete)
    total = r["total"]
    contagem = r["contagem"]
    opcoes = r["opcoes"]

    status = "🟢 Ativa" if enquete.get("ativa") else "🔒 Encerrada"

    texto = (
        f"📊 <b>Resultado — Enquete #{enquete_id}</b>\n"
        f"<i>{enquete.get('pergunta')}</i>\n\n"
        f"Status: {status}\n"
        f"Total de votos: <b>{total}</b>\n\n"
    )

    for i, opt in enumerate(opcoes):
        qtd = contagem.get(i, 0)
        pct = (qtd / total * 100) if total > 0 else 0
        barra = "█" * int(pct / 5)
        texto += f"<b>{opt}</b>\n{qtd} voto(s) — {pct:.1f}%\n{barra}\n\n"

    # Adiciona botões de ação
    botoes = []
    if enquete.get("ativa"):
        botoes.append([InlineKeyboardButton("🔒 Encerrar", callback_data=f"enq_encerrar_{enquete_id}")])
    else:
        botoes.append([InlineKeyboardButton("🔓 Reabrir", callback_data=f"enq_reabrir_{enquete_id}")])
    botoes.append([InlineKeyboardButton("🗑️ Apagar", callback_data=f"enq_apagar_{enquete_id}")])
    botoes.append([InlineKeyboardButton("🔄 Atualizar", callback_data=f"enq_atualizar_{enquete_id}")])

    await update.message.reply_text(texto, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(botoes))


async def callback_resultado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botões dentro do resultado (encerrar, reabrir, apagar, atualizar)."""
    query = update.callback_query
    if not eh_admin(query.from_user.id):
        await query.answer("⛔ Acesso restrito.", show_alert=True)
        return

    data = query.data
    if data.startswith("enq_encerrar_"):
        eid = int(data.split("_")[-1])
        encerrar_enquete(eid)
        await query.answer("🔒 Enquete encerrada!")
    elif data.startswith("enq_reabrir_"):
        eid = int(data.split("_")[-1])
        reabrir_enquete(eid)
        await query.answer("🔓 Enquete reaberta!")
    elif data.startswith("enq_apagar_"):
        eid = int(data.split("_")[-1])
        apagar_enquete(eid)
        await query.answer("🗑️ Enquete apagada!")
        await query.edit_message_text(f"🗑️ Enquete #{eid} apagada com sucesso.")
        return
    elif data.startswith("enq_atualizar_"):
        eid = int(data.split("_")[-1])
        await query.answer("🔄 Atualizando...")

    # Recria a mensagem com dados atualizados
    enquete_id = int(data.split("_")[-1])
    enquete = obter_enquete(enquete_id)
    if not enquete:
        await query.edit_message_text("❌ Enquete não encontrada.")
        return

    r = calcular_resultado(enquete)
    total = r["total"]
    contagem = r["contagem"]
    opcoes = r["opcoes"]

    status = "🟢 Ativa" if enquete.get("ativa") else "🔒 Encerrada"

    texto = (
        f"📊 <b>Resultado — Enquete #{enquete_id}</b>\n"
        f"<i>{enquete.get('pergunta')}</i>\n\n"
        f"Status: {status}\n"
        f"Total de votos: <b>{total}</b>\n\n"
    )

    for i, opt in enumerate(opcoes):
        qtd = contagem.get(i, 0)
        pct = (qtd / total * 100) if total > 0 else 0
        barra = "█" * int(pct / 5)
        texto += f"<b>{opt}</b>\n{qtd} voto(s) — {pct:.1f}%\n{barra}\n\n"

    botoes = []
    if enquete.get("ativa"):
        botoes.append([InlineKeyboardButton("🔒 Encerrar", callback_data=f"enq_encerrar_{enquete_id}")])
    else:
        botoes.append([InlineKeyboardButton("🔓 Reabrir", callback_data=f"enq_reabrir_{enquete_id}")])
    botoes.append([InlineKeyboardButton("🗑️ Apagar", callback_data=f"enq_apagar_{enquete_id}")])
    botoes.append([InlineKeyboardButton("🔄 Atualizar", callback_data=f"enq_atualizar_{enquete_id}")])

    try:
        await query.edit_message_text(texto, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(botoes))
    except Exception:
        pass  # Se não mudou nada, ignora


async def comando_resultado_detalhado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Uso: <code>/resultado_detalhado &lt;ID&gt;</code>", parse_mode="HTML")
        return

    try:
        enquete_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID inválido.")
        return

    enquete = obter_enquete(enquete_id)
    if not enquete:
        await update.message.reply_text(f"❌ Enquete #{enquete_id} não encontrada.")
        return

    votos = enquete.get("votos", {})
    if not votos:
        await update.message.reply_text("ℹ️ Nenhum voto ainda.")
        return

    opcoes = enquete.get("opcoes", [])
    texto = f"📋 <b>Votos detalhados — Enquete #{enquete_id}</b>\n\n"
    for chat_id, v in votos.items():
        idx = v.get("opcao_idx", -1)
        opt = opcoes[idx] if 0 <= idx < len(opcoes) else "?"
        nome = v.get("nome", "?")
        texto += f"• <b>{nome}</b> (<code>{chat_id}</code>) → {opt}\n"

    if len(texto) > 4000:
        texto = texto[:3990] + "\n\n<i>[...]</i>"

    await update.message.reply_text(texto, parse_mode="HTML")


async def comando_listar_enquetes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return

    enquetes = listar_enquetes()
    if not enquetes:
        await update.message.reply_text("ℹ️ Nenhuma enquete criada ainda.")
        return

    texto = "📋 <b>Enquetes criadas:</b>\n\n"
    for e in enquetes[:20]:
        status = "🟢" if e.get("ativa") else "🔒"
        total = len(e.get("votos", {}))
        texto += f"{status} <b>#{e['id']}</b> — {e['pergunta'][:50]}\n   {total} voto(s)\n"

    texto += "\n<i>Use /resultado &lt;id&gt; para ver os votos.</i>"
    await update.message.reply_text(texto, parse_mode="HTML")


async def comando_encerrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Uso: <code>/encerrar &lt;ID&gt;</code>", parse_mode="HTML")
        return

    try:
        eid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID inválido.")
        return

    if encerrar_enquete(eid):
        await update.message.reply_text(f"🔒 Enquete #{eid} encerrada.")
    else:
        await update.message.reply_text("❌ Enquete não encontrada.")


async def comando_apagar_enquete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Uso: <code>/apagar_enquete &lt;ID&gt;</code>\nOu <code>/apagar_enquete todas</code> para apagar todas.",
            parse_mode="HTML",
        )
        return

    arg = context.args[0].lower()
    if arg == "todas":
        qtd = apagar_todas()
        await update.message.reply_text(f"🗑️ {qtd} enquete(s) apagada(s).")
        return

    try:
        eid = int(arg)
    except ValueError:
        await update.message.reply_text("❌ ID inválido.")
        return

    if apagar_enquete(eid):
        await update.message.reply_text(f"🗑️ Enquete #{eid} apagada.")
    else:
        await update.message.reply_text("❌ Enquete não encontrada.")


# ═══════════════════════════════════════════════════════════
# ConversationHandler
# ═══════════════════════════════════════════════════════════

conv_criar_enquete = ConversationHandler(
    entry_points=[
        CommandHandler("criar_enquete", iniciar_criacao_enquete),
        CommandHandler("enviar_enquete", iniciar_criacao_enquete),
        CallbackQueryHandler(iniciar_criacao_enquete, pattern="^criar_enquete$"),  # <-- ADICIONE ESTA LINHA
    ],
    states={
        AGUARDANDO_PERGUNTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_pergunta)],
        AGUARDANDO_OPCOES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_opcoes)],
        AGUARDANDO_DESTINO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_destino)],
        AGUARDANDO_PRAZO: [CallbackQueryHandler(receber_prazo, pattern="^prazo_")],
        AGUARDANDO_CONFIRMACAO: [
            CallbackQueryHandler(confirmar_criacao, pattern="^enq_confirmar$"),
            CallbackQueryHandler(cancelar_criacao, pattern="^enq_cancelar$"),
        ],
    },
    fallbacks=[CommandHandler("cancelar", cancelar_criacao)],
    per_message=False,
)

# ═══════════════════════════════════════════════════════════
# RENDERIZAÇÃO E ATUALIZAÇÃO AUTOMÁTICA
# ═══════════════════════════════════════════════════════════

EMOJIS_LETRAS = ["🅰️", "🅱️", "🆎", "🅾️", "🅿️", "🇦", "🇧", "🇨", "🇩", "🇪"]


def barra_progresso(pct: float, tamanho: int = 16) -> str:
    """Gera barra visual em blocos. Ex: ██████░░░░░░░░░░ 40%"""
    preenchidos = int(round((pct / 100) * tamanho))
    preenchidos = max(0, min(tamanho, preenchidos))
    return "█" * preenchidos + "░" * (tamanho - preenchidos)


def construir_teclado(enquete_id: int, opcoes: list, voto_usuario_idx: int | None = None):
    """Monta o teclado com emojis de letras. Se o usuário votou, desabilita."""
    botoes = []
    for idx, opt in enumerate(opcoes):
        emoji = EMOJIS_LETRAS[idx] if idx < len(EMOJIS_LETRAS) else "▫️"
        if voto_usuario_idx is not None:
            # Já votou → botão inerte
            if idx == voto_usuario_idx:
                botoes.append([InlineKeyboardButton(f"✅  {opt} (seu voto)", callback_data="voto_ja_registrado")])
            else:
                botoes.append([InlineKeyboardButton(f"{emoji}  {opt}", callback_data="voto_ja_registrado")])
        else:
            botoes.append([InlineKeyboardButton(f"{emoji}  {opt}", callback_data=f"voto_{enquete_id}_{idx}")])
    return InlineKeyboardMarkup(botoes)


def mensagem_enquete_aberta(pergunta: str, opcoes: list) -> str:
    """Mensagem inicial antes de qualquer voto (sem barra)."""
    linhas_opcoes = "\n".join(
        f"{EMOJIS_LETRAS[i] if i < len(EMOJIS_LETRAS) else '▫️'}  {opt}" for i, opt in enumerate(opcoes)
    )
    return (
        "╔══════════════════════════╗\n"
        "   📊  <b>ENQUETE VIGIASAÚDE</b>\n"
        "╚══════════════════════════╝\n\n"
        f"❓ <b>{pergunta}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🗳️ <b>Resultados parciais:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{linhas_opcoes}\n\n"
        "🔒 <i>Voto único. Aguardando votos...</i>"
    )


def mensagem_enquete_com_resultados(enquete: dict, voto_usuario_idx: int | None = None) -> str:
    """
    Se o usuário JÁ votou → mostra os resultados com barras.
    Se NÃO votou → mostra apenas a pergunta e as opções (sem resultados).
    """
    pergunta = enquete.get("pergunta", "")
    r = calcular_resultado(enquete)
    total = r["total"]
    contagem = r["contagem"]
    opcoes = r["opcoes"]

    # ─── Caso 1: usuário ainda NÃO votou → sem resultados ───
    if voto_usuario_idx is None:
        linhas_opcoes = "\n".join(
            f"{EMOJIS_LETRAS[i] if i < len(EMOJIS_LETRAS) else '▫️'}  {opt}" for i, opt in enumerate(opcoes)
        )
        return (
            "╔══════════════════════════╗\n"
            "   📊  <b>ENQUETE VIGIASAÚDE</b>\n"
            "╚══════════════════════════╝\n\n"
            f"❓ <b>{pergunta}</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🗳️ <b>Escolha uma opção:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{linhas_opcoes}\n\n"
            "🔒 <i>Voto único. Os resultados aparecem após você votar.</i>"
        )

    # ─── Caso 2: usuário JÁ votou → mostra resultados ───
    linhas = []
    for i, opt in enumerate(opcoes):
        qtd = contagem.get(i, 0)
        pct = (qtd / total * 100) if total > 0 else 0.0
        barra = barra_progresso(pct)

        emoji = EMOJIS_LETRAS[i] if i < len(EMOJIS_LETRAS) else "▫️"
        marcador = "✅ " if voto_usuario_idx == i else f"{emoji}  "

        linhas.append(f"{marcador}<b>{opt}</b>\n<code>{barra}</code> {pct:.1f}%  •  {qtd} voto(s)")

    bloco_opcoes = "\n\n".join(linhas)

    return (
        "╔══════════════════════════╗\n"
        "   📊  <b>ENQUETE VIGIASAÚDE</b>\n"
        "╚══════════════════════════╝\n\n"
        f"❓ <b>{pergunta}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>{total} voto(s) até agora</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{bloco_opcoes}\n\n"
        "✅ <i>Seu voto foi contabilizado. Obrigado por participar!</i>"
    )


def mensagem_inicial_enquete(enquete: dict) -> str:
    """Mensagem inicial (sem voto) com contagem regressiva."""
    pergunta = enquete.get("pergunta", "")
    opcoes = enquete.get("opcoes", [])
    tempo = tempo_restante(enquete)

    linhas_opcoes = "\n".join(
        f"{EMOJIS_LETRAS[i] if i < len(EMOJIS_LETRAS) else '▫️'}  {opt}" for i, opt in enumerate(opcoes)
    )

    if tempo == "sem prazo":
        rodape_tempo = "♾️ <i>Sem prazo definido.</i>"
    elif tempo == "expirada":
        rodape_tempo = "🔒 <i>Enquete expirada.</i>"
    else:
        rodape_tempo = f"⏳ <i>Tempo restante: <b>{tempo}</b></i>"

    return (
        "╔══════════════════════════╗\n"
        "   📊  <b>ENQUETE VIGIASAÚDE</b>\n"
        "╚══════════════════════════╝\n\n"
        f"❓ <b>{pergunta}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🗳️ <b>Escolha uma opção:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{linhas_opcoes}\n\n"
        f"{rodape_tempo}\n"
        "🔒 <i>Voto único. Os resultados aparecem após você votar.</i>"
    )


async def atualizar_uma_mensagem(
    bot,
    enquete: dict,
    chat_id: str,
    message_id: int,
    voto_usuario_idx: int | None = None,
):
    """Edita uma mensagem específica com base no voto do usuário."""
    try:
        votos = enquete.get("votos", {})

        # Descobre se ESTE usuário já votou
        ja_votou = chat_id in votos
        if ja_votou and voto_usuario_idx is None:
            voto_usuario_idx = votos[chat_id].get("opcao_idx")

        ativa = enquete.get("ativa", True)

        # Monta o texto conforme o estado do usuário
        if ja_votou:
            # Já votou → mostra resultados
            texto = mensagem_enquete_com_resultados(enquete, voto_usuario_idx)
            teclado = construir_teclado(enquete["id"], enquete["opcoes"], voto_usuario_idx) if ativa else None
            if not ativa:
                texto += "\n\n🔒 <b>Esta enquete foi encerrada.</b>"
        else:
            # Ainda não votou → mostra só a pergunta, sem resultados
            if not ativa:
                # Se a enquete foi encerrada e o usuário não votou, avisa
                texto = (
                    "╔══════════════════════════╗\n"
                    "   📊  <b>ENQUETE VIGIASAÚDE</b>\n"
                    "╚══════════════════════════╝\n\n"
                    f"❓ <b>{enquete.get('pergunta')}</b>\n\n"
                    "🔒 <b>Esta enquete foi encerrada.</b>\n"
                    "<i>Você não votou a tempo.</i>"
                )
                teclado = None
            else:
                texto = mensagem_enquete_com_resultados(enquete, None)
                teclado = construir_teclado(enquete["id"], enquete["opcoes"], None)

        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=texto,
                parse_mode="HTML",
                reply_markup=teclado,
            )
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.debug(f"Falha ao editar msg de {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Erro em atualizar_uma_mensagem: {e}")


async def atualizar_enquetes_job(context: ContextTypes.DEFAULT_TYPE):
    """Job agendado: atualiza mensagens dos usuários que JÁ votaram."""
    enquetes = listar_enquetes()
    for enq in enquetes:
        mensagens = obter_mensagens(enq["id"])
        if not mensagens:
            continue

        votos = enq.get("votos", {})

        for chat_id, message_id in mensagens.items():
            # Atualiza somente se o usuário já votou (para ver os resultados) OU se a enquete foi encerrada
            if chat_id in votos or not enq.get("ativa"):
                await atualizar_uma_mensagem(context.bot, enq, chat_id, message_id)
                await asyncio.sleep(0.05)


async def verificar_enquetes_expiradas(context: ContextTypes.DEFAULT_TYPE):
    """Job: apaga enquetes expiradas do chat do usuário."""
    expiradas = obter_enquetes_expiradas()
    for enq in expiradas:
        logger.info(f"⏰ Enquete #{enq['id']} expirou. Apagando mensagens...")

        mensagens = obter_mensagens(enq["id"])

        for chat_id, message_id in mensagens.items():
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.debug(f"Não foi possível apagar msg {message_id} de {chat_id}: {e}")

        encerrar_enquete(enq["id"])
        limpar_mensagens(enq["id"])

        try:
            from config import ADMIN_CHAT_ID

            if ADMIN_CHAT_ID:
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=(
                        f"⏰ <b>Enquete #{enq['id']} expirou</b>\n\n"
                        f"❓ {enq.get('pergunta', '')[:100]}\n\n"
                        f"📊 Use <code>/resultado {enq['id']}</code> para ver os votos finais."
                    ),
                    parse_mode="HTML",
                )
        except Exception as e:
            logger.error(f"Erro ao notificar admin sobre enquete expirada: {e}")
