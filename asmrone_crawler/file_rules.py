import re
from pathlib import Path, PurePosixPath


AUDIO_EXTENSIONS = {
    ".aac",
    ".avi",
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
    ".wma",
}

NO_DIALOGUE_RE = re.compile(
    r"(台詞|台词|セリフ)\s*(?:レス|なし|無し|ナシ|無|抜き)"
    r"|no\s*(?:dialogue|voice|vocal)"
    r"|voice\s*off"
    r"|voiceless",
    re.IGNORECASE,
)
SOUND_ONLY_RE = re.compile(
    r"(?:効果音|SE|SFX)\s*(?:のみ|だけ|素材)"
    r"|(?:フェラ音|耳舐め音|咀嚼音|水音|吐息|息遣い)\s*のみ"
    r"|環境音(?:のみ|素材)?"
    r"|sound\s*effects?\s*(?:only|素材)?",
    re.IGNORECASE,
)


def _compact(value: str) -> str:
    return re.sub(r"[\s_\-・/\\（）()［\]\[\]【】]+", "", value or "").lower()


def is_audio_file(file_path: str, file_type: str | None = None) -> bool:
    return file_type == "audio" or Path(file_path or "").suffix.lower() in AUDIO_EXTENSIONS


def _path_parts(file_path: str):
    path = PurePosixPath((file_path or "").replace("\\", "/"))
    return [part for part in path.parts if part not in ("", ".", "..")]


def _is_sound_effect_material_path(file_path: str) -> bool:
    parts = [_compact(part) for part in _path_parts(file_path)]
    if not parts:
        return False

    material_parts = {
        "効果音",
        "se",
        "sfx",
        "soundeffect",
        "soundeffects",
        "行動系",
    }
    for part in parts[:-1]:
        if part in material_parts:
            return True
        if any(token in part for token in ("効果音素材", "se素材", "sfx素材")):
            return True
    return False


def tts_skip_reason(
    file_path: str,
    file_type: str | None = None,
    duration: float | None = None,
) -> str | None:
    if not is_audio_file(file_path, file_type):
        return None

    if NO_DIALOGUE_RE.search(file_path or ""):
        return "no_dialogue"
    if SOUND_ONLY_RE.search(file_path or ""):
        return "sound_only"

    if _is_sound_effect_material_path(file_path):
        return "sound_effect_material"

    if duration is not None:
        if duration < 3:
            return "short_audio"
        if duration < 60 and _is_sound_effect_material_path(file_path):
            return "short_sound_effect"

    return None
