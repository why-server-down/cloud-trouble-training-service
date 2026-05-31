# Frontend Implementation Tasks

This document tracks frontend work discovered while reviewing the backend and AI code.
Code changes for these tasks must stay under `frontend/`.

## Progress

- [x] Phase 1: Restore a clean frontend build
- [x] Phase 2: Connect the AI tutor UI
- [x] Phase 3: Unify mission status and hint score updates
- [x] Phase 4: Improve authentication lifecycle
- [x] Phase 5: Improve terminal connection feedback
- [x] Phase 6: Add a profile details page
- [x] Phase 7: Improve UI text and feedback
- [x] Phase 8: Add responsive workspace layout
- [x] Phase 9: Redesign the frontend as an incident drill console

## Phase 1: Restore A Clean Frontend Build

- [x] Add the missing `askTutor()` API client for `POST /api/chat/`.
- [x] Remove unused `MissionStatus` props and state.
- [x] Remove the unused React import from `src/main.tsx`.
- [x] Verify with `npm.cmd run build`.

## Phase 2: Connect The AI Tutor UI

- [x] Render `TutorChat` while a mission is active.
- [x] Add styles for the tutor panel and chat messages.
- [x] Reset the visible conversation when the active mission changes.
- [x] Show API failures without discarding the user's question.

## Phase 3: Unify Mission Status And Hint Score Updates

- [x] Replace direct `http://localhost:8000` mission status calls with `getMissionStatus()`.
- [x] Refresh the displayed score immediately after using a hint.
- [x] Close the active mission panel when polling reports `failed`, `completed`, or `abandoned`.
- [x] Decide how tutor hint levels map to `POST /api/missions/hint`.
- [x] Keep the backend scoring rules as the source of truth.

Tutor guidance level is derived from `min(hints_used, 3)`. Increasing the guidance level
requires a successful `POST /api/missions/hint`, so the backend remains responsible for scoring.

## Phase 4: Improve Authentication Lifecycle

- [x] Add an API client for `GET /api/auth/me`.
- [x] Display username, completed mission count, and total score.
- [x] Add an API client for `POST /api/auth/logout`.
- [x] Clear local authentication state when an API call returns `401`.

Authenticated API requests dispatch `auth-expired` on `401`. The app clears local credentials
and returns to the login screen. Profile statistics refresh every 15 seconds.

## Phase 5: Improve Terminal Connection Feedback

- [x] Print a new prompt after terminal validation errors.
- [x] Improve WebSocket disconnect and reconnect feedback.
- [x] Review whether stale terminal session IDs should be replaced after reload.

WebSocket disconnects retry up to 3 times with a 2-second delay. Reloading with a stored token
creates a fresh terminal session instead of reusing a potentially stale session ID.

## Phase 6: Add A Profile Details Page

- [x] Open the profile details page from the header summary.
- [x] Display account information and the statistics available from `GET /api/auth/me`.
- [x] Calculate the average completed-mission score from backend profile statistics.
- [x] Allow the user to refresh profile statistics manually.

Mission history and per-mission statistics need a backend API before they can be displayed.

## Phase 7: Improve UI Text And Feedback

- [x] Clean up broken Korean text in the login, mission, tutor, and terminal screens.
- [x] Replace mission `alert()` calls with in-app toast messages.
- [x] Replace mission and terminal `confirm()` calls with an in-app confirmation modal.
- [x] Remove terminal debug logging and stale local simulation output.
- [x] Provide readable frontend copy for mission seed data that currently contains broken text.

## Phase 8: Add Responsive Workspace Layout

- [x] Keep the desktop mission and terminal split layout.
- [x] Add mission and terminal tabs for smaller screens.
- [x] Keep both panels mounted while switching tabs so the terminal connection remains active.
- [x] Adjust the header, mission cards, and action buttons for smaller screens.

## Phase 9: Redesign As An Incident Drill Console

- [x] Replace the generic dashboard styling with an operations-workbench visual language.
- [x] Use restrained incident colors, technical labels, and squared panel geometry.
- [x] Apply the visual system consistently to login, missions, terminal, profile, modal, and toast UI.
- [x] Preserve the responsive split layout and mobile workspace tabs.
- [x] Self-host `IBM Plex Sans KR` for Korean UI typography while keeping monospace technical labels.

## Backend And AI Follow-ups

These are integration issues found during review. They cannot be fixed from the frontend-only
scope, so they are recorded here for coordination.

- [x] Verify the `ai-data` path used by `backend/app/ai/tutor_service.py`.
- [x] Align Qdrant usage in `ai-data` with backend dependencies and Docker Compose services.
- [x] Replace the Compose frontend `NEXT_PUBLIC_API_URL` variable with Vite build configuration.
- [ ] Validate WebSocket terminal session ownership on the backend.
