# handler_cadastro.py
import logging
import os

logger = logging.getLogger(__name__)
import re
from bot_seguranca import safe_callback
from config import is_admin
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from database import salvar_regulacao, registrar_consentimento_lgpd, supabase
from utils import (
    DISCLAIMER_TEXTO,
    TECLADO_MENU,
    ETAPA_SUS,
    ETAPA_NOME,
    ETAPA_CELULAR,
    ETAPA_NASCIMENTO,
    ETAPA_REGULACAO,
    ETAPA_CBO,
    ETAPA_PROCEDIMENTO,
    ETAPA_LGPD,
    ETAPA_RESUMO,
    ETAPA_CORRIGINDO,
    ETAPA_CONFIRMAR_REUSO,
    ETAPA_ESCOLHER_SUS,
    formatar_data,
    formatar_celular,
    formatar_maiusculo,
    verificar_se_e_menu_e_executar,
)


async def iniciar_cadastro_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o cadastro de uma nova regulação institucional."""
    from config import is_admin

    user_id = update.effective_user.id
    admin_user = is_admin(user_id)

    # 1. Verifica se o usuário já tem cadastros no histórico vitalício
    try:
        res_hist = (
            supabase.table("VigiaSaude_Teresina_autorizados")
            .select("cadastros_realizados")
            .eq("chat_id", user_id)
            .execute()
        )
        cadastros_feitos = res_hist.data[0].get("cadastros_realizados", 0) if res_hist.data else 0
    except Exception as e:
        logger.error(f"Erro ao buscar histórico: {e}")
        cadastros_feitos = 0

    # 2. Conta quantas regulações ativas ele tem agora
    try:
        res_ativos = supabase.table("VigiaSaude_Teresina").select("id", count="exact").eq("chat_id", user_id).execute()
        total_regs = res_ativos.count if hasattr(res_ativos, "count") else len(res_ativos.data or [])
    except Exception as e:
        logger.error(f"Erro ao buscar ativos: {e}")
        total_regs = 0

    # 3. BLOQUEIOS (Só aplica se NÃO for admin)
    if not admin_user:
        if cadastros_feitos >= 3:
            await update.message.reply_text(
                "🚫 <b>Limite Gratuito Atingido</b>\n\n"
                "Você já utilizou suas 3 vagas gratuitas no VigiaSaúde Cidadão.\n\n"
                "Para monitorar novos exames, conheça nossa versão Premium:\n"
                "👉 @vigiasaude_bot",
                parse_mode="HTML",
            )
            return ConversationHandler.END

        if total_regs >= 3:
            await update.message.reply_text(
                f"📌 <b>Limite de regulações atingido</b>\n\n"
                f"Você já cadastrou <b>{total_regs}/3</b> regulações — "
                "esse é o máximo permitido pelo sistema.\n\n"
                "💡 <b>Como cadastrar novas regulações?</b>\n"
                "Você pode <b>excluir</b> regulações antigas que já foram finalizadas "
                "e liberar espaço. Use o comando:\n\n"
                "<code>/excluir</code>\n\n"
                "Assim que excluir uma, poderá cadastrar novas normalmente. 😊",
                parse_mode="HTML",
            )
            return ConversationHandler.END

    # 4. Inicia o fluxo de perguntas
    await update.message.reply_text(
        "Ok! Digite o número do Cartão SUS do paciente (15 dígitos):",
        parse_mode="HTML",
    )
    return ETAPA_SUS

    # =========================================================
    # AQUI ENTRA O RESTO DO SEU CÓDIGO (O QUE JÁ EXISTIA)
    # Provavelmente a escolha do Cartão SUS e o envio do teclado
    # Exemplo:
    # await update.message.reply_text("Digite o Cartão SUS:", ...)
    # return ETAPA_SUS
    # =========================================================
    # ---------------------------------------------------------
    # Se chegou até aqui, é Admin OU está dentro do limite.
    # ---------------------------------------------------------

    # Limpa APENAS os dados de fluxos anteriores, mas não trava o atual
    context.user_data.pop("sus", None)
    context.user_data.pop("nome", None)
    context.user_data.pop("nascimento", None)
    context.user_data.pop("numero_regulacao", None)
    context.user_data.pop("cbo", None)
    context.user_data.pop("procedimento", None)

    context.user_data["_em_fluxo_admin"] = "cadastro"
    context.user_data["_em_fluxo_admin"] = "cadastro"

    try:
        res_sus = (
            supabase.table("VigiaSaude_Teresina")
            .select("numero_sus, nome_paciente, data_nascimento")
            .eq("chat_id", user_id)
            .order("id", desc=True)
            .execute()
        )
        registros = res_sus.data or []
    except Exception as e:
        logger.error(f"Erro ao buscar SUS: {e}")
        registros = []

    sus_unicos = {}
    for r in registros:
        num = r.get("numero_sus")
        if num and num not in sus_unicos:
            sus_unicos[num] = r
    sus_lista = list(sus_unicos.items())

    if not sus_lista:
        await update.message.reply_text(
            "📝 <b>Iniciando cadastro de nova regulação.</b>\n\n"
            f"Você tem <b>{total_regs}/3</b> regulações cadastradas.\n\n"
            "Por favor, digite o <b>número do Cartão SUS</b> do paciente (15 dígitos):",
            parse_mode="HTML",
            reply_markup=TECLADO_CANCELAR,
        )
        return ETAPA_SUS

    if len(sus_lista) == 1:
        num, dados = sus_lista[0]
        nome = dados.get("nome_paciente") or "—"
        teclado = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Usar mesmo Cartão do SUS", callback_data=f"usar_sus_{num}")],
                [InlineKeyboardButton("🔄 Cadastrar novo SUS", callback_data="novo_sus")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="iniciar")],
            ]
        )
        await update.message.reply_text(
            "📝 <b>Iniciando cadastro de nova regulação.</b>\n\n"
            f"Você tem <b>{total_regs}/3</b> regulações cadastradas.\n\n"
            f"💳 Detectei um Cartão do SUS cadastrado:\n"
            f"<code>{num}</code> · {nome}\n\n"
            "Deseja usar o mesmo número de Cartão do SUS?",
            parse_mode="HTML",
            reply_markup=teclado,
        )
    else:
        botoes = []
        for num, dados in sus_lista:
            nome = (dados.get("nome_paciente") or "—")[:22]
            botoes.append([InlineKeyboardButton(f"💳 {num} · {nome}", callback_data=f"usar_sus_{num}")])
        botoes.append([InlineKeyboardButton("➕ Cadastrar novo SUS", callback_data="novo_sus")])
        botoes.append([InlineKeyboardButton("❌ Cancelar", callback_data="iniciar")])
        await update.message.reply_text(
            "📝 <b>Iniciando cadastro de nova regulação.</b>\n\n"
            f"Você tem <b>{total_regs}/3</b> regulações cadastradas.\n\n"
            "💳 <b>Selecione qual Cartão do SUS deseja usar:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(botoes),
        )

    return ETAPA_ESCOLHER_SUS


@safe_callback
async def callback_escolher_sus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a escolha do SUS no início do cadastro."""
    query = update.callback_query
    data = query.data

    if data == "cancelar":
        await query.edit_message_text("❌ Cadastro cancelado.")
        context.user_data.clear()
        return ConversationHandler.END

    if data == "novo_sus":
        for k in ("sus", "nome", "nascimento"):
            context.user_data.pop(k, None)
        await query.edit_message_text(
            "Ok! Digite o <b>número do Cartão SUS</b> do paciente (15 dígitos):",
            parse_mode="HTML",
        )
        return ETAPA_SUS

    if data.startswith("usar_sus_"):
        num_sus = data.replace("usar_sus_", "")
        try:
            # AQUI ESTAVA O ERRO: A linha do 'res' tinha sido apagada sem querer
            res = (
                supabase.table("VigiaSaude_Teresina")
                .select("nome_paciente, data_nascimento")
                .eq("chat_id", update.effective_user.id)
                .eq("numero_sus", num_sus)
                .order("id", desc=True)
                .limit(1)
                .execute()
            )
            dados = res.data[0] if res.data else {}
        except Exception as e:
            logger.error(f"Erro ao buscar dados do SUS: {e}")
            dados = {}

        context.user_data["sus"] = num_sus
        context.user_data["nome"] = dados.get("nome_paciente") or ""
        context.user_data["nascimento"] = dados.get("data_nascimento") or ""

        texto_id = (
            f"✅ <b>SUS carregado:</b> <code>{num_sus}</code>\n\n"
            f"👤 <b>Paciente:</b> {dados.get('nome_paciente') or '—'}\n"
            f"📅 <b>Nascimento:</b> {dados.get('data_nascimento') or '—'}\n\n"
            "🆔 <b>Agora digite o ID da Regulação (8 dígitos):</b>"
        )

        # Apaga a mensagem dos botões antiga
        try:
            await query.message.delete()
        except Exception:
            pass

        # Busca o caminho absoluto da imagem
        caminho_imagem = os.path.join(os.path.dirname(__file__), "comprovante_sus.jpg")

        # Envia a foto como nova mensagem
        try:
            with open(caminho_imagem, "rb") as foto:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id, photo=foto, caption=texto_id, parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Erro ao enviar imagem: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=texto_id + "\n\n(Imagem ilustrativa indisponível no momento)",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Erro ao enviar imagem: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=texto_id + "\n\n(Imagem ilustrativa indisponível no momento)",
                parse_mode="HTML",
            )

        return ETAPA_REGULACAO

    return ConversationHandler.END


async def receber_sus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END
    import re as _re

    chat_id = update.effective_chat.id
    texto_bruto = update.message.text.strip()

    # Normaliza: mantém só dígitos (remove espaços, pontos, traços)
    numero_sus = _re.sub(r"\D", "", texto_bruto)

    if not numero_sus:
        await update.message.reply_text(
            "⚠️ Não consegui identificar nenhum dígito.\n\nDigite o número do Cartão SUS (apenas números):"
        )
        return ETAPA_SUS

    context.user_data["sus"] = numero_sus

    try:
        resposta = supabase.table("VigiaSaude_Teresina").select("*").eq("numero_sus", numero_sus).execute()
        registros = resposta.data

        if registros and len(registros) > 0:
            dados_antigos = registros[0]
            context.user_data["_dados_reuso_pendente"] = {
                "nome": dados_antigos.get("nome_paciente"),
                "celular": dados_antigos.get("celular"),
                "nascimento": dados_antigos.get("data_nascimento"),
                "cbo": dados_antigos.get("cbo"),
                "procedimento": dados_antigos.get("procedimento"),
            }

            nome = dados_antigos.get("nome_paciente") or "Não informado"
            celular = dados_antigos.get("celular") or "Não informado"
            nasc = dados_antigos.get("data_nascimento") or "Não informado"

            print("DEBUG: SUS encontrado! Aguardando confirmação.")

            teclado = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("✅ Usar esses dados", callback_data="reuso_sim")],
                    [InlineKeyboardButton("🔄 Digitar do zero", callback_data="reuso_nao")],
                ]
            )

            await update.message.reply_text(
                f"🔍 <b>Cartão do SUS já cadastrado!</b>\n\n"
                f"Encontramos os seguintes dados:\n"
                f"👤 <b>Nome:</b> {nome}\n"
                f"📱 <b>Celular:</b> {celular}\n"
                f"📅 <b>Nascimento:</b> {nasc}\n\n"
                f"Deseja usar esses dados?",
                parse_mode="HTML",
                reply_markup=teclado,
            )
            return ETAPA_CONFIRMAR_REUSO

    except Exception as e:
        print(f"ERRO no bloco do SUS: {e}")

    print("DEBUG: SUS não encontrado. Indo para ETAPA_REGULACAO.")

    # Envia a imagem de exemplo junto com o pedido do ID
    texto_id = (
        "Agora digite o <b>ID da Regulação</b> (8 dígitos):\n\n"
        "📌 <i>Confira no seu comprovante de agendamento, conforme o exemplo abaixo:</i>"
    )

    caminho_imagem = os.path.join(os.path.dirname(__file__), "comprovante_sus.jpg")
    try:
        with open(caminho_imagem, "rb") as foto:
            await update.message.reply_photo(photo=foto, caption=texto_id, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Erro ao enviar imagem no SUS: {e}")
        await update.message.reply_text(texto_id, parse_mode="HTML")

    return ETAPA_REGULACAO


async def callback_reuso_dados(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a escolha do usuário: reusar dados ou digitar do zero."""
    query = update.callback_query
    await query.answer()

    dados = context.user_data.get("_dados_reuso_pendente") or {}

    if query.data == "reuso_sim":
        context.user_data["nome"] = dados.get("nome")
        context.user_data["celular"] = dados.get("celular")
        context.user_data["nascimento"] = dados.get("nascimento")
        context.user_data["cbo"] = dados.get("cbo")
        context.user_data["procedimento"] = dados.get("procedimento")

        await query.edit_message_text(
            "✅ <b>Dados carregados com sucesso!</b>\n\nAgora digite apenas o <b>Número da Regulação</b>:",
            parse_mode="HTML",
        )
        return ETAPA_REGULACAO

    else:
        for campo in ("nome", "celular", "nascimento", "cbo", "procedimento"):
            context.user_data[campo] = None
        context.user_data.pop("_dados_reuso_pendente", None)

        await query.edit_message_text(
            "Ok! Vamos começar do zero.\n\n👤 Qual o <b>nome completo do paciente</b>?",
            parse_mode="HTML",
        )
        return ETAPA_NOME


async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END

    nome = update.message.text.strip()
    nome = nome.replace("<", "").replace(">", "").replace("&", "&amp;")[:80]
    context.user_data["nome"] = nome

    # Agora pede a Data de Nascimento em vez do celular
    await update.message.reply_text(
        "Agora, digite a <b>Data de Nascimento</b> do paciente (ex: DD/MM/AAAA):", parse_mode="HTML"
    )
    return ETAPA_NASCIMENTO


async def receber_celular(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END
    celular = formatar_celular(update.message.text.strip())
    context.user_data["celular"] = celular
    await update.message.reply_text(
        "Digite a <b>data de nascimento</b> do paciente (DD/MM/AAAA):",
        parse_mode="HTML",
    )
    return ETAPA_NASCIMENTO


async def receber_nascimento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END

    nascimento = formatar_data(update.message.text.strip())
    context.user_data["nascimento"] = nascimento

    texto_cbo = (
        "✅ <b>Data de nascimento registrada.</b>\n\n"
        "Agora informe a <b>Especialidade</b> da consulta/exame.\n"
        "<i>(ex: CARDIOLOGISTA, ORTOPEDISTA)</i>\n\n"
        "Se não souber, digite <code>0</code> para pular."
    )

    # Envia a mensagem pedindo o CBO (sem foto do comprovante, pois a foto era do ID)
    await update.message.reply_text(texto_cbo, parse_mode="HTML")

    return ETAPA_CBO  # <-- AQUI ESTAVA O ERRO! Agora vai para a Especialidade.


async def receber_regulacao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END

    num_reg = re.sub(r"\D", "", update.message.text)

    if not num_reg or len(num_reg) != 8:
        await update.message.reply_text(
            f"⚠️ <b>O ID da regulação deve ter 8 dígitos.</b>\n\nDigite novamente:",
            parse_mode="HTML",
        )
        return ETAPA_REGULACAO

    try:
        chat_id = str(update.effective_user.id)
        res_dup = (
            supabase.table("VigiaSaude_Teresina")
            .select("id")
            .eq("numero_reg", num_reg)
            .eq("chat_id", int(chat_id) if chat_id.isdigit() else chat_id)
            .execute()
        )
        if res_dup.data:
            await update.message.reply_text(f"⚠️ <b>Você já cadastrou a regulação {num_reg}!</b>", parse_mode="HTML")
            context.user_data.clear()
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Erro ao verificar duplicata: {e}")

    # Salva o ID
    context.user_data["numero_regulacao"] = num_reg

    # FLUXO LINEAR: SEMPRE pede o nome (a não ser que venha do botão de reuso)
    if context.user_data.get("nome"):
        await update.message.reply_text(
            "Agora, digite a <b>Data de Nascimento</b> do paciente (ex: DD/MM/AAAA):", parse_mode="HTML"
        )
        return ETAPA_NASCIMENTO
    else:
        await update.message.reply_text("Qual o nome completo do paciente?")
        return ETAPA_NOME


async def receber_cbo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END

    valor = update.message.text.strip()

    if valor == "0":
        context.user_data["cbo"] = ""
        await update.message.reply_text(
            "Agora informe o <b>Procedimento/Exame</b>.\n<i>(ex: CONSULTA, EXAME)</i>",
            parse_mode="HTML",
        )
        return ETAPA_PROCEDIMENTO

    cbo = update.message.text.strip()
    cbo = cbo.replace("<", "").replace(">", "").replace("&", "&amp;")[:80]
    cbo = cbo.replace("<", "").replace(">", "").replace("&", "&amp;")[:80]
    context.user_data["cbo"] = formatar_maiusculo(cbo) if cbo != "0" else ""

    await update.message.reply_text(
        f"✅ <b>Especialidade registrada:</b> {formatar_maiusculo(valor)}\n\n"
        "Agora informe a <b>descrição do Procedimento/Exame / Consulta</b>:\n"
        "<i>(ex: EXAME, CONSULTA)</i>",
        parse_mode="HTML",
    )
    return ETAPA_PROCEDIMENTO


async def receber_procedimento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END

    procedimento = formatar_maiusculo(update.message.text.strip())
    context.user_data["procedimento"] = procedimento

    # Em vez de salvar no banco, chama a tela de resumo
    return await mostrar_resumo(update, context)


from bot_seguranca import safe_callback

from bot_seguranca import safe_callback


@safe_callback
async def finalizar_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    # O query.answer() é obrigatório para parar de girar o botão no Telegram
    await query.answer()

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    dados = context.user_data

    if query.data == "cancelar_cadastro" or query.data == "resumo_cancelar":
        try:
            await query.message.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Cadastro cancelado pelo usuário.",
            reply_markup=TECLADO_MENU,
        )
        context.user_data.clear()
        context.user_data.pop("_em_fluxo_admin", None)
        return ConversationHandler.END

    dados_salvar = {
        "chat_id": user_id,
        "numero_sus": dados.get("sus"),
        "nome_paciente": dados.get("nome"),
        "data_nascimento": dados.get("nascimento"),
        "numero_reg": dados.get("numero_regulacao"),
        "cbo": dados.get("cbo"),
        "procedimento": dados.get("procedimento"),
    }

    # Tenta salvar
    sucesso = await salvar_regulacao(dados_salvar)

    if sucesso:
        try:
            # Atualiza o contador vitalício
            res_atual = (
                supabase.table("VigiaSaude_Teresina_autorizados")
                .select("cadastros_realizados")
                .eq("chat_id", user_id)
                .execute()
            )
            atual = res_atual.data[0].get("cadastros_realizados", 0) if res_atual.data else 0
            supabase.table("VigiaSaude_Teresina_autorizados").update({"cadastros_realizados": atual + 1}).eq(
                "chat_id", user_id
            ).execute()
        except Exception as e:
            print(f"Erro ao atualizar contador: {e}")

        try:
            await query.message.delete()
        except Exception:
            pass

        # ENVIA A MENSAGEM FINAL (Isso destrava o botão de vez)
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ <b>Regulação cadastrada com sucesso!</b>\n\nVocê receberá alertas quando houver mudanças.",
            parse_mode="HTML",
            reply_markup=TECLADO_MENU,
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ <b>Erro interno ao salvar.</b> Tente novamente mais tarde.",
            reply_markup=TECLADO_MENU,
        )

    context.user_data.clear()
    context.user_data.pop("_em_fluxo_admin", None)
    return ConversationHandler.END


async def mostrar_resumo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mostra a tela de resumo antes de salvar no banco."""
    query = update.callback_query
    if query:
        await query.answer()
        chat_id = query.message.chat_id
    else:
        chat_id = update.message.chat_id

    dados = context.user_data

    texto = (
        "📋 <b>RESUMO DO CADASTRO</b>\n\n"
        f"👤 <b>Paciente:</b> {dados.get('nome', 'Não informado')}\n"
        f"🩺 <b>Especialidade:</b> {dados.get('cbo', 'Não informada')}\n"
        f"📋 <b>Procedimento:</b> {dados.get('procedimento', 'Não informado')}\n"
        f"🆔 <b>Regulação:</b> <code>{dados.get('numero_regulacao', 'S/N')}</code>\n"
        f"📅 <b>Nascimento:</b> {dados.get('nascimento', 'Não informada')}\n"
        f"🏦 <b>Cartão SUS:</b> <code>{dados.get('sus', 'Não informado')}</code>\n\n"
        "<i>Os dados estão corretos?</i>"
    )

    teclado = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Confirmar e Salvar", callback_data="resumo_confirmar")],
            [InlineKeyboardButton("✏️ Corrigir Dados", callback_data="resumo_corrigir")],
            [InlineKeyboardButton("❌ Cancelar Cadastro", callback_data="resumo_cancelar")],
        ]
    )

    await context.bot.send_message(chat_id=chat_id, text=texto, parse_mode="HTML", reply_markup=teclado)

    # Retorna um novo estado para aguardar o clique do usuário
    return ETAPA_RESUMO


async def processar_resumo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "resumo_confirmar":
        # Aqui chamamos a sua função antiga de salvar no banco (finalizar_cadastro)
        return await finalizar_cadastro(update, context)

    elif data == "resumo_cancelar":
        await query.edit_message_text(
            "❌ <b>Cadastro cancelado.</b>\n\nVolte ao menu para tentar novamente.", parse_mode="HTML"
        )
        context.user_data.clear()
        return ConversationHandler.END

    elif data == "resumo_corrigir":
        teclado = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🏦 Cartão SUS", callback_data="corrigir_sus"),
                    InlineKeyboardButton("🆔 ID Regulação", callback_data="corrigir_regulacao"),
                ],
                [
                    InlineKeyboardButton("Nome", callback_data="corrigir_nome"),
                    InlineKeyboardButton("Nascimento", callback_data="corrigir_nascimento"),
                ],
                [
                    InlineKeyboardButton("Especialidade", callback_data="corrigir_cbo"),
                    InlineKeyboardButton("Procedimento", callback_data="corrigir_procedimento"),
                ],
                [InlineKeyboardButton("⬅️ Voltar ao Resumo", callback_data="resumo_voltar")],
            ]
        )

        # O parse_mode="HTML" garante que o negrito funcione
        await query.edit_message_text("✏️ <b>O que você deseja corrigir?</b>", reply_markup=teclado, parse_mode="HTML")
        return ETAPA_RESUMO

    elif data == "resumo_voltar":
        return await mostrar_resumo(update, context)

    return ETAPA_RESUMO


async def iniciar_correcao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    campo = query.data.replace("corrigir_", "")  # Ex: sus, regulacao, nome, etc.
    context.user_data["_editando_campo"] = campo

    mensagens = {
        "sus": "Digite o novo <b>Cartão SUS</b> (15 dígitos):",
        "regulacao": "Digite o novo <b>ID da Regulação</b> (8 dígitos):",
        "nome": "Digite o novo <b>Nome</b> do paciente:",
        "nascimento": "Digite a nova <b>Data de Nascimento</b> (DD/MM/AAAA):",
        "cbo": "Digite a nova <b>Especialidade</b>:",
        "procedimento": "Digite o novo <b>Procedimento</b>:",
    }

    await query.edit_message_text(mensagens.get(campo, "Digite o novo valor:"), parse_mode="HTML")

    # Retorna um estado para aguardar a digitação do novo valor
    return ETAPA_CORRIGINDO


async def receber_correcao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    campo = context.user_data.get("_editando_campo")
    novo_valor = update.message.text.strip()

    # Tratamentos específicos
    if campo == "sus":
        novo_valor = re.sub(r"\D", "", novo_valor)
    elif campo == "nascimento":
        try:
            from datetime import datetime

            data_obj = datetime.strptime(novo_valor, "%d/%m/%Y")
            novo_valor = data_obj.strftime("%Y-%m-%d")
        except ValueError:
            await update.message.reply_text("⚠️ Data inválida. Digite no formato DD/MM/AAAA:")
            return ETAPA_CORRIGINDO
    elif campo in ["cbo", "procedimento", "nome"]:
        novo_valor = novo_valor.upper()

    # Salva o novo valor
    chaves = {
        "sus": "sus",
        "regulacao": "numero_regulacao",
        "nome": "nome",
        "nascimento": "nascimento",
        "cbo": "cbo",
        "procedimento": "procedimento",
    }

    context.user_data[chaves.get(campo, campo)] = novo_valor

    # Limpa a flag de edição
    context.user_data.pop("_editando_campo", None)

    # Volta para a tela de resumo com os dados atualizados
    return await mostrar_resumo(update, context)
