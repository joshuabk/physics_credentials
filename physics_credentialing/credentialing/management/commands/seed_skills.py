"""Seed the skill catalog from the Physics Credentialing Checklist.

Safe to re-run: existing categories/skills are matched by name and left alone,
so credential records are never disturbed. New items in the list get added.
"""
from django.core.management.base import BaseCommand

from credentialing.models import Skill, SkillCategory

# (category, [ (subcategory, [ (skill, as_applicable, renewal_months) ]) ])
CHECKLIST = [
    ("1. Clinical Systems & Software Review", [
        ("Oncology Information Systems", [
            ("ARIA", False, None),
            ("Mosaiq", False, None),
        ]),
        ("QA and Verification Systems", [
            ("SunCHECK and Assets", False, None),
            ("Mobius", False, None),
            ("ClearCalc", False, None),
            ("ClearCheck", False, None),
        ]),
    ]),
    ("2. Machine QA Credentialing", [
        ("Daily QA", [
            ("Daily QA + SunCHECK", False, None),
            ("Daily QA DQA software", True, None),
            ("PDI Host", False, None),
            ("WL SunCHECK", False, None),
            ("Daily Enhanced couch MPC", False, None),
        ]),
        ("Monthly QA", [
            ("Monthly QA + SunCHECK", False, None),
            ("Monthly MPC", False, None),
        ]),
        ("Annual QA", [
            ("Annual QA + SunCHECK", False, None),
        ]),
        ("PSQA", [
            ("Portal Dosimetry", False, None),
            ("MapCHECK", False, None),
            ("SRS MapCHECK", False, None),
            ("Log Files - Varian", False, None),
            ("Log Files - Elekta", False, None),
            ("Tolerances", False, None),
        ]),
        ("Other", [
            ("CT QA", False, None),
            ("Startup / Shutdown Procedures", False, None),
            ("Emergency Off Procedures", False, None),
        ]),
        ("Machine Output Evaluation and Adjustment", [
            ("Varian TrueBeam", True, None),
            ("Varian Clinac", True, None),
            ("Elekta Versa/Infinity", True, None),
            ("Elekta Synergy", True, None),
            ("Halcyon", True, None),
            ("GK", True, None),
            ("MR", True, None),
        ]),
    ]),
    ("3. Plan Checks", [
        ("", [
            ("Initial", False, None),
            ("Weekly", False, None),
            ("Final", False, None),
            ("Electron", False, None),
            ("SBRT", False, None),
            ("SRS", False, None),
            ("TBI", False, None),
            ("Eye Plaque", False, None),
            ("HDR", False, None),
            ("LDR", False, None),
            ("Velocity Fusion", False, None),
        ]),
        ("Special Physics / Other", [
            ("Reirradiation", False, None),
            ("Cardiac Device Cases", False, None),
            ("Billing and documentation", False, None),
            ("Mosfets/OSLDs for patients", False, None),
        ]),
    ]),
    ("4. Brachytherapy Planning", [
        ("HDR, per afterloader and TPS", [
            ("Cylinder", False, None),
            ("Multi-Channel Cylinder", False, None),
            ("Multi-Channel Interstitial Cylinder", False, None),
            ("Tandem & Ovoid + needles", False, None),
            ("Tandem & Ring + needles", False, None),
            ("Syed", False, None),
            ("Prostate", False, None),
            ("Skin", False, None),
            ("EQD2", False, None),
            ("Documentation", False, None),
            ("Patient Lists", False, None),
        ]),
        ("LDR", [
            ("Prostate (LDR)", False, None),
            ("Eye Plaque (LDR)", False, None),
        ]),
    ]),
    ("5. Brachytherapy Operations", [
        ("HDR Operations, per afterloader", [
            ("Daily QA (HDR)", False, None),
            ("Source Exchange", False, None),
            ("Inventory (HDR)", False, None),
        ]),
        ("LDR Operations", [
            ("Inventory (LDR)", False, None),
            ("Seed calibration", False, None),
        ]),
        ("Radiation Safety", [
            ("Shipping Hazardous Materials", False, None),
        ]),
    ]),
    ("6. Clinical Policies & Procedures", [
        ("Lucidoc Policies", [
            ("Treatment Planning Policy", False, None),
            ("Weekly SSD", False, None),
            ("Motion Management", False, None),
            ("IGRT Shifts", False, None),
            ("Cardiac Devices", False, None),
            ("High Dose", False, None),
            ("Stereotactic Treatments", False, None),
            ("PSQA (Policy)", False, None),
            ("WL frequency and expectations", False, None),
        ]),
        ("Memos & Email Notifications", [
            ("Physics Remote Work Guidelines", False, None),
            ("Physics Policies & Procedures Folder", False, None),
            ("Clinical Electron Setup", False, None),
            ("Machine Matching", False, None),
            ("Brass Mesh Bolus", False, None),
            ("Online Event Reporting", False, None),
            ("HDR GYN Constraints", False, None),
            ("LDR NS Constraints", False, None),
            ("SBRT Board Process", False, None),
            ("Reirradiation SPC", False, None),
            ("MPC", False, None),
            ("Breast entrance on skin", False, None),
            ("Billing Cont Physics", False, None),
            ("Logfile troubleshooting", False, None),
            ("TG51 Output Calibration email", False, None),
        ]),
    ]),
    ("7. Equipment & Asset Management", [
        ("", [
            ("Equipment Calibration", False, None),
            ("Equipment Inventory", False, None),
            ("Calibration Report Folder", False, None),
            ("Biomed Stickers / PMI Process", False, None),
            ("Engineer Service Reports and Physics Return-to-Service Reports", False, None),
        ]),
    ]),
    ("8. Communication & Operations", [
        ("", [
            ("Machine Down Procedures", False, None),
            ("Adjustments Communication (equipment, output, calibrations etc)", False, None),
            ("Physicist Email Distribution Lists", False, None),
            ("Dosimetry Email Distribution Lists", False, None),
            ("Organizational Structure Review", False, None),
            ("Department Contacts", False, None),
            ("Annual review in October", False, None),
            ("Merit increase in December", False, None),
            ("Engineering Contacts", False, None),
        ]),
    ]),
    ("9. IT Resources", [
        ("Websites and Applications", [
            ("ARIA, Velocity (ariaweb)", False, None),
            ("Citrix - Mosaiq, Variseed", False, None),
            ("SunCHECK (web)", False, None),
            ("Mobius (web)", False, None),
            ("QGenda", False, None),
            ("Concur", False, None),
            ("Event Reporting System", False, None),
            ("EMR Request", False, None),
            ("Billing Q&A", False, None),
            ("MR Linac RDP", False, None),
            ("E-Time (NS intranet)", False, None),
            ("Lucidoc (NS intranet)", False, None),
            ("Engineering request (NS intranet)", False, None),
            ("Biomed request (NS intranet)", False, None),
        ]),
        ("Access & Logins", [
            ("ARIA login", False, None),
            ("Mosaiq login", False, None),
            ("NS Login", False, None),
            ("Machines login", False, None),
            ("SunCHECK login", False, None),
            ("Mobius login", False, None),
            ("Daily QA DQA3 software login", True, None),
            ("Remote Access", False, None),
            ("Mapped Drives", False, None),
            ("Physics AD Group", False, None),
            ("Dosimetry-Physics Shared Folder Access", False, None),
            ("MRL Remote Desktop Access", True, None),
            ("MR U-Drive Access", True, None),
            ("Velocity login", False, None),
            ("ADP clock-in", False, None),
            ("Concur/Expense Reporting", False, None),
        ]),
    ]),
    ("10. Required Training", [
        ("HR Related", [
            ("Annual CBLs", False, 12),
            ("Annual TB Questionnaire", False, 12),
            ("Quarterly CPR Training", False, 3),
        ]),
        ("Emergency Training", [
            ("HDR Annual Emergency Training", False, 12),
            ("Gamma Knife Annual Emergency Training", True, 12),
            ("MR Annual Emergency Training", True, 12),
            ("Annual Radiation Safety Training (CBL)", False, 12),
        ]),
    ]),
    ("11. Specialty Program Credentialing", [
        ("", [
            ("MR-Linac", True, None),
            ("Gamma Knife", True, None),
            ("TBI (Specialty)", True, None),
            ("Eye Plaque (Specialty)", True, None),
            ("Halcyon (Specialty)", True, None),
        ]),
    ]),
]


class Command(BaseCommand):
    help = 'Seed skill categories and skills from the credentialing checklist'

    def handle(self, *args, **options):
        created_cats = created_skills = 0
        for cat_order, (cat_name, subs) in enumerate(CHECKLIST, start=1):
            cat, was_created = SkillCategory.objects.get_or_create(
                name=cat_name, defaults={'order': cat_order})
            created_cats += was_created
            order = 0
            for sub_name, skills in subs:
                for name, as_applicable, renewal in skills:
                    order += 1
                    _, was_created = Skill.objects.get_or_create(
                        category=cat, subcategory=sub_name, name=name,
                        defaults={'order': order, 'as_applicable': as_applicable,
                                  'renewal_months': renewal})
                    created_skills += was_created
        total = Skill.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'Seed complete: {created_cats} new categories, {created_skills} new skills '
            f'({total} skills total).'))
