import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from database import supabase
from utils import TECLADO_MENU
from utils import (
    SELECIONAR_REGULACAO,
    SELECIONAR_CAMPO,
    AGUARDAR_NOVO_VALOR,
    SELECIONAR_REGULACAO_EXCLUIR,
    CONFIRMAR_EXCLUSAO,
    TECLADO_MENU,
)

logger = logging.getLogger(__name__)


def _mascarar_nome_custom(nome: str) -> str:
    if not nome or str(nome).lower() in ["none", "não informado", ""]:
        return "Não informado"
    partes = nome.strip().split()
    if len(partes) <= 1:
        return partes[0].capitalize()
    primeiro = partes[0].capitalize()
    iniciais = [f"{p[0].upper()}." for p in partes[1:]]
    return f"{primeiro} {' '.join(iniciais)}"


# --- FLUXO DE CORREÇÃO ---
async def iniciar_corrigir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user_id = update.effective_user.id
        res = supabase.table("VigiaSaude_Teresina").select("*").eq("chat_id", user_id).execute()
        regulacoes_brutas = res.data if res.data else []

        if not regulacoes_brutas:
            msg = "⚠️ Nenhuma regulação cadastrada para corrigir."
            if update.message:
                await update.message.reply_text(msg)
            elif update.callback_query:
                await update.callback_query.message.reply_text(msg)
            return ConversationHandler.END

        # 🛡️ Remove duplicatas com base no 'numero_reg' para a exibição
        vistos = set()
        regulacoes = []
        for reg in regulacoes_brutas:
            num_reg = reg.get("numero_reg")
            if num_reg not in vistos:
                vistos.add(num_reg)
                regulacoes.append(reg)

        teclado = []
        for reg in regulacoes:
            num_reg = reg.get("numero_reg")
            nome = reg.get("nome_paciente", "")
            rotulo = f"✏️ Reg: {num_reg} - {_mascarar_nome_custom(nome)}"
            teclado.append([InlineKeyboardButton(rotulo, callback_data=f"corr_reg_{num_reg}")])

        teclado.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_corr")])

        msg = "🔧 <b>Selecione qual regulação deseja corrigir:</b>"
        if update.message:
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                msg, reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML"
            )

        context.user_data["_fluxo_corrigir_ativo"] = True
        return SELECIONAR_REGULACAO
    except Exception as e:
        logger.error(f"Erro em iniciar_corrigir: {e}")
        context.user_data.pop("_fluxo_corrigir_ativo", None)
        return ConversationHandler.END


async def mostrar_resumo_regulacao(update_or_query, context, num_reg, chat_id=None):
    """
    Busca os dados atuais da regulação no Supabase e exibe o resumo para confirmação.
    """
    try:
        query = supabase.table("VigiaSaude_Teresina").select("*").eq("numero_reg", num_reg)
        if chat_id is not None:
            query = query.eq("chat_id", chat_id)
        response = query.execute()

        if response.data:
            reg = response.data[0]
            resumo = (
                f"📋 <b>Regulação:</b> <code>{num_reg}</code>\n"
                f"👤 <b>Paciente:</b> {reg.get('nome_paciente', 'Não informado')}\n"
                f"🩺 <b>Especialidade:</b> {reg.get('cbo', 'Não informado')}\n"
                f"📱 <b>Celular:</b> {reg.get('celular', 'Não informado')}\n"
                f"🏥 <b>Procedimento:</b> {reg.get('procedimento', 'Não informado')}\n\n"
                f"✅ <b>Alteração realizada com sucesso!</b>"
            )

            teclado = [
                [InlineKeyboardButton("✏️ Editar outro campo", callback_data=f"corr_reg_{num_reg}")],
                [InlineKeyboardButton("🏁 Finalizar", callback_data="finalizar_corr")],
            ]
            reply_markup = InlineKeyboardMarkup(teclado)

            if hasattr(update_or_query, "message") and update_or_query.message:
                await update_or_query.message.reply_text(resumo, reply_markup=reply_markup, parse_mode="HTML")
            elif hasattr(update_or_query, "edit_message_text"):
                await update_or_query.edit_message_text(resumo, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Erro ao buscar resumo da regulação: {e}")
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text("✅ Campo atualizado com sucesso!", reply_markup=TECLADO_MENU)


async def selecionar_regulacao_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    print(f"🔴 CALLBACK: {update.callback_query.data}", flush=True)
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "finalizar_corr":
        await query.edit_message_text("✅ Operação finalizada.")
        context.user_data.clear()
        return ConversationHandler.END

    if data.startswith("corr_reg_"):
        num_reg = data.replace("corr_reg_", "")
        context.user_data["edit_num_reg"] = num_reg

        # Busca os dados atuais (filtrado por chat_id)
        chat_id = update.effective_user.id
        dados = {}
        try:
            res = (
                supabase.table("VigiaSaude_Teresina")
                .select("*")
                .eq("numero_reg", num_reg)
                .eq("chat_id", chat_id)
                .execute()
            )
            if res.data:
                dados = res.data[0]
        except Exception as e:
            logger.error(f"Erro ao buscar dados da regulação: {e}")

        resumo_atual = (
            f"📋 <b>Regulação selecionada:</b> <code>{num_reg}</code>\n\n"
            f"👤 <b>Paciente:</b> {dados.get('nome_paciente', 'Não informado')}\n"
            f"🩺 <b>Especialidade:</b> {dados.get('cbo', 'Não informado')}\n"
            f"📱 <b>Celular:</b> {dados.get('celular', 'Não informado')}\n"
            f"🏥 <b>Procedimento:</b> {dados.get('procedimento', 'Não informado')}\n\n"
            f"✏️ <b>Escolha qual campo deseja alterar:</b>"
        )

        teclado = [
            [InlineKeyboardButton("🆔 ID da Regulação", callback_data="corr_campo_numero_reg")],
            [InlineKeyboardButton("👤 Nome do Paciente", callback_data="corr_campo_nome_paciente")],
            [InlineKeyboardButton("🩺 Especialidade / CBO", callback_data="corr_campo_cbo")],
            [InlineKeyboardButton("📱 Celular", callback_data="corr_campo_celular")],
            [InlineKeyboardButton("🩺 Procedimento", callback_data="corr_campo_procedimento")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_corr")],
        ]

        await query.edit_message_text(resumo_atual, reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML")
        return SELECIONAR_CAMPO

    return SELECIONAR_REGULACAO


async def selecionar_campo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancelar_corr":
        await query.edit_message_text("❌ Correção cancelada.")
        context.user_data.clear()
        return ConversationHandler.END

    if data.startswith("corr_campo_"):
        campo = data.replace("corr_campo_", "")
        context.user_data["edit_campo"] = campo

        # ⚠️ Aviso especial quando o campo é o número da regulação
        if campo in ("numero_reg", "numero_regulacao", "id_regulacao"):
            await query.edit_message_text(
                "⚠️ <b>ATENÇÃO — Verifique com muito cuidado!</b>\n\n"
                "Antes de digitar o novo ID, confirme:\n"
                "✅ O ID no seu <b>comprovante de agendamento</b>\n"
                "✅ Se os <b>8 dígitos</b> conferem <b>exatamente</b>\n"
                "✅ Se o número é da <b>sua</b> regulação\n\n"
                "❌ <b>Se você digitar o ID errado, o bot pode mostrar "
                "dados de outro paciente do SUS.</b>\n\n"
                "📌 <i>Exemplo real:</i>\n"
                "Cadastrar <code>12345678</code> em vez de <code>87654321</code> "
                "pode trazer um agendamento <b>completamente diferente</b>.\n\n"
                "💡 O ID correto tem <b>8 dígitos</b>. Em caso de dúvida, "
                "procure o comprovante de agendamento ou a unidade básica de saúde.\n\n"
                "<b>Digite o novo ID da regulação:</b>",
                parse_mode="HTML",
            )
            return AGUARDAR_NOVO_VALOR

        # Outros campos: mensagem padrão
        await query.edit_message_text(f"✍️ Digite o novo valor para o campo <b>{campo}</b>:", parse_mode="HTML")
        return AGUARDAR_NOVO_VALOR

    return SELECIONAR_CAMPO


async def salvar_novo_valor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    novo_valor = update.message.text.strip()
    num_reg = context.user_data.get("edit_num_reg")
    campo = context.user_data.get("edit_campo")
    chat_id = str(update.effective_user.id)

    # 1. Validação básica
    if not novo_valor:
        await update.message.reply_text(
            "⚠️ Você não digitou nada. Tente novamente:",
            reply_markup=TECLADO_MENU,
        )
        return ConversationHandler.END

    # 2. Validações específicas por campo
    if campo in ("numero_reg", "numero_regulacao", "id_regulacao"):
        # Remove tudo que não é dígito
        import re

        novo_valor_limpo = re.sub(r"\D", "", novo_valor)

        if len(novo_valor_limpo) != 8:
            await update.message.reply_text(
                f"⚠️ <b>O ID da regulação deve ter 8 dígitos.</b>\n\n"
                f"Você digitou <b>{len(novo_valor_limpo)}</b> dígito(s).\n\n"
                "📌 <i>Confira no seu comprovante de agendamento ou na "
                "unidade básica de saúde.</i>\n\n"
                "Tente novamente ou use /corrigir para recomeçar.",
                parse_mode="HTML",
                reply_markup=TECLADO_MENU,
            )
            context.user_data.clear()
            return ConversationHandler.END

        novo_valor = novo_valor_limpo

        # Verifica se o novo ID já existe para este usuário
        try:
            res_dup = (
                supabase.table("VigiaSaude_Teresina")
                .select("id")
                .eq("numero_reg", novo_valor)
                .eq("chat_id", int(chat_id) if chat_id.isdigit() else chat_id)
                .execute()
            )

            if res_dup.data:
                await update.message.reply_text(
                    f"⚠️ <b>Você já tem uma regulação com o ID {novo_valor}!</b>\n\n"
                    "Se você realmente precisa trocar, apague primeiro a regulação "
                    "duplicada com /excluir e cadastre novamente.\n\n"
                    "A correção foi cancelada.",
                    parse_mode="HTML",
                    reply_markup=TECLADO_MENU,
                )
                context.user_data.clear()
                return ConversationHandler.END
        except Exception as e:
            logger.error(f"Erro ao verificar duplicata: {e}")

    elif campo == "celular":
        # Valida tamanho mínimo de celular
        import re

        digitos = re.sub(r"\D", "", novo_valor)
        if len(digitos) < 10:
            await update.message.reply_text(
                "⚠️ <b>Número de celular inválido.</b>\n\nDigite com DDD (ex: 86999999999).",
                parse_mode="HTML",
                reply_markup=TECLADO_MENU,
            )
            context.user_data.clear()
            return ConversationHandler.END
        novo_valor = digitos

    # 3. Executa o UPDATE com filtro por chat_id (CRÍTICO)
    try:
        query = supabase.table("VigiaSaude_Teresina").update({campo: novo_valor}).eq("numero_reg", num_reg)

        # Se o chat_id for numérico, compara como int
        try:
            query = query.eq("chat_id", int(chat_id))
        except (ValueError, TypeError):
            query = query.eq("chat_id", chat_id)

        query.execute()

        # Se o campo alterado foi o ID da regulação, reseta o status
        if campo in ("numero_reg", "numero_regulacao", "id_regulacao"):
            try:
                query_reset = (
                    supabase.table("VigiaSaude_Teresina")
                    .update({"status_anterior_cidadao": None})
                    .eq("numero_reg", novo_valor)
                )
                try:
                    query_reset = query_reset.eq("chat_id", int(chat_id))
                except (ValueError, TypeError):
                    query_reset = query_reset.eq("chat_id", chat_id)
                query_reset.execute()
                logger.info(f"Status resetado para nova regulação {novo_valor}")
            except Exception as e:
                logger.warning(f"Erro ao resetar status: {e}")

            # Mostra mensagem especial informando que o ID mudou
            await update.message.reply_text(
                f"✅ <b>ID da regulação atualizado!</b>\n\n"
                f"• <b>ID anterior:</b> <code>{num_reg}</code>\n"
                f"• <b>Novo ID:</b> <code>{novo_valor}</code>\n\n"
                "💡 <i>O status desta regulação será atualizado automaticamente "
                "na próxima verificação (a cada 6 horas). Você também pode "
                "forçar agora com /verificar_especifico.</i>",
                parse_mode="HTML",
                reply_markup=TECLADO_MENU,
            )
        else:
            # Exibe o resumo normal para outros campos
            try:
                chat_id_int = int(chat_id)
            except (ValueError, TypeError):
                chat_id_int = chat_id
            await mostrar_resumo_regulacao(update, context, num_reg, chat_id_int)

    except Exception as e:
        logger.error(f"Erro ao salvar alteração no Supabase: {e}")
        await update.message.reply_text(
            "❌ Erro ao atualizar o dado no banco de dados.",
            reply_markup=TECLADO_MENU,
        )

    context.user_data.clear()
    return ConversationHandler.END


# --- FLUXO DE EXCLUSÃO ---
async def iniciar_excluir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user_id = update.effective_user.id
        res = supabase.table("VigiaSaude_Teresina").select("*").eq("chat_id", user_id).execute()
        regulacoes_brutas = res.data if res.data else []

        # Remove duplicatas com base no 'numero_reg' para a exibição
        vistos = set()
        regulacoes = []
        for reg in regulacoes_brutas:
            num_reg = reg.get("numero_reg")
            if num_reg not in vistos:
                vistos.add(num_reg)
                regulacoes.append(reg)

        teclado = []
        for reg in regulacoes:
            num_reg = reg.get("numero_reg")
            nome = reg.get("nome_paciente", "")
            rotulo = f"🗑️ Reg: {num_reg} - {_mascarar_nome_custom(nome)}"
            teclado.append([InlineKeyboardButton(rotulo, callback_data=f"excl_reg_{num_reg}")])

        teclado.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_excl")])

        msg = "⚠️ <b>Selecione qual regulação deseja excluir permanentemente:</b>"
        if update.message:
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                msg, reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML"
            )
        context.user_data["_fluxo_excluir_ativo"] = True
        return SELECIONAR_REGULACAO_EXCLUIR
    except Exception as e:
        logger.error(f"Erro em iniciar_excluir: {e}")
        context.user_data.pop("_fluxo_excluir_ativo", None)
        return ConversationHandler.END


async def selecionar_regulacao_excluir_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancelar_excl":
        await query.edit_message_text("❌ Exclusão cancelada.")
        context.user_data.clear()
        return ConversationHandler.END

    if data.startswith("excl_reg_"):
        num_reg = data.replace("excl_reg_", "")
        context.user_data["del_num_reg"] = num_reg

        teclado = [
            [InlineKeyboardButton("✅ Sim, quero excluir", callback_data="conf_excl_sim")],
            [InlineKeyboardButton("❌ Não, cancelar", callback_data="cancelar_excl")],
        ]

        await query.edit_message_text(
            f"⚠️ Tem certeza que deseja excluir a regulação <b>{num_reg}</b>?",
            reply_markup=InlineKeyboardMarkup(teclado),
            parse_mode="HTML",
        )
        return CONFIRMAR_EXCLUSAO

    return SELECIONAR_REGULACAO_EXCLUIR


async def confirmar_exclusao_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancelar_excl":
        await query.edit_message_text("❌ Exclusão cancelada.")
        context.user_data.clear()
        return ConversationHandler.END

    if data == "conf_excl_sim":
        num_reg = context.user_data.get("del_num_reg")
        user_id = update.effective_user.id
        try:
            supabase.table("VigiaSaude_Teresina").delete().eq("numero_reg", num_reg).eq("chat_id", user_id).execute()
            await query.edit_message_text(f"🗑️ Regulação <b>{num_reg}</b> excluída com sucesso.", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Erro ao excluir regulação no Supabase: {e}")
            await query.edit_message_text("❌ Erro ao excluir regulação do banco de dados.")

    context.user_data.clear()
    return ConversationHandler.END
