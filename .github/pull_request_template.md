<!-- English or Spanish, whichever you prefer. -->

## What changes

## How it was checked

- [ ] The suite passes (`QT_QPA_PLATFORM=offscreen uv run pytest -n auto -m "not a_solas"`).
- [ ] Each new test was seen failing without the change.
- [ ] A visual change was checked in a screenshot.
- [ ] If a dump's pages change, `tools/update_screen_references.py` was run and its diff reviewed.
- [ ] Nobody and no specific machine is named in code or comments.
