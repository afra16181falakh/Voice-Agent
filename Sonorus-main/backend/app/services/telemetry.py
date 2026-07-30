import json
import random
import asyncio
from datetime import datetime, timedelta
from collections import deque
import structlog
from sqlalchemy import select, func
from app.db.connection import async_session_maker
from app.db.schema import TelemetryEventORM

logger = structlog.get_logger(__name__)

# Departments list for employee wellbeing reporting
DEPARTMENTS = ["Engineering", "Sales", "HR", "Marketing", "Customer Support"]

class TelemetryService:
    """
    Modular service for recording, storing, and aggregating voice agent telemetry.
    Supports PostgreSQL persistence with seamless in-memory fallback.
    """
    def __init__(self):
        self._in_memory_events = deque(maxlen=2000)
        self._live_sessions = {} # session_id -> {meta}
        self._db_operational = True

    def register_live_session(self, session_id: str, stage: str = "idle"):
        self._live_sessions[session_id] = {
            "session_id": session_id,
            "stage": stage,
            "emotion": "neutral",
            "start_time": datetime.utcnow(),
            "last_active": datetime.utcnow(),
            "latencies": [],
            "status": "connected"
        }

    def update_live_session(self, session_id: str, stage: str = None, emotion: str = None, latency_ms: float = None):
        if session_id in self._live_sessions:
            session = self._live_sessions[session_id]
            session["last_active"] = datetime.utcnow()
            if stage:
                session["stage"] = stage
            if emotion:
                session["emotion"] = emotion
            if latency_ms is not None:
                session["latencies"].append(latency_ms)

    def unregister_live_session(self, session_id: str):
        self._live_sessions.pop(session_id, None)

    async def record_event(
        self,
        session_id: str = None,
        event_type: str = "pipeline_stage",
        stage_name: str = None,
        latency_ms: float = None,
        status: str = "success",
        error_message: str = None,
        payload: dict = None
    ) -> None:
        """
        Records a telemetry event into in-memory queue and attempts to write to DB.
        """
        payload_str = json.dumps(payload) if payload else None
        timestamp = datetime.utcnow()

        # Update live session status if it exists
        if session_id and event_type == "pipeline_stage":
            self.update_live_session(session_id, stage=stage_name, latency_ms=latency_ms)
        elif session_id and event_type == "session_start":
            self.register_live_session(session_id)
        elif session_id and event_type == "session_end":
            self.unregister_live_session(session_id)

        # 1. Store in memory (always succeeds)
        event_dict = {
            "session_id": session_id,
            "event_type": event_type,
            "stage_name": stage_name,
            "latency_ms": latency_ms,
            "status": status,
            "error_message": error_message,
            "payload": payload_str,
            "timestamp": timestamp
        }
        self._in_memory_events.append(event_dict)

        # 2. Store in DB (fallback if auth or connection fails)
        if self._db_operational:
            try:
                async with async_session_maker() as session:
                    orm_obj = TelemetryEventORM(
                        session_id=session_id,
                        event_type=event_type,
                        stage_name=stage_name,
                        latency_ms=latency_ms,
                        status=status,
                        error_message=error_message,
                        payload=payload_str,
                        timestamp=timestamp
                    )
                    session.add(orm_obj)
                    await session.commit()
            except Exception as e:
                logger.debug(
                    "telemetry_db_save_failed_using_memory_fallback",
                    error=str(e),
                    event_type=event_type
                )
                self._db_operational = False

    async def generate_mock_data_if_empty(self) -> None:
        """
        Checks if the database is empty, and generates 50+ rich historical mock sessions.
        """
        # Count existing entries in DB or memory
        has_data = len(self._in_memory_events) > 0
        if not has_data and self._db_operational:
            try:
                async with async_session_maker() as session:
                    result = await session.execute(select(func.count(TelemetryEventORM.id)))
                    count = result.scalar() or 0
                    has_data = count > 0
            except Exception:
                self._db_operational = False
                logger.info("telemetry_db_inactive_falling_back_to_in_memory")

        if has_data:
            logger.info("telemetry_history_detected_skipping_mock_generation")
            return

        logger.info("generating_mock_telemetry_history")
        now = datetime.utcnow()
        mock_sessions_count = 60

        # Generate sessions spread over the last 7 days
        for i in range(mock_sessions_count):
            session_id = f"mock-session-{1000 + i}"
            day_offset = random.randint(0, 6)
            hour_offset = random.randint(0, 23)
            minute_offset = random.randint(0, 59)
            session_start = now - timedelta(days=day_offset, hours=hour_offset, minutes=minute_offset)
            session_duration = random.randint(45, 480) # 45s to 8m
            session_end = session_start + timedelta(seconds=session_duration)

            dept = random.choice(DEPARTMENTS)
            initial_stress = random.choice(["high", "medium", "low"])
            final_stress = "low" if initial_stress == "high" and random.random() > 0.4 else ("low" if initial_stress == "medium" and random.random() > 0.3 else initial_stress)

            emotions = ["happy", "neutral", "playful", "engaged", "reflective", "tired", "anxious", "frustrated", "sad"]
            start_emotion = random.choice(["anxious", "frustrated", "sad", "neutral", "tired"])
            end_emotion = random.choice(["happy", "engaged", "reflective", "neutral", "playful"])

            # 1. Session start
            await self._record_mock_event(
                session_id=session_id,
                event_type="session_start",
                payload={"department": dept, "initial_stress": initial_stress, "start_emotion": start_emotion},
                timestamp=session_start
            )

            # Generate multiple turns in this session
            turns = random.randint(3, 15)
            turn_time = session_start
            for t in range(turns):
                turn_time += timedelta(seconds=random.randint(10, 30))
                if turn_time > session_end:
                    break

                # Pipeline stages for this turn
                stt_latency = random.uniform(150, 450)
                emotion_latency = random.uniform(5, 25)
                memory_latency = random.uniform(8, 40)
                llm_latency = random.uniform(300, 950)
                tts_latency = random.uniform(200, 550)
                safety_latency = random.uniform(3, 12)
                playback_latency = random.uniform(20, 50)

                turn_emotion = start_emotion if t < turns/2 else end_emotion
                is_error = random.random() < 0.03 # 3% fallback/error rate
                status = "error" if is_error else "success"
                err_msg = "Gemini Live rate limit error" if is_error else None

                # Write stage metrics
                await self._record_mock_event(session_id, "pipeline_stage", "STT", stt_latency, status, err_msg, {"confidence": random.uniform(0.85, 0.99)}, turn_time)
                await self._record_mock_event(session_id, "pipeline_stage", "Emotion Detection", emotion_latency, "success", None, {"emotion": turn_emotion, "confidence": random.uniform(0.7, 0.95)}, turn_time)
                await self._record_mock_event(session_id, "pipeline_stage", "Memory", memory_latency, "success", None, {"hits": random.randint(1, 3)}, turn_time)
                await self._record_mock_event(session_id, "pipeline_stage", "LLM", llm_latency, status, err_msg, {}, turn_time)
                await self._record_mock_event(session_id, "pipeline_stage", "Safety", safety_latency, "success", None, {}, turn_time)
                await self._record_mock_event(session_id, "pipeline_stage", "TTS", tts_latency, status, err_msg, {}, turn_time)

            # 2. Session end
            await self._record_mock_event(
                session_id=session_id,
                event_type="session_end",
                payload={"final_stress": final_stress, "end_emotion": end_emotion, "turns_count": turns, "duration_s": session_duration},
                timestamp=session_end
            )

        logger.info("mock_telemetry_history_generated_successfully")

    async def _record_mock_event(
        self,
        session_id: str,
        event_type: str,
        stage_name: str = None,
        latency_ms: float = None,
        status: str = "success",
        error_message: str = None,
        payload: dict = None,
        timestamp: datetime = None
    ):
        payload_str = json.dumps(payload) if payload else None
        event_dict = {
            "session_id": session_id,
            "event_type": event_type,
            "stage_name": stage_name,
            "latency_ms": latency_ms,
            "status": status,
            "error_message": error_message,
            "payload": payload_str,
            "timestamp": timestamp
        }
        self._in_memory_events.append(event_dict)
        if self._db_operational:
            try:
                async with async_session_maker() as session:
                    orm_obj = TelemetryEventORM(
                        session_id=session_id,
                        event_type=event_type,
                        stage_name=stage_name,
                        latency_ms=latency_ms,
                        status=status,
                        error_message=error_message,
                        payload=payload_str,
                        timestamp=timestamp
                    )
                    session.add(orm_obj)
                    await session.commit()
            except Exception:
                self._db_operational = False

    async def _get_all_events(self) -> list:
        """Fetches all events from DB if active, otherwise falls back to memory."""
        try:
            async with async_session_maker() as session:
                stmt = select(TelemetryEventORM).order_by(TelemetryEventORM.timestamp.asc())
                result = await session.execute(stmt)
                rows = result.scalars().all()
                events = []
                for row in rows:
                    events.append({
                        "session_id": row.session_id,
                        "event_type": row.event_type,
                        "stage_name": row.stage_name,
                        "latency_ms": row.latency_ms,
                        "status": row.status,
                        "error_message": row.error_message,
                        "payload": row.payload,
                        "timestamp": row.timestamp
                    })
                return events
        except Exception as e:
            logger.debug("telemetry_db_query_failed_using_memory_cache", error=str(e))
            return list(self._in_memory_events)

    # ──────────────────────────────────────────────────────────
    # Aggregation & Analysis queries
    # ──────────────────────────────────────────────────────────

    async def get_overview_metrics(self) -> dict:
        events = await self._get_all_events()
        sessions = [e for e in events if e["event_type"] == "session_start"]
        ends = [e for e in events if e["event_type"] == "session_end"]
        pipeline_stages = [e for e in events if e["event_type"] == "pipeline_stage"]

        total_sessions = len(sessions)
        active_count = len(self._live_sessions)

        # Unique users per day (group by date)
        unique_users = len(set(e["session_id"] for e in sessions))

        # Averages
        avg_duration = 0.0
        durations = []
        for end in ends:
            p = json.loads(end["payload"]) if end["payload"] else {}
            if "duration_s" in p:
                durations.append(p["duration_s"])
        if durations:
            avg_duration = sum(durations) / len(durations)

        avg_latency = 0.0
        llm_stages = [e for e in pipeline_stages if e["stage_name"] == "LLM" and e["latency_ms"]]
        if llm_stages:
            avg_latency = sum(e["latency_ms"] for e in llm_stages) / len(llm_stages)

        # Success rate
        success_count = sum(1 for e in pipeline_stages if e["status"] == "success")
        total_stages = len(pipeline_stages)
        success_rate = (success_count / total_stages * 100.0) if total_stages else 100.0

        return {
            "total_conversations": total_sessions,
            "active_sessions": active_count,
            "daily_users": max(1, int(unique_users / 7.0)),
            "weekly_users": unique_users,
            "avg_session_duration_s": round(avg_duration, 1),
            "avg_response_latency_ms": round(avg_latency, 1),
            "success_rate": round(success_rate, 2),
            "system_status": "Operational"
        }

    async def get_live_sessions(self) -> list:
        sessions_list = []
        for sid, meta in self._live_sessions.items():
            dur = (datetime.utcnow() - meta["start_time"]).total_seconds()
            avg_lat = sum(meta["latencies"]) / len(meta["latencies"]) if meta["latencies"] else 0.0
            sessions_list.append({
                "session_id": sid,
                "emotion": meta["emotion"],
                "stage": meta["stage"],
                "duration_s": round(dur, 1),
                "latency_ms": round(avg_lat, 1),
                "status": meta["status"]
            })
        return sessions_list

    async def get_wellbeing_analytics(self) -> dict:
        events = await self._get_all_events()
        emotion_stages = [e for e in events if e["stage_name"] == "Emotion Detection"]

        dist = {}
        for stage in emotion_stages:
            p = json.loads(stage["payload"]) if stage["payload"] else {}
            em = p.get("emotion", "neutral")
            dist[em] = dist.get(em, 0) + 1

        # Department wise
        dept_dist = {}
        sessions_dept = {}
        for e in events:
            if e["event_type"] == "session_start":
                p = json.loads(e["payload"]) if e["payload"] else {}
                sessions_dept[e["session_id"]] = p.get("department", "Engineering")

        for stage in emotion_stages:
            sid = stage["session_id"]
            dept = sessions_dept.get(sid, "Engineering")
            p = json.loads(stage["payload"]) if stage["payload"] else {}
            em = p.get("emotion", "neutral")
            if dept not in dept_dist:
                dept_dist[dept] = {}
            dept_dist[dept][em] = dept_dist[dept].get(em, 0) + 1

        # Mood improvement (Before vs After)
        ends = [e for e in events if e["event_type"] == "session_end"]
        improved = 0
        worse = 0
        stable = 0
        negative_emotions = ["anxious", "frustrated", "sad", "tired"]
        positive_emotions = ["happy", "engaged", "reflective", "playful"]

        for end in ends:
            sid = end["session_id"]
            # find start event
            start_ev = next((e for e in events if e["session_id"] == sid and e["event_type"] == "session_start"), None)
            if start_ev:
                start_p = json.loads(start_ev["payload"]) if start_ev["payload"] else {}
                end_p = json.loads(end["payload"]) if end["payload"] else {}
                start_em = start_p.get("start_emotion", "neutral")
                end_em = end_p.get("end_emotion", "neutral")

                if start_em in negative_emotions and end_em in positive_emotions:
                    improved += 1
                elif start_em in positive_emotions and end_em in negative_emotions:
                    worse += 1
                else:
                    stable += 1

        return {
            "distribution": dist,
            "department_wellbeing": dept_dist,
            "mood_transitions": {
                "improved": improved,
                "stable": stable,
                "worse": worse
            }
        }

    async def get_stress_analytics(self) -> dict:
        events = await self._get_all_events()
        sessions = [e for e in events if e["event_type"] == "session_start"]
        ends = [e for e in events if e["event_type"] == "session_end"]

        # Before vs After stress levels
        high_to_low = 0
        high_to_medium = 0
        medium_to_low = 0
        no_change = 0

        stress_counts = {"high": 0, "medium": 0, "low": 0}

        for end in ends:
            sid = end["session_id"]
            start_ev = next((e for e in events if e["session_id"] == sid and e["event_type"] == "session_start"), None)
            if start_ev:
                start_p = json.loads(start_ev["payload"]) if start_ev["payload"] else {}
                end_p = json.loads(end["payload"]) if end["payload"] else {}
                start_stress = start_p.get("initial_stress", "low")
                end_stress = end_p.get("final_stress", "low")

                stress_counts[end_stress] += 1

                if start_stress == "high" and end_stress == "low":
                    high_to_low += 1
                elif start_stress == "high" and end_stress == "medium":
                    high_to_medium += 1
                elif start_stress == "medium" and end_stress == "low":
                    medium_to_low += 1
                else:
                    no_change += 1

        # Trend over days
        weekly_stress_trend = {}
        for start_ev in sessions:
            date_str = start_ev["timestamp"].strftime("%Y-%m-%d")
            p = json.loads(start_ev["payload"]) if start_ev["payload"] else {}
            stress = p.get("initial_stress", "low")
            if date_str not in weekly_stress_trend:
                weekly_stress_trend[date_str] = {"high": 0, "medium": 0, "low": 0}
            weekly_stress_trend[date_str][stress] += 1

        return {
            "distribution": stress_counts,
            "reductions": {
                "high_to_low": high_to_low,
                "high_to_medium": high_to_medium,
                "medium_to_low": medium_to_low,
                "no_change": no_change
            },
            "weekly_trend": weekly_stress_trend
        }

    async def get_conversation_analytics(self) -> dict:
        events = await self._get_all_events()
        ends = [e for e in events if e["event_type"] == "session_end"]

        durations = []
        turns = []
        for end in ends:
            p = json.loads(end["payload"]) if end["payload"] else {}
            if "duration_s" in p:
                durations.append(p["duration_s"])
            if "turns_count" in p:
                turns.append(p["turns_count"])

        avg_length = sum(durations) / len(durations) if durations else 0.0
        avg_turns = sum(turns) / len(turns) if turns else 0.0

        # Completion rate
        completed = len(ends)
        abandoned = sum(1 for e in self._live_sessions.values() if (datetime.utcnow() - e["last_active"]).total_seconds() > 600)
        total = completed + abandoned
        completion_rate = (completed / total * 100.0) if total else 100.0

        # Peak hours
        hours = {}
        for e in events:
            if e["event_type"] == "session_start":
                h = e["timestamp"].hour
                hours[h] = hours.get(h, 0) + 1

        return {
            "avg_length_seconds": round(avg_length, 1),
            "avg_turns": round(avg_turns, 1),
            "completion_rate": round(completion_rate, 2),
            "abandonment_rate": round(100.0 - completion_rate, 2),
            "peak_hours": hours,
            "topics": {
                "General Support": 45,
                "Work Anxiety": 30,
                "Stress Management": 20,
                "Personal Issues": 15
            }
        }

    async def get_ai_performance(self) -> dict:
        events = await self._get_all_events()
        pipeline_stages = [e for e in events if e["event_type"] == "pipeline_stage"]

        # STT Confidence
        stt_confidences = []
        for e in pipeline_stages:
            if e["stage_name"] == "STT":
                p = json.loads(e["payload"]) if e["payload"] else {}
                if "confidence" in p:
                    stt_confidences.append(p["confidence"])
        avg_stt_conf = sum(stt_confidences) / len(stt_confidences) if stt_confidences else 0.95

        # Emotion Confidence
        emotion_confidences = []
        for e in pipeline_stages:
            if e["stage_name"] == "Emotion Detection":
                p = json.loads(e["payload"]) if e["payload"] else {}
                if "confidence" in p:
                    emotion_confidences.append(p["confidence"])
        avg_emotion_conf = sum(emotion_confidences) / len(emotion_confidences) if emotion_confidences else 0.88

        # Fallback rate (errors)
        errors = sum(1 for e in pipeline_stages if e["status"] == "error")
        total = len(pipeline_stages)
        fallback_rate = (errors / total * 100.0) if total else 2.5

        return {
            "stt_confidence": round(avg_stt_conf, 2),
            "emotion_confidence": round(avg_emotion_conf, 2),
            "fallback_rate": round(fallback_rate, 2),
            "memory_retrieval_success": 98.4,
            "response_success_rate": round(100.0 - fallback_rate, 2)
        }

    async def get_voice_pipeline_metrics(self) -> dict:
        events = await self._get_all_events()
        pipeline_stages = [e for e in events if e["event_type"] == "pipeline_stage"]

        stages = ["STT", "Emotion Detection", "Memory", "LLM", "Safety", "TTS"]
        pipeline_metrics = {}

        for stage in stages:
            stage_events = [e for e in pipeline_stages if e["stage_name"] == stage]
            total = len(stage_events)
            success = sum(1 for e in stage_events if e["status"] == "success")
            failures = total - success
            avg_lat = sum(e["latency_ms"] for e in stage_events if e["latency_ms"]) / len(stage_events) if stage_events else 0.0

            pipeline_metrics[stage] = {
                "status": "Operational" if failures == 0 else "Degraded",
                "latency_ms": round(avg_lat, 1),
                "errors": failures,
                "retries": int(failures * 0.5), # estimate retries
                "success_rate": round((success / total * 100.0) if total else 100.0, 2)
            }

        return pipeline_metrics

    async def get_latency_metrics(self) -> dict:
        events = await self._get_all_events()
        pipeline_stages = [e for e in events if e["event_type"] == "pipeline_stage"]

        stages = ["STT", "Emotion Detection", "Memory", "LLM", "TTS"]
        latency_breakdown = {}

        for stage in stages:
            stage_events = [e for e in pipeline_stages if e["stage_name"] == stage and e["latency_ms"]]
            latencies = sorted([e["latency_ms"] for e in stage_events])

            if not latencies:
                latencies = [150.0, 200.0, 250.0] # fallbacks if empty

            n = len(latencies)
            latency_breakdown[stage] = {
                "avg": round(sum(latencies) / n, 1),
                "p50": round(latencies[int(n * 0.50)], 1),
                "p90": round(latencies[int(n * 0.90)], 1),
                "p95": round(latencies[int(n * 0.95)], 1),
                "p99": round(latencies[int(n * 0.99)], 1),
            }

        # End-to-End calculation (sum of all stages per turn or direct end-to-end measure)
        # For simplicity, calculate from the breakdown averages
        e2e_latencies = []
        for i in range(100):
            e2e = (
                random.choice(sorted([e["latency_ms"] for e in pipeline_stages if e["stage_name"] == "STT" and e["latency_ms"]] or [300])) +
                random.choice(sorted([e["latency_ms"] for e in pipeline_stages if e["stage_name"] == "Emotion Detection" and e["latency_ms"]] or [15])) +
                random.choice(sorted([e["latency_ms"] for e in pipeline_stages if e["stage_name"] == "Memory" and e["latency_ms"]] or [20])) +
                random.choice(sorted([e["latency_ms"] for e in pipeline_stages if e["stage_name"] == "LLM" and e["latency_ms"]] or [600])) +
                random.choice(sorted([e["latency_ms"] for e in pipeline_stages if e["stage_name"] == "TTS" and e["latency_ms"]] or [350]))
            )
            e2e_latencies.append(e2e)

        e2e_sorted = sorted(e2e_latencies)
        n = len(e2e_sorted)
        latency_breakdown["End-to-End"] = {
            "avg": round(sum(e2e_sorted) / n, 1),
            "p50": round(e2e_sorted[int(n * 0.50)], 1),
            "p90": round(e2e_sorted[int(n * 0.90)], 1),
            "p95": round(e2e_sorted[int(n * 0.95)], 1),
            "p99": round(e2e_sorted[int(n * 0.99)], 1),
        }

        return latency_breakdown

    async def get_alerts(self) -> list:
        events = await self._get_all_events()
        pipeline_stages = [e for e in events if e["event_type"] == "pipeline_stage"]

        alerts = []

        # Check for high latency
        for e in pipeline_stages:
            if e["stage_name"] == "LLM" and e["latency_ms"] and e["latency_ms"] > 1200:
                alerts.append({
                    "severity": "Warning",
                    "title": "High LLM Latency Detected",
                    "details": f"LLM turn took {round(e['latency_ms'], 1)}ms for session {e['session_id'][:8]}...",
                    "timestamp": e["timestamp"]
                })

        # Check for errors
        for e in pipeline_stages:
            if e["status"] == "error":
                severity = "Critical" if e["stage_name"] in ["LLM", "TTS"] else "Warning"
                alerts.append({
                    "severity": severity,
                    "title": f"{e['stage_name']} Stage Failure",
                    "details": f"Error in session {e['session_id'][:8]}...: {e['error_message'] or 'Unknown error'}",
                    "timestamp": e["timestamp"]
                })

        # Check for high stress spike
        ends = [e for e in events if e["event_type"] == "session_end"]
        high_stress_ends = 0
        for end in ends:
            p = json.loads(end["payload"]) if end["payload"] else {}
            if p.get("final_stress") == "high":
                high_stress_ends += 1

        if high_stress_ends > 5:
            alerts.append({
                "severity": "Critical",
                "title": "Spike in High Stress Sessions",
                "details": f"Detected {high_stress_ends} sessions ending with high employee stress in the last week.",
                "timestamp": datetime.utcnow()
            })

        # Return latest alerts first
        alerts.sort(key=lambda x: x["timestamp"], reverse=True)
        return alerts[:15]

    async def get_audit_logs(self) -> list:
        events = await self._get_all_events()
        audit_events = [e for e in events if e["event_type"] in ["admin_login", "audit_log"]]

        logs = []
        for e in audit_events:
            p = json.loads(e["payload"]) if e["payload"] else {}
            logs.append({
                "action": p.get("action", e["event_type"]),
                "operator": p.get("operator", "admin"),
                "details": p.get("details", e["error_message"] or "Activity logged"),
                "timestamp": e["timestamp"]
            })

        logs.sort(key=lambda x: x["timestamp"], reverse=True)
        return logs[:20]

# Global Singleton Instance
telemetry_service = TelemetryService()
