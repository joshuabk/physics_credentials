# Physics Credentialing Tracker

Tracks skill credentialing for the Northside Hospital radiation oncology medical physics group.

## Setup
```
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_skills                       # loads the checklist skill catalog
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
