#!/usr/bin/python3

import logging
import time
from datetime import datetime, timezone
from typing import List, Union

import telegram
from retry import retry
from telegram.error import BadRequest, RetryAfter, TimedOut


class TelegramNotifier:

    def __init__(self, token: str, chat_id_list: List[str], logger_name: str):
        assert token
        assert chat_id_list
        self.bot = telegram.Bot(token=token)
        self.chat_id_list = chat_id_list
        self.logger = logging.getLogger('{}'.format(logger_name))
        self.logger.info('Init telegram notifier succeed: {}'.format(str(chat_id_list)))

    @retry((RetryAfter, TimedOut), delay=5)
    def _send_message_to_single_chat(self, chat_id: str, message: str,
                                     photo_url_list: Union[List[str], None],
                                     video_url_list: Union[List[str], None], disable_preview: bool):
        if video_url_list:
            self.bot.send_video(chat_id=chat_id,
                                video=video_url_list[0],
                                caption=message,
                                timeout=60)
        elif photo_url_list:
            if len(photo_url_list) == 1:
                self.bot.send_photo(chat_id=chat_id,
                                    photo=photo_url_list[0],
                                    caption=message,
                                    timeout=60)
            else:
                media_group = [telegram.InputMediaPhoto(media=photo_url_list[0], caption=message)]
                for photo_url in photo_url_list[1:10]:
                    media_group.append(telegram.InputMediaPhoto(media=photo_url))
                self.bot.send_media_group(chat_id=chat_id, media=media_group, timeout=60)
        else:
            self.bot.send_message(chat_id=chat_id,
                                  text=message,
                                  disable_web_page_preview=disable_preview,
                                  timeout=60)

    def send_message(self,
                     message: str,
                     photo_url_list: Union[List[str], None] = None,
                     video_url_list: Union[List[str], None] = None,
                     disable_preview: bool = True):
        for chat_id in self.chat_id_list:
            try:
                self._send_message_to_single_chat(chat_id, message, photo_url_list, video_url_list,
                                                  disable_preview)
            except BadRequest as e:
                # Telegram cannot send some photos/videos for unknown reasons.
                self.logger.error('{}, trying to send message without media.'.format(e))
                self._send_message_to_single_chat(chat_id, message, None, None, disable_preview)

    @retry((RetryAfter, TimedOut), delay=5)
    def _get_updates(self, offset=None) -> List[telegram.Update]:
        return self.bot.get_updates(offset=offset)

    @staticmethod
    def _get_new_update_offset(updates: List[telegram.Update]) -> Union[int, None]:
        if not updates:
            return None
        return updates[-1].update_id + 1

    def confirm(self, message: str) -> bool:
        updates = self._get_updates()
        update_offset = self._get_new_update_offset(updates)
        message = '{}\nPlease reply Y/N'.format(message)
        self.send_message(message)
        sending_time = datetime.utcnow().replace(tzinfo=timezone.utc)
        while True:
            updates = self._get_updates(offset=update_offset)
            update_offset = self._get_new_update_offset(updates)
            for update in updates:
                received_message = update.message
                if received_message.date < sending_time:
                    continue
                if received_message.chat.id not in self.chat_id_list:
                    continue
                text = received_message.text.upper()
                if text == 'Y':
                    return True
                if text == 'N':
                    return False
            time.sleep(10)
