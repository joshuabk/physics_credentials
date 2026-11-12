import csv
import datetime
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (CaseLog, ChecklistItem, ChecklistProgress, Credential, Physicist, Skill,
                     SkillCategory, TreatmentSystem, UserProfile)
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

def _checklist_items(systems_by_type=None):
    """Every (skill, system) pair on the checklist, in display order.

    General skills yield (skill, None); per-system skills yield one pair per
    active system of their type. A per-system skill with no systems defined
    yields (skill, None) flagged so the UI can say so.
    """
    if systems_by_type is None:
        systems_by_type = TreatmentSystem.active_by_type()
    for skill in Skill.objects.filter(is_active=True).select_related('category'):
        systems = skill.checklist_systems(systems_by_type)
        if not systems:
            yield skill, None, True
            continue
        for system in systems:
            yield skill, system, False


def _grouped_skills(physicist=None):
    """Categories -> [{'subcategory', 'skills': [{'skill', 'items': [...]}]}] structure.

    Each skill carries one item per system it is credentialed on (a single item
    with system=None for general skills). When a physicist is given, each item
    carries their credential (or None).
    """
    creds = {}
    if physicist is not None:
        creds = {(c.skill_id, c.system_id): c
                 for c in physicist.credentials.select_related('skill', 'system')}

    by_cat = {}
    for skill, system, missing in _checklist_items():
        cat_entry = by_cat.setdefault(skill.category_id, {'category': skill.category,
                                                          'groups': [], 'seen': {}})
        key = skill.subcategory
        if key not in cat_entry['seen']:
            cat_entry['seen'][key] = {'subcategory': key, 'skills': [], 'rows': {}}
            cat_entry['groups'].append(cat_entry['seen'][key])
        group = cat_entry['seen'][key]
        if skill.pk not in group['rows']:
            group['rows'][skill.pk] = {'skill': skill, 'items': [], 'no_systems': False}
            group['skills'].append(group['rows'][skill.pk])
        row = group['rows'][skill.pk]
        if missing:
            row['no_systems'] = True
            continue
        cred = creds.get((skill.pk, system.pk if system else None))
        row['items'].append({
            'system': system,
            'credential': cred,
            'status': cred.effective_status if cred else 'not_started',
        })

    categories = []
    for cat in SkillCategory.objects.all():
        entry = by_cat.get(cat.pk)
        if not entry:
            continue
        for g in entry['groups']:
            del g['rows']
            for row in g['skills']:
                row['span'] = max(len(row['items']), 1)
        del entry['seen']
        categories.append(entry)
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
                                       ).select_related('physicist', 'skill', 'system'):
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


def _item_anchor(skill, system):
    return f"skill-{skill.pk}" if system is None else f"skill-{skill.pk}-sys-{system.pk}"


def _attach_training(categories, physicist):
    """Add review-topic ticks and logged cases to every checklist item.

    Each item gains 'training': {'topics', 'done', 'total', 'cases', 'case_count',
    'min_cases', 'anchor'} when its skill has topics, a case target or logged cases.
    """
    topics_by_skill = {}
    for t in ChecklistItem.objects.filter(skill__is_active=True).order_by('skill_id', 'order', 'pk'):
        topics_by_skill.setdefault(t.skill_id, []).append(t)
    ticked = {}
    for p in ChecklistProgress.objects.filter(credential__physicist=physicist):
        ticked.setdefault(p.credential_id, {})[p.item_id] = p
    cases = {}
    for c in CaseLog.objects.filter(credential__physicist=physicist):
        cases.setdefault(c.credential_id, []).append(c)

    for cat in categories:
        for g in cat['groups']:
            for row in g['skills']:
                skill = row['skill']
                topics = topics_by_skill.get(skill.pk, [])
                for item in row['items']:
                    cred = item['credential']
                    cred_ticks = ticked.get(cred.pk, {}) if cred else {}
                    cred_cases = cases.get(cred.pk, []) if cred else []
                    if not (topics or skill.min_cases or skill.requirement or cred_cases):
                        item['training'] = None
                        continue
                    rows, done, total = [], 0, 0
                    for i, t in enumerate(topics):
                        heading = i + 1 < len(topics) and topics[i + 1].indent > t.indent
                        tick = cred_ticks.get(t.pk)
                        if not heading:
                            total += 1
                            done += bool(tick)
                        rows.append({'item': t, 'heading': heading, 'tick': tick,
                                     'pad': 14 + 22 * t.indent})
                    item['training'] = {
                        'topics': rows, 'done': done, 'total': total,
                        'cases': cred_cases, 'case_count': len(cred_cases),
                        'min_cases': skill.min_cases,
                        'anchor': _item_anchor(skill, item['system']),
                        'complete': done == total and len(cred_cases) >= (skill.min_cases or 0),
                    }
    return categories


@login_required_
def physicist_detail(request, pk):
    physicist = get_object_or_404(Physicist, pk=pk)
    categories = _attach_training(_grouped_skills(physicist), physicist)
    summary = physicist.credential_summary()
    return render(request, 'credentialing/physicist_detail.html', {
        'physicist': physicist,
        'categories': categories,
        'summary': summary,
        'percent': physicist.percent_complete(),
        'can_edit': _can_edit(request, physicist),
        'is_admin': _is_admin(request),
        'status_choices': Credential.STATUS_CHOICES,
        'role_choices': CaseLog.ROLE_CHOICES,
        'open_panel': request.GET.get('open', ''),
        'today': timezone.now().date(),
    })


def _training_target(request, physicist_pk, skill_pk, system_pk):
    """Resolve the (physicist, skill, system) a training update is for.

    Returns (physicist, skill, system, error_redirect); error_redirect is set when
    the request should stop.
    """
    physicist = get_object_or_404(Physicist, pk=physicist_pk)
    skill = get_object_or_404(Skill, pk=skill_pk)
    back = redirect('physicist_detail', pk=physicist.pk)
    if request.method != 'POST':
        return physicist, skill, None, back
    if not _can_edit(request, physicist):
        messages.error(request, 'You do not have permission to update this checklist.')
        return physicist, skill, None, back
    system = None
    if skill.is_per_system:
        if system_pk is None:
            messages.error(request, f'"{skill.name}" is credentialed per system — pick a system.')
            return physicist, skill, None, back
        system = get_object_or_404(TreatmentSystem, pk=system_pk, system_type=skill.system_type)
    elif system_pk is not None:
        messages.error(request, f'"{skill.name}" is not credentialed per system.')
        return physicist, skill, None, back
    return physicist, skill, system, None


def _back_to_panel(physicist, skill, system):
    anchor = _item_anchor(skill, system)
    return redirect(f"/physicists/{physicist.pk}/?open={anchor}#{anchor}")


def _user(request):
    return request.user if request.user.is_authenticated else None


@login_required_
def save_checklist(request, physicist_pk, skill_pk, system_pk=None):
    """Save the ticked review topics for one physicist's skill (and system)."""
    physicist, skill, system, stop = _training_target(request, physicist_pk, skill_pk, system_pk)
    if stop:
        return stop
    cred, _ = Credential.objects.get_or_create(physicist=physicist, skill=skill, system=system)
    wanted = set()
    for raw in request.POST.getlist('topic'):
        if raw.isdigit():
            wanted.add(int(raw))
    valid = set(skill.checklist_items.values_list('pk', flat=True))
    wanted &= valid
    current = {p.item_id: p for p in cred.checklist_progress.all()}
    for item_id, p in current.items():
        if item_id not in wanted:
            p.delete()
    for item_id in wanted - set(current):
        ChecklistProgress.objects.create(credential=cred, item_id=item_id, checked_by=_user(request))
    if wanted:
        cred.mark_started(_user(request))
    messages.success(request, f'{cred.label}: review topics saved ({len(wanted)} ticked).')
    return _back_to_panel(physicist, skill, system)


@login_required_
def add_case(request, physicist_pk, skill_pk, system_pk=None):
    """Log one training case against a physicist's skill (and system)."""
    physicist, skill, system, stop = _training_target(request, physicist_pk, skill_pk, system_pk)
    if stop:
        return stop
    data = request.POST
    try:
        date = datetime.datetime.strptime(data.get('date', '').strip(), '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, 'Enter the date of the case.')
        return _back_to_panel(physicist, skill, system)
    role = data.get('role', 'proctored')
    if role not in dict(CaseLog.ROLE_CHOICES):
        role = 'proctored'
    cred, _ = Credential.objects.get_or_create(physicist=physicist, skill=skill, system=system)
    CaseLog.objects.create(
        credential=cred, date=date, role=role,
        case_type=data.get('case_type', '').strip()[:150],
        patient=data.get('patient', '').strip()[:100],
        performed_with=data.get('performed_with', '').strip()[:150],
        notes=data.get('notes', '').strip(),
        created_by=_user(request))
    cred.mark_started(_user(request))
    count = cred.cases.count()
    target = f' of {skill.min_cases}' if skill.min_cases else ''
    messages.success(request, f'{cred.label}: case logged ({count}{target}).')
    return _back_to_panel(physicist, skill, system)


@login_required_
def delete_case(request, physicist_pk, case_pk):
    case = get_object_or_404(CaseLog.objects.select_related('credential__skill', 'credential__system'),
                             pk=case_pk, credential__physicist_id=physicist_pk)
    cred = case.credential
    physicist, skill, system, stop = _training_target(
        request, physicist_pk, cred.skill_id, cred.system_id)
    if stop:
        return stop
    case.delete()
    messages.success(request, f'{cred.label}: case removed.')
    return _back_to_panel(physicist, skill, system)


@login_required_
def update_credential(request, physicist_pk, skill_pk, system_pk=None):
    """Inline status update from the checklist page.

    system_pk is required for per-system skills and must be omitted for general ones.
    """
    physicist = get_object_or_404(Physicist, pk=physicist_pk)
    skill = get_object_or_404(Skill, pk=skill_pk)
    if request.method != 'POST':
        return redirect('physicist_detail', pk=physicist.pk)
    if not _can_edit(request, physicist):
        messages.error(request, 'You do not have permission to update this checklist.')
        return redirect('physicist_detail', pk=physicist.pk)

    system = None
    if skill.is_per_system:
        if system_pk is None:
            messages.error(request, f'"{skill.name}" is credentialed per system — pick a system.')
            return redirect('physicist_detail', pk=physicist.pk)
        system = get_object_or_404(TreatmentSystem, pk=system_pk, system_type=skill.system_type)
    elif system_pk is not None:
        messages.error(request, f'"{skill.name}" is not credentialed per system.')
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
        physicist=physicist, skill=skill, system=system,
        defaults={'status': status, 'date_completed': date_completed,
                  'verified_by': verified_by, 'notes': notes,
                  'updated_by': request.user if request.user.is_authenticated else None})
    messages.success(request, f'{cred.label}: {cred.get_status_display()}.')
    anchor = f"skill-{skill.pk}" if system is None else f"skill-{skill.pk}-sys-{system.pk}"
    return redirect(f"/physicists/{physicist.pk}/#{anchor}")


@login_required_
def matrix(request):
    """Skills x physicists grid for the whole group."""
def _matrix_rows(physicists, system_filter=''):
    """[(category, [{'skill','system','no_systems','cells'}])] for the matrix and CSV export.

    system_filter (a TreatmentSystem pk) keeps only that system's rows plus general skills.
    """
    cred_map = {}
    for c in Credential.objects.filter(physicist__in=physicists, skill__is_active=True):
        cred_map[(c.physicist_id, c.skill_id, c.system_id)] = c.effective_status

    by_cat = {}
    for skill, system, missing in _checklist_items():
        if system_filter and system is not None and str(system.pk) != system_filter:
            continue
        cells = [cred_map.get((p.pk, skill.pk, system.pk if system else None), 'not_started')
                 for p in physicists]
        by_cat.setdefault(skill.category_id, []).append(
            {'skill': skill, 'system': system, 'no_systems': missing, 'cells': cells})
    return [(cat, by_cat[cat.pk]) for cat in SkillCategory.objects.all() if cat.pk in by_cat]


@login_required_
def matrix(request):
    """Skills x physicists grid for the whole group."""
    physicists = list(Physicist.objects.filter(is_active=True))
    category_filter = request.GET.get('category', '')
    system_filter = request.GET.get('system', '')

    # The system dropdown offers only the systems relevant to the chosen
    # category: the types its per-system skills are credentialed on (e.g.
    # linacs for Machine QA, afterloaders for Brachytherapy Operations).
    type_source = Skill.objects.filter(is_active=True).exclude(system_type='')
    if category_filter.isdigit():
        type_source = type_source.filter(category_id=category_filter)
    used_types = set(type_source.values_list('system_type', flat=True))
    all_systems = list(TreatmentSystem.objects.filter(is_active=True,
                                                      system_type__in=used_types))
    if system_filter and not any(str(sy.pk) == system_filter for sy in all_systems):
        system_filter = ''

    categories = [{'category': cat, 'rows': rows}
                  for cat, rows in _matrix_rows(physicists, system_filter)
                  if not category_filter or str(cat.pk) == category_filter]

    return render(request, 'credentialing/matrix.html', {
        'physicists': physicists,
        'categories': categories,
        'all_categories': SkillCategory.objects.all(),
        'all_systems': all_systems,
        'category_filter': category_filter,
        'system_filter': system_filter,
        'is_admin': _is_admin(request),
    })


@login_required_
def matrix_export(request):
    """CSV export of the full matrix."""
    physicists = list(Physicist.objects.filter(is_active=True))
    labels = dict(Credential.STATUS_CHOICES)
    labels['expired'] = 'Expired'

    response = HttpResponse(content_type='text/csv')
    stamp = timezone.now().strftime('%Y-%m-%d')
    response['Content-Disposition'] = f'attachment; filename="physics_credentialing_{stamp}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Category', 'Subcategory', 'Skill', 'System'] + [str(p) for p in physicists])
    for cat, rows in _matrix_rows(physicists):
        for r in rows:
            system_label = str(r['system']) if r['system'] else ('(no systems defined)' if r['no_systems'] else '')
            writer.writerow([cat.name, r['skill'].subcategory, r['skill'].name, system_label]
                            + [labels.get(cell, '') for cell in r['cells']])
    return response


# ─── Admin management ─────────────────────────────────────────────────────────

def _physicist_form_context(physicist=None, data=None):
    values = {
        'first_name': physicist.first_name if physicist else '',
        'last_name': physicist.last_name if physicist else '',
        'email': physicist.email if physicist else '',
        'title': physicist.title if physicist else '',
        'location': physicist.location if physicist else '',
        'hire_date': physicist.hire_date.isoformat() if physicist and physicist.hire_date else '',
        'is_active': physicist.is_active if physicist else True,
    }
    if data is not None:
        values.update({k: data.get(k, '').strip() for k in
                       ('first_name', 'last_name', 'email', 'title', 'location', 'hire_date')})
        values['is_active'] = bool(data.get('is_active'))
    locations = (Physicist.objects.exclude(location='')
                 .order_by('location').values_list('location', flat=True).distinct())
    return {'physicist': physicist, 'v': values, 'locations': list(locations), 'is_admin': True}


def _parse_physicist_post(request, physicist=None):
    """Validate the physicist form. Returns (cleaned dict, error message)."""
    data = request.POST
    first = data.get('first_name', '').strip()
    last = data.get('last_name', '').strip()
    email = data.get('email', '').strip()
    if not (first and last and email):
        return None, 'First name, last name, and email are required.'
    dup = Physicist.objects.filter(email__iexact=email)
    if physicist is not None:
        dup = dup.exclude(pk=physicist.pk)
    if dup.exists():
        return None, 'A physicist with that email already exists.'
    hire_date = data.get('hire_date', '').strip() or None
    if hire_date:
        try:
            hire_date = datetime.datetime.strptime(hire_date, '%Y-%m-%d').date()
        except ValueError:
            return None, 'Hire date must be a valid date.'
    cleaned = {
        'first_name': first, 'last_name': last, 'email': email,
        'title': data.get('title', '').strip(),
        'location': data.get('location', '').strip(),
        'hire_date': hire_date,
    }
    if physicist is not None:
        cleaned['is_active'] = bool(data.get('is_active'))
    return cleaned, None


@admin_required
def add_physicist(request):
    if request.method == 'POST':
        cleaned, error = _parse_physicist_post(request)
        if error:
            messages.error(request, error)
            return render(request, 'credentialing/physicist_form.html',
                          _physicist_form_context(data=request.POST))
        p = Physicist.objects.create(**cleaned)
        messages.success(request, f'Added {p}.')
        return redirect('physicist_detail', pk=p.pk)
    return render(request, 'credentialing/physicist_form.html', _physicist_form_context())


@admin_required
def edit_physicist(request, pk):
    physicist = get_object_or_404(Physicist, pk=pk)
    if request.method == 'POST':
        cleaned, error = _parse_physicist_post(request, physicist)
        if error:
            messages.error(request, error)
            return render(request, 'credentialing/physicist_form.html',
                          _physicist_form_context(physicist, data=request.POST))
        for field, value in cleaned.items():
            setattr(physicist, field, value)
        physicist.save()
        messages.success(request, f'Saved {physicist}.')
        return redirect('physicist_detail', pk=physicist.pk)
    return render(request, 'credentialing/physicist_form.html', _physicist_form_context(physicist))


@admin_required
def deactivate_physicist(request, pk):
    physicist = get_object_or_404(Physicist, pk=pk)
    if request.method == 'POST':
        physicist.is_active = False
        physicist.save()
        messages.success(request, f'{physicist} deactivated.')
    return redirect('physicist_list')


# ─── Skill management ─────────────────────────────────────────────────────────

def _skill_form_context(skill=None, data=None):
    """Context for the skill form: existing categories plus current field values."""
    values = {
        'category': str(skill.category_id) if skill else '',
        'new_category': '',
        'subcategory': skill.subcategory if skill else '',
        'name': skill.name if skill else '',
        'order': skill.order if skill else '',
        'as_applicable': skill.as_applicable if skill else False,
        'renewal_months': skill.renewal_months if skill and skill.renewal_months else '',
        'system_type': skill.system_type if skill else '',
        'is_active': skill.is_active if skill else True,
        'requirement': skill.requirement if skill else '',
        'min_cases': skill.min_cases if skill and skill.min_cases else '',
        'checklist': skill.checklist_text() if skill else '',
    }
    if data is not None:
        values.update({
            'category': data.get('category', ''),
            'new_category': data.get('new_category', '').strip(),
            'subcategory': data.get('subcategory', '').strip(),
            'name': data.get('name', '').strip(),
            'order': data.get('order', '').strip(),
            'as_applicable': bool(data.get('as_applicable')),
            'renewal_months': data.get('renewal_months', '').strip(),
            'system_type': data.get('system_type', ''),
            'is_active': bool(data.get('is_active')),
            'requirement': data.get('requirement', '').strip(),
            'min_cases': data.get('min_cases', '').strip(),
            'checklist': data.get('checklist', ''),
        })
    subcategories = (Skill.objects.exclude(subcategory='').order_by('subcategory')
                     .values_list('subcategory', flat=True).distinct())
    return {
        'skill': skill,
        'categories': SkillCategory.objects.all(),
        'subcategories': list(subcategories),
        'system_types': TreatmentSystem.TYPE_CHOICES,
        'system_counts': _system_counts(),
        'v': values,
        'is_admin': True,
    }


def _system_counts():
    """{'linac': 3, 'hdr': 1, ...} active systems per type, for the skill form."""
    return {t: len(v) for t, v in TreatmentSystem.active_by_type().items()}


def _parse_skill_post(request, skill=None):
    """Validate the skill form. Returns (cleaned dict, error message)."""
    data = request.POST
    name = data.get('name', '').strip()
    subcategory = data.get('subcategory', '').strip()
    new_category = data.get('new_category', '').strip()
    category_id = data.get('category', '')

    if not name:
        return None, 'Skill name is required.'

    # Category: either an existing one or a new one typed in
    category = None
    if new_category:
        category = SkillCategory.objects.filter(name__iexact=new_category).first()
        if category is None:
            last = SkillCategory.objects.order_by('-order').first()
            category = SkillCategory.objects.create(
                name=new_category, order=(last.order + 1) if last else 0)
    elif category_id:
        category = SkillCategory.objects.filter(pk=category_id).first()
    if category is None:
        return None, 'Choose a category or enter a new one.'

    order_raw = data.get('order', '').strip()
    if order_raw:
        try:
            order = int(order_raw)
            if order < 0:
                raise ValueError
        except ValueError:
            return None, 'Order must be a whole number (0 or greater).'
    elif skill is not None:
        order = skill.order
    else:
        last = Skill.objects.filter(category=category).order_by('-order').first()
        order = (last.order + 1) if last else 1

    renewal_raw = data.get('renewal_months', '').strip()
    renewal_months = None
    if renewal_raw:
        try:
            renewal_months = int(renewal_raw)
            if renewal_months <= 0:
                raise ValueError
        except ValueError:
            return None, 'Renewal months must be a whole number greater than 0, or blank.'

    system_type = data.get('system_type', '')
    if system_type and system_type not in dict(TreatmentSystem.TYPE_CHOICES):
        return None, 'Unknown system type.'

    min_raw = data.get('min_cases', '').strip()
    min_cases = None
    if min_raw:
        try:
            min_cases = int(min_raw)
            if min_cases <= 0:
                raise ValueError
        except ValueError:
            return None, 'Minimum cases must be a whole number greater than 0, or blank.'

    dup = Skill.objects.filter(category=category, subcategory=subcategory, name=name)
    if skill is not None:
        dup = dup.exclude(pk=skill.pk)
    if dup.exists():
        where = f'{category.name} / {subcategory}' if subcategory else category.name
        return None, f'"{name}" already exists in {where}.'

    return {
        'category': category,
        'subcategory': subcategory,
        'name': name,
        'order': order,
        'as_applicable': bool(data.get('as_applicable')),
        'renewal_months': renewal_months,
        'system_type': system_type,
        'is_active': bool(data.get('is_active')),
        'requirement': data.get('requirement', '').strip(),
        'min_cases': min_cases,
    }, None


def _skills_url(category=None, skill=None, inactive=False):
    """URL back into the Skills page, focused on a category (and optionally a skill row)."""
    url = '/skills/'
    params = []
    if category is not None:
        params.append(f'category={category.pk}')
    if inactive:
        params.append('inactive=1')
    if params:
        url += '?' + '&'.join(params)
    if skill is not None:
        url += f'#skill-{skill.pk}'
    return url


def _normalize_category_order():
    for i, cat in enumerate(SkillCategory.objects.all(), start=1):
        if cat.order != i:
            cat.order = i
            cat.save(update_fields=['order'])


def _normalize_skill_order(category):
    for i, skill in enumerate(category.skills.order_by('order', 'name'), start=1):
        if skill.order != i:
            skill.order = i
            skill.save(update_fields=['order'])


@admin_required
def skill_list(request):
    """Two-pane skill manager: categories down the left, the selected category's skills on the right."""
    show_inactive = request.GET.get('inactive') == '1'
    all_categories = list(SkillCategory.objects.prefetch_related('skills'))

    selected = None
    wanted = request.GET.get('category', '')
    for cat in all_categories:
        if str(cat.pk) == wanted:
            selected = cat
    if selected is None and all_categories:
        selected = all_categories[0]

    sidebar = []
    for cat in all_categories:
        skills = list(cat.skills.all())
        sidebar.append({
            'category': cat,
            'active_count': sum(1 for s in skills if s.is_active),
            'total_count': len(skills),
            'is_selected': selected is not None and cat.pk == selected.pk,
        })

    groups, inactive_count, skill_count = [], 0, 0
    if selected is not None:
        seen = {}
        skills = list(selected.skills.prefetch_related('credentials'))
        for skill in skills:
            if not skill.is_active:
                inactive_count += 1
                if not show_inactive:
                    continue
            skill_count += 1
            key = skill.subcategory
            if key not in seen:
                seen[key] = {'subcategory': key, 'skills': []}
                groups.append(seen[key])
            seen[key]['skills'].append({
                'skill': skill,
                'credential_count': sum(1 for c in skill.credentials.all()
                                        if c.status != 'not_started'),
            })
        for g in groups:
            rows = g['skills']
            for i, row in enumerate(rows):
                row['is_first'] = i == 0
                row['is_last'] = i == len(rows) - 1

    idx = next((i for i, c in enumerate(all_categories) if selected and c.pk == selected.pk), -1)
    return render(request, 'credentialing/skill_list.html', {
        'sidebar': sidebar,
        'selected': selected,
        'selected_is_first': idx == 0,
        'selected_is_last': idx == len(all_categories) - 1,
        'selected_total': len(selected.skills.all()) if selected else 0,
        'groups': groups,
        'skill_count': skill_count,
        'inactive_count': inactive_count,
        'show_inactive': show_inactive,
        'is_admin': True,
    })


@admin_required
def add_skill(request):
    if request.method == 'POST':
        cleaned, error = _parse_skill_post(request)
        if error:
            messages.error(request, error)
            return render(request, 'credentialing/skill_form.html',
                          _skill_form_context(data=request.POST))
        skill = Skill.objects.create(**cleaned)
        skill.set_checklist_from_text(request.POST.get('checklist', ''))
        messages.success(request, f'Added skill "{skill.name}" to {skill.category.name}.')
        return redirect(_skills_url(skill.category, skill))
    ctx = _skill_form_context()
    # Pre-select a category when arriving from a category's "+ Add" link,
    # and default the order to the next slot in that category.
    category_id = request.GET.get('category', '')
    ctx['v']['category'] = category_id
    ctx['v']['subcategory'] = request.GET.get('subcategory', '')
    if category_id:
        last = Skill.objects.filter(category_id=category_id).order_by('-order').first()
        ctx['v']['order'] = (last.order + 1) if last else 1
    return render(request, 'credentialing/skill_form.html', ctx)


@admin_required
def edit_skill(request, pk):
    skill = get_object_or_404(Skill, pk=pk)
    if request.method == 'POST':
        cleaned, error = _parse_skill_post(request, skill)
        if error:
            messages.error(request, error)
            return render(request, 'credentialing/skill_form.html',
                          _skill_form_context(skill, data=request.POST))
        for field, value in cleaned.items():
            setattr(skill, field, value)
        skill.save()
        skill.set_checklist_from_text(request.POST.get('checklist', ''))
        messages.success(request, f'Saved "{skill.name}".')
        return redirect(_skills_url(skill.category, skill, inactive=not skill.is_active))
    return render(request, 'credentialing/skill_form.html', _skill_form_context(skill))


@admin_required
def delete_skill(request, pk):
    """Permanently remove a skill and every credential recorded against it."""
    skill = get_object_or_404(Skill, pk=pk)
    category = skill.category
    if request.method == 'POST':
        name = skill.name
        skill.delete()
        _normalize_skill_order(category)
        messages.success(request, f'Deleted "{name}" from {category.name}.')
    return redirect(_skills_url(category))


@admin_required
def toggle_skill(request, pk):
    """Hide a skill from checklists (or restore it) without losing credential history."""
    skill = get_object_or_404(Skill, pk=pk)
    if request.method == 'POST':
        skill.is_active = not skill.is_active
        skill.save()
        messages.success(request, f'"{skill.name}" {"restored" if skill.is_active else "hidden"}.')
    return redirect(_skills_url(skill.category, skill, inactive=not skill.is_active))


@admin_required
def move_skill(request, pk, direction):
    """Swap a skill with its neighbour (same category and subcategory)."""
    skill = get_object_or_404(Skill, pk=pk)
    if request.method == 'POST':
        _normalize_skill_order(skill.category)
        skill.refresh_from_db()
        siblings = skill.category.skills.filter(subcategory=skill.subcategory)
        if direction == 'up':
            neighbour = siblings.filter(order__lt=skill.order).order_by('-order').first()
        else:
            neighbour = siblings.filter(order__gt=skill.order).order_by('order').first()
        if neighbour is not None:
            skill.order, neighbour.order = neighbour.order, skill.order
            skill.save(update_fields=['order'])
            neighbour.save(update_fields=['order'])
    return redirect(_skills_url(skill.category, skill, inactive=not skill.is_active))


@admin_required
def add_category(request):
    """Create an empty category from the sidebar form on the Skills page."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Category name is required.')
        elif SkillCategory.objects.filter(name__iexact=name).exists():
            messages.error(request, f'A category named "{name}" already exists.')
        else:
            last = SkillCategory.objects.order_by('-order').first()
            cat = SkillCategory.objects.create(name=name, order=(last.order + 1) if last else 1)
            messages.success(request, f'Added category "{cat.name}". Now add its first skill.')
            return redirect(_skills_url(cat))
    return redirect('skill_list')


@admin_required
def rename_category(request, pk):
    cat = get_object_or_404(SkillCategory, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Category name is required.')
        elif SkillCategory.objects.filter(name__iexact=name).exclude(pk=cat.pk).exists():
            messages.error(request, f'A category named "{name}" already exists.')
        else:
            cat.name = name
            cat.save()
            messages.success(request, f'Renamed category to "{cat.name}".')
    return redirect(_skills_url(cat))


@admin_required
def move_category(request, pk, direction):
    cat = get_object_or_404(SkillCategory, pk=pk)
    if request.method == 'POST':
        _normalize_category_order()
        cat.refresh_from_db()
        if direction == 'up':
            neighbour = SkillCategory.objects.filter(order__lt=cat.order).order_by('-order').first()
        else:
            neighbour = SkillCategory.objects.filter(order__gt=cat.order).order_by('order').first()
        if neighbour is not None:
            cat.order, neighbour.order = neighbour.order, cat.order
            cat.save(update_fields=['order'])
            neighbour.save(update_fields=['order'])
    return redirect(_skills_url(cat))


@admin_required
def delete_category(request, pk):
    """Only an empty category can be deleted; skills must be moved or deleted first."""
    cat = get_object_or_404(SkillCategory, pk=pk)
    if request.method == 'POST':
        if cat.skills.exists():
            messages.error(request, f'"{cat.name}" still has skills. Delete or move them first.')
            return redirect(_skills_url(cat))
        name = cat.name
        cat.delete()
        messages.success(request, f'Deleted category "{name}".')
    return redirect('skill_list')


# ─── Treatment system management ──────────────────────────────────────────────

def _system_form_context(system=None, data=None):
    values = {
        'name': system.name if system else '',
        'system_type': system.system_type if system else '',
        'manufacturer': system.manufacturer if system else '',
        'location': system.location if system else '',
        'is_active': system.is_active if system else True,
    }
    if data is not None:
        values.update({k: data.get(k, '').strip()
                       for k in ('name', 'system_type', 'manufacturer', 'location')})
        values['is_active'] = bool(data.get('is_active'))
    locations = set(Physicist.objects.exclude(location='').values_list('location', flat=True))
    locations |= set(TreatmentSystem.objects.exclude(location='').values_list('location', flat=True))
    return {
        'system': system,
        'v': values,
        'system_types': TreatmentSystem.TYPE_CHOICES,
        'locations': sorted(locations),
        'is_admin': True,
    }


def _parse_system_post(request, system=None):
    data = request.POST
    name = data.get('name', '').strip()
    system_type = data.get('system_type', '').strip()
    if not name:
        return None, 'System name is required.'
    if system_type not in dict(TreatmentSystem.TYPE_CHOICES):
        return None, 'Choose a system type.'
    dup = TreatmentSystem.objects.filter(name__iexact=name)
    if system is not None:
        dup = dup.exclude(pk=system.pk)
    if dup.exists():
        return None, f'A system named "{name}" already exists.'
    cleaned = {
        'name': name,
        'system_type': system_type,
        'manufacturer': data.get('manufacturer', '').strip(),
        'location': data.get('location', '').strip(),
    }
    if system is not None:
        cleaned['is_active'] = bool(data.get('is_active'))
    return cleaned, None


@admin_required
def system_list(request):
    """Treatment systems grouped by type, with the skills credentialed on each type."""
    skills_by_type = {}
    for skill in Skill.objects.filter(is_active=True).exclude(system_type=''):
        skills_by_type.setdefault(skill.system_type, []).append(skill)

    groups = []
    for code, label in TreatmentSystem.TYPE_CHOICES:
        systems = list(TreatmentSystem.objects.filter(system_type=code)
                       .annotate(credential_count=Count('credentials')))
        skills = skills_by_type.get(code, [])
        if systems or skills:
            groups.append({'code': code, 'label': label, 'systems': systems,
                           'skills': skills, 'active_count': sum(1 for s in systems if s.is_active)})
    return render(request, 'credentialing/system_list.html', {
        'groups': groups,
        'system_types': TreatmentSystem.TYPE_CHOICES,
        'is_admin': True,
    })


@admin_required
def add_system(request):
    if request.method == 'POST':
        cleaned, error = _parse_system_post(request)
        if error:
            messages.error(request, error)
            return render(request, 'credentialing/system_form.html',
                          _system_form_context(data=request.POST))
        last = TreatmentSystem.objects.filter(system_type=cleaned['system_type']).order_by('-order').first()
        system = TreatmentSystem.objects.create(order=(last.order + 1) if last else 1, **cleaned)
        messages.success(request, f'Added {system}. Skills set to "per {system.get_system_type_display()}" '
                                  f'now have a checkbox for it on every checklist.')
        return redirect('system_list')
    ctx = _system_form_context()
    ctx['v']['system_type'] = request.GET.get('type', '')
    return render(request, 'credentialing/system_form.html', ctx)


@admin_required
def edit_system(request, pk):
    system = get_object_or_404(TreatmentSystem, pk=pk)
    if request.method == 'POST':
        cleaned, error = _parse_system_post(request, system)
        if error:
            messages.error(request, error)
            return render(request, 'credentialing/system_form.html',
                          _system_form_context(system, data=request.POST))
        for field, value in cleaned.items():
            setattr(system, field, value)
        system.save()
        messages.success(request, f'Saved {system}.')
        return redirect('system_list')
    return render(request, 'credentialing/system_form.html', _system_form_context(system))


@admin_required
def toggle_system(request, pk):
    """Retire a system (hides its checkboxes, keeps history) or bring it back."""
    system = get_object_or_404(TreatmentSystem, pk=pk)
    if request.method == 'POST':
        system.is_active = not system.is_active
        system.save()
        messages.success(request, f'{system} {"restored" if system.is_active else "retired"}.')
    return redirect('system_list')


@admin_required
def delete_system(request, pk):
    """Permanently remove a system and every credential recorded against it."""
    system = get_object_or_404(TreatmentSystem, pk=pk)
    if request.method == 'POST':
        name = str(system)
        system.delete()
        messages.success(request, f'Deleted {name}.')
    return redirect('system_list')
