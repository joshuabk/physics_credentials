import csv
import datetime
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Credential, Physicist, Skill, SkillCategory, UserProfile
from .site_settings import login_enabled

STATUS_ORDER = ['credentialed', 'in_progress', 'expired', 'not_started', 'not_applicable']


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def login_required_(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if login_enabled() and not request.user.is_authenticated:
            return redirect('login')
        return view(request, *args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not login_enabled():
            # Login is turned off: everyone has full (admin) access.
            return view(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return redirect('login')
        profile = getattr(request.user, 'profile', None)
        if not (profile and profile.is_admin):
            messages.error(request, 'You do not have permission to do that.')
            return redirect('dashboard')
        return view(request, *args, **kwargs)
    return wrapper


def _is_admin(request):
    if not login_enabled():
        return True
    profile = getattr(request.user, 'profile', None)
    return bool(profile and profile.is_admin)


def _can_edit(request, physicist):
    """Admins edit anyone; a physicist may update their own checklist."""
    if not login_enabled():
        return True
    profile = getattr(request.user, 'profile', None)
    if profile is None:
        return False
    if profile.is_admin:
        return True
    return profile.role == 'physicist' and profile.physicist_id == physicist.pk


def login_view(request):
    if not login_enabled():
        return redirect('dashboard')
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        user = authenticate(request, username=request.POST.get('username', ''),
                            password=request.POST.get('password', ''))
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        messages.error(request, 'Invalid username or password.')
    return render(request, 'credentialing/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


# ─── Core pages ───────────────────────────────────────────────────────────────

def _grouped_skills(physicist=None):
    """Categories -> [{'subcategory', 'skills': [{'skill','credential'}]}] structure.

    When a physicist is given, each skill carries their credential (or None).
    """
    creds = {}
    if physicist is not None:
        creds = {c.skill_id: c for c in physicist.credentials.select_related('skill')}

    categories = []
    for cat in SkillCategory.objects.prefetch_related('skills'):
        groups, seen = [], {}
        for skill in cat.skills.filter(is_active=True):
            key = skill.subcategory
            if key not in seen:
                seen[key] = {'subcategory': key, 'skills': []}
                groups.append(seen[key])
            cred = creds.get(skill.pk)
            seen[key]['skills'].append({
                'skill': skill,
                'credential': cred,
                'status': cred.effective_status if cred else 'not_started',
            })
        if groups:
            categories.append({'category': cat, 'groups': groups})
    return categories


@login_required_
def dashboard(request):
    today = timezone.now().date()
    physicists = Physicist.objects.filter(is_active=True)
    total_skills = Skill.objects.filter(is_active=True).count()

    summaries = []
    for p in physicists:
        s = p.credential_summary()
        summaries.append({'physicist': p, **s, 'percent': p.percent_complete()})

    # Expired + expiring-soon credentials across the group
    attention = []
    for c in Credential.objects.filter(status='credentialed', physicist__is_active=True,
                                       skill__is_active=True, skill__renewal_months__isnull=False,
                                       date_completed__isnull=False
                                       ).select_related('physicist', 'skill'):
        if c.is_expired:
            attention.append({'credential': c, 'kind': 'expired', 'when': c.expiration_date})
        elif c.expires_soon:
            attention.append({'credential': c, 'kind': 'expiring', 'when': c.expiration_date})
    attention.sort(key=lambda x: x['when'])

    profile = getattr(request.user, 'profile', None)
    return render(request, 'credentialing/dashboard.html', {
        'summaries': summaries,
        'total_skills': total_skills,
        'attention': attention[:25],
        'attention_count': len(attention),
        'today': today,
        'is_admin': _is_admin(request),
        'my_physicist': profile.physicist if profile else None,
    })


@login_required_
def physicist_list(request):
    physicists = Physicist.objects.filter(is_active=True)
    rows = [{'physicist': p, **p.credential_summary(), 'percent': p.percent_complete()}
            for p in physicists]
    return render(request, 'credentialing/physicist_list.html', {
        'rows': rows,
        'is_admin': _is_admin(request),
    })


@login_required_
def physicist_detail(request, pk):
    physicist = get_object_or_404(Physicist, pk=pk)
    categories = _grouped_skills(physicist)
    summary = physicist.credential_summary()
    return render(request, 'credentialing/physicist_detail.html', {
        'physicist': physicist,
        'categories': categories,
        'summary': summary,
        'percent': physicist.percent_complete(),
        'can_edit': _can_edit(request, physicist),
        'is_admin': _is_admin(request),
        'status_choices': Credential.STATUS_CHOICES,
        'today': timezone.now().date(),
    })


@login_required_
def update_credential(request, physicist_pk, skill_pk):
    """Inline status update from the checklist page."""
    physicist = get_object_or_404(Physicist, pk=physicist_pk)
    skill = get_object_or_404(Skill, pk=skill_pk)
    if request.method != 'POST':
        return redirect('physicist_detail', pk=physicist.pk)
    if not _can_edit(request, physicist):
        messages.error(request, 'You do not have permission to update this checklist.')
        return redirect('physicist_detail', pk=physicist.pk)

    status = request.POST.get('status', 'not_started')
    valid = {s for s, _ in Credential.STATUS_CHOICES}
    if status not in valid:
        status = 'not_started'

    date_completed = request.POST.get('date_completed', '').strip() or None
    if date_completed:
        try:
            date_completed = datetime.datetime.strptime(date_completed, '%Y-%m-%d').date()
        except ValueError:
            date_completed = None
    verified_by = request.POST.get('verified_by', '').strip()
    notes = request.POST.get('notes', '').strip()

    # Completing a skill without a date defaults to today
    if status == 'credentialed' and not date_completed:
        date_completed = timezone.now().date()
    if status in ('not_started', 'not_applicable'):
        date_completed = None

    cred, _ = Credential.objects.update_or_create(
        physicist=physicist, skill=skill,
        defaults={'status': status, 'date_completed': date_completed,
                  'verified_by': verified_by, 'notes': notes,
                  'updated_by': request.user if request.user.is_authenticated else None})
    messages.success(request, f'{skill.name}: {cred.get_status_display()}.')
    return redirect(f"/physicists/{physicist.pk}/#skill-{skill.pk}")


@login_required_
def matrix(request):
    """Skills x physicists grid for the whole group."""
    physicists = list(Physicist.objects.filter(is_active=True))
    cred_map = {}
    for c in Credential.objects.filter(physicist__in=physicists,
                                       skill__is_active=True).select_related('skill'):
        cred_map[(c.physicist_id, c.skill_id)] = c.effective_status

    category_filter = request.GET.get('category', '')
    categories = []
    for cat in SkillCategory.objects.prefetch_related('skills'):
        if category_filter and str(cat.pk) != category_filter:
            continue
        rows = []
        for skill in cat.skills.filter(is_active=True):
            cells = [cred_map.get((p.pk, skill.pk), 'not_started') for p in physicists]
            rows.append({'skill': skill, 'cells': cells})
        if rows:
            categories.append({'category': cat, 'rows': rows})

    return render(request, 'credentialing/matrix.html', {
        'physicists': physicists,
        'categories': categories,
        'all_categories': SkillCategory.objects.all(),
        'category_filter': category_filter,
        'is_admin': _is_admin(request),
    })


@login_required_
def matrix_export(request):
    """CSV export of the full matrix."""
    physicists = list(Physicist.objects.filter(is_active=True))
    cred_map = {}
    for c in Credential.objects.filter(physicist__in=physicists, skill__is_active=True):
        cred_map[(c.physicist_id, c.skill_id)] = c.effective_status

    labels = dict(Credential.STATUS_CHOICES)
    labels['expired'] = 'Expired'

    response = HttpResponse(content_type='text/csv')
    stamp = timezone.now().strftime('%Y-%m-%d')
    response['Content-Disposition'] = f'attachment; filename="physics_credentialing_{stamp}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Category', 'Subcategory', 'Skill'] + [str(p) for p in physicists])
    for cat in SkillCategory.objects.prefetch_related('skills'):
        for skill in cat.skills.filter(is_active=True):
            row = [cat.name, skill.subcategory, skill.name]
            for p in physicists:
                row.append(labels.get(cred_map.get((p.pk, skill.pk), 'not_started'), ''))
            writer.writerow(row)
    return response


# ─── Admin management ─────────────────────────────────────────────────────────

@admin_required
def add_physicist(request):
    if request.method == 'POST':
        first = request.POST.get('first_name', '').strip()
        last = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        title = request.POST.get('title', '').strip()
        if first and last and email:
            if Physicist.objects.filter(email=email).exists():
                messages.error(request, 'A physicist with that email already exists.')
            else:
                p = Physicist.objects.create(first_name=first, last_name=last,
                                             email=email, title=title)
                messages.success(request, f'Added {p}.')
                return redirect('physicist_detail', pk=p.pk)
        else:
            messages.error(request, 'First name, last name, and email are required.')
    return render(request, 'credentialing/physicist_form.html')


@admin_required
def deactivate_physicist(request, pk):
    physicist = get_object_or_404(Physicist, pk=pk)
    if request.method == 'POST':
        physicist.is_active = False
        physicist.save()
        messages.success(request, f'{physicist} deactivated.')
    return redirect('physicist_list')
