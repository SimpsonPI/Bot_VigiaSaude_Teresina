from datetime import timezone, timedelta
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Carrega o .env se existir localmente (no seu PC), mas ignora se não achar (no Railway)
load_dotenv()

# Tokens e Credenciais Principais isolados
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_TOKEN_SUPORTE = os.getenv("TELEGRAM_TOKEN_SUPORTE")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Validação segura que não quebra o deploy se as variáveis já estiverem no painel do Railway
if not TELEGRAM_BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    print("⚠️ ATENÇÃO: Alguma variável de ambiente principal está faltando!")

# ==================== IDs DE ADMINISTRAÇÃO ====================

# Pega o ID do chat admin (para notificações)
raw_admin_chat_id = os.getenv("ADMIN_CHAT_ID", "5444152614").strip()
ADMIN_CHAT_ID = int(raw_admin_chat_id) if raw_admin_chat_id.isdigit() else None

# Lista de IDs com permissão de Admin (pode ter vários separados por vírgula)
# Coloquei os dois IDs que apareceram no seu código para garantir o acesso
raw_admin_ids = os.getenv("ADMIN_IDS", "5242040324,5444152614").strip()
ADMIN_IDS = [int(x.strip()) for x in raw_admin_ids.split(",") if x.strip().isdigit()]


def is_admin(user_id: int) -> bool:
    """Verifica se o usuário é administrador."""
    return user_id in ADMIN_IDS


# ==================== CONFIGURAÇÕES DE API E SERVIDOR ====================

SCRAPER_KEY = os.getenv("SCRAPER_KEY")
PORT = int(os.getenv("PORT", 10000))

# URL Base do Formulário WebApp no GitHub Pages
URL_FORMULARIO_PAGES = "https://simpsonpi.github.io/alerta-sus-bot/"

# ==================== CONTATOS E CANAIS OFICIAIS DO ALERTASUS ====================
EMAIL_SUPORTE = "suportevigiasaude@gmail.com"
BOT_SUPORTE_USERNAME = "@central_vigiasaude_bot"
BOT_SUPORTE_LINK = "https://t.me/central_vigiasaude_bot"

# ==================== VALIDAÇÃO DAS VARIÁVEIS OBRIGATÓRIAS ====================

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("⚠️ ERRO CRÍTICO: Variáveis SUPABASE_URL ou SUPABASE_KEY não configuradas no arquivo .env!")

# ==================== CLIENTE SUPABASE ====================

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==================== CONFIGURAÇÕES GLOBAIS ====================

FUSO_HORARIO = timezone(timedelta(hours=-3))
URL_BUSCA_FMS = "https://agendamentos.sus.fms.pmt.pi.gov.br/detail_scheduling/index"

BOT_APP = None
MAIN_LOOP = None

# ==================== CONFIGURAÇÕES DO BOT DE SUPORTE ====================

# ID do canal de suporte no Telegram
CANAL_SUPORTE_ID = -1004479965268

# ==================== ESTADOS DO CONVERSATIONHANDLER ====================

MENU_PRINCIPAL = 0  # Menu inicial com FAQ e opções
AGUARDANDO_MENSAGEM = 1  # Aguardando mensagem do usuário
AGUARDANDO_RESPOSTA_ADMIN = 2  # Aguardando resposta do administrador
AGUARDANDO_FAQ = 3  # Navegando pelo FAQ

# ==================== MENSAGENS DO SISTEMA ====================

MSG_RESPOSTA_ENVIADA = "✅ Resposta enviada com sucesso para o usuário!"
MSG_ATENDIMENTO_ENCERRADO = "❌ Atendimento encerrado. Se precisar de algo, acesse o menu novamente!"
MSG_MODAL_RESPOSTA = "✍️ <b>Modo de Resposta Ativado</b> para o ID: <code>{user_id}</code>\n\nDigite a mensagem que deseja enviar para este usuário agora:"

MSG_BOAS_VINDAS = (
    "🤖 <b>Central de Atendimento ao Usuário VigiaSaude Teresina</b>\n\n"
    "É um prazer ter você aqui! Como posso ajudá-lo hoje?\n\n"
    "🔹 <b>Menu Principal:</b>\n"
    "• /ajuda - Perguntas Frequentes (FAQ)\n"
    "• /suporte - Falar com a equipe de suporte\n"
    "• /privacidade - Política de privacidade\n\n"
    f"📧 <b>E-mail Oficial:</b> {EMAIL_SUPORTE}\n"
    f"🤖 <b>Bot de Atendimento:</b> {BOT_SUPORTE_USERNAME}"
)

MSG_SUPORTE_INICIAL = (
    "🛠️ <b>Canais de Atendimento</b>\n\n"
    "Precisa de auxílio ou deseja reportar um problema?\n"
    f"• <b>E-mail:</b> <code>{EMAIL_SUPORTE}</code>\n"
    f"• <b>Telegram:</b> {BOT_SUPORTE_USERNAME}\n\n"
    "Nossa equipe responderá em horário comercial."
)

MSG_ATENDIMENTO_INICIADO = (
    "🎧 <b>Atendimento Personalizado VigiaSaude Teresina</b>\n\n"
    "Olá! Escreva abaixo a sua dúvida ou demanda para que nossa equipe receba por aqui:\n\n"
    "✏️ <i>Digite sua mensagem agora...</i>"
)

RODAPE_ALERTAS = f"\n\n━━━━━━━━━━━━━━━━━━━━\n📧 E-mail: {EMAIL_SUPORTE}\n🤖 Atendimento: {BOT_SUPORTE_LINK}"

# ==================== CONFIGURAÇÕES DE SEGURANÇA ====================

TIMEOUT_ATENDIMENTO = 3600  # 1 hora
MAX_TENTATIVAS_ENVIO = 3

# ==================== CONFIGURAÇÕES DO BANCO DE DADOS ====================

TABELA_USUARIOS = "usuarios"
TABELA_REGULACOES = "regulacoes"
TABELA_CHAMADOS = "chamados_suporte"
TABELA_HISTORICO = "historico_atendimento"

# ==================== FUNÇÕES AUXILIARES ====================


# ==================== IDs DE ADMINISTRAÇÃO ====================

# Define o seu ID como admin fixo (o ID que você me passou)
ADMIN_CHAT_ID = 5242040324
ADMIN_IDS = [5242040324]


def is_admin(user_id: int) -> bool:
    """Verifica se um usuário é administrador."""
    return user_id in ADMIN_IDS or user_id == ADMIN_CHAT_ID


def get_fuso_horario():
    """Retorna o fuso horário configurado."""
    return FUSO_HORARIO


def get_supabase_client() -> Client:
    """Retorna o cliente Supabase configurado."""
    return supabase


# ==================== VALIDAÇÃO ADICIONAL ====================

if not TELEGRAM_BOT_TOKEN:
    print("⚠️ AVISO: TELEGRAM_BOT_TOKEN não configurado. O bot principal pode não funcionar.")

if CANAL_SUPORTE_ID >= 0:
    print(
        "⚠️ AVISO: CANAL_SUPORTE_ID parece ser um ID de grupo positivo. Certifique-se de que é um ID de canal/chat válido."
    )

# ==================== EXPORTAÇÕES ====================

__all__ = [
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_TOKEN_SUPORTE",
    "ADMIN_CHAT_ID",
    "ADMIN_IDS",
    "SCRAPER_KEY",
    "PORT",
    "URL_FORMULARIO_PAGES",
    "EMAIL_SUPORTE",
    "BOT_SUPORTE_USERNAME",
    "BOT_SUPORTE_LINK",
    "RODAPE_ALERTAS",
    "supabase",
    "FUSO_HORARIO",
    "URL_BUSCA_FMS",
    "BOT_APP",
    "MAIN_LOOP",
    "CANAL_SUPORTE_ID",
    "MENU_PRINCIPAL",
    "AGUARDANDO_MENSAGEM",
    "AGUARDANDO_RESPOSTA_ADMIN",
    "AGUARDANDO_FAQ",
    "MSG_RESPOSTA_ENVIADA",
    "MSG_ATENDIMENTO_ENCERRADO",
    "MSG_MODAL_RESPOSTA",
    "MSG_BOAS_VINDAS",
    "MSG_SUPORTE_INICIAL",
    "MSG_ATENDIMENTO_INICIADO",
    "TIMEOUT_ATENDIMENTO",
    "MAX_TENTATIVAS_ENVIO",
    "TABELA_USUARIOS",
    "TABELA_REGULACOES",
    "TABELA_CHAMADOS",
    "TABELA_HISTORICO",
    "is_admin",
    "get_fuso_horario",
    "get_supabase_client",
]
