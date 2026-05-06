# Email Assist MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local FastAPI MVP for campaign-based inquiry email sending, reply tracking, reminder control, attachment archiving, extraction, and export.

**Architecture:** Use a modular FastAPI single-process app with SQLite persistence and local file storage. Keep external SMTP/IMAP/AI operations behind service adapters so the core campaign state machine, matching, archiving, and extraction orchestration are testable without real credentials.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, Jinja2, pytest, openpyxl, python-multipart, httpx, pydantic-settings, standard-library SMTP/IMAP/email modules.

---

## File Structure

- `pyproject.toml`: project metadata, dependencies, pytest settings.
- `.gitignore`: exclude local config, database, generated campaign data, virtualenvs, caches.
- `README.md`: local setup, run, and verification instructions.
- `app/main.py`: FastAPI app factory and route registration.
- `app/config.py`: local settings loader and data directory defaults.
- `app/database.py`: SQLite connection, schema creation, row helpers.
- `app/models.py`: dataclasses/enums for campaign, recipient, messages, attachments, extraction fields.
- `app/services/campaigns.py`: campaign creation, recipient state transitions, all-replied detection.
- `app/services/matching.py`: reply matching confidence logic.
- `app/services/reminders.py`: deadline-minus-six-hour reminder selection and duplicate prevention.
- `app/services/storage.py`: campaign directory creation, safe file naming, body/raw/attachment writes.
- `app/services/extraction.py`: local attachment parsing and OpenAI-compatible extraction adapter.
- `app/services/exporting.py`: Excel summary and ZIP package creation.
- `app/services/mail.py`: SMTP/IMAP adapter interfaces and minimal standard-library implementation.
- `app/web.py`: HTML page routes and JSON/API actions for MVP workflows.
- `app/templates/*.html`: simple local Web UI pages.
- `tests/*.py`: focused behavior tests for state machine, matching, reminders, storage, extraction, export, and API smoke.

## Tasks

### Task 1: Project Scaffolding and Test Harness

- [ ] Create `pyproject.toml`, `.gitignore`, package directories, and a minimal app factory.
- [ ] Add a smoke test for `create_app()` and run it to verify imports.

### Task 2: Campaign State Machine

- [ ] Write failing tests for recipient transitions and `all_replied` detection.
- [ ] Implement campaign and recipient models plus campaign service methods.
- [ ] Verify tests pass.

### Task 3: Reply Matching

- [ ] Write failing tests for strict thread matching, fallback sender/subject matching, and low-confidence review state.
- [ ] Implement matching service.
- [ ] Verify tests pass.

### Task 4: Reminder Scheduling

- [ ] Write failing tests for deadline-minus-six-hour reminder eligibility, manual-vs-auto strategy, and duplicate suppression.
- [ ] Implement reminder service.
- [ ] Verify tests pass.

### Task 5: Storage and Attachment Extraction

- [ ] Write failing tests for safe campaign paths, attachment archiving, CSV/XLSX parsing, and unsupported-file error reporting.
- [ ] Implement storage and extraction services.
- [ ] Verify tests pass.

### Task 6: SQLite Persistence

- [ ] Write failing tests for schema initialization and campaign persistence round trip.
- [ ] Implement SQLite schema and repository helpers.
- [ ] Verify tests pass.

### Task 7: Exporting

- [ ] Write failing tests for Excel summary sheets and ZIP package contents.
- [ ] Implement export service.
- [ ] Verify tests pass.

### Task 8: FastAPI Web MVP

- [ ] Write failing API smoke tests for health, settings page, campaign create/list/detail, manual refresh placeholder, and export endpoint.
- [ ] Implement FastAPI routes and simple templates.
- [ ] Verify tests pass.

### Task 9: Mail and AI Adapters

- [ ] Write failing tests for SMTP message construction and OpenAI-compatible request payload construction using mock transports.
- [ ] Implement adapter interfaces and minimal standard-library/httpx integrations.
- [ ] Verify tests pass.

### Task 10: Documentation and Full Verification

- [ ] Update README with setup, run, data layout, credentials boundary, and known MVP limits.
- [ ] Run `pytest`.
- [ ] Run a syntax/import check.
- [ ] Report exact verification coverage and gaps.

## Self-Review

- Spec coverage: This plan covers local Web MVP, SMTP/IMAP adapters, reply tracking, deadline reminders, local storage, attachment parsing/AI adapter, Excel/ZIP export, and validation.
- Scope control: The first implementation is a working local MVP, not a production mail gateway or multi-user system.
- Placeholder scan: No implementation step depends on undefined external credentials; real SMTP/IMAP/AI calls are adapter-based and testable with mocks.
