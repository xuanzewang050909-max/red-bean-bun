"""Run the preregistered 32-candidate r2; identical dataset and quality gates."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_q1_bilateral import main
from software.q1_soft_support import candidates, directional_evidence, softened_response

if __name__ == "__main__":
    main(protocol_name="docs/q1_soft_support_protocol_r2.json", candidate_factory=candidates,
         evidence_factory=directional_evidence, response_factory=softened_response,
         extra_source_names=("software/q1_soft_support.py", "scripts/evaluate_q1_soft_support.py",
                             "tests/test_q1_soft_support.py"))
