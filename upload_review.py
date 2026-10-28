"""Temporary, opt-in upload acceptance gate; it never enables public uploads.

Only an explicitly approved, short-lived review key can bootstrap the existing
anonymous business session. The key is sent in a header, never returned or saved
in the signed session. A signed grant also requires a live owner in private
storage, so expiry, deletion, key rotation and data loss revoke access.
"""
import hashlib
import hmac
import os
import re
import sqlite3
import time

from flask import current_app, request, session

from business_store import BusinessError, owner_key


_GRANT = 'upload_review'
_KEY_PATTERN = re.compile(r'[a-f0-9]{64}')


def configure_upload_review(app):
    """Read configuration without changing the existing public upload flag."""
    enabled = app.config.get('UPLOAD_REVIEW_ENABLED')
    if enabled is None:
        value = os.environ.get('ENABLE_BUSINESS_UPLOAD_REVIEW', 'false').lower()
        if value not in ('true', 'false', '1', '0'):
            raise ValueError('ENABLE_BUSINESS_UPLOAD_REVIEW must be true or false.')
        enabled = value in ('true', '1')
    if not isinstance(enabled, bool):
        raise ValueError('UPLOAD_REVIEW_ENABLED must be a boolean.')
    key_hash = app.config.get('UPLOAD_REVIEW_KEY_SHA256',
                              os.environ.get('MARGINGUARD_UPLOAD_REVIEW_KEY_SHA256', ''))
    deadline = app.config.get('UPLOAD_REVIEW_DEADLINE', os.environ.get('MARGINGUARD_UPLOAD_REVIEW_DEADLINE', '0'))
    try:
        if isinstance(deadline, bool) or not re.fullmatch(r'[0-9]{1,12}', str(deadline)):
            raise ValueError
        deadline = int(deadline)
    except (TypeError, ValueError):
        raise ValueError('Upload review requires an integer UTC deadline.') from None
    ttl = app.config.get('UPLOAD_REVIEW_GRANT_TTL', 1800)
    if isinstance(ttl, bool) or not isinstance(ttl, int) or not 1 <= ttl <= 7200:
        raise ValueError('Upload review session duration must be between 1 and 7200 seconds.')
    if enabled:
        if not app.config.get('PUBLIC_MODE'):
            raise ValueError('Upload review is only available with public-mode protections.')
        if app.config.get('ENABLE_BUSINESS_UPLOAD'):
            raise ValueError('Choose public uploads or controlled upload review, not both.')
        if not isinstance(key_hash, str) or not _KEY_PATTERN.fullmatch(key_hash) or deadline <= 0:
            raise ValueError('Upload review requires a SHA-256 key digest and UTC deadline.')
        now = app.config.get('UPLOAD_REVIEW_CLOCK', time.time)()
        if deadline > now + 7200:
            raise ValueError('Upload review deadline must be within the next two hours.')
        # An expired deadline starts safely with the gate closed, so an old
        # review configuration cannot take Synthetic Demo or ABS offline.
    app.config.update(UPLOAD_REVIEW_ENABLED=enabled, UPLOAD_REVIEW_KEY_SHA256=key_hash,
                      UPLOAD_REVIEW_DEADLINE=deadline, UPLOAD_REVIEW_GRANT_TTL=ttl)


def _now():
    return current_app.config.get('UPLOAD_REVIEW_CLOCK', time.time)()


def review_window_open():
    config = current_app.config
    return (config.get('UPLOAD_REVIEW_ENABLED') is True
            and not config.get('ENABLE_BUSINESS_UPLOAD', False)
            and isinstance(config.get('UPLOAD_REVIEW_KEY_SHA256'), str)
            and _KEY_PATTERN.fullmatch(config['UPLOAD_REVIEW_KEY_SHA256']) is not None
            and _now() < config.get('UPLOAD_REVIEW_DEADLINE', 0))


def _fingerprint():
    return current_app.config['UPLOAD_REVIEW_KEY_SHA256']


def validate_review_bootstrap():
    """Validate a one-time bootstrap header; the caller still creates the owner.

    Missing header returns False. An invalid or misplaced supplied header fails
    without creating storage or an anonymous session. Only the existing GET
    /api/business/session endpoint can exchange it for a signed review grant.
    """
    provided = request.headers.get('X-Upload-Review-Key')
    if provided is None:
        return False
    if not review_window_open():
        raise BusinessError('uploads_disabled', 'Controlled upload testing is unavailable or has ended.', 503)
    if request.endpoint != 'business.browser_session' or request.method != 'GET':
        raise BusinessError('review_rejected', 'Start the controlled upload session before submitting data.', 403)
    if current_app.config.get('PUBLIC_MODE') and not request.is_secure:
        raise BusinessError('review_rejected', 'Use the secure HTTPS site to start a controlled upload session.', 403)
    origin = request.headers.get('Origin')
    if ((origin and origin != request.host_url.rstrip('/'))
            or request.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none')):
        raise BusinessError('review_rejected', 'Open the controlled upload page on this website and retry.', 403)
    if (not _KEY_PATTERN.fullmatch(provided)
            or not hmac.compare_digest(hashlib.sha256(provided.encode('ascii')).hexdigest(), _fingerprint())):
        raise BusinessError('review_rejected', 'The review key is invalid or expired. Check it with the test organiser.', 403)
    return True


def grant_review_session(owner_token, server_expires):
    """Call after session.clear(), business_owner assignment and authentication.

    Call only when validate_review_bootstrap() succeeded on this request. A valid
    signed grant alone must not silently recreate an expired or lost owner.
    """
    if not validate_review_bootstrap() or not _KEY_PATTERN.fullmatch(owner_token):
        raise BusinessError('review_rejected', 'A valid review key is required to start this session.', 403)
    now = _now()
    session[_GRANT] = {
        'key_version': _fingerprint(), 'owner': owner_key(owner_token),
        'issued': now,
        'expires': min(now + current_app.config['UPLOAD_REVIEW_GRANT_TTL'],
                       current_app.config['UPLOAD_REVIEW_DEADLINE'], server_expires),
    }


def revoke_review_session():
    session.pop(_GRANT, None)


def review_session_authorized(*, check_store=True):
    if not review_window_open():
        return False
    grant, owner = session.get(_GRANT), session.get('business_owner')
    if not isinstance(grant, dict) or not isinstance(owner, str) or not _KEY_PATTERN.fullmatch(owner):
        return False
    if set(grant) != {'key_version', 'owner', 'issued', 'expires'}:
        return False
    if (not isinstance(grant['key_version'], str) or not _KEY_PATTERN.fullmatch(grant['key_version'])
            or not isinstance(grant['owner'], str) or not _KEY_PATTERN.fullmatch(grant['owner'])):
        return False
    if not all(isinstance(grant[k], (int, float)) and not isinstance(grant[k], bool)
               for k in ('issued', 'expires')):
        return False
    now = _now()
    if (not grant['issued'] <= now < grant['expires'] <= current_app.config['UPLOAD_REVIEW_DEADLINE']
            or grant['expires'] > grant['issued'] + current_app.config['UPLOAD_REVIEW_GRANT_TTL']):
        return False
    if (not hmac.compare_digest(grant['key_version'], _fingerprint())
            or not hmac.compare_digest(grant['owner'], owner_key(owner))):
        return False
    if check_store:
        # Lazy import avoids a blueprint/helper import cycle. Never touches an
        # anonymous visitor's storage: all signed-grant checks precede this read.
        from business_api import get_business_store
        try:
            get_business_store().authenticate(owner_key(owner), touch=False)
        except (BusinessError, OSError, ValueError, sqlite3.Error):
            return False
    return True


def business_upload_enabled():
    return bool(current_app.config.get('ENABLE_BUSINESS_UPLOAD', False)
                or review_session_authorized())
