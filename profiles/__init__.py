from profiles.youtube import YouTubeEditRules, get_youtube_rules


def get_edit_rules(profile, style):
    if str(profile).strip().lower() == "youtube":
        return get_youtube_rules(style)
    raise ValueError(f"Perfil ainda não suportado para edição automática: {profile}")
