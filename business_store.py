"""Private, short-lived business data with transactional ownership and quotas.

Only normalized JSON is retained, in a SQLite database outside the project.
All writes use BEGIN IMMEDIATE, so quotas and replacement work across workers.
"""
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time


class BusinessError(ValueError):
    def __init__(self, code, message, status=400, issues=None):
        self.code, self.status, self.issues = code, status, issues
        super().__init__(message)


def owner_key(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()


class BusinessStore:
    def __init__(self, root, *, clock=time.time, pending_ttl=900, idle_ttl=1800,
                 absolute_ttl=7200, max_bytes=500 * 1024 * 1024,
                 max_dataset_bytes=20 * 1024 * 1024, max_jobs=2,
                 max_sessions=100, max_file_bytes=5 * 1024 * 1024,
                 max_rows=50000, max_series=100,
                 worker_memory_bytes=384 * 1024 * 1024,
                 max_worker_output_bytes=25 * 1024 * 1024):
        self.root = Path(root).expanduser()
        project = Path(__file__).resolve().parent
        if self.root.is_symlink():
            raise ValueError('Business storage must be a private real directory.')
        self.root = self.root.resolve()
        if self.root == project or project in self.root.parents:
            raise ValueError('Business storage must be outside the project.')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.root.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Business storage must be owned by this process user and mode 0700.')
        self.path = self.root / 'business.sqlite3'
        if self.path.is_symlink():
            raise ValueError('Business database must not be a symlink.')
        self.clock, self.pending_ttl, self.idle_ttl = clock, pending_ttl, idle_ttl
        self.absolute_ttl, self.max_bytes = absolute_ttl, max_bytes
        self.max_dataset_bytes, self.max_jobs = max_dataset_bytes, max_jobs
        self.max_sessions = max_sessions
        self.max_file_bytes, self.max_rows, self.max_series = max_file_bytes, max_rows, max_series
        self.worker_memory_bytes = worker_memory_bytes
        self.max_worker_output_bytes = max_worker_output_bytes
        self._cleanup_started = False
        self._cleanup_lock = threading.Lock()
        # Set private permissions before SQLite opens the database.
        descriptor = os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        os.chmod(self.path, 0o600)
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sessions (
                    owner TEXT PRIMARY KEY, csrf TEXT NOT NULL, created REAL NOT NULL,
                    seen REAL NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, revision TEXT NOT NULL,
                    state TEXT NOT NULL, expires REAL NOT NULL,
                    payload TEXT NOT NULL, bytes INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS datasets_owner ON datasets(owner);
                CREATE TABLE IF NOT EXISTS rates (
                    owner TEXT NOT NULL, bucket TEXT NOT NULL, window INTEGER NOT NULL,
                    count INTEGER NOT NULL, PRIMARY KEY(owner,bucket,window));
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS global_rates (
                    bucket TEXT NOT NULL, window INTEGER NOT NULL,
                    expires REAL NOT NULL, count INTEGER NOT NULL,
                    PRIMARY KEY(bucket,window));
            ''')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=5, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA secure_delete=ON')
            db.execute('PRAGMA journal_mode=DELETE')
            # Bound database growth as well as JSON admission. Temporary rollback
            # journal/OS disk space still requires a hosting filesystem quota.
            page_size = db.execute('PRAGMA page_size').fetchone()[0]
            pages = max(128, (self.max_bytes + page_size - 1) // page_size + 128)
            db.execute('PRAGMA max_page_count=%d' % pages)
            yield db
            if db.in_transaction:
                db.commit()
        except Exception:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def _session(self, db, owner, now, touch=False):
        row = db.execute('SELECT * FROM sessions WHERE owner=?', (owner,)).fetchone()
        if row is None or row['expires'] <= now or row['seen'] + self.idle_ttl <= now:
            raise BusinessError('session_expired', 'Your temporary session expired. Start a new upload session.', 401)
        if touch:
            db.execute('UPDATE sessions SET seen=? WHERE owner=?', (now, owner))
        return row

    def create_session(self):
        self.cleanup()
        token, csrf = secrets.token_hex(32), secrets.token_hex(32)
        owner, now = owner_key(token), self.clock()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] >= self.max_sessions:
                raise BusinessError('session_capacity', 'Temporary service capacity reached. Try again later.', 429)
            db.execute('INSERT INTO sessions VALUES (?,?,?,?,?)',
                       (owner, csrf, now, now, now + self.absolute_ttl))
            db.commit()
        return token, csrf, now + self.absolute_ttl

    def authenticate(self, owner, *, touch=True):
        now = self.clock()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._session(db, owner, now, touch)
            db.commit()
        return dict(row)

    def active(self, owner):
        now = self.clock()
        with self._connect() as db:
            self._session(db, owner, now)
            row = db.execute("SELECT id,revision FROM datasets WHERE owner=? AND state='ready' AND expires>?",
                             (owner, now)).fetchone()
        return {'dataset_id': row['id'], 'revision': row['revision']} if row else None

    def rate(self, owner, bucket, limit, seconds):
        now = self.clock()
        window = int(now // seconds)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._session(db, owner, now)
            old = db.execute('SELECT count FROM rates WHERE owner=? AND bucket=? AND window=?',
                             (owner, bucket, window)).fetchone()
            if old and old[0] >= limit:
                raise BusinessError('rate_limit', 'Request limit reached. Please wait before trying again.', 429)
            db.execute('INSERT INTO rates VALUES (?,?,?,1) ON CONFLICT(owner,bucket,window) DO UPDATE SET count=count+1',
                       (owner, bucket, window))
            db.commit()

    def acquire_job(self, owner, seconds):
        now, job_id = self.clock(), secrets.token_hex(16)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._session(db, owner, now)
            db.execute('DELETE FROM jobs WHERE expires<=?', (now,))
            if db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] >= self.max_jobs:
                raise BusinessError('processing_busy', 'All validation slots are busy. Try again shortly.', 429)
            db.execute('INSERT INTO jobs VALUES (?,?,?)', (job_id, owner, now + seconds))
            db.commit()
        return job_id

    def global_rate(self, bucket, limit, seconds):
        """Atomic admission shared by every owner and application worker.

        Only trusted server policy chooses the bucket and limits. These counters
        deliberately have no owner so creating/deleting a session cannot reset
        admission. Fixed windows may permit a boundary burst of twice the limit.
        """
        if (not isinstance(bucket, str) or not 1 <= len(bucket) <= 64
                or type(limit) is not int or limit <= 0
                or type(seconds) is not int or seconds <= 0):
            raise ValueError('Global admission requires a valid bounded policy.')
        now = self.clock()
        window = int(now // seconds)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM global_rates WHERE expires<=?', (now,))
            row = db.execute('SELECT count FROM global_rates WHERE bucket=? AND window=?',
                             (bucket, window)).fetchone()
            if row and row[0] >= limit:
                raise BusinessError('global_rate_limit',
                                    'The temporary upload service is busy. Wait a minute and try again.', 429)
            db.execute('INSERT INTO global_rates VALUES (?,?,?,1) '
                       'ON CONFLICT(bucket,window) DO UPDATE SET count=count+1',
                       (bucket, window, (window + 1) * seconds))
            db.commit()

    def release_job(self, job_id):
        with self._connect() as db:
            db.execute('DELETE FROM jobs WHERE id=?', (job_id,))

    def save_pending(self, owner, payload):
        text = json.dumps(payload, separators=(',', ':'), allow_nan=False)
        size = len(text.encode('utf-8'))
        if size > self.max_dataset_bytes:
            raise BusinessError('normalized_too_large', 'Normalized data exceeds the temporary dataset limit.', 413)
        identifier, revision, now = secrets.token_hex(16), secrets.token_hex(16), self.clock()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            session = self._session(db, owner, now)
            previous = db.execute("SELECT COALESCE(SUM(bytes),0) FROM datasets WHERE owner=? AND state='pending'", (owner,)).fetchone()[0]
            used = db.execute('SELECT COALESCE(SUM(bytes),0) FROM datasets').fetchone()[0]
            if used - previous + size > self.max_bytes:
                raise BusinessError('storage_capacity', 'Temporary storage is full. Try again later.', 429)
            db.execute("DELETE FROM datasets WHERE owner=? AND state='pending'", (owner,))
            db.execute('INSERT INTO datasets VALUES (?,?,?,?,?,?,?)',
                       (identifier, owner, revision, 'pending', min(now + self.pending_ttl, session['expires']), text, size))
            db.commit()
        return identifier, revision

    def load(self, owner, identifier, *, state=None, revision=None):
        now = self.clock()
        with self._connect() as db:
            self._session(db, owner, now)
            row = db.execute('SELECT * FROM datasets WHERE id=? AND owner=?', (identifier, owner)).fetchone()
        if row is None:
            raise BusinessError('dataset_not_found', 'This temporary dataset is not available to this session.', 404)
        if row['expires'] <= now:
            raise BusinessError('dataset_expired', 'The temporary dataset expired. Upload it again.', 410)
        if state and row['state'] != state:
            raise BusinessError('dataset_state', 'The dataset is not in the required state.', 409)
        if revision is not None and row['revision'] != revision:
            raise BusinessError('revision_conflict', 'The dataset version changed. Reload its catalog.', 409)
        return dict(row, payload=json.loads(row['payload']))

    def confirm(self, owner, identifier, revision, payload):
        text = json.dumps(payload, separators=(',', ':'), allow_nan=False)
        size, now = len(text.encode('utf-8')), self.clock()
        if size > self.max_dataset_bytes:
            raise BusinessError('normalized_too_large', 'Confirmed data exceeds the temporary dataset limit.', 413)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            session = self._session(db, owner, now)
            row = db.execute('SELECT * FROM datasets WHERE id=? AND owner=?', (identifier, owner)).fetchone()
            if not row:
                raise BusinessError('dataset_not_found', 'This temporary dataset is not available to this session.', 404)
            if row['expires'] <= now:
                raise BusinessError('dataset_expired', 'The upload expired before confirmation.', 410)
            if row['state'] != 'pending' or row['revision'] != revision:
                raise BusinessError('revision_conflict', 'This upload has already changed or been confirmed.', 409)
            prior = db.execute('SELECT COALESCE(SUM(bytes),0) FROM datasets WHERE owner=?', (owner,)).fetchone()[0]
            used = db.execute('SELECT COALESCE(SUM(bytes),0) FROM datasets').fetchone()[0]
            if used - prior + size > self.max_bytes:
                raise BusinessError('storage_capacity', 'Temporary storage is full. Try again later.', 429)
            db.execute('DELETE FROM datasets WHERE owner=? AND id<>?', (owner, identifier))
            new_revision = secrets.token_hex(16)
            db.execute("UPDATE datasets SET state='ready',revision=?,expires=?,payload=?,bytes=? WHERE id=?",
                       (new_revision, session['expires'], text, size, identifier))
            db.commit()
        return new_revision

    def delete(self, owner, identifier, state=None):
        self.load(owner, identifier, state=state)
        with self._connect() as db:
            db.execute('DELETE FROM datasets WHERE id=? AND owner=?', (identifier, owner))

    def delete_session(self, owner):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for table in ('datasets', 'rates', 'jobs', 'sessions'):
                db.execute('DELETE FROM ' + table + ' WHERE owner=?', (owner,))
            db.commit()

    def cleanup(self):
        now = self.clock()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM sessions WHERE expires<=? OR seen+?<=?', (now, self.idle_ttl, now))
            db.execute('DELETE FROM datasets WHERE expires<=? OR owner NOT IN (SELECT owner FROM sessions)', (now,))
            db.execute('DELETE FROM rates WHERE owner NOT IN (SELECT owner FROM sessions)')
            db.execute('DELETE FROM jobs WHERE expires<=? OR owner NOT IN (SELECT owner FROM sessions)', (now,))
            db.execute('DELETE FROM global_rates WHERE expires<=?', (now,))
            db.commit()

    def start_cleanup(self, interval=300):
        if interval <= 0:
            return
        with self._cleanup_lock:
            if self._cleanup_started:
                return
            self._cleanup_started = True
        def loop():
            while True:
                time.sleep(interval)
                try:
                    self.cleanup()
                except (sqlite3.Error, OSError):
                    # Access checks still enforce expiry; retry without private logs.
                    continue
        threading.Thread(target=loop, name='business-expiry-cleanup', daemon=True).start()
