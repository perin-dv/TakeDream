"""Shared semantic scoring for story slots, diversity and opening/ending."""
import math


PREPARATION = ("bride_prep", "groom_prep", "makeup", "hair")
DETAILS = ("dress_detail", "shoe_detail", "bouquet_detail", "ring_detail", "invitation_detail")
CEREMONY = ("ceremony_wide", "bride_entrance", "groom_waiting", "ring_exchange", "couple_praying", "applause", "ceremony_exit")
COUPLE = ("couple_portrait", "couple_closeup", "holding_hands", "embrace", "smiling_couple", "kiss")
BAD_ENDING = ("children", "guests_reaction", "officiant", "party", "decor_detail")
SLOT_TAGS = {
    "opening": DETAILS + PREPARATION + ("ceremony_wide", "couple_portrait", "couple_closeup"),
    "preparation": PREPARATION, "details": DETAILS + ("decor_detail",),
    "anticipation": ("groom_waiting", "bride_entrance", "ceremony_wide"),
    "ceremony": CEREMONY + ("vows", "officiant"),
    "emotional_peak": ("kiss", "vows", "ring_exchange", "emotional_reaction", "family_moment"),
    "couple_hero": COUPLE, "closing": COUPLE + ("ring_detail", "ceremony_exit", "bouquet_detail"),
}
PHASE_SLOTS = {"cold_open": "opening", "preparation_a": "preparation", "preparation_b": "anticipation",
               "details": "details", "ceremony": "ceremony", "vows_couple": "emotional_peak", "finale": "closing"}


def build_semantic_director(target_ms):
    weights = (0.06, 0.18, 0.12, 0.10, 0.21, 0.13, 0.15, 0.05)
    phases, cursor = [], 0
    for slot,weight in zip(SLOT_TAGS,weights):
        end = cursor + int(target_ms*weight)
        phases.append({"key":slot,"label":slot.replace("_"," "), "story_sections":[],
                       "desired_shots":max(1, int((end-cursor)/4000)), "topic_repeat_limit":2,
                       "target_shot_ms":4000,"audio_intent":"music_priority",
                       "unclassified_source_band":[cursor/max(1,target_ms),end/max(1,target_ms)]})
        cursor = end
    return {"engine":"semantic-story-director-v1","phases":phases}


def scores(candidate):
    semantic = candidate.get("visual_semantics") or {}
    return {item["name"]: float(item.get("score", 0)) for item in semantic.get("tags", []) if isinstance(item, dict) and item.get("name")}


def strongest(values, names):
    return max((values.get(name, 0.0) for name in names), default=0.0)


def quality_risk(candidate):
    quality = (candidate.get("visual_semantics") or {}).get("quality") or {}
    return max(strongest(scores(candidate), ("low_value_frame",)),
               max(float(quality.get(key, 0) or 0) for key in ("shake_score", "motion_blur_score", "whip_score")))


def slot_score(candidate, slot):
    values = scores(candidate)
    support = strongest(values, SLOT_TAGS.get(slot, ()))
    role = {"opening": "opening_score", "closing": "closing_score", "couple_hero": "hero_score"}.get(slot)
    roles = (candidate.get("visual_semantics") or {}).get("roles") or {}
    if role:
        support = max(support, float(roles.get(role, 0) or 0))

    risk = quality_risk(candidate)
    # Um take pode ser semanticamente perfeito (beijo, entrada, casal), mas se a
    # região segura ainda contém chicote/tremor/blur forte ele não deve dominar
    # um slot só porque o assunto é bom. Acima deste limite sai do pool semântico.
    if risk >= 0.60:
        return -1.0

    penalty = risk * 0.90
    if slot in ("opening", "closing"):
        penalty += strongest(values, BAD_ENDING) * 0.65
    return support - penalty


def repetition_penalty(candidate, selected):
    values = scores(candidate)
    tags = {name for name, value in values.items() if value >= 0.30 and name in set(sum((tuple(x) for x in SLOT_TAGS.values()), ()))}
    embedding = (candidate.get("visual_semantics") or {}).get("embedding") or []
    penalty = 0.0
    for other in selected:
        previous = scores(other)
        other_tags = {name for name, value in previous.items() if value >= 0.30 and name in tags}
        overlap = len(other_tags) / max(1, len(tags))
        current = overlap * 12.0
        other_embedding = (other.get("visual_semantics") or {}).get("embedding") or []
        if embedding and len(embedding) == len(other_embedding):
            norm = math.sqrt(sum(x*x for x in embedding) * sum(x*x for x in other_embedding))
            cosine = sum(a*b for a,b in zip(embedding, other_embedding)) / norm if norm else 0
            current += max(0.0, (cosine - 0.82) / 0.18) * 30.0
        if candidate.get("asset_id") == other.get("asset_id"):
            current += 5.0
            if abs(int(candidate.get("start_ms", 0)) - int(other.get("start_ms", 0))) < 8000:
                current += 10.0
        penalty += current
    return min(90.0, penalty)


def semantic_section(candidate):
    values = scores(candidate)
    groups = {"making_of": PREPARATION + DETAILS, "cerimonia": CEREMONY + ("kiss", "officiant"),
              "votos_falas": ("vows",), "casal": COUPLE, "festa": ("party", "dance", "guests_reaction", "children"),
              "recepcao": ("decor_detail", "family_moment"), "finale": ("ceremony_exit",)}
    ranked = sorted(((strongest(values, names), section) for section,names in groups.items()), reverse=True)
    return (ranked[0][1], ranked[0][0]) if ranked and ranked[0][0] >= 0.30 else (None, 0.0)
