# Language Policy: UI & Code in English, User Interaction & Docs in Spanish

## Scope and Invariants
1. **User Interface (UI) 100% in English**:
   - All UI elements (MLOps Dashboard on port 8778, replay viewers, inspection modals, battle logs, plots, buttons, labels, tooltips, cards, headers, form controls, and user-facing frontend notifications) MUST be written in English.
   - Absolutely no Spanish text in the UI.

2. **Source Code 100% in English**:
   - All programming code (Python, JavaScript, TypeScript, HTML, CSS, SQL, shell scripts), identifiers (variables, functions, classes, modules, constants), docstrings, inline comments, log entries (`logger.*`, `print`), exception messages, and assertions MUST be written in English.
   - Absolutely no Spanish text in code or comments.

3. **User Interaction in Spanish**:
   - Conversations, answers, status updates, pair programming discussions, and explanations directed to the USER must be in Spanish.

4. **Documentation in Spanish**:
   - Project documentation in `docs/*.md` (architecture, game model, tactical rules, and `05_ROADMAP_EVOLUTIVO.md`) remains in Spanish for the time being.

5. **Opportunistic Refactoring Policy (No Unsolicited Mass Sweep)**:
   - Do NOT run a massive retroactive sweep of the codebase solely to translate historical files.
   - HOWEVER, whenever any file containing code or UI is modified, extended, or refactored for a task, you MUST opportunistically translate and clean up any residual Spanish text in that file or component to English.
   - From this point forward, NEVER introduce Spanish into any code or user interface.
