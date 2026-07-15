"""Keep automated tests physically separated from the local owner database."""

import os
from pathlib import Path


TEST_DB = Path(__file__).resolve().parents[3] / "data" / "xiaobai-test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["APP_ENV"] = "test"
