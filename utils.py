# utils.py
import re
from html import escape
from telegram import ReplyKeyboardMarkup

DISCLAIMER_TEXTO = (
    "⚠️ <b>Aviso Importante:</b> Esta é uma ferramenta particular e independente. "
    "Não possui qualquer vínculo oficial com a Fundação Municipal de Saúde (FMS) ou outros órgãos públicos municipais, estaduais ou federais."
)

# Estados das Conversações
CONSULTAR_ID = 1
SELECIONAR_REGULACAO = 10
SELECIONAR_CAMPO = 11
AGUARDAR_NOVO_VALOR = 12
SELECIONAR_REGULACAO_EXCLUIR = 20
CONFIRMAR_EXCLUSAO = 21
ETAPA_SUS = 30
ETAPA_NOME = 31
ETAPA_CELULAR = 32
ETAPA_NASCIMENTO = 33
ETAPA_REGULACAO = 34
ETAPA_CBO = 35
ETAPA_PROCEDIMENTO = 36
ETAPA_RESUMO = 38
ETAPA_CORRIGINDO = 39
ETAPA_LGPD = 37
ETAPA_CONFIRMAR_REUSO = 99
ETAPA_ESCOLHER_SUS = 100
# Broadcast (comunicação em massa)
BROADCAST_ESCOLHER_SEGMENTO = 50
BROADCAST_ENVIAR_CONTEUDO = 51
BROADCAST_CONFIRMAR_ENVIO = 52

# utils.py
from telegram import ReplyKeyboardMarkup

TECLADO_MENU = ReplyKeyboardMarkup(
    [
        ["/iniciar", "/cadastrar_nova"],
        ["/meus_cadastros"],
        ["/excluir", "/suporte"],
        ["/privacidade"],
    ],
    resize_keyboard=True,
)

TECLADO_CANCELAR = ReplyKeyboardMarkup([["🚫 Cancelar Operação"]], resize_keyboard=True)


# Formatadores e utilitários
def formatar_maiusculo(texto: str) -> str:
    """Converte o texto digitado para letras maiúsculas e remove espaços excedentes."""
    if not texto:
        return ""
    return str(texto).strip().upper()


# Formatadores e utilitários
def formatar_data(texto: str) -> str:
    nums = re.sub(r"\D", "", texto)
    if len(nums) == 8:
        dia, mes, ano = nums[:2], nums[2:4], nums[4:]
        return f"{ano}-{mes}-{dia}"
    elif "/" in texto:
        partes = texto.split("/")
        if len(partes) == 3 and len(partes[2]) == 4:
            return f"{partes[2]}-{partes[1].zfill(2)}-{partes[0].zfill(2)}"
    return texto


def formatar_celular(texto: str) -> str:
    nums = re.sub(r"\D", "", texto)
    if len(nums) == 11:
        ddd, d1, d2 = nums[:2], nums[2:7], nums[7:]
        return f"({ddd}) {d1}-{d2}"
    elif len(nums) == 10:
        ddd, d1, d2 = nums[:2], nums[2:6], nums[6:]
        return f"({ddd}) {d1}-{d2}"
    return texto


def mascarar_nome(nome: str) -> str:
    if not nome or str(nome).strip().upper() in ["N/A", "NONE", "", "NULO"]:
        return "N/A"
    partes = str(nome).strip().split()
    if len(partes) == 1:
        return f"{partes[0]}***"
    return f"{partes[0]} {partes[-1][0].upper()}***"


def _mascarar_sus(sus: str) -> str:
    if not sus or len(sus) < 15:
        return sus or "N/A"
    return f"{sus[:3]}****{sus[-4:]}"


def tratar_status_fms(status_fms: str) -> str:
    if not status_fms:
        return "PENDENTE"
    status_clean = str(status_fms).strip().upper()
    termos_invalidos = [
        "",
        "N/A",
        "NONE",
        "SEM STATUS",
        "NÃO INFORMADO",
        "INFORMADA NO PORTAL",
        "NÃO INFORMADA NO PORTAL",
        "INDEFINIDO",
    ]
    for termo in termos_invalidos:
        if termo in status_clean:
            return "PENDENTE"
    return status_clean


def _extrair_id_e_nome(reg: dict):
    num_id = (
        reg.get("numero_reg")
        or reg.get("num_reg")
        or reg.get("numero_regulacao")
        or reg.get("numero_solicitacao")
        or reg.get("id_regulacao")
        or reg.get("id")
    )
    nome = reg.get("nome_paciente") or reg.get("paciente") or reg.get("nome") or "Paciente não informado"
    cbo = reg.get("cbo") or reg.get("especialidade") or ""
    return str(num_id), str(nome), str(cbo)


def _montar_msg_html(numero_reg: str, resultado: dict, reg_db: dict = None) -> str:
    resultado = resultado or {}
    reg_db = reg_db or {}
    cbo = resultado.get("cbo") or reg_db.get("cbo") or "N/A"
    procedimento = resultado.get("procedimento") or reg_db.get("procedimento") or "N/A"
    paciente_raw = resultado.get("paciente") or reg_db.get("nome_paciente") or "N/A"
    sus_raw = resultado.get("cartao_sus") or reg_db.get("numero_sus") or "N/A"

    situacao = resultado.get("situacao") or resultado.get("status") or reg_db.get("status") or "PENDENTE"

    # Captura a posição da fila e a previsão de atendimento
    posicao = resultado.get("posicao_fila") or reg_db.get("posicao_fila") or "Não informada"
    previsao = resultado.get("previsao_atendimento") or reg_db.get("previsao_atendimento") or "Não informada"

    msg = (
        f"📋 <b>STATUS DA REGULAÇÃO</b>\n\n"
        f"<b>ID Regulação:</b> <code>{escape(str(numero_reg))}</code>\n"
        f"<b>Cartão SUS:</b> <code>{escape(str(_mascarar_sus(sus_raw)))}</code>\n"
        f"<b>Paciente:</b> {escape(str(mascarar_nome(paciente_raw)))}\n"
        f"<b>Especialidade:</b> {escape(str(cbo))}\n"
        f"<b>Procedimento:</b> {escape(str(procedimento))}\n"
        f"<b>Status:</b> <b>{escape(str(situacao))}</b>\n"
        f"<b>Posição:</b> {escape(str(posicao))}\n"
        f"<b>Previsão:</b> {escape(str(previsao))}\n"
    )

    data_consulta = resultado.get("data_consulta")
    estabelecimento = resultado.get("estabelecimento")
    autorizacao = resultado.get("autorizacao")
    endereco = resultado.get("endereco")
    telefone = resultado.get("telefone")
    alerta = resultado.get("alerta_fms")

    if data_consulta or estabelecimento or str(situacao).upper() == "MARCADA":
        msg += f"\n📅 <b>DADOS DO AGENDAMENTO</b>\n"
        if data_consulta:
            msg += f"• <b>Data/Hora:</b> {escape(str(data_consulta))}\n"
        if autorizacao:
            msg += f"• <b>Autorização:</b> <code>{escape(str(autorizacao))}</code>\n"
        msg += f"\n🏥 <b>LOCAL DO ATENDIMENTO</b>\n"
        if estabelecimento:
            msg += f"• <b>Local:</b> {escape(str(estabelecimento))}\n"
        if endereco:
            msg += f"• <b>Endereço:</b> {escape(str(endereco))}\n"
        if telefone:
            msg += f"• <b>Telefone:</b> {escape(str(telefone))}\n"
        if alerta:
            msg += f"\n⚠️ <b>AVISO:</b> <i>{escape(str(alerta))}</i>\n"
    elif alerta:
        msg += f"\n⚠️ <b>AVISO:</b> <i>{escape(str(alerta))}</i>\n"

    msg += f"\n\n<i>ℹ️ Ferramenta particular independente sem vínculo com a FMS ou órgãos públicos.</i>"
    return msg


async def verificar_se_e_menu_e_executar(update, context) -> bool:
    if not update.message or not update.message.text:
        return False
    texto = update.message.text.strip()
    opcoes = [
        "📋 Verificar Todas",
        "🔍 Verificar Específico",
        "➕ Cadastrar Nova",
        "✏️ Corrigir ID",
        "🗑️ Excluir Regulação",
        "ℹ️ Ajuda",
        "🚫 Cancelar Operação",
    ]
    if texto in opcoes:
        context.user_data.clear()
        msg_resp = (
            "❌ Operação cancelada com sucesso." if "cancelar" in texto.lower() else "Saindo da operação atual..."
        )
        await update.message.reply_text(msg_resp, reply_markup=TECLADO_MENU)
        return True
    return False
