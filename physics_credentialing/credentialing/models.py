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
    hire_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def credential_summary(self):
        """Counts by effective status across all active skills."""
        skills = Skill.objects.filter(is_active=True)
        creds = {c.skill_id: c for c in self.credentials.select_related('skill')}
        summary = {'credentialed': 0, 'in_progress': 0, 'not_started': 0,
                   'not_applicable': 0, 'expired': 0, 'total': 0}
        for s in skills:
            c = creds.get(s.pk)
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
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['category__order', 'order', 'name']
        unique_together = [('category', 'subcategory', 'name')]

    def __str__(self):
        return self.name


class Credential(models.Model):
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('credentialed', 'Credentialed'),
        ('not_applicable', 'N/A'),
    ]

    physicist = models.ForeignKey(Physicist, on_delete=models.CASCADE, related_name='credentials')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='credentials')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    date_completed = models.DateField(null=True, blank=True)
    verified_by = models.CharField(max_length=150, blank=True,
                                   help_text="Physicist who trained/verified this competency")
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='credential_updates')

    class Meta:
        ordering = ['skill__category__order', 'skill__order']
        unique_together = [('physicist', 'skill')]

    def __str__(self):
        return f"{self.physicist} — {self.skill} ({self.get_status_display()})"

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
