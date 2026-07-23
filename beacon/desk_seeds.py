from __future__ import annotations

from collections.abc import Mapping

PILOT_DESK_THREADS: tuple[Mapping[str, object], ...] = (
    {
        "seed_key": "pilot-20260723:inbox-copy-complete",
        "subject": "Tell me when the Inbox copy is finished",
        "kind": "blocker",
        "priority": "important",
        "requires_approval": False,
        "body": (
            "Verified need — I need a stable stopping point before I analyze the "
            "large intake. Please tell me when the current copy is completely "
            "finished. I will then verify that the files have stopped changing "
            "before starting; I will not inspect or analyze files that are still "
            "arriving."
        ),
    },
    {
        "seed_key": "pilot-20260723:ai-privacy-boundary",
        "subject": "Choose the privacy boundary for AI analysis",
        "kind": "approval",
        "priority": "important",
        "requires_approval": True,
        "body": (
            "Verified need — the five-asset pilot stayed local and sent no media "
            "to an external service. Please approve local-only analysis as "
            "Beacon’s default. Any future cloud or external-model use would "
            "remain off and require a separate, clearly named approval describing "
            "exactly which files would leave ATLAS."
        ),
    },
    {
        "seed_key": "pilot-20260723:candidate-only-metadata",
        "subject": "Approve candidate-only metadata storage",
        "kind": "approval",
        "priority": "important",
        "requires_approval": True,
        "body": (
            "Verified need — may I save Beacon’s titles, descriptions, tags, "
            "confidence, and evidence as suggestions beside the catalog facts? "
            "Accepting this does not authorize renaming, moving, deleting, or "
            "overwriting any original. Suggested metadata will remain visibly "
            "separate from verified facts until you accept or reject it."
        ),
    },
    {
        "seed_key": "pilot-20260723:portrait-context",
        "subject": "Who and what should I remember for “Us.JPG”?",
        "kind": "clarification",
        "priority": "normal",
        "requires_approval": False,
        "body": (
            "Optional enrichment — this is one portrait asset with two "
            "byte-identical file locations, not two separate photos. I can see "
            "two smiling adults outdoors, but I will not guess their identities "
            "or relationship. Tell me the people’s preferred names, the occasion "
            "or approximate date, and the title you would want to find later. "
            "You can also tell me to leave it generic."
        ),
    },
    {
        "seed_key": "pilot-20260723:branded-video-context",
        "subject": "Confirm the Happy Egg Co. video context",
        "kind": "clarification",
        "priority": "normal",
        "requires_approval": False,
        "body": (
            "Optional enrichment — the short video is clearly a Happy Egg Co. "
            "branded spot, but the client, campaign, usage rights, and filename "
            "shorthand are not verified. What project or client should it belong "
            "to? Do “Scott N Belinda,” “06,” “R2,” and “V1” identify talent, "
            "spot number, revision, and version? Please correct any part that "
            "does not."
        ),
    },
    {
        "seed_key": "pilot-20260723:audio-context",
        "subject": "How should I describe “Desert Dividend”?",
        "kind": "question",
        "priority": "normal",
        "requires_approval": False,
        "body": (
            "Optional enrichment — the WAV metadata says it was made with Suno, "
            "but I have not inferred its genre, mood, instruments, vocals, "
            "lyrics, or intended use. Tell me anything you already know—such as "
            "project, genre, mood, or whether it is a keeper—and I will preserve "
            "that as human-provided context. Deeper local audio analysis can be "
            "proposed separately."
        ),
    },
)
