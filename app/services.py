import json
import os
from pathlib import Path

# Load a local .env file without requiring third-party packages. Existing shell
# variables always take precedence. Never print secret values.
def _load_dotenv():
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("\"'")
        if key and value:
            os.environ.setdefault(key, value)

_load_dotenv()

EXERCISES = [
    {"id":"clear-speech","title":"Clear speech warm-up","level":"Beginner","duration":"3 min","target":"Please speak slowly and clearly.","tip":"Try a comfortable pace. Pause naturally between words."},
    {"id":"r-sound","title":"R sound practice","level":"Guided","duration":"4 min","target":"Red roses grow near the river.","tip":"Listen to the model, then practise at your own pace. A clinician can tailor the target sound."},
    {"id":"sentence-flow","title":"Sentence flow","level":"Intermediate","duration":"4 min","target":"Today I am practising speaking with a steady rhythm.","tip":"Focus on comfortable phrasing and natural pauses."},
    {"id":"everyday-conversation","title":"Everyday conversation","level":"Open practice","duration":"5 min","target":"Hello, could you please tell me where the library is?","tip":"Practise a phrase you might use in a real conversation."}
]

CONVERSATIONS = [
    {
        "id": "cafe-order",
        "title": "At a neighborhood cafe",
        "category": "Everyday errands",
        "level": "Beginner",
        "duration": "3 turns",
        "situation": "Order a drink, answer a follow-up, and finish the interaction.",
        "turns": [
            {"partner": "Hi there! What can I get started for you?", "goal": "Order a drink. Add a size or temperature if you like.", "starter": "Could I have a ..."},
            {"partner": "Would you like anything to eat with that?", "goal": "Accept, decline, or ask what is available.", "starter": "No, thank you. / What snacks do you have?"},
            {"partner": "What name should I put on the order?", "goal": "Give a first name and close politely.", "starter": "It's ... Thanks!"},
        ],
    },
    {
        "id": "library-help",
        "title": "Finding a book at the library",
        "category": "Asking for help",
        "level": "Beginner",
        "duration": "3 turns",
        "situation": "Ask a librarian for help finding a book and learn how to borrow it.",
        "turns": [
            {"partner": "Hello! What can I help you find today?", "goal": "Ask for a kind of book, subject, or section.", "starter": "I'm looking for ..."},
            {"partner": "Do you have a particular author or title in mind?", "goal": "Share a preference, or ask for a recommendation.", "starter": "I enjoy books about ..."},
            {"partner": "I can help you check it out. Do you have a library card?", "goal": "Respond and ask one question if you have one.", "starter": "Yes, I do. / How long can I borrow it?"},
        ],
    },
    {
        "id": "appointment-call",
        "title": "Booking an appointment",
        "category": "Phone calls",
        "level": "Guided",
        "duration": "3 turns",
        "situation": "Call an office to arrange a routine appointment. No personal or medical details are needed.",
        "turns": [
            {"partner": "Good morning, how can I help you?", "goal": "Say you would like to book an appointment.", "starter": "I'd like to make an appointment, please."},
            {"partner": "What day or time works best for you?", "goal": "Suggest a day or ask what times are available.", "starter": "Do you have anything available on ...?"},
            {"partner": "I have you down for that time. Is there anything else?", "goal": "Confirm the time and end the call politely.", "starter": "That works for me. Thank you."},
        ],
    },
    {
        "id": "asking-directions",
        "title": "Asking for directions",
        "category": "Getting around",
        "level": "Beginner",
        "duration": "3 turns",
        "situation": "Ask someone for directions and check that you understood.",
        "turns": [
            {"partner": "Hello! Can I help you with something?", "goal": "Ask how to get to a nearby place.", "starter": "Could you tell me how to get to ...?"},
            {"partner": "Go straight and turn left at the next street.", "goal": "Check the directions or ask how far it is.", "starter": "So I go straight, then turn left?"},
            {"partner": "Yes, it's just past the park. You can't miss it.", "goal": "Thank them and finish the conversation.", "starter": "Thanks for your help!"},
        ],
    },
    {
        "id": "making-plans",
        "title": "Making weekend plans",
        "category": "Social conversations",
        "level": "Open practice",
        "duration": "3 turns",
        "situation": "Make a simple plan with a friend. There is no single correct response.",
        "turns": [
            {"partner": "Are you free to do something this weekend?", "goal": "Say whether you are free and suggest an activity.", "starter": "I'm free on ... Would you like to ...?"},
            {"partner": "That sounds fun. What time should we meet?", "goal": "Suggest a time and place.", "starter": "How about meeting at ... around ...?"},
            {"partner": "Perfect. I'll see you then!", "goal": "Confirm the plan and respond warmly.", "starter": "Great, see you then!"},
        ],
    },
    {
        "id": "store-return",
        "title": "Returning an item to a store",
        "category": "Everyday errands",
        "level": "Guided",
        "duration": "3 turns",
        "situation": "Explain a simple return request and ask about the next step.",
        "turns": [
            {"partner": "Hi! How can I help you today?", "goal": "Explain that you would like to return an item.", "starter": "I'd like to return this because ..."},
            {"partner": "Do you have the receipt with you?", "goal": "Answer and ask what options are available.", "starter": "Yes, here it is. / What are my options?"},
            {"partner": "We can exchange it or refund your payment.", "goal": "Choose an option and close politely.", "starter": "I'd prefer ... Thank you."},
        ],
    },
]

class PracticeService:
    def exercises(self):
        return EXERCISES

    def conversations(self):
        return CONVERSATIONS

    def conversation_feedback(self, data):
        conversation_id = str(data.get("conversation_id", "")).strip()
        conversation = next((item for item in CONVERSATIONS if item["id"] == conversation_id), None)
        if not conversation:
            raise ValueError("Choose a valid conversation")

        turns = data.get("turns")
        if not isinstance(turns, list) or len(turns) != len(conversation["turns"]):
            raise ValueError(f"Complete all {len(conversation['turns'])} conversation turns")

        lines = []
        total_characters = 0
        for index, turn in enumerate(turns):
            if not isinstance(turn, dict) or turn.get("turn_index") != index:
                raise ValueError("Conversation turns must be submitted in order")
            transcript = str(turn.get("transcript", "")).strip()
            if not transcript:
                raise ValueError(f"Add a transcript for turn {index + 1}")
            total_characters += len(transcript)
            if total_characters > 5000:
                raise ValueError("Conversation transcript must be 5,000 characters or fewer")
            lines.extend([
                f"Partner: {conversation['turns'][index]['partner']}",
                f"You: {transcript}",
            ])

        return {
            "exercise_id": conversation_id,
            "target": conversation["title"],
            "transcript": "\n".join(lines),
            "feedback": {
                "activity_type": "conversation",
                "completed_turns": len(turns),
                "message": "Role-play complete. Your responses are saved so you can reflect or practise the scenario again.",
                "disclaimer": "This transcript is for reflection only. It does not assess pronunciation, conversation quality, or clinical progress.",
            },
        }

    def feedback(self, data):
        exercise_id = str(data.get("exercise_id", "")).strip()
        transcript = str(data.get("transcript", "")).strip()
        if len(transcript) > 2000:
            raise ValueError("Transcript must be 2,000 characters or fewer")
        exercise = next((e for e in EXERCISES if e["id"] == exercise_id), None)
        if not exercise:
            raise ValueError("Choose a valid exercise")
        if not transcript:
            raise ValueError("A transcript is required for this feedback flow")
        target_words = set(exercise["target"].lower().strip(".,?!").split())
        spoken_words = set(transcript.lower().strip(".,?!").split())
        overlap = len(target_words & spoken_words)
        score = round(100 * overlap / max(1, len(target_words)))
        feedback = {
            "prompt_word_overlap_percent": score,
            "word_coverage_percent": score,
            "matched_words": sorted(target_words & spoken_words),
            "missing_words": sorted(target_words - spoken_words),
            "message": "Your transcript includes many prompt words. Review the hints and practise again." if score >= 60 else "Keep practising in short, comfortable attempts. Try listening to the prompt again.",
            "disclaimer": "This is text overlap only. It does not measure pronunciation, articulation, fluency, or clinical progress; it is not a diagnosis or clinical assessment."
        }
        return {"exercise_id": exercise_id, "target": exercise["target"], "transcript": transcript, "feedback": feedback}

    def demo_reply(self, message):
        return ("I can help you choose a practice exercise, explain how to use the practice screen, "
                "or suggest a gentle next step. I cannot diagnose a speech or language condition. "
                "For personalised therapy goals, work with a qualified speech-language professional.")

class GeminiConversationClient:
    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    MAX_MESSAGES = 14
    MAX_HISTORY_CHARACTERS = 10000
    OPEN_SCENARIO = "open-conversation"
    LANGUAGE_NAMES = {
        "bn-IN": "Bengali",
        "en-IN": "English (India)",
        "gu-IN": "Gujarati",
        "hi-IN": "Hindi",
        "kn-IN": "Kannada",
        "ml-IN": "Malayalam",
        "mr-IN": "Marathi",
        "pa-IN": "Punjabi",
        "ta-IN": "Tamil",
        "te-IN": "Telugu",
    }

    def __init__(self, api_key=None, model=None, fallback_model=None):
        self.api_key = (api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")).strip()
        self.model = (
            model or os.getenv("GEMINI_MODEL", "").strip() or "gemini-2.5-flash"
        ).strip()
        self.fallback_model = (
            fallback_model or os.getenv("GEMINI_FALLBACK_MODEL", "").strip() or "gemini-3.8-flash"
        ).strip()
        self.configured = bool(self.api_key)

    def status(self):
        return {
            "configured": self.configured,
            "model": self.model,
            "message": "Gemini is configured; provider access will be verified by the first reply."
            if self.configured else "Add GEMINI_API_KEY to .env to enable live AI conversations.",
        }

    @staticmethod
    def _provider_error():
        return RuntimeError("Gemini request failed. Check your API key, account access, network, and model settings.")

    def _build_payload(self, scenario, language, history, start=False):
        if not self.configured:
            raise RuntimeError("Gemini is not configured. Add GEMINI_API_KEY to .env and restart SpeakWell.")
        if scenario == self.OPEN_SCENARIO:
            scenario_context = "an open, friendly everyday conversation chosen by the learner"
        else:
            selected = next((item for item in CONVERSATIONS if item["id"] == scenario), None)
            if not selected:
                raise ValueError("Choose a valid conversation scenario")
            scenario_context = f"{selected['title']}: {selected['situation']}"
        if not language.strip() or len(language) > 16:
            raise ValueError("Choose a supported conversation language")
        language_name = self.LANGUAGE_NAMES.get(language, language)
        if not isinstance(history, list) or len(history) > self.MAX_MESSAGES:
            raise ValueError("Conversation history is too long. Start a new conversation.")
        total_characters = 0
        previous_role = "model"
        for message in history:
            if not isinstance(message, dict) or message.get("role") not in {"user", "model"}:
                raise ValueError("Conversation messages must have a valid role and text")
            text = message.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                raise ValueError("Each conversation message must contain 1–2,000 characters")
            if message["role"] == previous_role:
                raise ValueError("Conversation messages must alternate between user and assistant")
            previous_role = message["role"]
            total_characters += len(text)
        if total_characters > self.MAX_HISTORY_CHARACTERS:
            raise ValueError("Conversation history is too long. Start a new conversation.")
        if start:
            if history:
                raise ValueError("A new conversation cannot include previous messages")
            contents = [{
                "role": "user",
                    "parts": [{"text": f"Start a friendly spoken role-play about {scenario_context}. Begin with one natural, short line addressed to the learner."}],
            }]
        else:
            if not history or history[-1]["role"] != "user":
                raise ValueError("Add your spoken or typed reply before asking Gemini to respond")
            contents = [
                {"role": message["role"], "parts": [{"text": message["text"]}]}
                for message in history
            ]

        payload = {
            "systemInstruction": {
                "parts": [{
                    "text": (
                        "You are a friendly, patient conversation partner for spoken-language practice. "
                        f"Speak in {language_name}. Stay in this scenario: {scenario_context}. Keep each response natural "
                        "and concise (at most two short sentences). Answer direct questions first, respond to what "
                        "the learner actually said, and use complete thoughts rather than fragments. Do not invent "
                        "personal facts about the learner. In role-play, you may add plausible fictional details "
                        "to keep the conversation moving, but never present them as facts about a real business or "
                        "person. Ask at most one relevant follow-up question. Do not score pronunciation, diagnose, "
                        "or claim clinical expertise. Never repeat private personal information."
                    )
                }]
            },
            "contents": contents,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 64},
        }
        return payload

    def reply(self, scenario, language, history, start=False):
        return self.reply_with_model(scenario, language, history, start)[0]

    def reply_with_model(self, scenario, language, history, start=False):
        payload = self._build_payload(scenario, language, history, start)
        import requests

        models = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models.append(self.fallback_model)
        data = None
        active_model = self.model
        for index, model in enumerate(models):
            try:
                response = requests.post(
                    self.API_URL.format(model=model),
                    headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=(5, 25),
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code == 429:
                    raise RuntimeError(
                        "Gemini is temporarily rate-limited. Wait a moment or check your Google AI quota."
                    ) from exc
                retryable = status_code is None or status_code >= 500
                if retryable and index + 1 < len(models):
                    continue
                raise self._provider_error() from exc
            try:
                data = response.json()
            except ValueError as exc:
                raise self._provider_error() from exc
            active_model = model
            break
        if data is None:
            raise self._provider_error()

        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = " ".join(part["text"].strip() for part in parts if isinstance(part.get("text"), str)).strip()
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise self._provider_error() from exc
        if not text:
            raise self._provider_error()
        return text, active_model

    def stream_reply_with_model(self, scenario, language, history, start=False):
        payload = self._build_payload(scenario, language, history, start)
        import requests

        models = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models.append(self.fallback_model)
        response = None
        active_model = self.model
        for index, model in enumerate(models):
            try:
                response = requests.post(
                    self.API_URL.replace(":generateContent", ":streamGenerateContent").format(model=model),
                    params={"alt": "sse"},
                    headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=(5, 25),
                    stream=True,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                if response is not None:
                    response.close()
                    response = None
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code == 429:
                    raise RuntimeError(
                        "Gemini is temporarily rate-limited. Wait a moment or check your Google AI quota."
                    ) from exc
                retryable = status_code is None or status_code >= 500
                if retryable and index + 1 < len(models):
                    continue
                raise self._provider_error() from exc
            active_model = model
            break
        if response is None:
            raise self._provider_error()

        def text_chunks():
            received_text = False
            try:
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if isinstance(line, bytes):
                        line = line.decode("utf-8")
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                        parts = chunk["candidates"][0]["content"]["parts"]
                        text = "".join(
                            part["text"] for part in parts if isinstance(part.get("text"), str)
                        )
                    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
                        raise self._provider_error() from exc
                    if text:
                        received_text = True
                        yield text
                if not received_text:
                    raise self._provider_error()
            except requests.RequestException as exc:
                raise self._provider_error() from exc
            finally:
                response.close()

        return text_chunks(), active_model

class GnaniClient:
    """Server-side client for the documented Gnani Prisma STT and Timbre TTS REST APIs."""
    STT_URL = "https://api.vachana.ai/stt/v3"

    def __init__(self):
        self.api_key = os.getenv("GNANI_API_KEY", "").strip()
        self.stt_model = os.getenv("GNANI_STT_MODEL", "prisma-v3.0")
        self.tts_model = os.getenv("GNANI_TTS_MODEL", "timbre-v2.5")
        self.tts_voice = os.getenv("GNANI_TTS_VOICE", "Nalini")
        self.mode = "live" if self.api_key else "unavailable"
        self.configured = bool(self.api_key)

    def status(self):
        return {
            "mode": "live" if self.api_key else "unavailable",
            "configured": bool(self.api_key),
            "capabilities": {"speech_to_text": bool(self.api_key), "text_to_speech": bool(self.api_key), "ai_companion": False, "pronunciation_assessment": False},
            "message": "Gnani credentials are configured; a successful live session is still required to verify provider access." if self.api_key else "Gnani API key is missing. Live speech is disabled; no demo mode is available.",
            "models": {"speech_to_text": self.stt_model, "reasoning": "Not configured", "text_to_speech": self.tts_model}
        }

    @staticmethod
    def _read_error(status_code=None):
        # Do not expose provider response bodies, which may contain sensitive data.
        if status_code == 401:
            return RuntimeError(
                "Gnani rejected the API key (HTTP 401). Set GNANI_API_KEY to an active "
                "Gnani API Key ID with Timbre access, then restart SpeakWell."
            )
        if status_code == 403:
            return RuntimeError(
                "Gnani denied this request (HTTP 403). Check that the API key has "
                "Timbre speech-synthesis access."
            )
        return RuntimeError("Gnani request failed. Check your API key, account access, network, and model settings.")

    def _require_key(self):
        if not self.api_key:
            raise RuntimeError("Gnani is not configured. Add GNANI_API_KEY to .env and restart SpeakWell.")

    def synthesize(self, text, language="en-IN"):
        self._require_key()
        text = str(text).strip()
        if not text or len(text) > 1000:
            raise ValueError("Text must contain 1–1,000 characters")
        import requests
        from gnani.tts import AudioConfig, GnaniTTSClient
        from gnani.tts.exceptions import APIError

        try:
            audio = GnaniTTSClient(api_key=self.api_key, timeout=60).synthesize(
                text,
                voice=self.tts_voice,
                model=self.tts_model,
                language=language,
                speed=1.0,
                audio_config=AudioConfig(
                    sample_rate=48000,
                    encoding="linear_pcm",
                    num_channels=1,
                    sample_width=2,
                    container="wav",
                ),
            )
        except APIError as exc:
            raise self._read_error(exc.status_code) from exc
        except (requests.RequestException, TimeoutError) as exc:
            raise self._read_error() from exc
        if len(audio) > 8 * 1024 * 1024:
            raise RuntimeError("Gnani audio response exceeded the size limit")
        if not audio:
            raise RuntimeError("Gnani returned empty audio")
        return audio, "audio/wav"
