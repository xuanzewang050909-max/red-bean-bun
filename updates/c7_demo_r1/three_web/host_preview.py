"""Local browser test only; never included in a deployment. No real PL operations."""
import asyncio
import argparse
import json
import shutil
from pathlib import Path
import tornado.httpserver
import tornado.netutil
from test_web import PACKAGE, host_runtime, si, service, validate_package


async def main(destination,port):
    root=Path(destination).resolve()
    shutil.copytree(PACKAGE,root)
    # Runtime substitutes exist in tests only, visibly marked by the real UI.
    with host_runtime():
        hardware=si.IntegratedHardware(root)
        hardware.board=si.helpers(PACKAGE)
        hardware.base.prepare()
        hardware.environment=dict(evidence_kind='HOST_TEST_DOUBLE_NOT_BOARD',no_hardware=True)
        hardware.evidence_kind='HOST_TEST_DOUBLE_NOT_BOARD'
        manager=service.Manager(root,validate_package(root),hardware)
        await asyncio.get_running_loop().run_in_executor(manager.executor,hardware.open)
        sockets=tornado.netutil.bind_sockets(port,'127.0.0.1')
        server=tornado.httpserver.HTTPServer(service.application(manager));server.add_sockets(sockets)
        print(json.dumps(dict(url='http://127.0.0.1:'+str(port),scope='HOST_ONLY_REPLAY_TEST_DOUBLE',session=manager.session_id)),flush=True)
        try:await asyncio.Event().wait()
        finally:
            server.stop();await server.close_all_connections();manager.executor.shutdown(wait=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--port',type=int,default=18765)
    a=p.parse_args();asyncio.run(main(a.output,a.port))
