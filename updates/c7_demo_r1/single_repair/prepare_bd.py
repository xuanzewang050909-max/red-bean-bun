from software import *
import re
src=Path('D:/PLD/retina_c7_isolated_recovery/hardware/atomic_bridge_guard50_r1/integration/reconstructed_bd_50mhz.tcl')
s=src.read_text();a=s.index('  set ps7_0 [ create_bd_cell');b=s.index(' ] $ps7_0',a)+len(' ] $ps7_0')
ps=s[a:b]
dest=Path(__file__).parent/'hardware'
(dest/'ps7_verified_50m.tcl').write_text('# Verbatim PS7 configuration from verified Guard50 design.\n'+ps+'\n')
(OUT/'integration_sources.json').write_text(json.dumps(dict(parent=str(src),sha256=hashlib.sha256(src.read_bytes()).hexdigest(),ps7_copy_sha256=hashlib.sha256((dest/'ps7_verified_50m.tcl').read_bytes()).hexdigest(),new_design='Independent PS7 GP0 control + shared master DDR HP0; no CNN or AtomicBridge; no observer; direct m_axi DDR (stream DMA not needed)',clock_mhz=50,board_accesses=0),indent=2))
print('PS7_SOURCE_BOUND')
