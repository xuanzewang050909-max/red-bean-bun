"""Repeatable notebook lifecycle around the unchanged, sealed C7 web release.

Import and open_demo perform file checks only. Hardware begins only in start.
Faults retain ownership/context; no reset, retry, process killing or cleanup.
"""
import asyncio
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

CONFIRMATION = 'I_CONFIRM_BOARD_IDLE_AND_START_C7_DEMO'
_instances = {}


def info(path):
    data = Path(path).read_bytes()
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root/'demo_manifest.json').read_bytes())
    if manifest['schema'] != 'c7-repeatable-demo-v1':
        raise RuntimeError('DEMO_SCHEMA_MISMATCH')
    for name, expected in manifest['files'].items():
        path = (root/name).resolve()
        if root not in path.parents or info(path) != expected:
            raise RuntimeError('DEMO_FILE_IDENTITY_MISMATCH: '+name)
    return manifest


def _boot_id():
    # Linux boot identity only: no MMIO, device, driver, network or hardware read.
    return str(uuid.UUID(Path('/proc/sys/kernel/random/boot_id').read_text().strip()))


def _acquire_owner(path):
    import fcntl
    stream = path.open('a+b')
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        stream.close()
        raise RuntimeError('DEMO_OWNED_BY_ANOTHER_KERNEL: keep the current session')
    return stream


class Demo:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.manifest = verify(self.root)
        self.app = self.root/'app'
        self.context = None
        self.attempt = None
        self.owner = None
        self.closed = False
        self.faulted = False
        self.last_export = None
        self.lock = asyncio.Lock()
        self.launch = None

    def _load(self):
        loaded = sys.modules.get('pynq_showcase')
        if loaded and Path(loaded.__file__).resolve() != self.app/'pynq_showcase/__init__.py':
            raise RuntimeError('DIFFERENT_WEB_PACKAGE_IN_KERNEL: use a dedicated demo kernel')
        if str(self.app) not in sys.path:
            sys.path.insert(0, str(self.app))
        self.launch = importlib.import_module('pynq_showcase.launch')
        self.write_json = importlib.import_module('pynq_showcase.protocol').write_json

    def _record(self, name, data):
        path = self.attempt/name
        if path.exists():
            raise RuntimeError('ATTEMPT_RECORD_ALREADY_EXISTS: '+str(path))
        self.write_json(path, data)

    def status(self):
        if self.context and self.context.get('manager'):
            state = self.context['manager'].status()
        else:
            state = dict(service_state='FAULT' if self.faulted else 'NOT_STARTED')
        return dict(**state, demo_attempt=str(self.attempt) if self.attempt else None,
                    urls=['http://'+a+':'+str(self.context['port'])+'/'
                          for a in self.context.get('addresses', [])] if self.context else [])

    async def start(self, confirmation, port=8090):
        if confirmation != CONFIRMATION:
            raise RuntimeError('MANUAL_IDLE_CONFIRMATION_REQUIRED')
        async with self.lock:
            if self.faulted:
                raise RuntimeError('FAULT_PRESERVED: do not retry or restart this kernel')
            if self.context and not self.closed:
                state = self.status()
                if state['service_state'] != 'READY':
                    raise RuntimeError('FAULT_OR_UNKNOWN_STATE_PRESERVED')
                # Idempotent even while a frame is busy: never prepare/load again.
                return dict(**state, reused_running_service=True)
            verify(self.root)
            boot = _boot_id()
            self._load()
            owner = _acquire_owner(self.root/'demo_owner.lock')
            attempts = self.root/'demo_attempts'
            attempts.mkdir(exist_ok=True)
            try:
                for previous in sorted(attempts.iterdir()):
                    if not previous.is_dir():
                        continue
                    intent = json.loads((previous/'start_intent.json').read_bytes())
                    if intent['boot_id'] == boot and not (previous/'closed.json').exists():
                        raise RuntimeError('UNFINISHED_SAME_BOOT_SESSION: '+str(previous))
                if shutil.disk_usage(self.root).free < 1024**3:
                    raise RuntimeError('SD_FREE_SPACE_BELOW_1_GIB: preserve old records')
            except BaseException:
                owner.close()
                raise
            self.owner = owner
            self.attempt = attempts/uuid.uuid4().hex
            self.attempt.mkdir()
            self.closed = False
            self.context = None
            self.last_export = None
            try:
                self._record('start_intent.json', dict(
                    schema='c7-demo-lifecycle-v1', boot_id=boot, pid=os.getpid(),
                    authorization=confirmation, port=port,
                    demo_manifest=info(self.root/'demo_manifest.json'),
                    wrapper=info(Path(__file__)), original_release=self.manifest['original_release']))
                # The original launcher has one fixed failure pathname. Preserve its
                # bytes by relocation before a later-boot start can reuse that name.
                old_failure = self.app/'browser_startup_failure.json'
                if old_failure.exists():
                    identity = info(old_failure)
                    archived = self.attempt/'prior_browser_startup_failure.json'
                    old_failure.rename(archived)
                    self._record('prior_failure_location.json', dict(
                        original=str(old_failure), archived=str(archived), identity=identity))
                self.context = self.launch.prepare(self.app, port=port)
                await self.launch.start(self.context)
                self._record('started.json', self.status())
                return dict(**self.status(), reused_running_service=False)
            except BaseException as exc:
                self.faulted = True
                self._record('failure.json', dict(type=type(exc).__name__, message=str(exc),
                                                  state=self.status(), no_automatic_retry=True))
                raise

    async def _export(self):
        if not self.context or not self.context.get('manager'):
            raise RuntimeError('SERVICE_HAS_NOT_STARTED')
        if self.closed:
            return self.last_export
        # Reuse existing serializer/exporter. Keep each exported snapshot immutable.
        original = Path(await self.launch.export_session(self.context))
        exports = self.attempt/'exports'
        exports.mkdir(exist_ok=True)
        target = exports/('C7_demo_'+uuid.uuid4().hex+'.zip')
        with original.open('rb') as source, target.open('xb') as dest:
            shutil.copyfileobj(source, dest)
        if info(original) != info(target):
            raise RuntimeError('EXPORT_COPY_IDENTITY_MISMATCH')
        self.last_export = str(target)
        return self.last_export

    async def export(self):
        async with self.lock:
            return await self._export()

    async def finish(self):
        async with self.lock:
            if self.closed:
                return self.last_export
            if self.faulted or not self.context or not self.context.get('manager'):
                raise RuntimeError('NO_HEALTHY_RUNNING_SESSION: preserve context')
            manager = self.context['manager']
            # Same conditions as the sealed Manager.finish, before any export.
            if (manager.active or manager.queue or manager.exporting or manager.error
                    or manager.hardware.retained or manager.hardware.state != 'IDLE'):
                raise RuntimeError('NOT_IDLE_OR_FAULTED: wait or preserve the failure; no cleanup')
            archive = await self._export()
            await self.launch.finish(self.context)
            self._record('closed.json', dict(status=self.status(), export=dict(path=archive, **info(archive)),
                                             reason='NORMAL_IDLE_FINISH', hardware_reset=False))
            self.closed = True
            self.owner.close()
            self.owner = None
            return archive


def open_demo(root):
    root = Path(root).resolve()
    verify(root)
    if Path(__file__).resolve() != root/'c7_demo.py':
        raise RuntimeError('WRAPPER_IMPORT_PATH_MISMATCH')
    if root not in _instances:
        _instances[root] = Demo(root)
    return _instances[root]
