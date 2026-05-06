from __future__ import annotations

import sys
from pathlib import Path

# Garante que a raiz do projeto esteja no sys.path durante a coleta do pytest.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)
