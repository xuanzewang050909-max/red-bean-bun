"""Preregistered Q4-r2; shares the training-only screen and identical gates."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_q4_refinement import main
from software.q4_ridge import candidates,ridge_mask

if __name__=='__main__':
    main('docs/q4_ridge_protocol_r2.json',candidates,ridge_mask)
