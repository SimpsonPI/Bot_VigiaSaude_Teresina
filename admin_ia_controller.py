import os
import json
import logging
import httpx
from telegram import Update
from telegram.ext import ContextTypes
from database import supabase
from datetime import datetime, timedelta

# Importa o storage das enquetes locais
try:
    from enquetes_storage import listar_enquetes, calcular_resultado

    ENQUETES_OK = True
except ImportError:
    ENQUETES_OK = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ enquetes_storage não encontrado. Contexto de enquetes desativado.")

ADMIN_ID = int(os.getenv("ADMIN_ID") or os.getenv("ADMIN_CHAT_ID") or "0")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
NOME_ADMIN = os.getenv("NOME_ADMIN", "Sr. Lincoln")

logger = logging.getLogger(__name__)

GITHUB_BASE_URL = "https://raw.githubusercontent.com/SimpsonPI/central_alertasus_2.5/main/"

TABELAS_PERMITIDAS = [
    "assinaturas",
    "VigiaSaude_Teresina",
    "pagamentos_pix",
    "lgpd_consentimentos",
]

SAUDACOES = [
    "olá",
    "oi",
    "bom dia",
    "boa tarde",
    "boa noite",
    "tudo bem",
    "hello",
    "hey",
    "e aí",
    "como vai",
    "opa",
    "salve",
]

PALAVRAS_CHAVE = [
    "resumo",
    "estatísticas",
    "quantos",
    "dados da tabela",
    "ler arquivo",
    "verificar regulação",
    "minha regulação",
    "total",
    "listar",
    "relatório",
    "vencimento",
    "pagamentos",
    "usuários ativos",
    "inativos",
    "status",
    "consulta",
    "plano",
    "assinatura",
    "bloqueado",
    "pendente",
    "pix",
    "custa",
    "enquete",
    "enquetes",
    "votação",
    "votos",
    "votar",  # ← NOVAS
]

PALAVRAS_NOVIDADES = [
    "novidades",
    "mudanças recentes",
    "o que mudou",
    "últimas",
    "recentes",
    "novos cadastros",
    "novas regulações",
    "atualizações hoje",
]


# ═══════════════════════════════════════════════════════════
# CONTEXTO DINÂMICO DO SISTEMA
# ═══════════════════════════════════════════════════════════


async def coletar_contexto_sistema() -> str:
    """
    Coleta um snapshot do estado atual do sistema para a IA.
    Inclui: enquetes, usuários, assinaturas, regulações, pagamentos, data/hora.
    """
    linhas = []
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    linhas.append(f"DATA/HORA ATUAL: {agora}")

    # ─── Enquetes ───
    if ENQUETES_OK:
        try:
            enquetes = listar_enquetes()
            ativas = [e for e in enquetes if e.get("ativa")]
            encerradas = [e for e in enquetes if not e.get("ativa")]

            linhas.append(f"\nENQUETES:")
            linhas.append(f"• Total: {len(enquetes)}")
            linhas.append(f"• Ativas: {len(ativas)}")
            linhas.append(f"• Encerradas: {len(encerradas)}")

            if ativas:
                linhas.append("• Detalhes das ativas:")
                for e in ativas[:5]:
                    r = calcular_resultado(e)
                    linhas.append(f'  - #{e["id"]}: "{e.get("pergunta", "")[:60]}" ({r["total"]} voto(s))')
            else:
                linhas.append("• Nenhuma enquete ativa no momento.")

            if encerradas:
                ult = encerradas[0]
                linhas.append(f'• Última encerrada: #{ult["id"]} — "{ult.get("pergunta", "")[:60]}"')
        except Exception as e:
            logger.error(f"Erro ao coletar enquetes: {e}")
            linhas.append("ENQUETES: erro ao carregar.")

    # ─── Usuários/assinaturas ───
    try:
        res = supabase.table("assinaturas").select("*", count="exact").execute()
        total_users = res.count if hasattr(res, "count") and res.count is not None else len(res.data or [])

        res_ativos = supabase.table("assinaturas").select("*", count="exact").eq("status", "ativo").execute()
        total_ativos = (
            res_ativos.count
            if hasattr(res_ativos, "count") and res_ativos.count is not None
            else len(res_ativos.data or [])
        )

        linhas.append(f"\nUSUÁRIOS:")
        linhas.append(f"• Total de assinaturas: {total_users}")
        linhas.append(f"• Assinaturas ativas: {total_ativos}")
    except Exception as e:
        logger.error(f"Erro ao coletar usuários: {e}")

    # ─── Regulações ───
    try:
        res = supabase.table("VigiaSaude_Teresina").select("*", count="exact").execute()
        total_reg = res.count if hasattr(res, "count") and res.count is not None else len(res.data or [])
        linhas.append(f"\nREGULAÇÕES:")
        linhas.append(f"• Total cadastradas: {total_reg}")
    except Exception as e:
        logger.error(f"Erro ao coletar regulações: {e}")

    # ─── Pagamentos pendentes ───
    try:
        res = supabase.table("pagamentos_pix").select("*", count="exact").eq("status", "pending").execute()
        total_pend = res.count if hasattr(res, "count") and res.count is not None else len(res.data or [])
        linhas.append(f"\nPAGAMENTOS:")
        linhas.append(f"• Pix pendentes: {total_pend}")
    except Exception as e:
        logger.error(f"Erro ao coletar pagamentos: {e}")

    return "\n".join(linhas)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


async def obter_conhecimento() -> str:
    """Busca o conteúdo dos arquivos de conhecimento no GitHub."""
    conhecimento = ""
    try:
        url = f"{GITHUB_BASE_URL}conhecimento.md"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                conhecimento = response.text[:3000]
    except Exception as e:
        logger.error(f"Erro ao ler arquivo de conhecimento: {e}")
    return conhecimento


async def chamar_groq(system_prompt: str, user_message: str) -> str:
    """Chama a API do Groq e retorna a resposta em texto."""
    if not GROQ_API_KEY:
        return "❌ GROQ_API_KEY não configurada."
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.2,
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Erro ao chamar Groq: {e}")
        return f"❌ Erro na chamada à IA: {str(e)}"


# ═══════════════════════════════════════════════════════════
# HANDLER PRINCIPAL
# ═══════════════════════════════════════════════════════════


async def executar_acao_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para mensagens do administrador (linguagem natural)."""
    if update.effective_user.id != ADMIN_ID:
        return
    if not update.message or not update.message.text:
        return

    print(
        f"🔵 DEBUG IA ADMIN: chamada. _em_fluxo_admin={context.user_data.get('_em_fluxo_admin')}",
        flush=True,
    )

    em_fluxo = (
        context.user_data.get("_em_fluxo_admin")
        or context.user_data.get("_fluxo_corrigir_ativo")
        or context.user_data.get("_fluxo_excluir_ativo")
    )
    if em_fluxo:
        print(f"🔵 DEBUG IA ADMIN: bloqueada (em fluxo)", flush=True)
        return

    user_message = update.message.text

    user_message = update.message.text

    user_message = update.message.text
    user_text_lower = user_message.lower()

    # 1. Saudação simples
    if any(saudacao in user_text_lower for saudacao in SAUDACOES):
        prompt_conversa = (
            f"Você é o VS, assistente do {NOME_ADMIN}. "
            f"O usuário é {NOME_ADMIN}. "
            "Responda de forma amigável e curta. NUNCA invente informações."
        )
        resposta = await chamar_groq(prompt_conversa, user_message)
        try:
            await update.message.reply_text(resposta, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(resposta, parse_mode=None)
        return

    # 2. Novidades (últimas 24h)
    # 2. Se for pergunta sobre "novidades", consulta banco de dados
    if any(palavra in user_text_lower for palavra in PALAVRAS_NOVIDADES):
        try:
            from datetime import timezone

            agora = datetime.now(timezone.utc)
            inicio = agora - timedelta(days=1)

            novas_regulacoes = (
                supabase.table("VigiaSaude_Teresina")
                .select("*", count="exact")
                .gte("created_at", inicio.isoformat())
                .execute()
                .count
                or 0
            )
            novas_assinaturas = (
                supabase.table("assinaturas")
                .select("*", count="exact")
                .gte("created_at", inicio.isoformat())
                .execute()
                .count
                or 0
            )
            novos_pagamentos = (
                supabase.table("pagamentos_pix")
                .select("*", count="exact")
                .gte("created_at", inicio.isoformat())
                .execute()
                .count
                or 0
            )
            novos_chamados = (
                supabase.table("chamados_suporte")
                .select("*", count="exact")
                .gte("created_at", inicio.isoformat())
                .execute()
                .count
                or 0
            )

            total = novas_regulacoes + novas_assinaturas + novos_pagamentos + novos_chamados

            # Monta mensagem direta (sem IA) — evita resposta seca tipo "0"
            if total == 0:
                resposta_final = (
                    "🗒️ <b>Nenhuma novidade nas últimas 24h.</b>\n\n"
                    "Tudo tranquilo por aqui! Nenhuma nova regulação, "
                    "assinatura, pagamento ou chamado."
                )
            else:
                linhas = [f"📬 <b>Novidades das últimas 24h:</b>\n"]
                if novas_regulacoes > 0:
                    linhas.append(f"• 📋 <b>{novas_regulacoes}</b> nova(s) regulação(ões)")
                if novas_assinaturas > 0:
                    linhas.append(f"• 👥 <b>{novas_assinaturas}</b> nova(s) assinatura(s)")
                if novos_pagamentos > 0:
                    linhas.append(f"• 💳 <b>{novos_pagamentos}</b> novo(s) pagamento(s)")
                if novos_chamados > 0:
                    linhas.append(f"• 🎫 <b>{novos_chamados}</b> novo(s) chamado(s)")
                resposta_final = "\n".join(linhas)

        except Exception as e:
            logger.error(f"Erro ao buscar novidades: {e}")
            resposta_final = "❌ Não consegui buscar as novidades."

        try:
            await update.message.reply_text(resposta_final, parse_mode="HTML")
        except Exception:
            await update.message.reply_text(resposta_final, parse_mode=None)
        return

    # 3. Conversa genérica (sem palavras-chave) — MAS agora com contexto do sistema
    if not any(palavra in user_text_lower for palavra in PALAVRAS_CHAVE):
        contexto_sistema = await coletar_contexto_sistema()
        prompt_conversa = (
            f"Você é o VS, assistente do {NOME_ADMIN}. "
            f"O usuário é {NOME_ADMIN} (administrador do sistema).\n\n"
            f"CONTEXTO ATUAL DO SISTEMA:\n{contexto_sistema}\n\n"
            "Use essas informações para responder perguntas sobre o sistema. "
            "Se o admin perguntar sobre enquetes, usuários, regulações, etc., use os dados acima. "
            "Responda de forma amigável e curta. NUNCA invente informações que não estão no contexto."
        )
        resposta = await chamar_groq(prompt_conversa, user_message)
        try:
            await update.message.reply_text(resposta, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(resposta, parse_mode=None)
        return

    # 4. Pedido administrativo → carrega conhecimento + contexto
    try:
        conhecimento = await obter_conhecimento()
    except Exception as e:
        logger.error(f"Erro ao obter conhecimento: {e}")
        conhecimento = ""

    if not conhecimento:
        conhecimento = (
            "O VigiaSaúde é um serviço independente que monitora regulações de saúde (consultas e exames) "
            "no SUS de Teresina-PI. Ele avisa o usuário quando há mudança no status da regulação. "
            "Planos: Degustação (7 dias grátis), Trimestral (R$ 9,99) e Semestral (R$ 14,99). "
            "Cadastro: Número do SUS, Nome, Celular, Data de nascimento, ID da Regulação, Especialidade e Procedimento."
        )

    contexto_sistema = await coletar_contexto_sistema()

    prompt_deteccao = (
        f"Você é o VS, assistente do {NOME_ADMIN}. Identifique a ação que o administrador deseja executar. "
        "Responda APENAS com um JSON válido: "
        '{"acao": "consultar" | "ler_arquivo" | "resumo", '
        '"tabela": "nome_da_tabela", '
        '"filtros": {"campo": "valor"}, '
        '"arquivo": "nome_do_arquivo"} '
        "Tabelas disponíveis: assinaturas, 'VigiaSaude_Teresina', pagamentos_pix, lgpd_consentimentos. "
        "Para perguntas sobre preços de planos, use a ação 'resumo' (a informação está no conhecimento). "
        'Se não souber, retorne {"acao": "resumo"}.'
    )

    resposta_ia = await chamar_groq(prompt_deteccao, user_message)

    try:
        data = json.loads(resposta_ia)
        acao = data.get("acao", "resumo")
        tabela = data.get("tabela", "")
        filtros = data.get("filtros", {})
        arquivo = data.get("arquivo", "")

        if tabela and tabela not in TABELAS_PERMITIDAS:
            tabela = "assinaturas"

        dados_brutos = ""

        if acao == "consultar":
            try:
                query = supabase.table(tabela).select("*")
                if filtros:
                    for campo, valor in filtros.items():
                        query = query.eq(campo, valor)
                res = query.limit(20).execute()
                dados_brutos = json.dumps(res.data, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Erro ao consultar tabela {tabela}: {e}")
                dados_brutos = f"Erro: {str(e)}"

        elif acao == "ler_arquivo":
            try:
                url = f"{GITHUB_BASE_URL}{arquivo}"
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        dados_brutos = response.text[:3000]
                    else:
                        dados_brutos = f"Arquivo não encontrado (status {response.status_code})."
            except Exception as e:
                logger.error(f"Erro ao ler arquivo: {e}")
                dados_brutos = f"Erro: {str(e)}"

        elif acao == "resumo":
            try:
                total_assinaturas = supabase.table("assinaturas").select("*", count="exact").execute().count
                total_regulacoes = supabase.table("VigiaSaude_Teresina").select("*", count="exact").execute().count
                total_pix_pendentes = (
                    supabase.table("pagamentos_pix").select("*", count="exact").eq("status", "pending").execute().count
                )
                dados_brutos = f"Total assinaturas: {total_assinaturas}. Total regulações: {total_regulacoes}. Pagamentos pendentes: {total_pix_pendentes}."
            except Exception as e:
                logger.error(f"Erro ao gerar resumo: {e}")
                dados_brutos = f"Erro: {str(e)}"

        prompt_formatacao = (
            f"Você é o VS, assistente do {NOME_ADMIN}. "
            f"O administrador pediu: '{user_message}'.\n\n"
            f"DADOS DO BANCO:\n{dados_brutos}\n\n"
            f"CONTEXTO ATUAL DO SISTEMA:\n{contexto_sistema}\n\n"
            f"CONHECIMENTO DO SISTEMA:\n{conhecimento}\n\n"
            "Responda de forma EXTREMAMENTE OBJETIVA. Apenas traga os dados solicitados. "
            "Não explique o que é o sistema. Não adicione textos extras. "
            "Se for uma lista, formate como lista curta. Se forem números, apenas mostre os números."
        )
        resposta_final = await chamar_groq(prompt_formatacao, "Formate a resposta acima.")

    except json.JSONDecodeError:
        prompt_formatacao = (
            f"Você é o VS, assistente do {NOME_ADMIN}. "
            f"O administrador pediu: '{user_message}'.\n\n"
            f"CONTEXTO ATUAL DO SISTEMA:\n{contexto_sistema}\n\n"
            f"CONHECIMENTO DO SISTEMA:\n{conhecimento}\n\n"
            "Responda de forma amigável e curta usando o contexto acima. NUNCA invente informações."
        )
        resposta_final = await chamar_groq(prompt_formatacao, "Responda a pergunta.")

    try:
        await update.message.reply_text(resposta_final, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Erro ao enviar resposta com Markdown: {e}")
        await update.message.reply_text(resposta_final, parse_mode=None)
