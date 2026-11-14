# Compliance: photo evidence from Telegram (Issue #26)

The submission-wide legal basis, works council, provider, authentication and
licensing overview is [the root COMPLIANCE.md](../COMPLIANCE.md). This document
adds the implemented photo path and its specific limitations.

Stretch feature. Only synthetic photos and team test accounts; never real third
parties. Builds on the Telegram transport and retention of [TELEGRAM.md](TELEGRAM.md).

## What is processed

- Opt-in: the worker ingests `photo` messages only with
  `TELEGRAM_PHOTOS_ENABLED=true`, and only from allowlisted chat **and** sender.
  Files sent as documents, videos and stickers are ignored.
- The worker downloads the largest Telegram rendition up to 2 MB. Telegram
  normally re-encodes photo uploads, but SiteMind does not independently verify
  EXIF removal. Do not rely on metadata stripping as anonymisation. Oversized
  photos are skipped without blocking later updates.
- The image is stored as a `SourceAttachment` of the Telegram source message
  (the source of the derived Event). The caption is the source text.

## What leaves the API

- Only the image, the redacted caption (same masks as text extraction: emails,
  phone numbers, handles, sender ID) and the sender role go to the vision model.
  No chat/user IDs, usernames or timestamps. The LLM key stays in `api`.
- Image pixels are not blurred or redacted. Faces, signs and contact details can
  reach a live provider; caption redaction does not remove them. Keep this opt-in
  limited to synthetic images. Provider agreements and region/retention review
  must cover image processing as well as text.
- Vision runs only for Telegram sources; images from other channels (e.g. Gmail
  signatures) are never sent to the model.

## Faces and bystanders

- The prompt restricts findings to building elements and work state. It forbids
  describing, identifying or counting people, faces, clothing, vehicles or
  license plates. The model only reports `people_visible` as a boolean, stored in
  Event details so a reviewer knows the stored image shows people.
- No face detection, recognition or per-person metric is built. Flags stay on
  Zones, Tasks and trades (works council requirement).
- The test operator must ask team participants to photograph synthetic building
  elements, not colleagues, and explain the optional model transfer. The current
  bot notice is a general text/attachment notice, not photo-specific consent.
  A photo that shows people is still subject to the same retention. The prompt
  prohibition is not a technical guarantee that personal details cannot appear
  in generated findings.

## Retention and deletion

- Photos are raw data: `TELEGRAM_RETENTION_DAYS` (default 7, from API receipt)
  and `/delete_my_data` erase the attachment together with the caption (existing
  `erase_raw`). Retries cannot re-import erased photos.
- Retained for traceability: the Event (visual finding text, confidence, zone,
  `people_visible`, attachment ID and SHA-256 metadata), Evidence, Flag sources and
  audit. The prompt prohibits descriptions of people; the model output is not a
  verified anonymisation boundary.

## Evidence boundary (PLAN §3.2, #30)

- Every finding is an unconfirmed LLM statement (`origin: llm_vision`), even at
  high confidence. A closed-wall finding triggers the same deterministic Flag A
  check as a work announcement ("too late, but now known") and attaches to the
  matching Flag as a source. It never closes or acknowledges a Flag.
- A readable inspection tag becomes an *unconfirmed* inspection Evidence claim.
  It counts only after a human confirms it in the dashboard Evidence review (#9);
  counterclaims still need their own review. Zones come only from the caption,
  never guessed from the image: the API drops zone labels not found in it.
- The model may name the visible trade (e.g. drywall for gypsum boarding) so a
  photo from a sender without Crew mapping matches the right Task; it names
  work, never a person.
