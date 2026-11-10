import os
import unittest
from unittest.mock import Mock, patch
from app.services import PracticeService, GnaniClient, GeminiConversationClient
from gnani.tts.exceptions import APIError

class PracticeServiceTests(unittest.TestCase):
    def setUp(self): self.service = PracticeService()
    def test_exercises_available(self): self.assertGreaterEqual(len(self.service.exercises()), 4)
    def test_guided_conversations_have_multiple_turns(self):
        conversations = self.service.conversations()
        self.assertGreaterEqual(len(conversations), 6)
        self.assertTrue(all(len(item["turns"]) >= 3 for item in conversations))
    def test_exact_text_overlap(self):
        e=self.service.exercises()[0]
        result=self.service.feedback({"exercise_id":e["id"],"transcript":e["target"]})
        self.assertEqual(result["feedback"]["prompt_word_overlap_percent"],100)
        self.assertIn("does not measure pronunciation",result["feedback"]["disclaimer"])
    def test_partial_overlap(self):
        e=self.service.exercises()[0]
        result=self.service.feedback({"exercise_id":e["id"],"transcript":"Please speak"})
        self.assertLess(result["feedback"]["prompt_word_overlap_percent"],100)
    def test_reject_empty_transcript(self):
        with self.assertRaises(ValueError): self.service.feedback({"exercise_id":"clear-speech","transcript":""})
    def test_reject_unknown_exercise(self):
        with self.assertRaises(ValueError): self.service.feedback({"exercise_id":"bad","transcript":"hello"})
    def test_reject_long_transcript(self):
        with self.assertRaises(ValueError): self.service.feedback({"exercise_id":"clear-speech","transcript":"x"*2001})
    def test_conversation_feedback_saves_all_turns_without_a_score(self):
        conversation = self.service.conversations()[0]
        turns = [{"turn_index": index, "transcript": f"My response {index + 1}"}
                 for index in range(len(conversation["turns"]))]
        result = self.service.conversation_feedback({
            "conversation_id": conversation["id"], "turns": turns
        })

        self.assertEqual(result["feedback"]["activity_type"], "conversation")
        self.assertEqual(result["feedback"]["completed_turns"], 3)
        self.assertNotIn("prompt_word_overlap_percent", result["feedback"])
        self.assertIn("Partner: What name should I put on the order?", result["transcript"])
        self.assertIn("You: My response 3", result["transcript"])
    def test_conversation_feedback_rejects_missing_or_out_of_order_turns(self):
        conversation = self.service.conversations()[0]
        with self.assertRaisesRegex(ValueError, "Complete all"):
            self.service.conversation_feedback({
                "conversation_id": conversation["id"],
                "turns": [{"turn_index": 0, "transcript": "Hello"}],
            })
        turns = [{"turn_index": index, "transcript": "Hello"}
                 for index in range(len(conversation["turns"]))]
        turns[1]["turn_index"] = 0
        with self.assertRaisesRegex(ValueError, "in order"):
            self.service.conversation_feedback({
                "conversation_id": conversation["id"], "turns": turns
            })

class ProviderConfigTests(unittest.TestCase):
    def test_no_key_means_unavailable_not_demo(self):
        client=GnaniClient()
        if not client.api_key:
            self.assertFalse(client.configured)
            self.assertEqual(client.status()["mode"],"unavailable")
            self.assertFalse(client.status()["capabilities"]["speech_to_text"])

    def test_synthesize_uses_official_tts_client(self):
        with patch.dict(os.environ, {"GNANI_API_KEY": "test-key"}):
            with patch("gnani.tts.GnaniTTSClient") as tts_client:
                tts_client.return_value.synthesize.return_value = b"audio"
                audio, content_type = GnaniClient().synthesize(
                    "Please speak slowly and clearly.", "en-IN"
                )

        self.assertEqual(audio, b"audio")
        self.assertEqual(content_type, "audio/wav")
        tts_client.assert_called_once_with(api_key="test-key", timeout=60)
        options = tts_client.return_value.synthesize.call_args.kwargs
        self.assertEqual(options["model"], "timbre-v2.5")
        self.assertEqual(options["voice"], "Nalini")
        self.assertEqual(options["language"], "en-IN")
        self.assertEqual(options["audio_config"].container, "wav")

    def test_synthesize_sanitizes_provider_error(self):
        with patch.dict(os.environ, {"GNANI_API_KEY": "test-key"}):
            with patch("gnani.tts.GnaniTTSClient") as tts_client:
                tts_client.return_value.synthesize.side_effect = APIError(
                    403, "provider response must not be exposed"
                )
                with self.assertRaises(RuntimeError) as error:
                    GnaniClient().synthesize("Please speak.")

        self.assertNotIn("provider response", str(error.exception))

    def test_synthesize_explains_authentication_failure_without_leaking_provider_body(self):
        with patch.dict(os.environ, {"GNANI_API_KEY": "test-key"}):
            with patch("gnani.tts.GnaniTTSClient") as tts_client:
                tts_client.return_value.synthesize.side_effect = APIError(
                    401, "provider response must not be exposed"
                )
                with self.assertRaises(RuntimeError) as error:
                    GnaniClient().synthesize("Please speak.")

        self.assertIn("HTTP 401", str(error.exception))
        self.assertIn("Gnani API Key ID", str(error.exception))
        self.assertNotIn("provider response", str(error.exception))
        self.assertNotIn("test-key", str(error.exception))

class GeminiConversationTests(unittest.TestCase):
    def test_defaults_to_the_faster_model_with_a_resilience_fallback(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "", "GEMINI_FALLBACK_MODEL": ""}):
            client = GeminiConversationClient()
        self.assertEqual(client.model, "gemini-2.5-flash")
        self.assertEqual(client.fallback_model, "gemini-3.8-flash")

    def test_missing_key_disables_live_conversation(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            client = GeminiConversationClient()
        self.assertFalse(client.status()["configured"])
        with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
            client.reply("open-conversation", "en-IN", [], start=True)

    def test_reply_uses_context_and_official_generate_content_request(self):
        client = GeminiConversationClient(api_key="test-key", model="gemini-3.8-flash")
        response = Mock()
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "What would you like to drink?"}]}}]
        }
        history = [
            {"role": "user", "text": "I'd like to practise ordering at a cafe."},
            {"role": "model", "text": "Welcome! What can I get for you?"},
            {"role": "user", "text": "Could I have a tea?"},
        ]
        with patch("requests.post", return_value=response) as post:
            reply = client.reply("cafe-order", "en-IN", history)

        self.assertEqual(reply, "What would you like to drink?")
        args, kwargs = post.call_args
        self.assertEqual(args[0], client.API_URL.format(model="gemini-3.8-flash"))
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "test-key")
        self.assertEqual(kwargs["json"]["contents"][-1]["parts"][0]["text"], "Could I have a tea?")
        self.assertIn("Do not score pronunciation", kwargs["json"]["systemInstruction"]["parts"][0]["text"])
        self.assertIn("Answer direct questions first", kwargs["json"]["systemInstruction"]["parts"][0]["text"])
        self.assertIn("complete thoughts rather than fragments", kwargs["json"]["systemInstruction"]["parts"][0]["text"])
        self.assertEqual(kwargs["json"]["generationConfig"]["maxOutputTokens"], 64)
        self.assertEqual(kwargs["timeout"], (5, 25))

    def test_stream_reply_yields_text_chunks_and_closes_provider_response(self):
        import json
        client = GeminiConversationClient(api_key="test-key", model="gemini-2.5-flash")
        response = Mock()
        response.iter_lines.return_value = [
            f"data: {json.dumps({'candidates': [{'content': {'parts': [{'text': 'Hello '}]}}]})}",
            "",
            f"data: {json.dumps({'candidates': [{'content': {'parts': [{'text': 'there!'}]}}]})}",
        ]
        with patch("requests.post", return_value=response) as post:
            chunks, model = client.stream_reply_with_model(
                "open-conversation", "en-IN", [], start=True
            )
            self.assertEqual(list(chunks), ["Hello ", "there!"])

        self.assertEqual(model, "gemini-2.5-flash")
        self.assertEqual(
            post.call_args.args[0],
            client.API_URL.replace(":generateContent", ":streamGenerateContent").format(
                model="gemini-2.5-flash"
            ),
        )
        self.assertEqual(post.call_args.kwargs["params"], {"alt": "sse"})
        self.assertTrue(post.call_args.kwargs["stream"])
        response.close.assert_called_once()

    def test_start_builds_opening_prompt_without_history(self):
        client = GeminiConversationClient(api_key="test-key")
        response = Mock()
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Hello! How is your day going?"}]}}]
        }
        with patch("requests.post", return_value=response) as post:
            reply = client.reply("open-conversation", "en-IN", [], start=True)

        self.assertEqual(reply, "Hello! How is your day going?")
        self.assertIn("open, friendly everyday conversation", post.call_args.kwargs["json"]["systemInstruction"]["parts"][0]["text"])

    def test_invalid_scenario_and_non_alternating_history_are_rejected(self):
        client = GeminiConversationClient(api_key="test-key")
        with self.assertRaisesRegex(ValueError, "valid conversation scenario"):
            client.reply("user supplied instruction", "en-IN", [], start=True)
        with self.assertRaisesRegex(ValueError, "alternate"):
            client.reply("cafe-order", "en-IN", [
                {"role": "user", "text": "First"},
                {"role": "user", "text": "Second"},
            ])

    def test_provider_error_is_sanitized(self):
        import requests
        client = GeminiConversationClient(api_key="test-key")
        with patch("requests.post", side_effect=requests.Timeout("private response details")):
            with self.assertRaises(RuntimeError) as error:
                client.reply("open-conversation", "en-IN", [], start=True)
        self.assertNotIn("private response", str(error.exception))

    def test_temporary_provider_overload_uses_configured_fallback_model(self):
        import requests
        client = GeminiConversationClient(
            api_key="test-key", model="gemini-primary", fallback_model="gemini-fallback"
        )
        overloaded = requests.HTTPError("temporary overload")
        overloaded.response = Mock(status_code=503)
        response = Mock()
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Hello there!"}]}}]
        }
        with patch("requests.post", side_effect=[overloaded, response]) as post:
            result = client.reply_with_model("open-conversation", "en-IN", [], start=True)

        self.assertEqual(result, ("Hello there!", "gemini-fallback"))
        self.assertEqual(
            [call.args[0] for call in post.call_args_list],
            [
                client.API_URL.format(model="gemini-primary"),
                client.API_URL.format(model="gemini-fallback"),
            ],
        )

    def test_non_retryable_provider_error_does_not_use_fallback(self):
        import requests
        client = GeminiConversationClient(
            api_key="test-key", model="gemini-primary", fallback_model="gemini-fallback"
        )
        unauthorized = requests.HTTPError("unauthorized")
        unauthorized.response = Mock(status_code=403)
        with patch("requests.post", side_effect=unauthorized) as post:
            with self.assertRaises(RuntimeError):
                client.reply("open-conversation", "en-IN", [], start=True)

        post.assert_called_once()

    def test_rate_limit_returns_without_waiting_for_a_second_model(self):
        import requests
        client = GeminiConversationClient(
            api_key="test-key", model="gemini-primary", fallback_model="gemini-fallback"
        )
        rate_limited = requests.HTTPError("rate limited")
        rate_limited.response = Mock(status_code=429)
        with patch("requests.post", side_effect=rate_limited) as post:
            with self.assertRaisesRegex(RuntimeError, "rate-limited"):
                client.reply("open-conversation", "en-IN", [], start=True)

        post.assert_called_once()

    def test_status_does_not_expose_api_key(self):
        client = GeminiConversationClient(api_key="private-test-key")
        self.assertTrue(client.status()["configured"])
        self.assertNotIn("private-test-key", str(client.status()))

if __name__ == "__main__": unittest.main()
