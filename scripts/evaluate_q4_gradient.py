"""Run preregistered Q4-r4 on original training AH only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_q4_refinement import main
from software.q4_gradient import candidates, gradient_mask

if __name__ == '__main__':
    main('docs/q4_gradient_protocol_r4.json', candidates, gradient_mask)
