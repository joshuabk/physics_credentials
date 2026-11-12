# Physics Credentialing Tracker

Tracks skill credentialing for the Northside Hospital radiation oncology medical physics group.

## Setup
```
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_skills                       # loads the checklist skill catalog
python manage.py seed_systems                      # starter list of linacs / HDR / CT / GK (optional)
python manage.py create_admin --username admin --password <choose-one>
python manage.py runserver
```

## Roles
- **admin** — full access: add physicists, edit any checklist
- **physicist** — view everything, update own checklist (link login to a physicist record via UserProfile in /admin/)
- **viewer** — read-only

## Recurring trainings
Skills with a renewal cycle (annual CBLs, quarterly CPR, emergency trainings) automatically
show as **Expired** once the completion date is older than the cycle, and appear on the
dashboard's attention list 30 days before lapsing. Re-run `seed_skills` any time — it only
adds new items and never touches existing credentials.

## Per-system credentialing
Some skills need to be checked off separately on each machine — Daily QA on the TrueBeam
*and* on the Synergy, source exchange on each afterloader. Two steps:

1. **Systems** page (admins): add the treatment systems — "Varian TrueBeam" (Linac),
   "Varian Bravos" (HDR Afterloader), "CT Simulator" (CT Simulator), etc. Credential by
   model (one entry per model) unless the same model at two sites truly needs separate
   sign-off; then add a location.
2. **Skills** page: edit a skill and set *Credential per system* to the matching type.
   Leave it blank for skills that are a single checkbox.

A per-system skill then shows one row per active system on every checklist and in the
matrix (filterable by system), and the CSV export gains a System column. Retiring a system
hides its rows but keeps the history; deleting it erases those records. Existing
single-checkbox credentials are untouched when you change a skill to per-system — the old
record simply stops being shown. If you later clear the per-system setting, it reappears.

## Training checklists and case logs
Skills can carry the review topics and case minimums from the *Medical Physics Credentialing*
reference document. On a physicist's checklist, each such skill (or each system of a
per-system skill) has a **Training record** row: open it to tick review topics and log cases
(date, type/device, patient ID, observed / proctored / independent-reviewed, performed with,
notes). Ticking a topic or logging a case moves a Not Started skill to In Progress; when every
topic is ticked and the minimum is logged, the row shows **Ready for sign-off** and the
proctor sets the status to Credentialed as usual.

Edit topics, the requirement text and the case minimum on the skill's **Edit** page: one topic
per line, indented two spaces to nest under the line above (a line with nested lines shows as
a heading). Unchanged lines keep their ticks; reworded lines start unticked.

`python manage.py seed_checklists` loads the reference document's content onto the matching
skills (and adds Breast, Breath Hold and Compression, and HDR Treatment Delivery). It skips
skills that already have topics; `--replace` overwrites them.
