"""File-backed application settings (no database migration required).

Settings are stored in app_settings.json next to db.sqlite3. Defaults apply
when the file is missing, so a fresh checkout runs with login turned OFF.
"""
import json
from pathlib import Path

from django.conf import settings as django_settings

SETTINGS_FILE = Path(django_settings.BASE_DIR) / 'app_settings.json'

DEFAULTS = {
    'login_required': False,
}


def get_settings():
    data = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE) as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            data.update(stored)
    except (OSError, ValueError):
        pass
    return data


def set_setting(key, value):
    data = get_settings()
    data[key] = value
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def login_enabled():
    """True when the app requires users to sign in."""
    return bool(get_settings().get('login_required'))


def settings_context(request):
    """Template context processor so templates know whether login is on."""
    return {'login_enabled': login_enabled()}
