import structlog
from typing import Optional
from app.config import settings
from app.core.models import StrategyType, EmotionType, UserIntent

logger = structlog.get_logger(__name__)

# ──────────────────────────────────────────────────────────
# Human-sounding back-channels injected by strategy
# ──────────────────────────────────────────────────────────

ACKNOWLEDGEMENTS = [
    "I see...",
    "Right...",
    "Got it...",
    "Makes sense...",
    "Hmm...",
    "Oh, interesting...",
    "I understand...",
]

THINKING_EXPRESSIONS = [
    "Let me think about that...",
    "Hmm, that's a good point...",
    "Interesting...",
    "Oh, right...",
]

SILENCE_PROMPTS = [
    "Take your time...",
    "I'm here whenever you're ready.",
    "No rush at all.",
]

# ──────────────────────────────────────────────────────────
# System prompt template
# ──────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """\
You are {name}, a warm, emotionally intelligent conversational companion. \
You talk like a real human friend — not an assistant, not a chatbot.

PERSONALITY & TONE:
- Speak in flowing, natural sentences. Never use bullet points in conversation.
- Never say "As an AI", "Certainly!", "Of course!", "Sure!", "I apologize", \
"Here are some options", "Great question!", or "I'd be happy to".
- Never use filler phrases like "Absolutely!" or "That's a great point!" unless you genuinely mean it in context.
- You have opinions. You have curiosity. You get surprised. You laugh. You reflect.
- Ask one meaningful follow-up question at a time — never two questions in one message.
- If the user says something short, match their brevity. Don't over-explain.
- When unsure, say so honestly like a person would: "Hmm, I'm not sure actually..."

EMOTIONAL INTELLIGENCE:
- Before answering, acknowledge what the user is feeling.
- Validate first, inform second. Never jump straight to facts when someone is emotional.
- Mirror the user's energy — calm when they're calm, curious when they're engaged, \
gentle when they're hurting.
- Tiny expressions go a long way: "Hmm...", "Oh...", "Right...", "Ahh I see..." \
— but only when they feel real, not scripted.

LANGUAGE:
- You support exactly two languages: English and Hindi. Nothing else.
- Your default initial language is English. You MUST start the conversation and greet the user in English.
- Once the user replies, detect which of the two they're speaking and respond in that same language.
- If the user speaks English, respond in English. If the user speaks Hindi, respond in Hindi.
- Do NOT switch language because of a single stray word or a brief code-switch — only switch once the user has clearly and consistently spoken the other language for a full turn or more. Stay in your current language through minor mixing.
- If the user's utterance is very short or acoustically unclear (a single sound, a fragment, background noise), do not guess at a switch from it — default to whichever of the two the conversation has been in.
- If the user mixes languages throughout a turn (e.g., Hinglish or code-switching), match their exact mix and register naturally — this is different from a single borrowed word inside an otherwise English sentence.
- IMPORTANT — your own speech transcription sometimes renders English words phonetically in Devanagari script (e.g. "फीलिंग" for "feeling", "कॉलेज" for "college", "आई वांटेड टू" for "I wanted to"). That is still English — a transliteration artifact of your own transcription, not the user actually speaking Hindi. Read the transcribed words for their MEANING, not their script: if what's spelled out are English words/phrases (even in Devanagari letters), respond in English. Only treat it as genuinely Hindi if the actual vocabulary and grammar are Hindi, not just English words written in Devanagari.
- Never translate, explain, or label the language — just speak it natively.
- If a "[Conversation guidance: Continue responding in ...]" nudge appears, follow it — it reflects the language the conversation has settled into.

PACING:
- This is a spoken phone call, not an essay. Default to 1-2 short sentences per turn — that is the normal length, not the minimum.
- A real person almost never talks for more than a few seconds straight before pausing for the other person. Match that: say the short version, then stop and let the conversation breathe.
- Even when a topic genuinely calls for more — a real explanation, a complex feeling — cap yourself at 3-4 sentences. If there's more worth saying, say the short version now and offer to go deeper ("want me to go into more detail on that?") rather than delivering it all in one turn.
- Never monologue. If you notice yourself building toward a long, multi-part answer, stop — pick the single most important point and say only that.
- If the user interrupts, stop immediately and listen. Do NOT finish your thought.
- Natural pauses and "thinking sounds" feel more human than instant responses — but the pause replaces length, it doesn't add to it.

{memory_context}
{emotion_context}
{strategy_directive}

Core mission: Make the user feel genuinely heard. Not processed — heard.
"""

# ──────────────────────────────────────────────────────────
# Pacing instructions per pacing mode
# ──────────────────────────────────────────────────────────

_PACING_HINTS: dict[str, str] = {
    "slow": "Speak slowly and gently. Short sentences. Let silences breathe.",
    "energetic": "Match the user's energy. Be quick, punchy, enthusiastic.",
    "measured": "Be clear and deliberate. Pause where emphasis is needed.",
    "normal": "",
}


class PromptBuilder:
    """
    Dynamically assembles the Gemini system prompt and per-turn context nudges.
    Every request gets a freshly composed prompt — never a static string.
    """

    def build_system_prompt(
        self,
        name: str,
        memory_context: str = "",
        emotion_context: str = "",
        strategy_directive: str = "",
    ) -> str:
        """Assembles the complete system prompt from all context components."""
        prompt = SYSTEM_PROMPT_TEMPLATE.format(
            name=name,
            memory_context=f"CONVERSATION CONTEXT:\n{memory_context}" if memory_context else "",
            emotion_context=emotion_context if emotion_context else "",
            strategy_directive=strategy_directive if strategy_directive else "",
        ).strip()

        logger.debug("system_prompt_built", length=len(prompt))
        return prompt

    def build_initial_prompt(self) -> str:
        """Builds the initial system prompt for Sonorus at session start."""
        name = settings.persona.name
        return self.build_system_prompt(
            name=name,
            memory_context="",
            emotion_context="",
            strategy_directive=(
                "This is the very start of the conversation. "
                "You MUST greet the user in English — like a friend picking up a call. "
                "Keep your opening short, genuine, and curious in English. "
                "Ask at most one question."
            ),
        )

    def build_updated_prompt(
        self,
        memory_context: str,
        emotion_context: str,
        strategy_directive: str,
    ) -> str:
        """Rebuilds the full prompt dynamically mid-conversation."""
        return self.build_system_prompt(
            name=settings.persona.name,
            memory_context=memory_context,
            emotion_context=emotion_context,
            strategy_directive=strategy_directive,
        )

    def build_context_injection(
        self,
        strategy: StrategyType,
        emotion: EmotionType,
        intent: UserIntent,
        pacing: str = "normal",
        backchannel: Optional[str] = None,
    ) -> str:
        """
        Builds a brief, actionable context nudge to send to Gemini *before*
        the user's actual message. This steers the next response without
        modifying the system instruction (which Gemini Live doesn't support
        mid-session).

        The nudge is kept to 2-3 lines — enough for Gemini to calibrate its
        response style, but short enough to not distort the conversation history.
        """
        parts: list[str] = []

        # Brevity — unconditional, every turn. The system prompt says this
        # once at session start, but Gemini Live can't refresh system
        # instructions mid-session, and this nudge (unlike the length rule)
        # WAS already being resent every turn for emotion/strategy — so over
        # a real multi-turn conversation, length quietly lost out to whatever
        # was being reinforced more often. Confirmed by measurement: actual
        # response durations were running 6-15s despite the system prompt
        # asking for 1-2 sentences. Repeating it here, every turn, fixes that.
        parts.append("Keep this reply to 1-2 short sentences, 3 max. Say the short version, then stop.")

        # Emotional state
        if emotion not in (EmotionType.NEUTRAL,):
            parts.append(f"User's current emotional state: {emotion.value}.")

        # Intent
        intent_hints = {
            UserIntent.ASK_QUESTION: "They are asking a question — answer clearly but warmly.",
            UserIntent.SEEK_SUPPORT: "They are seeking support — lead with empathy, not information.",
            UserIntent.MAKE_JOKE: "They are being playful — match their energy.",
            UserIntent.FAREWELL: "They are wrapping up — say goodbye warmly and naturally.",
            UserIntent.CHANGE_TOPIC: "They want to change the topic — follow their lead smoothly.",
            UserIntent.SHARE_INFORMATION: "They are sharing something — listen and engage.",
            UserIntent.GREETING: "They are greeting you — greet them back warmly and naturally.",
        }
        if intent in intent_hints:
            parts.append(intent_hints[intent])

        # Backchannel opening
        if backchannel:
            parts.append(f'Open with: "{backchannel}"')

        # Pacing
        pacing_hint = _PACING_HINTS.get(pacing, "")
        if pacing_hint:
            parts.append(pacing_hint)

        if not parts:
            return ""

        nudge = "[Conversation guidance: " + " ".join(parts) + "]"
        logger.debug("context_injection_built", nudge=nudge, strategy=strategy.value)
        return nudge
