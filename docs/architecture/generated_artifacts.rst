Generated Architecture Artifacts
================================

This project uses automatic tools to generate *structural views*
of the codebase.

These artifacts describe **what depends on what**, but they do **not**
capture the *semantic intent* of the system.

They are complementary to the manually written architecture documents.

Dependency Graph
----------------

Generated with ``pydeps``.

Purpose:

- show module-level dependencies
- highlight layer boundaries (engine, runner, analysis)
- identify unwanted coupling
- support refactoring and cleanup

Notes:

- regenerated automatically
- purely structural (import-based)
- does not represent runtime control flow

Call Graph
----------

Generated with ``code2flow``.

Purpose:

- show function-level call relationships
- visualize execution paths across modules
- support debugging and reasoning about control flow

Notes:

- regenerated automatically
- approximates call relationships
- does not represent data flow or decision semantics

Important Limitations
---------------------

Generated artifacts **do not describe semantic intent**.

In particular, they cannot explain:

- why a callback must (or must not) exist
- where rationales must be captured
- how actor, action, and rationale are causally aligned
- which component owns a responsibility

These questions are answered exclusively by the
manually written architecture and contract documents
(e.g. decision flow, environment contract, replay format).

Design Principle
----------------

Automatic artifacts describe **structure**.

Manual documentation describes **meaning**.

Both are required for a complete and maintainable system.