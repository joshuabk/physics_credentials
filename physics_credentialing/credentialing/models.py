import datetime

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Physicist(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='physicist')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    title = models.CharField(max_length=120, blank=True,
                             help_text="e.g. Medical Physicist, Senior Physicist, Chief Physicist")
    location = models.CharField(max_length=120, blank=True,
                                help_text="Site or clinic this physicist is based at")
    hire_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def credential_summary(self):
        """Counts by effective status across every checklist item.

        A general skill is one item; a per-system skill is one item for each
        active treatment system of its type.
        """
        creds = {(c.skill_id, c.system_id): c
                 for c in self.credentials.select_related('skill')}
        systems_by_type = TreatmentSystem.active_by_type()
        summary = {'credentialed': 0, 'in_progress': 0, 'not_started': 0,
                   'not_applicable': 0, 'expired': 0, 'total': 0}
        for s in Skill.objects.filter(is_active=True):
            for system in s.checklist_systems(systems_by_type):
                c = creds.get((s.pk, system.pk if system else None))
                status = c.effective_status if c else 'not_started'
                summary[status] += 1
                if status != 'not_applicable':
                    summary['total'] += 1
        return summary

    def percent_complete(self):
        s = self.credential_summary()
        if s['total'] == 0:
            return 0
        return round(100 * s['credentialed'] / s['total'])


class TreatmentSystem(models.Model):
    """A treatment or imaging system that skills can be credentialed against.

    Model-level by default ("Varian Bravos", "Elekta Synergy"); add a location
    when the same model at two sites should be credentialed separately.
    """
    TYPE_CHOICES = [
        ('linac', 'Linac'),
        ('hdr', 'HDR Afterloader'),
        ('ldr', 'LDR / Seed Program'),
        ('ct', 'CT Simulator'),
        ('gk', 'Gamma Knife'),
        ('mrl', 'MR-Linac'),
        ('tps', 'Treatment Planning System'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=150, unique=True,
                            help_text='e.g. "Varian TrueBeam", "Varian Bravos", "Elekta Synergy"')
    system_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    manufacturer = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=120, blank=True,
                                help_text="Leave blank if this entry covers every site")
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['system_type', 'order', 'name']

    def __str__(self):
        return f"{self.name} ({self.location})" if self.location else self.name

    @classmethod
    def active_by_type(cls):
        """{'linac': [systems...], 'hdr': [...]} for every active system."""
        grouped = {}
        for s in cls.objects.filter(is_active=True):
            grouped.setdefault(s.system_type, []).append(s)
        return grouped


class SkillCategory(models.Model):
    name = models.CharField(max_length=200, unique=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = 'skill categories'

    def __str__(self):
        return self.name


class Skill(models.Model):
    category = models.ForeignKey(SkillCategory, on_delete=models.CASCADE, related_name='skills')
    subcategory = models.CharField(max_length=200, blank=True,
                                   help_text="Optional grouping within the category (e.g. 'Daily QA', 'HDR Operations')")
    name = models.CharField(max_length=250)
    order = models.PositiveIntegerField(default=0)
    as_applicable = models.BooleanField(
        default=False,
        help_text="Skill only applies to some physicists (e.g. Gamma Knife, MR-Linac)")
    renewal_months = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="If set, the credential expires this many months after completion "
                  "(12 = annual training, 3 = quarterly). Blank = never expires.")
    system_type = models.CharField(
        max_length=10, blank=True, choices=TreatmentSystem.TYPE_CHOICES,
        help_text="If set, this skill is credentialed separately on each active system of "
                  "this type (e.g. once per linac). Blank = a single checkbox.")
    requirement = models.TextField(
        blank=True,
        help_text="Minimum cases, who proctors, and any guidance shown above the checklist "
                  "(e.g. 'Minimum 4 cases: 2 observed, 2 proctored with a senior physicist').")
    min_cases = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Number of logged cases needed before sign-off. Blank = no case log target.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['category__order', 'order', 'name']
        unique_together = [('category', 'subcategory', 'name')]

    def __str__(self):
        return self.name

    @property
    def is_per_system(self):
        return bool(self.system_type)

    def checklist_systems(self, systems_by_type=None):
        """The systems this skill is checked off against: [None] for a general skill."""
        if not self.system_type:
            return [None]
        if systems_by_type is None:
            systems_by_type = TreatmentSystem.active_by_type()
        return list(systems_by_type.get(self.system_type, []))

    @property
    def has_training_panel(self):
        """True when the skill has review topics or a case-log target to track."""
        return bool(self.requirement or self.min_cases or self.checklist_items.exists())

    def checklist_text(self):
        """The review topics as editable indented text (two spaces per level)."""
        return '\n'.join('  ' * i.indent + i.text for i in self.checklist_items.all())

    def set_checklist_from_text(self, text):
        """Replace the review topics from indented text, one topic per line.

        Indent with two spaces (or a tab) per level; a leading "-", "*" or "•" is
        ignored. Topics whose wording is unchanged keep their ticks; topics that
        are removed take their ticks with them.
        """
        lines = []
        for raw in (text or '').replace('\t', '  ').splitlines():
            if not raw.strip():
                continue
            spaces = len(raw) - len(raw.lstrip(' '))
            body = raw.strip().lstrip('-*\u2022').strip()
            if body:
                lines.append((min(spaces // 2, 4), body))
        existing = list(self.checklist_items.all())
        unused = list(existing)
        keep = []
        for order, (indent, body) in enumerate(lines, start=1):
            match = next((i for i in unused if i.text == body), None)
            if match is not None:
                unused.remove(match)
                if match.indent != indent or match.order != order:
                    match.indent, match.order = indent, order
                    match.save(update_fields=['indent', 'order'])
                keep.append(match)
            else:
                keep.append(ChecklistItem.objects.create(skill=self, text=body,
                                                         indent=indent, order=order))
        for item in unused:
            item.delete()
        return keep


class Credential(models.Model):
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('credentialed', 'Credentialed'),
        ('not_applicable', 'N/A'),
    ]

    physicist = models.ForeignKey(Physicist, on_delete=models.CASCADE, related_name='credentials')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='credentials')
    system = models.ForeignKey(TreatmentSystem, on_delete=models.CASCADE, null=True, blank=True,
                               related_name='credentials',
                               help_text="Set for per-system skills; blank for general skills")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    date_completed = models.DateField(null=True, blank=True)
    verified_by = models.CharField(max_length=150, blank=True,
                                   help_text="Physicist who trained/verified this competency")
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='credential_updates')

    class Meta:
        ordering = ['skill__category__order', 'skill__order', 'system__order']
        unique_together = [('physicist', 'skill', 'system')]

    def __str__(self):
        return f"{self.physicist} — {self.label} ({self.get_status_display()})"

    @property
    def label(self):
        """Skill name, with the system appended for per-system credentials."""
        return f"{self.skill.name} · {self.system}" if self.system_id else self.skill.name

    @property
    def expiration_date(self):
        """Date this credential lapses, for skills with a renewal cycle."""
        if self.status != 'credentialed' or not self.date_completed or not self.skill.renewal_months:
            return None
        months = self.skill.renewal_months
        d = self.date_completed
        month = d.month - 1 + months
        year = d.year + month // 12
        month = month % 12 + 1
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        day = min(d.day, [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
        return datetime.date(year, month, day)

    @property
    def is_expired(self):
        exp = self.expiration_date
        return exp is not None and exp < timezone.now().date()

    @property
    def expires_soon(self):
        """Within 30 days of lapsing."""
        exp = self.expiration_date
        today = timezone.now().date()
        return exp is not None and today <= exp <= today + datetime.timedelta(days=30)

    @property
    def effective_status(self):
        """Status with expiration applied — an expired credential is no longer current."""
        if self.status == 'credentialed' and self.is_expired:
            return 'expired'
        return self.status

    def mark_started(self, user=None):
        """Move a not-started credential to In Progress once training is logged."""
        if self.status == 'not_started':
            self.status = 'in_progress'
            self.updated_by = user
            self.save(update_fields=['status', 'updated_by', 'updated_at'])


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Administrator'),        # chief physicist / manager: edit everything
        ('physicist', 'Physicist'),        # update own checklist, view the group
        ('viewer', 'Viewer'),              # read-only
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='physicist')
    physicist = models.ForeignKey(Physicist, on_delete=models.SET_NULL, null=True, blank=True,
                                  help_text="Link this login to a physicist record")

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == 'admin'


class ChecklistItem(models.Model):
    """A review topic for a skill (e.g. "Dose grid resolution per modality").

    Topics are indented to form an outline; a topic followed by more-indented
    topics is shown as a heading, and only the lowest-level topics get a tick box.
    """
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='checklist_items')
    text = models.CharField(max_length=300)
    indent = models.PositiveSmallIntegerField(default=0)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['skill', 'order', 'pk']

    def __str__(self):
        return f"{self.skill.name}: {self.text}"


class ChecklistProgress(models.Model):
    """A ticked review topic on one physicist's credential."""
    credential = models.ForeignKey(Credential, on_delete=models.CASCADE, related_name='checklist_progress')
    item = models.ForeignKey(ChecklistItem, on_delete=models.CASCADE, related_name='progress')
    checked_on = models.DateField(default=datetime.date.today)
    checked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')

    class Meta:
        unique_together = [('credential', 'item')]

    def __str__(self):
        return f"{self.credential} — {self.item.text}"


class CaseLog(models.Model):
    """One logged training case (plan check, QA session, source exchange...)."""
    ROLE_CHOICES = [
        ('observed', 'Observed'),
        ('proctored', 'Proctored / performed with'),
        ('reviewed', 'Independent, reviewed'),
    ]

    credential = models.ForeignKey(Credential, on_delete=models.CASCADE, related_name='cases')
    date = models.DateField()
    case_type = models.CharField(max_length=150, blank=True,
                                 help_text="Plan check type, device, machine, applicator...")
    patient = models.CharField(max_length=100, blank=True,
                               help_text="Patient ID or initials, if the case is patient-specific")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='proctored')
    performed_with = models.CharField(max_length=150, blank=True,
                                      help_text="Proctoring or reviewing physicist")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')

    class Meta:
        ordering = ['date', 'pk']

    def __str__(self):
        return f"{self.credential} — {self.date} {self.case_type}"
