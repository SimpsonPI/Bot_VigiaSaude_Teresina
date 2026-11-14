import os
import re
import random
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from telegram.helpers import escape_markdown
from config import URL_BUSCA_FMS, SCRAPER_KEY


logger = logging.getLogger(__name__)

from datetime import datetime, timezone, timedelta

# Margem de segurança após o horário marcado antes de considerar "Vencida"
MARGEM_VENCIMENTO_HORAS = 3


def _status_corrigido(situacao: str | None, data_consulta: str | None) -> str | None:
    """
    Corrige o status com base na data.
    Se o portal diz 'Agendada' mas a data/hora já passou (com margem),
    retorna 'Vencida'.
    Formato esperado de data_consulta: 'DD/MM/YYYY - HH:MM'
    """
    if not situacao or not data_consulta:
        return situacao

    if str(situacao).strip().lower() != "agendada":
        return situacao

    try:
        partes = str(data_consulta).split(" - ")
        data_str = partes[0].strip()
        hora_str = partes[1].strip() if len(partes) > 1 else "23:59"

        dt_consulta = datetime.strptime(f"{data_str} {hora_str}", "%d/%m/%Y %H:%M")

        # Fuso Brasília (UTC-3)
        agora_br = (datetime.now(timezone.utc) - timedelta(hours=3)).replace(tzinfo=None)

        if dt_consulta + timedelta(hours=MARGEM_VENCIMENTO_HORAS) < agora_br:
            return "Vencida"
    except Exception as e:
        logger.warning(f"Falha ao corrigir status com data '{data_consulta}': {e}")

    return situacao


def _extrair_valor_campo_fms(soup: BeautifulSoup, rotulo: str) -> str | None:
    rotulo_normalizado = rotulo.strip().lower()
    for titulo in soup.find_all(["h4", "h5"]):
        if titulo.get_text(strip=True).lower() != rotulo_normalizado:
            continue
        paragrafo = titulo.find_next_sibling(["p", "div", "span"])
        if paragrafo:
            valor = paragrafo.get_text(strip=True)
            if valor:
                return valor
    return None


def _limpar_texto_alerta(alerta_bruto: str) -> str:
    """Remove duplicidades internas, prefixos colados e formata a mensagem do portal."""
    if not alerta_bruto:
        return ""

    texto = re.sub(r"situação\s*:?\s*\w*", "", alerta_bruto, flags=re.IGNORECASE).strip()
    texto = re.sub(r"\s+", " ", texto)

    frases = [f.strip() for f in texto.split(".") if f.strip()]
    frases_unicas = []
    for f in frases:
        if f.lower() not in [fu.lower() for fu in frases_unicas]:
            frases_unicas.append(f)

    return ". ".join(frases_unicas) + ("." if frases_unicas else "")


def _extrair_dados_html(soup: BeautifulSoup) -> dict:
    """Extrai e mapeia todos os campos da FMS com limpeza rigorosa de texto duplicado."""
    card = soup.find("div", class_="card-body") or soup

    # 1. Captura de Alertas, Avisos e Observações
    alertas = [
        re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        for a in card.find_all(
            "div",
            class_=re.compile(
                r"alert|bg-success|alert-success|alert-danger|alert-warning|mensagem-observacao|obs",
                re.I,
            ),
        )
    ]

    textos_observacao = []
    for elem in card.find_all(["p", "span", "div"]):
        txt = elem.get_text(strip=True)
        if any(
            termo in txt.upper()
            for termo in [
                "SOLICITAÇÃO CANCELADA",
                "COMPAREÇA",
                "UNIDADE BASICA",
                "UBS",
                "ESCLARECIMENTOS",
            ]
        ):
            textos_observacao.append(re.sub(r"\s+", " ", txt))

    todos_avisos = alertas + textos_observacao
    alerta_concatenado = " ".join(todos_avisos) if todos_avisos else ""
    alerta_texto = _limpar_texto_alerta(alerta_concatenado) or None

    # 2. Varredura de Títulos (Nova abordagem: busca pelo texto do título e pega o texto ao lado)
    campos_brutos = {}
    dados_mapeados = {
        "data_consulta": None,
        "autorizacao": None,
        "estabelecimento": None,
        "endereco": None,
        "telefone": None,
        "situacao": None,
        "posicao_fila": None,
        "previsao_atendimento": None,
    }

    # Procura por qualquer tag de título ou parágrafo que contenha os rótulos que queremos
    for elem in soup.find_all(["h4", "h5", "p", "span", "strong", "b"]):
        rotulo = elem.get_text(strip=True).lower()

        # Ignora textos muito longos (que não são rótulos)
        if len(rotulo) > 50:
            continue

        # Tenta pegar o valor no próximo elemento irmão, ou no pai, ou no próximo elemento da página
        valor_elem = elem.find_next_sibling(["p", "div", "span", "h4", "h5"]) or elem.find_next(["p", "div", "span"])

        if not valor_elem:
            continue

        valor = re.sub(r"\s+", " ", valor_elem.get_text(" ", strip=True)).strip()

        # Se o valor for vazio ou for o próprio título, tenta o próximo
        if not valor or valor.lower() == rotulo:
            continue

        # Mapeia os campos
        if "situação" in rotulo:
            dados_mapeados["situacao"] = valor
        elif "posição" in rotulo and "fila" in rotulo:
            dados_mapeados["posicao_fila"] = valor
        elif "previsão" in rotulo and "atendimento" in rotulo:
            dados_mapeados["previsao_atendimento"] = valor
        elif "data e hora" in rotulo:
            dados_mapeados["data_consulta"] = valor
        elif "autorização" in rotulo:
            dados_mapeados["autorizacao"] = valor
        elif "endereço" in rotulo:
            dados_mapeados["endereco"] = valor
        elif "estabelecimento" in rotulo:
            dados_mapeados["estabelecimento"] = valor
        elif "telefone" in rotulo:
            dados_mapeados["telefone"] = valor

        campos_brutos[elem.get_text(strip=True)] = valor

        # 3. Determinação da Situação (Ajustado para ler TUDO)
    situacao = dados_mapeados["situacao"] or campos_brutos.get("Situação") or _extrair_valor_campo_fms(soup, "Situação")

    if not situacao:
        if dados_mapeados["data_consulta"] or (alerta_texto and "MARCADO" in alerta_texto.upper()):
            situacao = "MARCADA"
        else:
            situacao = "Informada no portal"

    dados_mapeados["situacao"] = situacao

    # 🛑 AQUI: Tenta ler Posição e Previsão mesmo que o agendamento exista
    posicao = (
        dados_mapeados["posicao_fila"]
        or campos_brutos.get("Posição da Fila")
        or campos_brutos.get("Posição")
        or _extrair_valor_campo_fms(soup, "Posição da Fila")
        or "Não informada"
    )

    previsao = (
        dados_mapeados["previsao_atendimento"]
        or campos_brutos.get("Previsão de atendimento")
        or campos_brutos.get("Previsão")
        or _extrair_valor_campo_fms(soup, "Previsão de atendimento")
        or "Não informada"
    )

    dados_mapeados["posicao_fila"] = posicao
    dados_mapeados["previsao_atendimento"] = previsao

    # 🛑 ESTE BLOCO ESTAVA FALTANDO:
    return {
        "sucesso": True,
        "encontrado": True,
        "situacao": _status_corrigido(situacao, dados_mapeados["data_consulta"]),
        "posicao_fila": dados_mapeados["posicao_fila"],
        "previsao_atendimento": dados_mapeados["previsao_atendimento"],
        "data_consulta": dados_mapeados["data_consulta"],
        "autorizacao": dados_mapeados["autorizacao"],
        "estabelecimento": dados_mapeados["estabelecimento"],
        "endereco": dados_mapeados["endereco"],
        "telefone": dados_mapeados["telefone"],
        "alerta_fms": alerta_texto,
        "campos": campos_brutos,
        "status_resumido": f"Situação: {situacao}",
    }


def formatar_data_br(data_str: str | None) -> str:
    if not data_str:
        return "Não informada"
    data_limpa = str(data_str).split("T")[0].strip()
    if "-" in data_limpa:
        partes = data_limpa.split("-")
        if len(partes) == 3:
            return f"{partes[2]}/{partes[1]}/{partes[0]}"
    return data_limpa


def nome_paciente_exibicao(nome: str | None) -> str:
    if not nome or not nome.strip() or nome.strip() == "Aguardando consulta":
        return "Não informado"
    return nome.strip()


async def consultar_status_fms(numero_reg: str, max_tentativas: int = 2) -> dict:
    atraso = random.uniform(1.0, 2.0)
    await asyncio.sleep(atraso)

    url_fms_target = (
        f"https://agendamentos.sus.fms.pmt.pi.gov.br/detail_scheduling/index?utf8=%E2%9C%93&number_id={numero_reg}"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=45.0, headers=headers) as client:
            resposta = await client.get(url_fms_target)
            if resposta.status_code == 200 and "nenhum registro" not in resposta.text.lower():
                soup = BeautifulSoup(resposta.text, "html.parser")
                return _extrair_dados_html(soup)
    except Exception as e:
        logger.info(f"Acesso direto à FMS falhou ou bloqueou ({e}). Acionando ScraperAPI...")

    if not SCRAPER_KEY:
        return {
            "sucesso": False,
            "mensagem": "Erro de configuração na chave do ScraperAPI.",
        }

    scraper_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={url_fms_target}"

    for tentativa in range(1, max_tentativas + 1):
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
                resposta = await client.get(scraper_url)

                if resposta.status_code != 200:
                    if tentativa < max_tentativas:
                        await asyncio.sleep(2)
                        continue
                    return {
                        "sucesso": False,
                        "mensagem": f"Erro HTTP {resposta.status_code}",
                    }

                soup = BeautifulSoup(resposta.text, "html.parser")
                texto_pagina = soup.get_text().lower()

                if "nenhum registro" in texto_pagina or "não encontrado" in texto_pagina:
                    return {
                        "sucesso": False,
                        "mensagem": f"⚠️ A regulação *{numero_reg}* não foi encontrada no portal da FMS.",
                    }

                return _extrair_dados_html(soup)

        except Exception as e:
            logger.error(f"Erro na tentativa {tentativa} do ScraperAPI: {e}")
            if tentativa < max_tentativas:
                await asyncio.sleep(2)
            else:
                return {
                    "sucesso": False,
                    "mensagem": f"Erro de conexão com a FMS: {e}",
                }

    return {
        "sucesso": False,
        "mensagem": "Tempo limite de conexão excedido ao acessar a FMS.",
    }


async def consultar_status_sus(numero_reg: str) -> str | None:
    try:
        resultado = await consultar_status_fms(numero_reg)
        if isinstance(resultado, dict) and resultado.get("sucesso"):
            return resultado.get("situacao") or "Informada no portal"
        return None
    except Exception as e:
        logger.error(f"Erro na consulta simplificada de status SUS para {numero_reg}: {e}")
        return None


def montar_mensagem_regulacao(
    numero_reg: str,
    resultado: dict,
    nome_paciente: str | None = None,
    data_nascimento: str | None = None,
    email: str | None = None,
    titulo: str = "🏥 *SITUAÇÃO DA REGULAÇÃO*",
) -> str:
    nome_esc = escape_markdown(nome_paciente_exibicao(nome_paciente), version=1)
    numero_esc = escape_markdown(str(numero_reg), version=1)
    dt_esc = escape_markdown(formatar_data_br(data_nascimento), version=1)
    email_txt = email.strip() if email else "Não informado"
    email_esc = escape_markdown(email_txt, version=1)

    linhas = [
        titulo,
        "",
        f"👤 *Paciente:* *{nome_esc}*",
        f"🎂 *Data de Nascimento:* {dt_esc}",
        f"📧 *E-mail:* {email_esc}",
        f"🆔 *ID de Regulação:* `{numero_esc}`",
    ]

    if isinstance(resultado, dict):
        situacao = resultado.get("situacao") or "Informada no portal"

        # 🔄 Normaliza textos do FMS para algo mais claro ao usuário
        _sit_lower = str(situacao).strip().lower()
        if "informada" in _sit_lower:
            situacao = "Em fila"
        elif "agendada" in _sit_lower:
            situacao = "Agendada"
        elif "vencida" in _sit_lower or "expirada" in _sit_lower:
            situacao = "Vencida"
        elif "cancelada" in _sit_lower:
            situacao = "Cancelada"
        elif "reativar" in _sit_lower or "reativada" in _sit_lower:
            situacao = "Reativar"

        data_consulta = resultado.get("data_consulta")
        autorizacao = resultado.get("autorizacao")
        estabelecimento = resultado.get("estabelecimento")
        endereco = resultado.get("endereco")
        telefone = resultado.get("telefone")
        alerta = resultado.get("alerta_fms")
        posicao = resultado.get("posicao_fila") or "Não informada"
        previsao = resultado.get("previsao_atendimento") or "Não informada"

        linhas.append(f"📌 *Situação:* *{escape_markdown(str(situacao), version=1)}*")

        if data_consulta or estabelecimento:
            linhas.append("")
            linhas.append("📅 *DADOS DO AGENDAMENTO*")
            if data_consulta:
                linhas.append(f"• *Data/Hora:* {escape_markdown(str(data_consulta), version=1)}")
            if autorizacao:
                linhas.append(f"• *Autorização:* `{escape_markdown(str(autorizacao), version=1)}`")

            linhas.append("")
            linhas.append("🏥 *ESTABELECIMENTO DE SAÚDE*")
            if estabelecimento:
                linhas.append(f"• *Unidade:* {escape_markdown(str(estabelecimento), version=1)}")
            if endereco:
                linhas.append(f"• *Endereço:* {escape_markdown(str(endereco), version=1)}")
            if telefone:
                linhas.append(f"• *Telefone:* {escape_markdown(str(telefone), version=1)}")

            if alerta:
                linhas.append("")
                linhas.append(f"⚠️ *AVISO DO PORTAL:* _{escape_markdown(str(alerta), version=1)}_")
        else:
            linhas.append(f"• *Posição:* {escape_markdown(str(posicao), version=1)}")
            linhas.append(f"• *Previsão:* {escape_markdown(str(previsao), version=1)}")

            if alerta and alerta.strip():
                linhas.append("")
                linhas.append(f"⚠️ *MENSAGEM DO PORTAL:*\n_{escape_markdown(str(alerta.strip()), version=1)}_")

    return "\n".join(linhas)
