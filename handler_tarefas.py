import asyncio
from html import escape
import logging
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes
from database import (
    atualizar_campo_regulacao,
    buscar_todas_regulacoes_ativas,
    desativar_regulacoes_por_chat_id,
)

try:
    from scraper import consultar_status_fms
except ImportError:

    async def consultar_status_fms(num_reg):
        return None


logger = logging.getLogger(__name__)


async def executar_varredura_automatica(context: ContextTypes.DEFAULT_TYPE):
    """Executa a verificação periódica e notifica mudanças no Supabase."""
    logger.info("Iniciando varredura automática de rotina detalhada...")
    try:
        regulacoes = buscar_todas_regulacoes_ativas()
        if not regulacoes:
            logger.info("Nenhuma regulação ativa encontrada para monitorar.")
            return

        for reg in regulacoes:
            num_reg = reg.get("numero_reg") or reg.get("numero_regulacao") or reg.get("id_regulacao")
            chat_id = reg.get("chat_id") or reg.get("id_do_chat") or reg.get("telegram_id")
            status_antigo = reg.get("status_anterior_cidadao") or reg.get("status_atual") or "PENDENTE"

            if not num_reg or not chat_id:
                continue

            try:
                resultado_fms = await consultar_status_fms(str(num_reg))
            except Exception as err_sc:
                logger.error(f"Erro ao consultar FMS para regulação {num_reg}: {err_sc}")
                resultado_fms = None

            if isinstance(resultado_fms, dict) and resultado_fms.get("sucesso"):
                status_novo = resultado_fms.get("situacao") or "Informada no portal"
            else:
                status_novo = None

            if status_novo and str(status_novo).strip().upper() != str(status_antigo).strip().upper():
                try:
                    if asyncio.iscoroutinefunction(atualizar_campo_regulacao):
                        await atualizar_campo_regulacao(num_reg, "status_anterior", status_novo)
                    else:
                        atualizar_campo_regulacao(num_reg, "status_anterior_cidadao", status_novo)
                    logger.info(f"Status da regulação {num_reg} atualizado no Supabase para: {status_novo}")
                except Exception as err_upd:
                    logger.error(f"Erro ao atualizar status no Supabase: {err_upd}")

                nome_paciente = reg.get("nome_paciente") or "Não informado"
                cartao_sus = reg.get("numero_sus") or "Não informado"
                procedimento = reg.get("procedimento") or "Não informado"
                cbo = reg.get("cbo") or "Não informado"
                celular = reg.get("celular") or "Não informado"

                header_alerta = (
                    "🚨 <b>ALERTA DE ATUALIZAÇÃO NO SUS</b> 🚨\n\n"
                    f"<b>ID da Regulação:</b> <code>{escape(str(num_reg))}</code>\n"
                    f"📌 <b>Status Anterior:</b> {escape(str(status_antigo))}\n"
                    f"📌 <b>Novo Status:</b> <b>{escape(str(status_novo))}</b>\n"
                    "───────────────────────────\n"
                    "📋 <b>FICHA CADASTRAL (SUPABASE)</b>\n"
                    f"👤 <b>Paciente:</b> {escape(str(nome_paciente))}\n"
                    f"💳 <b>Cartão SUS:</b> {escape(str(cartao_sus))}\n"
                    f"🩺 <b>Procedimento:</b> {escape(str(procedimento))}\n"
                    f"🏷️ <b>Especialidade:</b> {escape(str(cbo))}\n"
                    f"📱 <b>Celular:</b> {escape(str(celular))}\n"
                    "───────────────────────────"
                )

                detalhes_fms = ""
                if isinstance(resultado_fms, dict) and resultado_fms.get("sucesso"):
                    detalhes_fms = "\n\n🏥 <b>SITUAÇÃO NO PORTAL FMS</b>\n"
                    alerta_fms = resultado_fms.get("alerta_fms") or resultado_fms.get("alerta")
                    if alerta_fms:
                        detalhes_fms += f"⚠️ <b>AVISO DO PORTAL:</b>\n<i>{escape(str(alerta_fms))}</i>\n\n"

                    if resultado_fms.get("data_consulta"):
                        detalhes_fms += f"• <b>Data/Hora:</b> {escape(str(resultado_fms.get('data_consulta')))}\n"
                        detalhes_fms += (
                            f"• <b>Local:</b> {escape(str(resultado_fms.get('estabelecimento') or 'Não informado'))}\n"
                        )
                        detalhes_fms += (
                            f"• <b>Endereço:</b> {escape(str(resultado_fms.get('endereco') or 'Não informado'))}\n"
                        )
                    else:
                        posicao = resultado_fms.get("posicao_fila") or "Não informada"
                        previsao = resultado_fms.get("previsao_atendimento") or "Não informada"
                        detalhes_fms += f"• <b>Posição na Fila:</b> {escape(str(posicao))}\n"
                        detalhes_fms += f"• <b>Previsão de Atendimento:</b> {escape(str(previsao))}\n"

                msg_completa = header_alerta + detalhes_fms

                try:
                    await context.bot.send_message(chat_id=chat_id, text=msg_completa, parse_mode="HTML")
                    logger.info(f"Notificação enviada para o chat_id {chat_id}.")
                except Forbidden:
                    logger.warning(f"🚫 O usuário {chat_id} bloqueou o bot. Desativando.")
                    desativar_regulacoes_por_chat_id(chat_id)
                except TelegramError as te:
                    logger.error(f"Erro Telegram ao enviar para {chat_id}: {te}")
                except Exception as e:
                    logger.error(f"Erro ao enviar para {chat_id}: {e}")

            await asyncio.sleep(0.1)

    except Exception as e:
        logger.error(f"Erro durante a varredura automática: {e}")


async def limpar_pagamentos_pendentes():
    """Remove pagamentos pendentes com mais de 24 horas."""
    try:
        from datetime import datetime, timedelta, timezone
        from database import supabase

        limite = datetime.now(timezone.utc) - timedelta(hours=24)

        supabase.table("pagamentos_pix").delete().eq("status", "pending").lt("created_at", limite.isoformat()).execute()
        logger.info("Pagamentos pendentes com mais de 24h foram limpos.")
    except Exception as e:
        logger.error(f"Erro ao limpar pagamentos: {e}")


from datetime import datetime
from database import supabase


async def verificar_alertas_consulta(context):
    """Varre o banco e envia alertas 7, 3 e 1 dia antes da consulta."""
    logger.info("⏰ Verificando alertas de consultas agendadas...")

    try:
        res = supabase.table("VigiaSaude_Teresina").select("*").execute()
        if not res.data:
            return

        hoje = datetime.now().date()

        for reg in res.data:
            chat_id = reg.get("chat_id")
            numero_reg = reg.get("numero_reg")
            nome = reg.get("nome_paciente", "Paciente")
            especialidade = reg.get("cbo", "Consulta")
            status = str(reg.get("status_anterior") or "").lower()
            data_str = reg.get("data_consulta")

            # Só envia se estiver "Agendada" ou "MARCADA" e tiver a data
            if ("agend" in status or "marcad" in status) and data_str:
                try:
                    # O scraper salva "DD/MM/YYYY - HH:MM", então cortamos no " - "
                    data_limpa = str(data_str).split(" - ")[0].strip()
                    data_consulta = datetime.strptime(data_limpa, "%d/%m/%Y").date()

                    dias_faltando = (data_consulta - hoje).days

                    # 🎯 VERIFICA SE FALTA 7, 3 OU 1 DIA
                    if dias_faltando in [7, 3, 1]:
                        # Trava para não enviar duplicado
                        campo_trava = f"alerta_{dias_faltando}d_enviado"
                        if reg.get(campo_trava) is True:
                            continue  # Já foi enviado, pula

                        emoji = "🟢" if dias_faltando == 7 else "🟡" if dias_faltando == 3 else "🔴"

                        texto = (
                            f"{emoji} <b>LEMBRETE DE CONSULTA!</b>\n\n"
                            f"Olá, sua consulta está chegando!\n\n"
                            f"👤 <b>Paciente:</b> {nome}\n"
                            f"🩺 <b>Especialidade:</b> {especialidade}\n"
                            f"🆔 <b>Regulação:</b> <code>{numero_reg}</code>\n"
                            f"📅 <b>Data da Consulta:</b> {data_limpa}\n"
                            f"⏳ <b>Faltam {dias_faltando} dia(s)!</b>\n\n"
                            f"<i>Não se esqueça de levar seus documentos e o Cartão SUS.</i>"
                        )

                        await context.bot.send_message(chat_id=chat_id, text=texto, parse_mode="HTML")

                        # Marca como enviado no banco
                        supabase.table("VigiaSaude_Teresina").update({campo_trava: True}).eq("chat_id", chat_id).eq(
                            "numero_reg", numero_reg
                        ).execute()
                        logger.info(f"✅ Alerta de {dias_faltando} dias enviado para {chat_id} (Reg: {numero_reg})")

                except ValueError:
                    pass  # Se a data estiver corrompida, ignora

    except Exception as e:
        logger.error(f"Erro na rotina de alertas de consulta: {e}")
