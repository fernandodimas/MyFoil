---
name: Architecture Analysis
description: Analyzes the codebase to document its structure, stack, and data flow.
version: 1.0
---

# Architecture Analysis Skill

This skill guides the agent to analyze the current project state and produce a comprehensive `ARCHITECTURE.md` documentation file.

## Instructions

1.  **Analyze Directory Structure**:
    - List top-level directories and their likely roles.
    - Identify source code roots (e.g., `app/`).

2.  **Identify Technology Stack**:
    - Backend framework (Flask, Django, etc.).
    - Database (SQLite, PostgreSQL, etc.).
    - Async/Queueing (Celery, Gevent, etc.).
    - Frontend (JS, CSS frameworks).

3.  **Map Data Flow**:
    - How requests are handled (Routes -> Views -> Services -> DB).
    - Real-time updates (Socket.IO).
    - Background tasks (Celery/Gevent).

4.  **Docker & Deployment**:
    - Analyze `docker-compose.yml`.
    - startup scripts.

5.  **Output**:
    - Create or update `ARCHITECTURE.md` in the project root with the findings.
    - Format with clear sections: "Overview", "Tech Stack", "Directory Layout", "Data Flow", "Infrastructure".
