"""Conservative, offline service bundles. Never block a shared CDN root."""
BUNDLES = {
    'youtube.com': ('youtube.com', 'youtu.be', 'youtube-nocookie.com', 'googlevideo.com', 'ytimg.com', 'youtubei.googleapis.com'),
    'facebook.com': ('facebook.com', 'fb.com', 'fb.watch', 'messenger.com', 'fbcdn.net'),
    'instagram.com': ('instagram.com', 'cdninstagram.com'),
    'x.com': ('x.com', 'twitter.com', 't.co', 'twimg.com'),
    'tiktok.com': ('tiktok.com', 'tiktokv.com', 'tiktokcdn.com', 'musical.ly'),
    'discord.com': ('discord.com', 'discord.gg', 'discordapp.com', 'discordapp.net', 'discordcdn.com'),
    'reddit.com': ('reddit.com', 'redd.it', 'redditstatic.com', 'redditmedia.com'),
    'snapchat.com': ('snapchat.com', 'sc-cdn.net'),
    'twitch.tv': ('twitch.tv', 'ttvnw.net', 'jtvnw.net', 'twitchcdn.net'),
    'roblox.com': ('roblox.com', 'rbxcdn.com'),
    'netflix.com': ('netflix.com', 'nflxvideo.net', 'nflximg.net', 'nflxso.net', 'nflxext.com'),
}
PRESETS = {
    'Social media': ('facebook.com', 'instagram.com', 'x.com', 'tiktok.com', 'snapchat.com', 'reddit.com'),
    'Video & streaming': ('youtube.com', 'twitch.tv', 'netflix.com'),
    'Gaming & chat': ('roblox.com', 'discord.com', 'store.steampowered.com', 'epicgames.com'),
}


def related_domains(domain):
    for roots in BUNDLES.values():
        if domain in roots:
            return set(roots)
    return {domain}
