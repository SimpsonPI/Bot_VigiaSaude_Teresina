from telegram import Update
from telegram.ext import ContextTypes
from utils import TECLADO_MENU


async def comando_recursos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "✨ <b>Conheça os recursos do VigiaSaúde Teresina:</b>\n\n"
        "🔔 <b>Monitoramento Automático:</b> O bot vigia o portal da FMS a cada 6 horas e te avisa no celular quando algo mudar.\n\n"
        "⏰ <b>Lembretes de Consulta:</b> Você recebe avisos 7, 3 e 1 dia antes do seu procedimento para não perder a vaga.\n\n"
        "🔄 <b>Verificação Manual:</b> Precisa de uma resposta rápida? Use o botão de verificar para consultar o status na hora.\n\n"
        "📊 <b>Semáforo de Status:</b> Entenda rapidamente se sua consulta está Agendada (🟢), Em Fila (🟡), Vencida (🔵) ou Cancelada (🔴).\n\n"
        "📌 <b>Limite Gratuito:</b> Você pode monitorar até 3 regulações. Ao excluir uma, você libera espaço para cadastrar outra.\n\n"
        "💡 <i>O VigiaSaúde é um serviço independente e não substitui o portal oficial da FMS.</i>"
    )

    if update.callback_query:
        await update.callback_query.answer()
        chat_id = update.callback_query.message.chat_id
    else:
        chat_id = update.message.chat_id

    await context.bot.send_message(chat_id=chat_id, text=texto, parse_mode="HTML", reply_markup=TECLADO_MENU)
