# Tabclose: an agent that keeps watching after you close the tab

*I created this piece of content for the purpose of entering the All Things Agentic Hackathon (Google x Devpost).*

## The problem

A solo founder ships one Cloud Run API and closes the laptop. Nobody is watching it. Traditional monitoring pages you, but you have to be awake, at a screen, and trust a single signal that could be a false alarm.

Tabclose is pager duty for that one API. It is built for **The Taskmaster** track: a job that keeps running after the request that started it is gone.

## What it does

1. **It runs after the tab closes.** Tabclose is a Cloud Run *Job* triggered by Cloud Scheduler, not a request-scoped handler. Closing the browser has zero effect on it. That is the whole point of the track.
2. **It refuses to trust a single observer.** When the primary probe thinks the API is down, Tabclose does not act. It asks a **second, independent observer running in a different region** to confirm. Only a corroborated outage is believed. One observer seeing a blip is not an incident.
3. **It leaves an artifact.** On a confirmed outage it writes the incident file to GCS and drafts a status update, so there is a durable record and a ready-to-send message, without the agent ever tweeting, paging, or restarting production on its own. The human commits anything irreversible.

## Why the second observer matters (the validator)

The core of Tabclose is a deterministic corroboration validator with veto power over the model. Gemini can suspect an outage all it wants; if the second regional observer does not see it, the validator vetoes and no incident is written. Delete that validator and a single flaky probe would fire false incidents. That is how you tell a real agent from a wrapper: removing the validator visibly changes the outcome.

## The stack

- **Gemini 2.5 Flash** via the Google **Agent Development Kit (ADK)** `LlmAgent`.
- **Cloud Run Jobs** (the agent tick) + **Cloud Scheduler** (the trigger).
- **Cloud Functions** in a second region as the independent Observer B.
- **Firestore** for idempotency and state, **GCS** for the incident artifact.
- Idempotency keyed on `(subject, detection window)` so a re-fired scheduler tick never writes a duplicate incident.

## Try it out

The offline end-to-end demo runs in your browser, zero setup, and shows the corroboration DENY/CONFIRM live:

**https://tabclose-taskmaster-agent.vercel.app**

Source: **https://github.com/kamalbuilds/tabclose-taskmaster-agent**

---

*Built for the All Things Agentic Hackathon. #AllThingsAgentic*
