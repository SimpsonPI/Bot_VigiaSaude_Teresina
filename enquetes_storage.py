from dateutil.parser import isoparse
# enquetes_storage.py
"""
Armazenamento local de enquetes em JSON.
Os dados ficam no arquivo 'enquetes_data.json' na pasta do projeto.
"""

import json
import os
import logging
from datetime import datetime, timezone
from threading import Lock

logger = logging.getLogger(__name__)

ARQUIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enquetes_data.json")
_lock = Lock()


def _carregar() -> dict:
    """Carrega os dados do arquivo JSON. Se não existir, retorna estrutura vazia."""
    if not os.path.exists(ARQUIVO):
        return {"proximo_id": 1, "enquetes": {}}
    try:
        with open(ARQUIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erro ao carregar enquetes: {e}")
        return {"proximo_id": 1, "enquetes": {}}


def _salvar(dados: dict):
    """Salva os dados no arquivo JSON."""
    try:
        with open(ARQUIVO, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erro ao salvar enquetes: {e}")


def criar_enquete(pergunta: str, opcoes: list, criador_id: str) -> int:
    """Cria uma nova enquete e retorna o ID."""
    with _lock:
        dados = _carregar()
        enquete_id = dados["proximo_id"]
        dados["proximo_id"] += 1

        dados["enquetes"][str(enquete_id)] = {
            "id": enquete_id,
            "pergunta": pergunta,
            "opcoes": opcoes,
            "criador_id": criador_id,
            "criada_em": datetime.now(timezone.utc).isoformat(),
            "ativa": True,
            "votos": {},  # {chat_id: {"nome": str, "opcao_idx": int, "votado_em": iso}}
        }

        _salvar(dados)
        return enquete_id


def obter_enquete(enquete_id: int) -> dict | None:
    """Retorna a enquete pelo ID, ou None se não existir."""
    dados = _carregar()
    return dados["enquetes"].get(str(enquete_id))


def registrar_voto(enquete_id: int, chat_id: str, nome: str, opcao_idx: int) -> tuple[bool, str]:
    """
    Registra um voto. Retorna (sucesso, mensagem).
    Se o usuário já votou, retorna (False, motivo).
    """
    with _lock:
        dados = _carregar()
        enq = dados["enquetes"].get(str(enquete_id))

        if not enq:
            return False, "Enquete não encontrada."
        if not enq.get("ativa"):
            return False, "Esta enquete já foi encerrada."
        if chat_id in enq["votos"]:
            return False, "Você já votou nesta enquete!"

        enq["votos"][chat_id] = {
            "nome": nome,
            "opcao_idx": opcao_idx,
            "votado_em": datetime.now(timezone.utc).isoformat(),
        }
        _salvar(dados)
        return True, "Voto registrado!"


def listar_enquetes() -> list:
    """Lista todas as enquetes ordenadas da mais recente para a mais antiga."""
    dados = _carregar()
    enqs = list(dados["enquetes"].values())
    enqs.sort(key=lambda x: x.get("criada_em", ""), reverse=True)
    return enqs


def encerrar_enquete(enquete_id: int) -> bool:
    """Encerra uma enquete (impede novos votos)."""
    with _lock:
        dados = _carregar()
        enq = dados["enquetes"].get(str(enquete_id))
        if not enq:
            return False
        enq["ativa"] = False
        _salvar(dados)
        return True


def reabrir_enquete(enquete_id: int) -> bool:
    """Reabre uma enquete encerrada."""
    with _lock:
        dados = _carregar()
        enq = dados["enquetes"].get(str(enquete_id))
        if not enq:
            return False
        enq["ativa"] = True
        _salvar(dados)
        return True


def apagar_enquete(enquete_id: int) -> bool:
    """Apaga uma enquete completamente (com todos os votos)."""
    with _lock:
        dados = _carregar()
        if str(enquete_id) in dados["enquetes"]:
            del dados["enquetes"][str(enquete_id)]
            _salvar(dados)
            return True
        return False


def apagar_todas() -> int:
    """Apaga todas as enquetes. Retorna quantas foram apagadas."""
    with _lock:
        dados = _carregar()
        qtd = len(dados["enquetes"])
        dados["enquetes"] = {}
        dados["proximo_id"] = 1
        _salvar(dados)
        return qtd


def calcular_resultado(enquete: dict) -> dict:
    """Calcula o resultado agregado de uma enquete."""
    opcoes = enquete.get("opcoes", [])
    votos = enquete.get("votos", {})
    total = len(votos)

    contagem = {i: 0 for i in range(len(opcoes))}
    for v in votos.values():
        idx = v.get("opcao_idx", -1)
        if idx in contagem:
            contagem[idx] += 1

    return {
        "total": total,
        "contagem": contagem,
        "opcoes": opcoes,
    }


def salvar_mensagem(enquete_id: int, chat_id: str, message_id: int):
    """Registra o message_id de cada destinatário para permitir edição posterior."""
    with _lock:
        dados = _carregar()
        enq = dados["enquetes"].get(str(enquete_id))
        if not enq:
            return
        enq.setdefault("mensagens", {})[str(chat_id)] = message_id
        _salvar(dados)


def obter_mensagens(enquete_id: int) -> dict:
    """Retorna o dicionário {chat_id: message_id} de uma enquete."""
    dados = _carregar()
    enq = dados["enquetes"].get(str(enquete_id))
    if not enq:
        return {}
    return enq.get("mensagens", {})


from datetime import datetime, timezone, timedelta


def definir_prazo(enquete_id: int, segundos: int | None):
    """Define o prazo de encerramento da enquete."""
    with _lock:
        dados = _carregar()
        enq = dados["enquetes"].get(str(enquete_id))
        if not enq:
            return False
        if segundos is None:
            enq["fecha_em"] = None
        else:
            fecha = datetime.now(timezone.utc) + timedelta(seconds=segundos)
            enq["fecha_em"] = fecha.isoformat()
        _salvar(dados)
        return True


def obter_enquetes_expiradas() -> list:
    """Retorna enquetes ativas cujo prazo já passou."""
    agora = datetime.now(timezone.utc)
    expiradas = []
    dados = _carregar()
    for enq in dados["enquetes"].values():
        if not enq.get("ativa"):
            continue
        fecha_str = enq.get("fecha_em")
        if not fecha_str:
            continue
        try:
            fecha = isoparse(fecha_str.replace("Z", "+00:00"))
            if agora >= fecha:
                expiradas.append(enq)
        except Exception:
            continue
    return expiradas


def tempo_restante(enquete: dict) -> str:
    """Retorna string legível do tempo restante (ex: '5 min', '2h 15min')."""
    fecha_str = enquete.get("fecha_em")
    if not fecha_str:
        return "sem prazo"
    try:
        fecha = isoparse(fecha_str.replace("Z", "+00:00"))
        restante = (fecha - datetime.now(timezone.utc)).total_seconds()
        if restante <= 0:
            return "expirada"
        horas = int(restante // 3600)
        minutos = int((restante % 3600) // 60)
        if horas > 0:
            return f"{horas}h {minutos}min"
        return f"{minutos}min"
    except Exception:
        return "?"


def limpar_mensagens(enquete_id: int):
    """Remove o registro de mensagens (usado após apagar do chat)."""
    with _lock:
        dados = _carregar()
        enq = dados["enquetes"].get(str(enquete_id))
        if enq:
            enq["mensagens"] = {}
            _salvar(dados)
