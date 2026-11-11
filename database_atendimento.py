# database_atendimento.py
import logging
from datetime import datetime, timezone
from database import supabase

logger = logging.getLogger(__name__)

# ==========================================
# FUNÇÕES PARA FAQ AUTOMATIZADO
# ==========================================


async def buscar_faq_por_palavras_chave(texto_usuario: str) -> dict | None:
    """Busca no banco de dados uma resposta do FAQ baseada nas palavras-chave."""
    try:
        # Normaliza o texto do usuário
        texto_normalizado = texto_usuario.lower().strip()

        # Busca todas as FAQs ativas
        res = supabase.table("faq_perguntas").select("*").eq("ativo", True).execute()

        if not res.data:
            return None

        # Verifica qual FAQ melhor corresponde ao texto do usuário
        melhor_match = None
        melhor_pontuacao = 0

        for faq in res.data:
            pontuacao = 0
            palavras_chave = faq.get("palavras_chave", [])

            for palavra in palavras_chave:
                if palavra.lower() in texto_normalizado:
                    pontuacao += 1

            # Verifica também se a pergunta está contida no texto
            if faq.get("pergunta", "").lower() in texto_normalizado:
                pontuacao += 3

            if pontuacao > melhor_pontuacao:
                melhor_pontuacao = pontuacao
                melhor_match = faq

        if melhor_match and melhor_pontuacao > 0:
            return melhor_match

        return None

    except Exception as e:
        logger.error(f"Erro ao buscar FAQ: {e}")
        return None


# ==========================================
# FUNÇÕES PARA ATENDIMENTO HUMANIZADO
# ==========================================


async def registrar_chamado_suporte(chat_id: str, nome_usuario: str, mensagem: str) -> int | None:
    """Registra um novo chamado de suporte humanizado."""
    try:
        res = (
            supabase.table("chamados_suporte")
            .insert(
                {
                    "chat_id": str(chat_id),
                    "nome_usuario": nome_usuario,
                    "mensagem": mensagem,
                    "status": "aberto",
                    "prioridade": "normal",
                }
            )
            .execute()
        )

        if res.data:
            chamado_id = res.data[0]["id"]
            logger.info(f"Chamado {chamado_id} registrado para o chat {chat_id}")
            return chamado_id
        return None

    except Exception as e:
        logger.error(f"Erro ao registrar chamado: {e}")
        return None


async def adicionar_mensagem_fila(chamado_id: int, chat_id: str, mensagem: str, enviado_por: str = "usuario") -> bool:
    """Adiciona uma mensagem à fila do chamado."""
    try:
        supabase.table("mensagens_fila").insert(
            {
                "chamado_id": chamado_id,
                "chat_id": str(chat_id),
                "mensagem": mensagem,
                "enviado_por": enviado_por,
            }
        ).execute()

        return True

    except Exception as e:
        logger.error(f"Erro ao adicionar mensagem à fila: {e}")
        return False


async def listar_chamados_abertos() -> list:
    """Lista todos os chamados abertos para o administrador."""
    try:
        res = (
            supabase.table("chamados_suporte")
            .select("*")
            .in_("status", ["aberto", "em_andamento"])
            .order("created_at", desc=True)
            .execute()
        )
        return res.data if res.data else []

    except Exception as e:
        logger.error(f"Erro ao listar chamados abertos: {e}")
        return []


async def responder_chamado(chamado_id: int, resposta_admin: str, atendente_id: str) -> bool:
    """Registra a resposta do administrador e atualiza o chamado."""
    try:
        agora = datetime.now(timezone.utc).isoformat()

        supabase.table("chamados_suporte").update(
            {
                "status": "respondido",
                "resposta_admin": resposta_admin,
                "atendente_id": str(atendente_id),
                "respondido_em": agora,
            }
        ).eq("id", chamado_id).execute()

        return True

    except Exception as e:
        logger.error(f"Erro ao responder chamado: {e}")
        return False


async def registrar_historico(chat_id: str, tipo: str, mensagem: str, origem: str = "bot") -> bool:
    """Registra uma mensagem no histórico de atendimento."""
    try:
        supabase.table("historico_atendimento").insert(
            {
                "chat_id": str(chat_id),
                "tipo": tipo,
                "mensagem": mensagem,
                "origem": origem,
            }
        ).execute()

        return True

    except Exception as e:
        logger.error(f"Erro ao registrar histórico: {e}")
        return False


# ==========================================
# FUNÇÕES DE CONFIGURAÇÃO
# ==========================================


async def obter_configuracao(chave: str) -> str | None:
    """Obtém uma configuração do sistema."""
    try:
        res = supabase.table("configuracoes_atendimento").select("valor").eq("chave", chave).execute()

        if res.data:
            return res.data[0]["valor"]
        return None

    except Exception as e:
        logger.error(f"Erro ao obter configuração {chave}: {e}")
        return None


async def obter_email_suporte() -> str:
    """Obtém o email de suporte configurado."""
    email = await obter_configuracao("email_suporte")
    return email or "suportevigiasaude@gmail.com"


async def buscar_estatisticas_admin_periodo() -> dict:
    """Busca estatísticas com recorte temporal (hoje, 7 dias, totais) e por plano."""
    from datetime import datetime, timedelta, timezone

    agora = datetime.now(timezone.utc)
    hoje_inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    semana_inicio = agora - timedelta(days=7)

    stats = {
        "hoje_novos_cadastros": 0,
        "hoje_chamados_abertos": 0,
        "semana_novos_cadastros": 0,
        "semana_chamados_abertos": 0,
        "semana_regulacoes": 0,
        "total_usuarios": 0,
        "total_chamados_abertos": 0,
        "total_regulacoes": 0,
        "total_assinaturas_ativas": 0,
        "planos_ativos": {},
        "ultimos_chamados": [],
    }

    def parse_iso(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except Exception:
            return None

    def is_status_ativo(s):
        return str(s).lower() in ("ativo", "active", "ativa")

    # ---------- ASSINATURAS ----------
    try:
        res = supabase.table("assinaturas").select("chat_id, tipo_plano, status, created_at").execute()
        assinaturas = res.data if res.data else []

        chat_ids_unicos = set()
        planos_ativos = {}

        for a in assinaturas:
            chat_id = str(a.get("chat_id", ""))
            if chat_id:
                chat_ids_unicos.add(chat_id)

            if is_status_ativo(a.get("status")):
                tipo = str(a.get("tipo_plano", "desconhecido")).lower()
                planos_ativos[tipo] = planos_ativos.get(tipo, 0) + 1

                criado = parse_iso(a.get("created_at"))
                if criado:
                    if criado >= hoje_inicio:
                        stats["hoje_novos_cadastros"] += 1
                    if criado >= semana_inicio:
                        stats["semana_novos_cadastros"] += 1

        stats["total_usuarios"] = len(chat_ids_unicos)
        stats["planos_ativos"] = planos_ativos
        stats["total_assinaturas_ativas"] = sum(planos_ativos.values())
        logger.info(f"📊 Planos ativos: {planos_ativos}")
    except Exception as e:
        logger.error(f"❌ Erro nas assinaturas: {repr(e)}")

    # ---------- CHAMADOS ----------
    try:
        res = supabase.table("chamados_suporte").select("id, nome_usuario, status, created_at").execute()
        chamados = res.data if res.data else []

        for c in chamados:
            if str(c.get("status", "")).lower() in ("aberto", "em_andamento"):
                stats["total_chamados_abertos"] += 1
                criado = parse_iso(c.get("created_at"))
                if criado:
                    if criado >= hoje_inicio:
                        stats["hoje_chamados_abertos"] += 1
                    if criado >= semana_inicio:
                        stats["semana_chamados_abertos"] += 1

        try:
            stats["ultimos_chamados"] = sorted(
                chamados,
                key=lambda x: str(x.get("created_at", "")),
                reverse=True,
            )[:5]
        except Exception:
            stats["ultimos_chamados"] = chamados[:5]
    except Exception as e:
        logger.error(f"❌ Erro nos chamados: {repr(e)}")

    # ---------- REGULAÇÕES ----------
    try:
        res = supabase.table("VigiaSaude_Teresina").select("numero_reg, created_at").execute()
        regs = res.data if res.data else []
        stats["total_regulacoes"] = len(regs)
        for r in regs:
            criado = parse_iso(r.get("created_at"))
            if criado and criado >= semana_inicio:
                stats["semana_regulacoes"] += 1
    except Exception as e:
        logger.error(f"❌ Erro nas regulações: {repr(e)}")

    logger.info(f"📊 ESTATÍSTICAS FINAIS: {stats}")
    return stats
