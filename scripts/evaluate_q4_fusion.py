"""Execute the frozen Q4-r3 multiscale/C2 fusion training screen."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_q4_refinement import main
from software.q4_fusion import candidates, fusion_mask

if __name__ == '__main__':
    main('docs/q4_fusion_protocol_r3.json', candidates, fusion_mask)
