from __future__ import annotations

import unittest

from src.models.messages import CandidateMessage
from src.preprocess.pipeline import (
    build_dialog_turns,
    build_fewshot_candidates,
    build_persona_profile,
    build_persona_prompt,
    build_voice_utterances,
    clean_messages,
    select_fewshots,
)


class PreprocessEnhancementTests(unittest.TestCase):
    def _candidate(
        self,
        message_id: str,
        timestamp: int,
        text: str,
        conversation_id: str = "conv-1",
        sender_role: str = "target",
        sender_wxid: str = "wxid_target",
    ) -> CandidateMessage:
        return CandidateMessage(
            message_id=message_id,
            timestamp=timestamp,
            sender_role=sender_role,
            sender_wxid=sender_wxid,
            conversation_id=conversation_id,
            message_type="text",
            text=text,
            is_system=False,
        )

    def test_clean_messages_enriches_truth_fields(self) -> None:
        messages = clean_messages(
            [
                self._candidate("m1", 1, "  你好呀  "),
                self._candidate("m2", 2, "好的呀😊"),
                self._candidate("m3", 3, "明天见！"),
            ],
            min_text_length=2,
            source_parser="minimal_v1",
        )
        self.assertEqual(messages[0].display_text, "你好呀")
        self.assertEqual(messages[0].normalized_text, "你好呀")
        self.assertEqual(messages[0].turn_index, 1)
        self.assertEqual(messages[0].prev_message_id, "")
        self.assertEqual(messages[0].next_message_id, "m2")
        self.assertEqual(messages[1].prev_message_id, "m1")
        self.assertEqual(messages[1].next_message_id, "m3")
        self.assertEqual(messages[2].source_parser, "minimal_v1")

    def test_persona_profile_and_prompt_are_deterministic(self) -> None:
        messages = clean_messages(
            [
                self._candidate("m1", 1, "你今天回来吗？"),
                self._candidate("m2", 2, "好的呀😊"),
                self._candidate("m3", 3, "我刚到家，准备洗澡啦。"),
            ],
            min_text_length=2,
            source_parser="minimal_v1",
        )
        voice_utterances = build_voice_utterances(messages)
        profile = build_persona_profile(messages, voice_utterances, target_wxid="wxid_target")
        prompt = build_persona_prompt(profile)

        self.assertEqual(profile.target_wxid, "wxid_target")
        self.assertIn("你", profile.preferred_terms)
        self.assertIn("呀", profile.tone_words)
        self.assertIn("😊", profile.emojis)
        self.assertGreater(profile.question_ratio, 0)
        self.assertIn("高频语气词/口头禅", prompt)
        self.assertIn("常用 emoji", prompt)
        self.assertIn("禁止暴露 AI 身份", prompt)

    def test_fewshot_scoring_penalizes_duplicates_and_prefers_style(self) -> None:
        messages = clean_messages(
            [
                self._candidate("m1", 1, "吃饭了吗", sender_role="counterpart", sender_wxid="wxid_owner"),
                self._candidate("m2", 2, "好的", sender_role="target"),
                self._candidate("m3", 3, "吃饭了吗", sender_role="counterpart", sender_wxid="wxid_owner"),
                self._candidate("m4", 4, "好的", sender_role="target"),
                self._candidate("m5", 5, "回家了吗", sender_role="counterpart", sender_wxid="wxid_owner"),
                self._candidate("m6", 6, "好的呀😊", sender_role="target"),
            ],
            min_text_length=2,
            source_parser="minimal_v1",
        )
        turns = build_dialog_turns(messages)
        profile = build_persona_profile(messages, build_voice_utterances(messages), target_wxid="wxid_target")
        candidates = build_fewshot_candidates(turns, profile)
        selected = select_fewshots(candidates, limit=2)

        duplicate_candidate = next(item for item in candidates if item.response == "好的")
        styled_candidate = next(item for item in candidates if item.response == "好的呀😊")
        self.assertLess(duplicate_candidate.score, styled_candidate.score)
        self.assertEqual(selected[0].response, "好的呀😊")

    def test_dialog_turns_only_use_counterpart_to_target_pairs(self) -> None:
        messages = clean_messages(
            [
                self._candidate("m1", 1, "在吗", sender_role="counterpart", sender_wxid="wxid_owner"),
                self._candidate("m2", 2, "在", sender_role="target"),
                self._candidate("m3", 3, "晚点回你", sender_role="target"),
                self._candidate("m4", 4, "收到", sender_role="counterpart", sender_wxid="wxid_owner"),
                self._candidate("m5", 5, "好呀", sender_role="target"),
            ],
            min_text_length=1,
            source_parser="minimal_v1",
        )
        turns = build_dialog_turns(messages)
        self.assertEqual(
            [(turn.context_message_id, turn.response_message_id) for turn in turns],
            [("m1", "m2"), ("m4", "m5")],
        )


if __name__ == "__main__":
    unittest.main()
