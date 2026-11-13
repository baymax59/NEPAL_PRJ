"""Case Intelligence inside cases (phase CM-5, docs/case-management/04 §10).

The existing Case Intelligence (similar cases, explanations, search, provisions, timeline, assistant) working on
one investigation:

- scope.py: what may be read in a case, for one user (never more than they may see).
- index.py: each content's text read once, keyed by its SHA-256, and shared by every case.
- search.py, similar.py, assistant.py, timeline.py, offences.py: the features.
- api.py: the endpoints.
"""
