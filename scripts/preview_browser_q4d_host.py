"""Local UI QA only. NOT deployed; conspicuous HOST_TEST_DOUBLE evidence."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from browser_q4d_fixtures import HostHardware
from pynq_q4d.protocol import validate_package, write_json
from pynq_q4d.service import Manager, application
import tornado.httpserver


async def main():
    root = ROOT / 'build/q4d_host_candidate_01/package'
    hardware = HostHardware(root, delay=0.25)
    manager = Manager(root, validate_package(root), hardware)
    await asyncio.get_running_loop().run_in_executor(manager.executor, hardware.open)
    server = tornado.httpserver.HTTPServer(application(manager))
    server.listen(8098, address='127.0.0.1')
    print('HOST TEST ONLY http://127.0.0.1:8098/ session ' + manager.session_id, flush=True)
    write_json(ROOT / 'build/q4d_host_preview.json', {'session': manager.session_id, 'directory': str(manager.directory), 'evidence_kind': hardware.evidence_kind})
    try:
        await asyncio.Event().wait()
    finally:
        server.stop()
        if manager.pump:
            await manager.pump
        manager.executor.shutdown(wait=True)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
