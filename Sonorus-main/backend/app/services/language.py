"""
Lightweight, dependency-free language identification for a single utterance.

Used to track which language the conversation has actually settled into
(see ConversationManager's confirmed_language streak logic) so a stray
word doesn't flip the whole session. Scoped to exactly two languages —
English and Hindi — per product decision.

Deliberately strict: classifies by MAJORITY script/keyword content, not
"any match at all". Confirmed in testing that Gemini's own STT sometimes
transliterates a handful of English words into Devanagari script within an
otherwise-English utterance — a single-match rule was misreading those as
"the user switched to Hindi" when they hadn't.
"""

_DEVANAGARI_START = 0x0900
_DEVANAGARI_END = 0x097F

# Fraction of the utterance's letters that must be Devanagari before it
# counts as Hindi — guards against a few transliterated words within an
# otherwise-English sentence.
_DEVANAGARI_RATIO_THRESHOLD = 0.5

# Romanized Hindi (Hinglish) hints — for Hindi spoken/transcribed in Latin
# script rather than Devanagari.
_HINGLISH_KEYWORDS = {
    "hai", "hain", "nahi", "nahin", "kya", "kaise", "kaisi", "kaisa",
    "tum", "tumhe", "aap", "aapka", "mera", "meri", "mujhe", "humein",
    "acha", "accha", "theek", "thik", "karo", "kar", "raha", "rahi",
    "matlab", "haan", "kyun", "kyu", "yaar", "bhai", "namaste", "namaskar",
    "kahan", "kab", "kaun", "chalo", "bahut", "bilkul",
}

# Minimum number of distinct Hinglish keyword hits before counting as Hindi —
# one borrowed word (e.g. "yaar" dropped into an English sentence) isn't
# enough on its own.
_HINGLISH_MIN_HITS = 2
_HINGLISH_RATIO_THRESHOLD = 0.3


def detect_language(text: str) -> str:
    """Best-effort single-utterance language guess: 'hindi' or 'english'."""
    if not text:
        return "english"

    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return "english"

    # 1. Devanagari script — majority of letters, not just one stray character.
    devanagari_count = sum(1 for ch in letters if _DEVANAGARI_START <= ord(ch) <= _DEVANAGARI_END)
    if devanagari_count / len(letters) >= _DEVANAGARI_RATIO_THRESHOLD:
        return "hindi"

    # 2. Romanized Hindi keyword fallback — needs multiple hits, or a
    # meaningful fraction of the utterance, not a single borrowed word.
    words = [w.strip(".,!?'\"").lower() for w in text.split()]
    if words:
        hits = sum(1 for w in words if w in _HINGLISH_KEYWORDS)
        if hits >= _HINGLISH_MIN_HITS or hits / len(words) >= _HINGLISH_RATIO_THRESHOLD:
            return "hindi"

    return "english"
