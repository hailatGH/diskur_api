from django_tgbot.decorators import processor
from django_tgbot.state_manager import message_types, update_types, state_types
from django_tgbot.types.inlinekeyboardmarkup import InlineKeyboardMarkup
from django_tgbot.types.inlinekeyboardbutton import InlineKeyboardButton
from django_tgbot.types.update import Update
from .bot import state_manager
from .models import TelegramState
from .bot import TelegramBot


@processor(state_manager, from_states=state_types.All)
def telegram_opt_in(bot: TelegramBot, update: Update, state: TelegramState):
    message = update.get_message().get_text()

    chat_id = update.get_chat().get_id()
    dashed = chat_id[:3] + '-' + chat_id[3:6] + '-' + chat_id[6:]

    if message == '/start':
        bot.sendMessage(
            update.get_chat().get_id(),
            text='Link to your Moogter account using this code: ' + dashed,
            reply_markup=InlineKeyboardMarkup.a(
                inline_keyboard=[
                    [
                        InlineKeyboardButton.a('Authorize', 
                            url=f'https://moogter.com/authorize_tg?cid={chat_id}')
                    ]
                ]
            )
        )
