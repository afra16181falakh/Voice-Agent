from abc import ABC, abstractmethod
from app.core.models import EmotionState, EmotionTimeline, EmotionType, StrategyDecision, ConversationContext

class IEmotionEngine(ABC):
    """
    Interface for tracking and managing the user's emotional state over time.
    """

    @abstractmethod
    async def analyze_utterance(self, session_id: str, text: str) -> EmotionState:
        """Analyzes a single utterance to detect the user's emotion and adds it to the timeline."""
        pass

    @abstractmethod
    async def get_timeline(self, session_id: str) -> EmotionTimeline:
        """Retrieves the full emotional timeline for the session."""
        pass

    @abstractmethod
    async def get_current_emotion(self, session_id: str) -> EmotionType:
        """Gets the most recent emotional state."""
        pass

    @abstractmethod
    async def clear_timeline(self, session_id: str) -> None:
        """Resets the emotional tracker for a session."""
        pass


class IResponseStrategyEngine(ABC):
    """
    Interface for selecting the dialogue response strategy (comfort, ask question, joke, explain, etc.)
    before generating a reply.
    """

    @abstractmethod
    async def determine_strategy(
        self, 
        session_id: str, 
        context: ConversationContext
    ) -> StrategyDecision:
        """
        Calculates the conversational response strategy to guide the AI persona based
        on user intent, emotion history, context, and memories.
        """
        pass
