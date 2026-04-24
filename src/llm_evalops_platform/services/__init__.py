"""Business logic layer — no FastAPI or storage imports at module level.

Modules
-------
compare  — compute_compare(): fetches metrics, computes deltas, persists CompareSession
gate     — evaluate_gate(): applies GateRule list, persists ReleaseDecision
"""
