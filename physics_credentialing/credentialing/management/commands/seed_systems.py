"""Seed the treatment systems from the device inventory (Nov 2026).

One entry per model: a skill credentialed on one unit of a model counts for
every unit of that model, so the checklist carries models, not serial numbers.
Safe to re-run: systems are matched by name and left alone. Edit, retire or
delete them on the Systems page.

Not seeded (confirm the model, then add on the Systems page):
  - The unnamed Elekta linacs (AOA_HWK, AOA_LO, CCG1, CCG2, MAC, NSMElekta,
    NSSAElekta, PR1, PR2) — the inventory doesn't say which model they are.
  - The five CT simulators' actual makes/models — seeded as one generic
    "CT Simulator" until confirmed.
Decommissioned units (23EX, LAW23EX2) are intentionally left out.
"""
from django.core.management.base import BaseCommand

from credentialing.models import TreatmentSystem

# Entries created by earlier versions of this seed, superseded by the
# one-per-model list below. Removed on re-run if no credentials were
# recorded against them; otherwise left alone and reported.
OBSOLETE = [
    # first seed
    "Varian Clinac", "Elekta Versa HD / Infinity", "Elekta Unity MR-Linac", "Gamma Knife",
    # site-based HDR seed
    "Bravos — Forsyth", "Bravos — Gwinnett",
    "GammaMed Plus — Blairsville", "GammaMed Plus — Conyers", "GammaMed Plus — Snellville",
    "GammaMed Plus — Cherokee", "GammaMed Plus — Northside Philip", "GammaMed Plus iX — Atlanta",
    "Flexitron — Lake Oconee", "Flexitron — Midtown", "Flexitron — Macon", "Flexitron — Preston Ridge",
    "microSelectron v3 — Forsyth", "microSelectron v3 — Midtown", "microSelectron v3 — Preston Ridge",
]

# (name, system_type, manufacturer)
SYSTEMS = [
    # Linacs
    ("Varian TrueBeam", "linac", "Varian"),
    ("Varian Trilogy", "linac", "Varian"),
    ("Varian Clinac iX", "linac", "Varian"),
    ("Varian Clinac EX/CD series", "linac", "Varian"),   # 21EX, 23iX/EX, 2100CD
    ("Varian Halcyon", "linac", "Varian"),
    ("Elekta Versa HD", "linac", "Elekta"),
    ("Elekta Synergy", "linac", "Elekta"),

    # CT simulation (one entry until scanner models are confirmed)
    ("CT Simulator", "ct", ""),

    # HDR afterloaders
    ("Varian Bravos", "hdr", "Varian"),
    ("Varian GammaMed Plus / Plus iX", "hdr", "Varian"),
    ("Elekta Flexitron", "hdr", "Elekta/Nucletron"),
    ("Elekta microSelectron v3", "hdr", "Elekta/Nucletron"),
]


class Command(BaseCommand):
    help = 'Seed the treatment systems from the device inventory (one entry per model)'

    def handle(self, *args, **options):
        removed = 0
        for old in TreatmentSystem.objects.filter(name__in=OBSOLETE):
            if old.credentials.exists():
                self.stdout.write(self.style.WARNING(
                    f'Kept obsolete "{old}" — it has credential records. '
                    f'Retire or delete it on the Systems page.'))
            else:
                old.delete()
                removed += 1
        if removed:
            self.stdout.write(f'Removed {removed} obsolete systems from earlier seeds.')

        created = 0
        order = {}
        for name, system_type, manufacturer in SYSTEMS:
            order[system_type] = order.get(system_type, 0) + 1
            _, was_created = TreatmentSystem.objects.get_or_create(
                name=name,
                defaults={'system_type': system_type, 'manufacturer': manufacturer,
                          'order': order[system_type]})
            created += was_created
        self.stdout.write(self.style.SUCCESS(
            f'Seed complete: {created} new systems ({TreatmentSystem.objects.count()} total).'))
