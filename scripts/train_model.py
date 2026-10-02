"""Train + validate the retention-risk model. Writes models/retention_model.pkl and
models/validation.json (served at GET /api/validation).

    python scripts/train_model.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.model.train import main  # noqa: E402

if __name__ == "__main__":
    main()
