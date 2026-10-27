"""Notebook lifecycle. Reserve the port before programming; never auto-reset."""
import asyncio
import platform
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import PIL
import tornado
import tornado.httpserver
import tornado.netutil

from .single_image import IntegratedHardware
from .protocol import file_info, require, validate_package, write_json
from .service import Manager, application


def prepare(root, port=8090):
    root = Path(root).resolve()
    manifest = validate_package(root)
    for name in ('pynq_showcase', 'pynq_showcase.protocol', 'pynq_showcase.hardware', 'pynq_showcase.evaluation', 'pynq_showcase.service', 'pynq_showcase.launch', 'pynq_showcase.quality_observer', 'pynq_showcase.single_image'):
        relative = 'pynq_showcase/__init__.py' if name == 'pynq_showcase' else name.replace('.', '/') + '.py'
        require(Path(sys.modules[name].__file__).resolve() == root / relative and
                file_info(root / relative) == manifest['artifacts'][relative], 'Stale imported module: use this fresh package/kernel before FPGA loading')
    require(platform.python_version_tuple()[:2] == ('3', '10'), 'Use the measured board Python 3.10 runtime')
    require(tornado.version_info >= (6, 1), 'Report the installed Tornado version; do not install Windows dependencies on the board')
    # Socket ownership is retained so availability cannot race Overlay download.
    sockets = tornado.netutil.bind_sockets(port, address='0.0.0.0', family=__import__('socket').AF_INET)
    hardware = IntegratedHardware(root)
    context = {'root': root, 'manifest': manifest, 'hardware': hardware, 'sockets': sockets,
               'port': port, 'executor': ThreadPoolExecutor(max_workers=1, thread_name_prefix='real-pl-owner'),
               'start_attempted': False, 'manager': None, 'server': None}
    try:
        hardware.prepare()
        context['runtime'] = {'numpy': np.__version__, 'Pillow': PIL.__version__, 'tornado': tornado.version,
                              **hardware.environment}
        print('BROWSER_PRECHECK_PASS: paired Q4d hashes/runtime/metadata checked; FPGA unchanged', flush=True)
        print('Runtime:', context['runtime'], flush=True)
        print('Port reserved:', port, flush=True)
        return context
    except Exception:
        for sock in sockets:
            sock.close()
        context['executor'].shutdown(wait=False)
        raise


async def start(context):
    require(not context['start_attempted'], 'Start once; do not reload or retry a failed hardware session')
    context['start_attempted'] = True
    try:
        await asyncio.get_running_loop().run_in_executor(context['executor'], context['hardware'].open)
        context['hardware'].environment.update(context['runtime'])
        manager = Manager(context['root'], context['manifest'], context['hardware'], context['executor'])
        context['manager'] = manager
        server = tornado.httpserver.HTTPServer(application(manager), max_buffer_size=1024 * 1024)
        context['server'] = server
        server.add_sockets(context['sockets'])
        addresses = subprocess.check_output(['hostname', '-I'], text=True).strip()
        context['addresses'] = addresses.split()
        print('BROWSER_SERVICE_READY: C7; im0324/512/final/T112 uses live PL single-image refinement; no frame sent yet', flush=True)
        for address in context['addresses']:
            print('Open http://' + address + ':' + str(context['port']) + '/', flush=True)
        print('Session:', manager.session_id, flush=True)
        return manager.status()
    except Exception as exc:
        write_json(context['root'] / 'browser_startup_failure.json',
                   {'type': type(exc).__name__, 'message': str(exc), 'hardware_state': context['hardware'].state,
                    'retained_buffers': len(context['hardware'].retained),
                    'recovery': 'Preserve context/kernel. Do not rerun start or automatically reload Overlay.'})
        raise


async def export_session(context):
    require(context['manager'] is not None, 'Service has not started')
    path = await context['manager'].export()
    print('BROWSER_RECORDS_READY:', path, flush=True)
    return str(path)


async def finish(context):
    require(context['manager'] is not None and context['server'] is not None, 'Service not running')
    context['manager'].finish()  # Reject active/FAULT before closing anything.
    context['server'].stop()
    await context['server'].close_all_connections()
    context['executor'].shutdown(wait=False)
    print('BROWSER_SERVICE_CLOSED_IDLE: native buffers already released; original records retained', flush=True)
