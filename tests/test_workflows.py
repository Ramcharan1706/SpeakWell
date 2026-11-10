import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import server


class PracticeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db_path = server.DB_PATH
        server.DB_PATH = Path(self.tmp.name) / "workflow.sqlite3"
        server.EVENT_HISTORY.clear()
        server.init_db()
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        server.DB_PATH = self.original_db_path
        self.tmp.cleanup()

    def test_practice_feedback_is_saved_and_published(self):
        self.assertTrue(self.client.get("/api/health").json()["ok"])
        exercises = self.client.get("/api/exercises").json()["exercises"]
        exercise = next(item for item in exercises if item["id"] == "r-sound")

        response = self.client.post("/api/practice/feedback", json={
            "exercise_id": exercise["id"],
            "transcript": exercise["target"],
        })

        self.assertEqual(response.status_code, 201)
        result = response.json()
        self.assertEqual(result["feedback"]["prompt_word_overlap_percent"], 100)
        saved = self.client.get("/api/sessions").json()["sessions"]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["id"], result["session_id"])
        event = json.loads(server.EVENT_HISTORY[-1])
        self.assertEqual(event["id"], result["session_id"])
        self.assertEqual(event["type"], "session.created")

    def test_invalid_practice_does_not_create_session_or_event(self):
        response = self.client.post("/api/practice/feedback", json={
            "exercise_id": "missing-exercise",
            "transcript": "A test sample",
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/sessions").json()["sessions"], [])
        self.assertEqual(len(server.EVENT_HISTORY), 0)

    def test_completed_conversation_is_persisted_and_published(self):
        conversation = self.client.get("/api/conversations").json()["conversations"][0]
        turns = [
            {"turn_index": index, "transcript": f"Response for turn {index + 1}"}
            for index in range(len(conversation["turns"]))
        ]
        response = self.client.post("/api/conversations/complete", json={
            "conversation_id": conversation["id"], "turns": turns
        })

        self.assertEqual(response.status_code, 201)
        result = response.json()
        self.assertEqual(result["feedback"]["activity_type"], "conversation")
        self.assertEqual(result["feedback"]["completed_turns"], 3)
        self.assertNotIn("prompt_word_overlap_percent", result["feedback"])
        saved = self.client.get("/api/sessions").json()["sessions"]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["id"], result["session_id"])
        self.assertIn("Response for turn 3", saved[0]["transcript"])
        self.assertEqual(json.loads(server.EVENT_HISTORY[-1])["id"], result["session_id"])

    def test_incomplete_conversation_is_not_saved(self):
        conversation = self.client.get("/api/conversations").json()["conversations"][0]
        response = self.client.post("/api/conversations/complete", json={
            "conversation_id": conversation["id"],
            "turns": [{"turn_index": 0, "transcript": "A response"}],
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/sessions").json()["sessions"], [])
        self.assertEqual(len(server.EVENT_HISTORY), 0)

    def test_gemini_conversation_is_saved_with_turn_count(self):
        response = self.client.post("/api/gemini/save", json={
            "scenario": "cafe-order",
            "history": [
                {"role": "user", "text": "Let's practise a cafe conversation."},
                {"role": "model", "text": "Welcome! What can I get for you?"},
                {"role": "user", "text": "Could I have a tea?"},
                {"role": "model", "text": "Would you like anything else?"},
            ],
        })

        self.assertEqual(response.status_code, 201)
        saved = self.client.get("/api/sessions").json()["sessions"]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["target"], "AI conversation · At a neighborhood cafe")
        self.assertEqual(saved[0]["feedback"]["activity_type"], "ai_conversation")
        self.assertEqual(saved[0]["feedback"]["completed_turns"], 1)
        self.assertIn("You: Could I have a tea?", saved[0]["transcript"])
        self.assertEqual(json.loads(server.EVENT_HISTORY[-1])["type"], "session.created")

    def test_gemini_conversation_cannot_save_without_a_completed_exchange(self):
        response = self.client.post("/api/gemini/save", json={
            "scenario": "open-conversation",
            "history": [
                {"role": "user", "text": "Let's talk."},
                {"role": "model", "text": "Hello!"},
            ],
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/sessions").json()["sessions"], [])
        self.assertEqual(len(server.EVENT_HISTORY), 0)


if __name__ == "__main__":
    unittest.main()
