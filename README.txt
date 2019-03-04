supybot-mastodon
~~~~~~~~~~~~~~~~

Hello. This is Mastodon.
Inspired by https://github.com/dridde/oiler_in

This plugin resolves Mastodon URLs and is able to control a Mastodon profile.
This includes: toots, replies, favs and boosts. Fun guaranteed! Handle with care!

Requirements:
- Mastodon.py

Configuration:
- Create a new Application on your Mastodon instance (/settings/applications)
- Copy and set client_id, client_secret and access_token
  channel #example plugins.Mastodon.client_id xxxxxxxxxxxxxxx
  channel #example plugins.Mastodon.client_secret xxxxxxxxxxxxxxx
  channel #example plugins.Mastodon.access_token xxxxxxxxxxxxxxx
- Set api_base_url to point to your Mastodon instance
  channel #example plugins.Mastodon.api_base_url https://mastodon.social
- Enable plugin for this specific channel:
  channel #example plugins.Mastodon.bot_enabled True
- Enable additional features if desired:
  channel #example plugins.Mastodon.streaming True
  channel #example plugins.Mastodon.resolve True

Notes:
The plugin is configured on a channel-to-channel basis.
All commands have to be sent from within a channel.

License:
BSD 3-Clause License
