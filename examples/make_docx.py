"""Regenerate examples/corpus/onboarding.docx (run from the repository root)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from builders import build_docx  # noqa: E402

build_docx(
    ROOT / "examples" / "corpus" / "onboarding.docx",
    [
        ("h1", "Technician onboarding"),
        ("p", "New technicians at the Larkspur depot shadow an experienced colleague for their first five shifts."),
        ("h2", "First week"),
        ("li", "Day 1: depot tour and safety briefing"),
        ("li", "Day 2: daily checks on a parked rover"),
        ("li", "Day 3 to 5: supervised runs on the flat route"),
        ("h2", "Sign-off"),
        ("p", "A shift lead signs off each skill once it has been shown twice without help."),
        ("table", [["Skill", "Signed off by"], ["Daily checks", "Shift lead"], ["Battery swap", "Shift lead"], ["Firmware update", "Depot manager"]]),
    ],
    title="Technician onboarding",
)
print("wrote examples/corpus/onboarding.docx")
