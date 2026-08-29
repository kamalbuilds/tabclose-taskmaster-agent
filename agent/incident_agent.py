"""The ADK agent: classify the failure and draft a customer-facing status
update, from raw evidence, ONLY after the corroboration validator has
passed.

Bounded authority (AIM.md non-negotiable 5, DESIGN.md "Bounded authority"):
this module drafts text. It never publishes, tweets, pages, or restarts
anything. `draft_incident()` returns strings for `job/artifact.py` to write
to GCS; it has no network calls other than the Gemini API, and no side
effects beyond that.

Structural guard: `draft_incident()` takes the validator's `Verdict` object
as its first argument and raises immediately if `verdict.passed` is not
True. This is what makes "run the agent on a rejected verdict" impossible
without directly deleting this check -- which is exactly the delete-the-
validator test `tests/test_verifier_red_green.py` exercises.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from agentspine.validator import Verdict

MODEL_NAME = "gemini-3.5-flash"

INSTRUCTION = """You are the on-call assistant for a solo founder's single
production API. Two independent observers, in different regions, have BOTH
confirmed the service is failing (this has already been verified by a
deterministic check before you were invoked -- you are not being asked to
judge whether an outage is real).

Given the raw evidence from both observers, do two things:
1. Classify the failure into one short category, e.g. "5xx error",
   "timeout / unreachable", "connection refused", "unexpected response body".
2. Draft a short, calm, customer-facing status update (3-5 sentences) that:
   - states the service is degraded/investigating
   - does not overpromise a fix time
   - gives a concrete "next update in N minutes" commitment
   - does not name internal infrastructure details the customer doesn't need

Respond in exactly this format, nothing else:

CLASSIFICATION: <one short line>
STATUS:
<the drafted status.md body, markdown, no h1>
"""


@dataclass
class IncidentDraft:
    classification: str
    status_md: str
    raw_model_output: str


def _format_evidence(probe_a: dict, probe_b: dict) -> str:
    def fmt(label: str, p: dict) -> str:
        return (
            f"{label} ({p.get('region')}):\n"
            f"  ok: {p.get('ok')}\n"
            f"  status_code: {p.get('status_code')}\n"
            f"  latency_ms: {p.get('latency_ms')}\n"
            f"  timestamp: {p.get('timestamp')}\n"
            f"  error: {p.get('error')}\n"
            f"  body_snippet: {p.get('body_snippet', '')[:300]!r}\n"
        )

    return fmt("Observer A", probe_a) + "\n" + fmt("Observer B", probe_b)


def _classify_with_gemini(probe_a: dict, probe_b: dict, model: str = MODEL_NAME) -> str:
    """Real call path: builds a short-lived ADK LlmAgent + InMemoryRunner,
    sends one message, returns the final text response. One tick, one
    session, no long-running conversation -- see LIMITATIONS.md's ADK
    100-event-cap / _init_session-replay notes for why sessions stay short
    here rather than persisting across ticks.
    """
    import asyncio

    from google.adk.agents import LlmAgent
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    agent = LlmAgent(name="incident_agent", model=model, instruction=INSTRUCTION)
    runner = InMemoryRunner(agent=agent, app_name="tabclose")

    async def _run() -> str:
        session = await runner.session_service.create_session(
            app_name="tabclose", user_id="tabclose-job"
        )
        message = types.Content(
            role="user",
            parts=[types.Part(text=_format_evidence(probe_a, probe_b))],
        )
        final_text = ""
        async for event in runner.run_async(
            user_id="tabclose-job", session_id=session.id, new_message=message
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(p.text or "" for p in event.content.parts)
        return final_text

    return asyncio.run(_run())


def _parse_model_output(text: str) -> tuple[str, str]:
    """Split the model's CLASSIFICATION/STATUS response. Falls back to
    treating the whole thing as the status body if the model didn't follow
    the format, so a formatting slip never crashes the tick.
    """
    classification = "unclassified"
    status_body = text.strip()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("CLASSIFICATION:"):
            classification = line.split(":", 1)[1].strip()
        if line.strip().upper().startswith("STATUS:"):
            status_body = "\n".join(lines[i + 1:]).strip()
            break
    return classification, status_body


ClassifyFn = Callable[[dict, dict], str]


def draft_incident(
    verdict: Verdict,
    probe_a: dict,
    probe_b: dict,
    run_id: str,
    service_name: str,
    *,
    classify_fn: Optional[ClassifyFn] = None,
) -> IncidentDraft:
    """Classify the failure and draft status.md. HARD GUARD: raises unless
    `verdict.passed` is True. `job/main.py` never has a code path that
    reaches this function before the corroboration validator has run.

    `classify_fn` defaults to the real Gemini call; tests inject a fake so
    the offline suite never makes a network call.
    """
    if not verdict.passed:
        raise RuntimeError(
            "draft_incident() called with a rejected verdict -- the agent "
            "must never run on an incident the validator did not corroborate."
        )

    classify_fn = classify_fn or _classify_with_gemini
    raw = classify_fn(probe_a, probe_b)
    classification, status_body = _parse_model_output(raw)

    status_md = (
        f"# {service_name} — Service Status\n\n"
        f"**Status:** Investigating\n"
        f"**Run:** `{run_id}`\n"
        f"**Detected by:** two independent observers "
        f"({probe_a.get('region')}, {probe_b.get('region')})\n"
        f"**Classification:** {classification}\n\n"
        f"{status_body}\n\n"
        f"---\n"
        f"_This is a DRAFT written by an automated agent. A human has not yet "
        f"reviewed or published it._\n"
    )

    return IncidentDraft(classification=classification, status_md=status_md, raw_model_output=raw)


def draft_all_clear(run_id: str, service_name: str, probe_a: dict, probe_b: dict) -> str:
    """Deterministic, no model call: written by job/allclear.py once a later
    tick sees both observers recover. No classification is needed to say
    "it's back up", so this doesn't touch Gemini at all -- keeps the model's
    footprint limited to the one place it adds value.
    """
    return (
        f"# {service_name} — All Clear\n\n"
        f"**Status:** Resolved\n"
        f"**Run:** `{run_id}`\n"
        f"**Confirmed recovered by:** two independent observers "
        f"({probe_a.get('region')}, {probe_b.get('region')})\n\n"
        f"Both observers now report the service healthy. This incident is closed.\n"
    )
