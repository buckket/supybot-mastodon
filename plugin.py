###
# Copyright (c) 2010-2019, buckket
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

###

import supybot.utils as utils
from supybot.commands import *

import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.schedule as schedule
import supybot.ircmsgs as ircmsgs
import supybot.log as log

try:
    from supybot.i18n import PluginInternationalization, internationalizeDocstring
    _ = PluginInternationalization("Mastodon")
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x


import re
import html
import textwrap

from functools import wraps

from mastodon import Mastodon as MastodonAPI
from mastodon import MastodonError, StreamListener


def is_bot_enabled(func):
    @wraps(func)
    def wrapper_is_bot_enabled(*args, **kwds):
        self, irc, msg, *other = args
        if self.registryValue("bot_enabled", msg.args[0]):
            return func(*args, **kwds)
        else:
            irc.reply(_("This channel has no associated Mastodon account."))
    return wrapper_is_bot_enabled


def cleanup_text(text):
    text = text.replace("<br>", " ")
    text = text.replace("\n", " ")
    text = re.sub(re.compile('<.*?>'), '', text)
    text = html.unescape(text)
    return text


class SupybotStreamListener(StreamListener):
    def __init__(self, irc, channel):
        self.irc = irc
        self.channel = channel

    def on_notification(self, notification):
        if notification["type"] == "mention":
            text = cleanup_text(notification["status"]["content"])
            message = _("Mention by @{}: {} – {}").format(notification["status"]["account"]["username"], text,
                                                          notification["status"]["url"])
            message = ircutils.safeArgument(message)
            for line in textwrap.wrap(message, 400):
                self.irc.queueMsg(ircmsgs.notice(self.channel, line))


class Mastodon(callbacks.Plugin):
    """Hello. This is Mastodon."""

    def __init__(self, irc):
        self.__parent = super(Mastodon, self)
        self.__parent.__init__(irc)

        self.streaming_channels = []
        for channel in irc.state.channels:
            if self.registryValue("streaming", channel):
                listener = SupybotStreamListener(irc=irc, channel=channel)
                api = MastodonAPI(client_id=self.registryValue("client_id", channel),
                                  client_secret=self.registryValue("client_secret", channel),
                                  access_token=self.registryValue("access_token", channel),
                                  api_base_url=self.registryValue("api_base_url", channel))
                streaming = api.stream_user(listener=listener, run_async=True, reconnect_async=True)
                log.info("Enabled Mastodon Streaming API for: {}".format(channel))
                self.streaming_channels.append(streaming)

    def die(self):
        for streaming in self.streaming_channels:
            streaming.close()
        self.__parent.die()

    def _get_mastodon_api(self, msg):
        return MastodonAPI(client_id=self.registryValue("client_id", msg.args[0]),
                           client_secret=self.registryValue("client_secret", msg.args[0]),
                           access_token=self.registryValue("access_token", msg.args[0]),
                           api_base_url=self.registryValue("api_base_url", msg.args[0]))

    def _get_status(self, api, toot, resolve=True):
        results = api.search_v2(toot, resolve=resolve)
        if results and results["statuses"]:
            return results["statuses"][0]
        else:
            return None

    def _toot(self, irc, msg, text, toot=None):
        try:
            api = self._get_mastodon_api(msg)
            if toot:
                to_status = self._get_status(api, toot)
                if to_status:
                    message = utils.str.ellipsisify(text, 500)
                    status = api.status_reply(to_status=to_status, status=message)
                else:
                    irc.reply(_("Please specify a toot to reply to."))
                    return
            else:
                message = utils.str.ellipsisify(text, 500)
                status = api.status_post(status=message)
            irc.reply(status["url"])
        except MastodonError as e:
            log.error("Mastodon.toot: {}".format(repr(e)))
            irc.error(_("An error has occurred."))

    @is_bot_enabled
    @internationalizeDocstring
    def mastodon(self, irc, msg, args):
        """Returns the link to the bot's Mastodon profile."""
        try:
            api = self._get_mastodon_api(msg)
            account = api.account_verify_credentials()
            irc.reply(account["url"])
        except MastodonError as e:
            log.error("Mastodon.mastodon: {}".format(repr(e)))
            irc.error(_("An error has occurred."))

    @is_bot_enabled
    @internationalizeDocstring
    def toot(self, irc, msg, args, text):
        """<text>

        Toots <text>
        """
        self._toot(irc, msg, text)

    @is_bot_enabled
    @internationalizeDocstring
    def reply(self, irc, msg, args, toot, text):
        """<toot url> <text>

        Toots <text> as reply to <toot url>
        """
        self._toot(irc, msg, text, toot)

    @is_bot_enabled
    @internationalizeDocstring
    def fav(self, irc, msg, args, toot):
        """<toot url>

        Favs toot <toot url>
        """
        api = self._get_mastodon_api(msg)
        fav_status = self._get_status(api, toot)
        if fav_status:
            try:
                api.status_favourite(fav_status)
                irc.reply(_("Done."))
            except MastodonError as e:
                log.error("Mastodon.fav: {}".format(repr(e)))
                irc.error(_("An error has occurred."))

    @is_bot_enabled
    @internationalizeDocstring
    def boost(self, irc, msg, args, toot):
        """<toot url>

        Boosts toot <toot url>
        """
        api = self._get_mastodon_api(msg)
        boost_status = self._get_status(api, toot)
        if boost_status:
            try:
                api.status_reblog(boost_status)
                irc.reply(_("Done."))
            except MastodonError as e:
                log.error("Mastodon.boost: {}".format(repr(e)))
                irc.error(_("An error has occurred."))

    @is_bot_enabled
    @internationalizeDocstring
    def delete(self, irc, msg, args, toot):
        """<toot url>

        Deletes toot <toot url>
        """
        api = self._get_mastodon_api(msg)
        delete_status = self._get_status(api, toot)
        if delete_status:
            try:
                api.status_delete(delete_status)
                irc.reply(_("Done."))
            except MastodonError as e:
                log.error("Mastodon.delete: {}".format(repr(e)))
                irc.error(_("An error has occurred."))

    @is_bot_enabled
    @internationalizeDocstring
    def follow(self, irc, msg, args, user):
        """<user uri>

        Follow user <user uri>
        """
        api = self._get_mastodon_api(msg)
        try:
            user_list = api.account_search(user)
            if user_list:
                api.account_follow(user_list[0])
                irc.reply(_("Done."))
        except MastodonError as e:
            log.error("Mastodon.follow: {}".format(repr(e)))
            irc.error(_("An error has occurred."))

    @is_bot_enabled
    @internationalizeDocstring
    def unfollow(self, irc, msg, args, user):
        """<user uri>

        Unfollow user <user uri>
        """
        api = self._get_mastodon_api(msg)
        try:
            user_list = api.account_search(user, following=True)
            if user_list:
                api.account_unfollow(user_list[0])
                irc.reply(_("Done."))
        except MastodonError as e:
            log.error("Mastodon.unfollow: {}".format(repr(e)))
            irc.error(_("An error has occurred."))

    def doPrivmsg(self, irc, msg):
        if ircmsgs.isCtcp(msg) or ircmsgs.isAction(msg):
            return
        if ircutils.isChannel(msg.args[0]) and self.registryValue("resolve", msg.args[0]):
            if msg.args[1].find("notice") != -1 or msg.args[1].find("@") != -1:
                matches = re.findall(r"(?P<url>https?://[^\s]+)", msg.args[1])
                if not matches:
                    return
                api = self._get_mastodon_api(msg)
                for url in matches:
                    status = self._get_status(api, url)
                    if status:
                        try:
                            text = cleanup_text(status["content"])
                            message = _("Toot by @{}: {}").format(status["account"]["acct"], text)
                            message = ircutils.safeArgument(message)
                            for line in textwrap.wrap(message, 400):
                                irc.queueMsg(ircmsgs.notice(msg.args[0], line))
                        except MastodonError as e:
                            log.error("Mastodon.doPrivmsg: {}".format(repr(e)))

    mastodon = wrap(mastodon, ["public"])
    toot = wrap(toot, ["public", "text"])
    reply = wrap(reply, ["public", "somethingWithoutSpaces", "text"])
    fav = wrap(fav, ["public", "somethingWithoutSpaces"])
    boost = wrap(boost, ["public", "somethingWithoutSpaces"])
    delete = wrap(delete, ["public", "somethingWithoutSpaces"])
    follow = wrap(follow, ["public", "somethingWithoutSpaces"])
    unfollow = wrap(unfollow, ["public", "somethingWithoutSpaces"])


Class = Mastodon
