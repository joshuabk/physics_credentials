"""Login toggle.

The switch lives in physics_credentialing/settings.py as LOGIN_REQUIRED.
Set it to True to require sign-in, False to run the app open.
Restart the dev server after changing it.
"""
from django.conf import settings


def login_enabled():
    """True when the app requires users to sign in."""
    return bool(getattr(settings, 'LOGIN_REQUIRED', False))


def settings_context(request):
    """Template context processor so templates know whether login is on."""
    return {'login_enabled': login_enabled()}
