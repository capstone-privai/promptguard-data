from integrations import anthropic_messages, openai_chat, openai_embeddings
from tests.support import IntegrationTest


class OpenAIChatTests(IntegrationTest):
    def test_complete_posts_messages_with_the_account_key(self):
        self.reply(json={"choices": [{"message": {"content": "Your parcel left Incheon."}}], "usage": {"total_tokens": 42}})
        text, calls, usage = openai_chat.complete(["where is OD-2026-00017?"], system="You are the order desk.")
        req = self.only_request()
        self.assertEqual((req.method, req.url), ("POST", "https://api.openai.com/v1/chat/completions"))
        self.assertEqual(req.header("Authorization"), "Bearer " + openai_chat.API_KEYS["default"])
        self.assertEqual(req.json()["messages"], [{"role": "system", "content": "You are the order desk."},
                                                  {"role": "user", "content": "where is OD-2026-00017?"}])
        self.assertEqual((text, calls, usage), ("Your parcel left Incheon.", [], {"total_tokens": 42}))

    def test_tool_calls_are_decoded(self):
        self.reply(json={"choices": [{"message": {"content": None, "tool_calls": [
            {"function": {"name": "set_intent", "arguments": "{\"intent\": \"refund\"}"}}]}}]})
        self.assertEqual(openai_chat.classify_intent("I want my money back", ["refund", "delivery"]), "refund")
        self.assertEqual(self.only_request().json()["temperature"], 0)

    def test_rate_limit_is_retried_then_reported(self):
        for _ in range(3):
            self.reply(429, headers={"Retry-After": "0"}, json={"error": {"message": "slow down"}})
        self.reply(json={"choices": [{"message": {"content": "- a\n- b\n- c\n- d"}}]})
        self.assertEqual(openai_chat.summarise_ticket("long ticket"), ["a", "b", "c"])
        self.assertEqual(len(self.sent), 4)
        self.assertEqual(self.sent[-1].header("Authorization"), "Bearer " + openai_chat.API_KEYS["batch"])

    def test_client_error_raises_chat_error(self):
        self.reply(400, json={"error": {"message": "max_tokens is too large"}})
        with self.assertRaises(openai_chat.ChatError) as ctx:
            openai_chat.complete(["hi"], max_tokens=10 ** 6)
        self.assertEqual(ctx.exception.status, 400)
        self.assertIn("max_tokens is too large", str(ctx.exception))


class EmbeddingTests(IntegrationTest):
    def test_inputs_are_batched_and_reordered(self):
        texts = [f"faq {i}" for i in range(70)]
        self.reply(json={"data": [{"index": i, "embedding": [i]} for i in reversed(range(64))]})
        self.reply(json={"data": [{"index": i, "embedding": [64 + i]} for i in range(6)]})
        self.assertEqual(openai_embeddings.embed(texts), [[i] for i in range(70)])
        self.assertEqual([len(r.json()["input"]) for r in self.sent], [64, 6])
        self.assertTrue(all(r.url == "https://api.openai.com/v1/embeddings" for r in self.sent))
        self.assertTrue(self.sent[0].header("Authorization").startswith("Bearer "))


class AnthropicTests(IntegrationTest):
    def test_send_includes_history_and_version_header(self):
        self.reply(json={"content": [{"type": "text", "text": "Sure."}], "stop_reason": "end_turn"})
        text, reason = anthropic_messages.send("and the refund?", history=[("hello", "hi")], system="desk")
        req = self.only_request()
        self.assertEqual(req.url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(req.header("x-api-key"), anthropic_messages.KEYS["prod"])
        self.assertEqual(req.header("anthropic-version"), "2023-06-01")
        self.assertEqual([m["role"] for m in req.json()["messages"]], ["user", "assistant", "user"])
        self.assertEqual((text, reason), ("Sure.", "end_turn"))

    def test_overloaded_is_retried_and_errors_are_typed(self):
        self.reply(529, json={"error": {"type": "overloaded_error", "message": "busy"}})
        self.reply(json={"input_tokens": 17})
        self.assertEqual(anthropic_messages.count_tokens("count me"), 17)
        self.assertEqual(self.sent[-1].header("x-api-key"), anthropic_messages.KEYS["eval"])
        self.reply(400, json={"error": {"type": "invalid_request_error", "message": "bad model"}})
        with self.assertRaises(anthropic_messages.ClaudeError) as ctx:
            anthropic_messages.send("x", model="nope")
        self.assertEqual(ctx.exception.kind, "invalid_request_error")

    def test_draft_reply(self):
        self.reply(json={"content": [{"type": "text", "text": " Hello, your order ships today. "}],
                         "stop_reason": "stop_sequence"})
        draft = anthropic_messages.draft_reply({"order": "OD-2026-00031", "body": "when?"})
        self.assertEqual(draft, {"order": "OD-2026-00031", "draft": "Hello, your order ships today.", "complete": True})
        self.assertEqual(self.only_request().json()["stop_sequences"], ["\n--\n"])
