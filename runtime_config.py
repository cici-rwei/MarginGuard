"""Explicit local/public configuration; private uploads never live in the repo."""
import os
import secrets
import tempfile
from datetime import timedelta
from pathlib import Path
from werkzeug.middleware.proxy_fix import ProxyFix


# Capacity policy for the existing anonymous service, not a feature-enable flag.
# These limits are server-controlled; untrusted requests cannot raise them.
LOCAL_UPLOAD_LIMITS = {
    'BUSINESS_MAX_FILE_BYTES': 5 * 1024 * 1024,
    'BUSINESS_MAX_ROWS': 50000,
    'BUSINESS_MAX_SERIES': 100,
    'BUSINESS_MAX_DATASET_BYTES': 20 * 1024 * 1024,
    'BUSINESS_MAX_STORAGE_BYTES': 500 * 1024 * 1024,
    'BUSINESS_MAX_JOBS': 2,
    'BUSINESS_MAX_SESSIONS': 100,
    'BUSINESS_WORKER_MEMORY_BYTES': 384 * 1024 * 1024,
    'BUSINESS_WORKER_MAX_OUTPUT_BYTES': 25 * 1024 * 1024,
}
PUBLIC_UPLOAD_LIMITS = {
    'BUSINESS_MAX_FILE_BYTES': 1024 * 1024,
    'BUSINESS_MAX_ROWS': 10000,
    'BUSINESS_MAX_SERIES': 20,
    'BUSINESS_MAX_DATASET_BYTES': 2 * 1024 * 1024,
    'BUSINESS_MAX_STORAGE_BYTES': 16 * 1024 * 1024,
    'BUSINESS_MAX_JOBS': 1,
    'BUSINESS_MAX_SESSIONS': 20,
    'BUSINESS_WORKER_MEMORY_BYTES': 128 * 1024 * 1024,
    'BUSINESS_WORKER_MAX_OUTPUT_BYTES': 2 * 1024 * 1024 + 64 * 1024,
}


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    if value.lower() not in ('true', 'false', '1', '0'):
        raise ValueError(name + ' must be true or false.')
    return value.lower() in ('true', '1')


def configure(app, overrides=None):
    public = (overrides or {}).get('PUBLIC_MODE', env_bool('MARGINGUARD_PUBLIC', False))
    app.config.update(PUBLIC_UPLOAD_LIMITS if public else LOCAL_UPLOAD_LIMITS)
    app.config.update(
        PUBLIC_MODE=public,
        TRUST_REVERSE_PROXY=env_bool('TRUST_REVERSE_PROXY', False),
        SECRET_KEY=os.environ.get('MARGINGUARD_SECRET_KEY') or (None if public else secrets.token_hex(32)),
        ENABLE_BUSINESS_UPLOAD=env_bool('ENABLE_BUSINESS_UPLOAD', not public),
        ENABLE_M5_DEMO=env_bool('ENABLE_M5_DEMO', not public),
        ENABLE_SYNTHETIC_DEMO=env_bool('ENABLE_SYNTHETIC_DEMO', False),
        M5_PUBLIC_LICENSE_CONFIRMED=env_bool('M5_PUBLIC_LICENSE_CONFIRMED'),
        BUSINESS_STORAGE_ROOT=Path(os.environ.get('MARGINGUARD_PRIVATE_DIR',
                                                 str(Path(tempfile.gettempdir()) / 'marginguard-private'))),
        BUSINESS_WORKER_TIMEOUT=5,
        SESSION_COOKIE_NAME='marginguard_session',
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=public,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
        MAX_CONTENT_LENGTH=32768,
        MAX_FORM_MEMORY_SIZE=16384,
        MAX_FORM_PARTS=8,
        DEBUG=False,
    )
    if overrides:
        app.config.update(overrides)
    if app.config['PUBLIC_MODE']:
        # Tests/admin configuration may tighten the profile, but cannot enlarge
        # the public budget. No unrestricted environment override is supported.
        for key, ceiling in PUBLIC_UPLOAD_LIMITS.items():
            value = app.config[key]
            if type(value) is not int or value <= 0:
                raise ValueError('Public upload capacity must use positive whole numbers.')
            app.config[key] = min(value, ceiling)
        secret = app.config.get('SECRET_KEY')
        if not isinstance(secret, str) or len(secret) < 32:
            raise ValueError('Public mode requires MARGINGUARD_SECRET_KEY with at least 32 characters.')
        app.config.update(SESSION_COOKIE_SECURE=True, DEBUG=False)
        if app.config['ENABLE_M5_DEMO'] and not app.config['M5_PUBLIC_LICENSE_CONFIRMED']:
            raise ValueError('Public M5 access requires verified rights and M5_PUBLIC_LICENSE_CONFIRMED=true.')
        hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
        if 'TRUSTED_HOSTS' not in (overrides or {}):
            app.config['TRUSTED_HOSTS'] = [hostname] if hostname else ['localhost', '127.0.0.1']
        if app.config['TRUST_REVERSE_PROXY']:
            # Only enable behind a trusted single TLS-terminating proxy.
            # Do not accept forwarded host or client address as authority.
            app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0, x_port=0, x_prefix=0)

