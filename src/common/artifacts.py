from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactPaths:
    output_base: Path
    legacy_contacts: Path
    legacy_messages: Path
    legacy_fewshot: Path
    legacy_rag: Path
    legacy_persona: Path
    truth_contacts: Path
    truth_messages: Path
    truth_dialog_turns: Path
    truth_persona_profile: Path
    voice_utterances: Path
    retrieval_rag: Path
    retrieval_fewshot_candidates: Path
    retrieval_fewshot: Path
    persona_prompt: Path
    manifest: Path


def resolve_artifact_paths(output_base: Path) -> ArtifactPaths:
    return ArtifactPaths(
        output_base=output_base,
        legacy_contacts=output_base / "contacts.json",
        legacy_messages=output_base / "messages.normalized.jsonl",
        legacy_fewshot=output_base / "fewshot.json",
        legacy_rag=output_base / "rag_corpus.jsonl",
        legacy_persona=output_base / "persona_prompt.txt",
        truth_contacts=output_base / "truth" / "contacts.json",
        truth_messages=output_base / "truth" / "messages.normalized.jsonl",
        truth_dialog_turns=output_base / "truth" / "dialog_turns.jsonl",
        truth_persona_profile=output_base / "truth" / "persona_profile.json",
        voice_utterances=output_base / "voice" / "utterances.normalized.jsonl",
        retrieval_rag=output_base / "retrieval" / "rag_corpus.jsonl",
        retrieval_fewshot_candidates=output_base / "retrieval" / "fewshot_candidates.jsonl",
        retrieval_fewshot=output_base / "retrieval" / "fewshot.json",
        persona_prompt=output_base / "persona" / "persona_prompt.txt",
        manifest=output_base / "artifacts" / "manifest.json",
    )
