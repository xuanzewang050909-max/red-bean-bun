"""Create an unexecuted board walkthrough from the reviewed Markdown source."""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = (ROOT / "docs/board_bringup_steps.md").read_text(encoding="utf-8")
    cells = []
    cursor = 0
    for match in re.finditer(r"^```python\n(.*?)^```", source, re.M | re.S):
        prose = source[cursor:match.start()].strip()
        if prose:
            # Repository-relative links are not available on the board.
            prose = re.sub(r"\[([^\]]+)\]\((?!https?://)([^)]+)\)", r"\1（项目文件：\2）", prose)
            cells.append({"cell_type": "markdown", "metadata": {}, "source": prose.splitlines(True)})
        code = match.group(1)
        parsed = "\n".join("# " + line if line.startswith("%") else line for line in code.splitlines())
        ast.parse(parsed, feature_version=(3, 6))
        cells.append({"cell_type": "code", "metadata": {}, "source": code.splitlines(True),
                      "execution_count": None, "outputs": []})
        cursor = match.end()
    prose = source[cursor:].strip()
    prose = re.sub(r"\[([^\]]+)\]\((?!https?://)([^)]+)\)", r"\1（项目文件：\2）", prose)
    cells.append({"cell_type": "markdown", "metadata": {}, "source": prose.splitlines(True)})
    notebook = {"nbformat": 4, "nbformat_minor": 4, "cells": cells,
                "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                             "language_info": {"name": "python"},
                             "retina_validation": {"status": "NOT_EXECUTED", "source": "docs/board_bringup_steps.md",
                                                   "requires_physical_board_observations": True}}}
    target = ROOT / "notebooks/board_validation.ipynb"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Created unexecuted notebook: {} ({} code cells)".format(target, sum(c["cell_type"] == "code" for c in cells)))


if __name__ == "__main__":
    main()
