import sys
from pathlib import Path

__project_root: Path = Path(__file__).parent.parent.parent
if str(__project_root) not in sys.path:
    sys.path.insert(0, str(__project_root))