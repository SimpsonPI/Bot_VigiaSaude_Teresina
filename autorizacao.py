# autorizacao.py
"""Controle de acesso privado do VigiaSaúde Cidadão."""

import logging
from database import supabase

logger = logging.getLogger(__name__)


def verificar_autorizado(chat_id: int) -> bool:
    """Retorna True se o chat_id está na whitelist e ativo."""
    try:
        res = (
            supabase.table("VigiaSaude_Teresina_autorizados").select("chat_id, ativo").eq("chat_id", chat_id).execute()
        )
        if not res.data:
            return False
        return bool(res.data[0].get("ativo"))
    except Exception as e:
        logger.error(f"Erro ao verificar autorização ({chat_id}): {e}")
        return False


def autorizar(chat_id: int, nome: str, admin_id: int) -> bool:
    """Adiciona ou reativa um chat_id na whitelist."""
    try:
        supabase.table("VigiaSaude_Teresina_autorizados").upsert(
            {
                "chat_id": chat_id,
                "nome": nome or None,
                "autorizado_por": admin_id,
                "ativo": True,
            },
            on_conflict="chat_id",
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Erro ao autorizar {chat_id}: {e}")
        return False


def desautorizar(chat_id: int) -> bool:
    """Marca como inativo (mantém histórico)."""
    try:
        supabase.table("VigiaSaude_Teresina_autorizados").update({"ativo": False}).eq("chat_id", chat_id).execute()
        return True
    except Exception as e:
        logger.error(f"Erro ao desautorizar {chat_id}: {e}")
        return False


def listar_autorizados() -> list:
    """Retorna lista de autorizados ativos."""
    try:
        res = (
            supabase.table("VigiaSaude_Teresina_autorizados")
            .select("*")
            .eq("ativo", True)
            .order("autorizado_em", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.error(f"Erro ao listar autorizados: {e}")
        return []
