# Sample tasks

Each `.json` file here is a `TaskSubmission` (see `app/schemas/models.py`) plus a `difficulty` label for human reference — the system itself never sees `difficulty`, since deciding that is the classifier's job.

- `spec` — the task description, as it would be sent to a model.
- `tests` — pytest-style test code, written assuming the generated code defines whatever function or class the spec asks for, in the same namespace the tests run in.

Sixteen tasks, roughly easy → hard, for exercising the cascade during development and as the initial bootstrap batch (see scripts/cutover.py's per-class minimums) and a standing regression check afterward.
