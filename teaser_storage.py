from dateutil.parser import isoparse
# teaser_storage.py
"""
Controla o envio de teasers e opt-out para usuários com plano expirado.
Armazena em um arquivo JSON local.
"""

import json
import os
import logging
from datetime import datetime, timezone
from threading import Lock

logger = logging.getLogger(__name__)

ARQUIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "teaser_data.json")
_lock = Lock()


def _carregar() -> dict:
    if not os.path.exists(ARQUIVO):
        return {"ultimos_envios": {}, "optouts": []}
    try:
        with open(ARQUIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erro ao carregar teaser_data: {e}")
        return {"ultimos_envios": {}, "optouts": []}


def _salvar(dados: dict):
    try:
        with open(ARQUIVO, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erro ao salvar teaser_data: {e}")


def pode_enviar_teaser(chat_id: str) -> bool:
    """Retorna True se o usuário pode receber teaser (não optou out e passou 24h)."""
    dados = _carregar()
    cid = str(chat_id)

    if cid in dados.get("optouts", []):
        return False

    ultimo = dados.get("ultimos_envios", {}).get(cid)
    if not ultimo:
        return True

    try:
        dt_ultimo = isoparse(ultimo.replace("Z", "+00:00"))
        segundos = (datetime.now(timezone.utc) - dt_ultimo).total_seconds()
        return segundos >= 24 * 3600  # 24h
    except Exception:
        return True


def registrar_envio_teaser(chat_id: str):
    with _lock:
        dados = _carregar()
        dados.setdefault("ultimos_envios", {})[str(chat_id)] = datetime.now(timezone.utc).isoformat()
        _salvar(dados)


def ativar_optout(chat_id: str):
    with _lock:
        dados = _carregar()
        optouts = dados.setdefault("optouts", [])
        cid = str(chat_id)
        if cid not in optouts:
            optouts.append(cid)
        _salvar(dados)


def desativar_optout(chat_id: str):
    with _lock:
        dados = _carregar()
        optouts = dados.get("optouts", [])
        cid = str(chat_id)
        if cid in optouts:
            optouts.remove(cid)
        _salvar(dados)


def esta_em_optout(chat_id: str) -> bool:
    dados = _carregar()
    return str(chat_id) in dados.get("optouts", [])
