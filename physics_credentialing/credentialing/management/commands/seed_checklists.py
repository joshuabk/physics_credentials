"""Load review topics, case minimums and requirements from the
Medical Physics Credentialing reference document onto the matching skills.

Safe to re-run: a skill that already has review topics, a requirement or a
minimum is left alone unless --replace is given. Skills the document needs that
are not in the catalog yet (Breast, Breath Hold and Compression, HDR Treatment
Delivery) are added.
"""
import textwrap

from django.core.management.base import BaseCommand
from django.db import transaction

from credentialing.models import Skill, SkillCategory

SENIOR = "Minimum 1 case with a senior physicist."

PLAN_INITIAL = """
Task/QCL
  Notes in task
  Timelines
Plan check
  Contours and support structures
  Prescribe treatment
  Technique and energy selection
  Isodose and MLC evaluation
  ClearCheck
  Dose grid resolution per modality
  Algorithm selection/defaults
  Plan scheduling
  Plan parameters
  Encounter
  Required documentation and sign offs
  CT order
  Secondary dose calculations (ClearCalc in plan document)
  Approval process
  Align RT
"""

PLAN_WEEKLY = """
Chart QA workspace
What parameters to review
Documentation and billing
"""

PLAN_FINAL = """
Documentation and billing
Brachytherapy Finals
"""

PLAN_ELECTRON = """
Plan normalization (dmax target structure)
dmax placement in bone
Secondary dose calculation criteria and notes
  Review dosimetry electron guide
MU limits
"""

PLAN_BREAST = """
Breath hold for left breast and some right breast
Free breath skin on BH scan
FB and BH user origin
Plan labeling and prescription documentation for BH
  Field Name Guide
Entrance field on printout
"""

PLAN_BH = """
Motion management policy
Plan and structure set naming
Non breast BH
  Average BH created from 3 separate BH scans, used to create ITV
SBRT board in plan only if compression
  Review memo
"""

PLAN_SBRT = """
Planning
  SBRT board only if compression
  Dose calculation grid
  Acuros algorithm use and high density structures
  CT slice thickness
  MU limits
  Acuros planning guide
Daily WL check procedure
QA
  Tolerances
  Devices
  Potential issues
SBRT Like policy
"""

PLAN_SRS = """
Registration review
  Bone and Cerebellum window
  Areas of interest
  MR distortion impact
  MR sequence and slice thickness
CT
  Slice thickness
  FOV
Plan
  FS limitations
  Target sizes
  Acuros and high density structures
  Review SRS precheck checklist
QA
  Tolerances
  QA Devices
  Potential issues
Daily WL check procedure
SRS Plan Check Checklist
"""

PSQA = """
Review
  Pass/Fail criteria (reference policy)
  What we do and don't QA (3D v IMRT/VMAT v ecomp)
  Primary and backup devices per machine and procedure
    Acceptable devices
  Recalibration: process for determining recal is needed and communication between physicists
  If there is a failure, reach out to a more experienced physicist
  If there is an MPA at clinic, what is the workflow
    Plan creation and delivery
    Documentation and approval status
    QA course completion
"""

MPC = """
Perform with a therapist
Review daily MPC with a senior physicist
  Tolerances and baselines
  Process if fails/troubleshooting
  Approval/notes
  MPC memo
  SunCHECK
"""

WL = """
Perform with senior physicist
Analyze
Tolerances and baselines
Process if fails/troubleshooting
Approval/notes
"""

MONTHLY = """
Run through test procedures and review recalibration procedures and decision making
  Equipment and calibration review
  Mechanicals
  Output & Adjusting
  MLC
  VisionRT
  Isoverify
  6DOF
Review monthly medical physics procedure manual
"""

ANNUAL = """
Run through test procedures and review recalibration procedures and decision making
Review NS specifics: Profiles
  1D tank setup/PDDs
  TG-51
Recheck/recalibration
  Daily QA baselines
  PSQA devices recalibration
  SW factors remeasured
  Monthly SunCHECK templates TG51 factors updated
Review annual medical physics procedure manual
"""

OUTPUT = """
Perform output adjustment with senior therapist
  If anything >1.5% communicate with a senior physicist first
For large output adjustments (>2%) review
  At what % you adjust
  Independent check prior to adjusting
  Prior to adjusting review: Daily QA, MPC, check setup, request second physicist help
"""

REPAIR = """
Communicate with Senior Physicist about any planned actions post repair
Documentation
  Web based app: enter path
  Machine folder
"""

SPC = """
Watch reirradiation training video
Review reirradiation memos
ClearCheck calculations
Excel calculations
Review task and documentation structure
Documentation
  SPC Request Form
  Physics consult document
  Billing
"""

HDR_PLANNING = """
Planning
  Digitization specs
  EQD2
  GYN EMBRACE constraints
  MR image fusion
  Physics double check and communications
  ClearCheck templates and checklist
Documentation
  Plan document
  Second calculation
  EQD2
  Decay
"""

HDR_TREATMENT = """
Prior to independent delivery
  HDR Emergency Training completed
  Physicist on license
  Login created for afterloader
  Afterloader and transfer tubes review
Treatment delivery
  Warmup complete/approved
  HDR Encounter
    Pre and post treatment delivery documents and sign offs
  Time Out
    Pre/post treatment surveys
  Patient log
  Final documentation
    Physician EOT
    Weekly physics charge and documentation
"""

SOURCE_EXCHANGE = """
SunCHECK and Excel (if applicable)
Documentation
Source survey and log
Source shipping
Day 0 source calibration
Completion of Shipping Hazardous Materials with West Physics online resources
If performed by MPA, physicist on license present in the department
New decay sheet creation
"""

HDR_APPLICATORS = [
    "Cylinder", "Multi-Channel Cylinder", "Multi-Channel Interstitial Cylinder",
    "Tandem & Ovoid + needles", "Tandem & Ring + needles", "Syed", "Prostate", "Skin",
]

# Skills the reference document needs that the seed catalog does not have:
# (category, subcategory, name, system_type, insert after skill named)
NEW_SKILLS = [
    ("3. Plan Checks", "", "Breast", "tps", "Electron"),
    ("3. Plan Checks", "", "Breath Hold and Compression", "tps", "Breast"),
    ("5. Brachytherapy Operations", "HDR Operations, per afterloader",
     "HDR Treatment Delivery", "hdr", "Daily QA (HDR)"),
]

# (category, skill name, requirement, minimum cases, topics)
TRAINING = [
    ("3. Plan Checks", "Initial", SENIOR, 1, PLAN_INITIAL),
    ("3. Plan Checks", "Weekly", SENIOR, 1, PLAN_WEEKLY),
    ("3. Plan Checks", "Final", SENIOR, 1, PLAN_FINAL),
    ("3. Plan Checks", "Electron", SENIOR, 1, PLAN_ELECTRON),
    ("3. Plan Checks", "Breast", SENIOR, 1, PLAN_BREAST),
    ("3. Plan Checks", "Breath Hold and Compression", SENIOR, 1, PLAN_BH),
    ("3. Plan Checks", "SBRT", SENIOR, 1, PLAN_SBRT),
    ("3. Plan Checks", "SRS",
     "Minimum 3 cases with a lead physicist, in addition to regular EBRT plan checks.", 3, PLAN_SRS),
    ("3. Plan Checks", "HDR",
     SENIOR + " Must be credentialed in HDR planning for that specific applicator before "
     "second physics plan checks can be performed. (Checklist still in progress.)", 1, ""),
    ("3. Plan Checks", "LDR", SENIOR + " (Checklist still in progress.)", 1, ""),
    ("3. Plan Checks", "Reirradiation",
     "SPC: minimum 2 with a lead physicist and 2 reviewed by a lead physicist.", 4, SPC),

    ("2. Machine QA Credentialing", "Portal Dosimetry",
     "Minimum 2 per device, and until successful independently.", 2, PSQA),
    ("2. Machine QA Credentialing", "MapCHECK",
     "Minimum 2 per device, and until successful independently.", 2, PSQA),
    ("2. Machine QA Credentialing", "SRS MapCHECK",
     "Minimum 2 per device, and until successful independently.", 2, PSQA),
    ("2. Machine QA Credentialing", "Daily Enhanced couch MPC",
     "Minimum 2 MPC reviews with a senior physicist.", 2, MPC),
    ("2. Machine QA Credentialing", "WL SunCHECK",
     "Minimum 2 WL deliveries and analysis with a senior physicist.", 2, WL),
    ("2. Machine QA Credentialing", "Monthly QA + SunCHECK",
     "Minimum 2 cases per machine type: 1 observed, 1 proctored.\n"
     "If MPAs perform machine QA at the credentialing clinic, at the discretion of the "
     "proctoring physicist: 3 months of machine QA for an experienced physicist, about "
     "1 year for a new physicist.", 2, MONTHLY),
    ("2. Machine QA Credentialing", "Annual QA + SunCHECK",
     "Minimum 1 annual with a senior physicist per machine type. Recommend 3 iterations of "
     "proctored output and PDDs (at the discretion of the senior physicist).", 1, ANNUAL),
    ("2. Machine QA Credentialing", "Machine Output Evaluation and Adjustment (TG-51)",
     "Minimum 1, recommended 3 proctored output adjustments with senior therapist per "
     "machine type.", 1, OUTPUT),

    ("7. Equipment & Asset Management",
     "Engineer Service Reports and Physics Return-to-Service Reports",
     "Post machine repair protocol.", None, REPAIR),

    ("5. Brachytherapy Operations", "HDR Treatment Delivery",
     'Minimum 4 cases: 2 observed, 2 proctored with a senior or "expert" brachytherapy '
     'physicist.', 4, HDR_TREATMENT),
    ("5. Brachytherapy Operations", "Source Exchange",
     'Minimum 2 cases + review of the first 2 independent source exchanges with a senior '
     '"expert" brachytherapy physicist.', 4, SOURCE_EXCHANGE),
] + [
    ("4. Brachytherapy Planning", name,
     'Minimum 4 cases: 2 observed, 2 proctored with a senior "expert" brachytherapy '
     'physicist. Review per applicator.', 4, HDR_PLANNING)
    for name in HDR_APPLICATORS
]


class Command(BaseCommand):
    help = 'Load review topics and case minimums from the credentialing reference document'

    def add_arguments(self, parser):
        parser.add_argument('--replace', action='store_true',
                            help='Overwrite topics/requirements already set on these skills '
                                 '(ticks on unchanged topics are kept)')

    @transaction.atomic
    def handle(self, *args, replace=False, **options):
        for cat_name, sub, name, system_type, after in NEW_SKILLS:
            cat = SkillCategory.objects.filter(name=cat_name).first()
            if cat is None or Skill.objects.filter(category=cat, name=name).exists():
                continue
            anchor = (Skill.objects.filter(category=cat, name=after).first()
                      or Skill.objects.filter(category=cat).order_by('-order').first())
            order = anchor.order + 1 if anchor else 1
            for s in Skill.objects.filter(category=cat, order__gte=order).order_by('-order'):
                s.order += 1
                s.save(update_fields=['order'])
            Skill.objects.create(category=cat, subcategory=sub, name=name, order=order,
                                 system_type=system_type)
            self.stdout.write(f'  added skill: {cat_name} / {name}')

        updated, skipped, missing = 0, [], []
        for cat_name, name, requirement, min_cases, topics in TRAINING:
            skill = Skill.objects.filter(category__name=cat_name, name=name).first()
            if skill is None:
                missing.append(f'{cat_name} / {name}')
                continue
            has_any = bool(skill.requirement or skill.min_cases or skill.checklist_items.exists())
            if has_any and not replace:
                skipped.append(name)
                continue
            skill.requirement = requirement
            skill.min_cases = min_cases
            skill.save(update_fields=['requirement', 'min_cases'])
            skill.set_checklist_from_text(textwrap.dedent(topics).strip('\n'))
            updated += 1

        self.stdout.write(self.style.SUCCESS(f'Training checklists loaded on {updated} skills.'))
        if skipped:
            self.stdout.write(f'Left alone (already set up; use --replace to overwrite): '
                              f'{", ".join(skipped)}')
        if missing:
            self.stdout.write(self.style.WARNING(
                'Not found in the skill catalog (renamed or deleted?): ' + '; '.join(missing)))
