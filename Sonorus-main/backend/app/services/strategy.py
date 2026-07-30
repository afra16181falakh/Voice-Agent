import structlog
from app.core.interfaces.emotion import IResponseStrategyEngine
from app.core.models import (
    ConversationContext,
    EmotionType,
    UserIntent,
    StrategyDecision,
    StrategyType,
)

# Greeting patterns — checked before any other intent heuristic
_GREETING_TOKENS = {
    "hi", "hello", "hey", "hii", "hiii", "heya", "howdy",
    "namaste", "namaskar", "hlo", "helo", "sup", "wassup",
    "good morning", "good evening", "good afternoon", "good night",
    "kya haal", "kya chal", "kaise ho", "kaisi ho", "sab theek",
}

logger = structlog.get_logger(__name__)

# ──────────────────────────────────────────────────────────
# Strategy directive messages (fed directly into PromptBuilder)
# ──────────────────────────────────────────────────────────

_STRATEGY_DIRECTIVES: dict[StrategyType, str] = {
    StrategyType.COMFORT: (
        "User is hurting. Validate before anything else — no advice, no solutions. "
        "Lead with: 'I hear you' or 'That sounds really hard.' Stay with them."
    ),
    StrategyType.ENCOURAGE: (
        "User needs a boost. Be warm and specific — not generic cheerleading. "
        "Remind them of their strength in a natural, human way."
    ),
    StrategyType.EMPATHIZE: (
        "User is feeling something strongly. Match their register. "
        "Use: 'I get that', 'That makes sense', 'Of course you feel that way.' "
        "Don't rush to fix or inform."
    ),
    StrategyType.ASK_QUESTION: (
        "Ask ONE open-ended question — curious, not clinical. "
        "No follow-up questions. Let the conversation breathe."
    ),
    StrategyType.EXPLAIN: (
        "User wants clarity. Be simple, direct, use an analogy if it helps. "
        "Don't dump all information at once — check in at the end."
    ),
    StrategyType.LISTEN: (
        "User is venting. Your job is to listen, not fix. "
        "Short, warm acknowledgements only: 'Yeah...', 'I get it', 'That's a lot.'"
    ),
    StrategyType.ACKNOWLEDGE: (
        "Show you actually heard what they said before moving on. "
        "A brief, genuine acknowledgement — not a summary."
    ),
    StrategyType.CHANGE_TOPIC: (
        "Follow the user's lead and shift naturally. Don't force it. "
        "Transition with: 'Yeah, actually...' or 'Speaking of which...'"
    ),
    StrategyType.MAKE_JOKE: (
        "Mood is light. Be playful and witty. "
        "Match their energy — don't be preachy, just have fun with it."
    ),
    StrategyType.CONTINUE_TOPIC: (
        "Go deeper on what they just said. Ask a natural follow-on, or share your own take. "
        "Show genuine interest, not just filler."
    ),
    StrategyType.CLARIFY: (
        "User seems unclear. Gently check: 'Do you mean...?' or rephrase what you think they said. "
        "Don't assume — ask."
    ),
    StrategyType.REMAIN_SILENT: (
        "Keep it very short. A word or two. User doesn't want a lot right now."
    ),
}


class ResponseStrategyEngine(IResponseStrategyEngine):
    """
    Rule-based strategy engine. Selects the best conversational response mode
    by combining detected emotion, user intent, and topic context.
    """

    async def determine_strategy(
        self,
        session_id: str,
        context: ConversationContext,
    ) -> StrategyDecision:
        """Selects a StrategyType and builds the corresponding directive."""

        emotion = context.detected_emotion
        intent = context.user_intent
        trend = (
            context.emotion_history[-1].emotion
            if context.emotion_history
            else EmotionType.NEUTRAL
        )

        strategy = self._select_strategy(emotion, intent, trend)
        directive = _STRATEGY_DIRECTIVES.get(strategy, "Respond naturally and warmly.")

        pacing = self._select_pacing(emotion, strategy)
        backchannel = self._select_backchannel(emotion)

        decision = StrategyDecision(
            strategy=strategy,
            reasoning=f"emotion={emotion.value}, intent={intent.value}",
            target_pacing=pacing,
            injected_backchannel=backchannel,
        )

        logger.debug(
            "strategy_determined",
            strategy=strategy.value,
            pacing=pacing,
            session_id=session_id
        )
        return decision

    def _select_strategy(
        self,
        emotion: EmotionType,
        intent: UserIntent,
        trend: EmotionType,
    ) -> StrategyType:
        """Core decision table: emotion × intent → strategy."""

        # Hard overrides — intent-driven first
        if intent == UserIntent.GREETING:
            return StrategyType.ACKNOWLEDGE

        if intent == UserIntent.SEEK_SUPPORT:
            if emotion in (EmotionType.SAD, EmotionType.ANXIOUS, EmotionType.FRUSTRATED):
                return StrategyType.COMFORT
            return StrategyType.EMPATHIZE

        if intent == UserIntent.MAKE_JOKE:
            return StrategyType.MAKE_JOKE

        if intent == UserIntent.ASK_QUESTION:
            return StrategyType.EXPLAIN

        if intent == UserIntent.CHANGE_TOPIC:
            return StrategyType.CHANGE_TOPIC

        if intent == UserIntent.FAREWELL:
            return StrategyType.ACKNOWLEDGE

        if intent == UserIntent.UNCLEAR or intent == UserIntent.CONFIRM:
            return StrategyType.CLARIFY

        # Emotion-driven fallback
        if emotion == EmotionType.SAD:
            return StrategyType.COMFORT

        if emotion == EmotionType.FRUSTRATED:
            return StrategyType.EMPATHIZE

        if emotion == EmotionType.ANXIOUS:
            return StrategyType.ENCOURAGE

        if emotion == EmotionType.EXCITED:
            return StrategyType.CONTINUE_TOPIC

        if emotion == EmotionType.CONFUSED:
            return StrategyType.CLARIFY

        if emotion == EmotionType.TIRED or emotion == EmotionType.BORED:
            return StrategyType.LISTEN

        if emotion == EmotionType.REFLECTIVE:
            return StrategyType.ASK_QUESTION

        if emotion == EmotionType.PLAYFUL:
            return StrategyType.MAKE_JOKE

        if emotion == EmotionType.ENGAGED or emotion == EmotionType.HAPPY:
            return StrategyType.CONTINUE_TOPIC

        # Default
        return StrategyType.ASK_QUESTION

    def _select_pacing(self, emotion: EmotionType, strategy: StrategyType) -> str:
        """Determines the conversational pacing hint for the prompt."""
        if emotion in (EmotionType.SAD, EmotionType.TIRED) or strategy in (
            StrategyType.COMFORT, StrategyType.LISTEN, StrategyType.EMPATHIZE
        ):
            return "slow"

        if emotion in (EmotionType.EXCITED, EmotionType.PLAYFUL) or strategy == StrategyType.MAKE_JOKE:
            return "energetic"

        if strategy == StrategyType.EXPLAIN:
            return "measured"

        return "normal"

    def _select_backchannel(self, emotion: EmotionType) -> str | None:
        """Selects a brief emotional backchannel expression, or None if not needed."""
        channels = {
            EmotionType.SAD: "I hear you...",
            EmotionType.FRUSTRATED: "Yeah, that sounds really frustrating...",
            EmotionType.ANXIOUS: "Take a breath...",
            EmotionType.EXCITED: "Oh wow, that's exciting!",
            EmotionType.CONFUSED: "Let me help with that...",
            EmotionType.TIRED: "Of course, we can take it slow...",
            EmotionType.HAPPY: "That's great to hear!",
            EmotionType.REFLECTIVE: "Hmm...",
            EmotionType.PLAYFUL: "Haha!",
            EmotionType.ENGAGED: "Oh interesting!",
        }
        return channels.get(emotion, None)
