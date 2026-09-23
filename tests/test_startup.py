from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.utils.startup import configure_startup_logging


class StartupLogTests(unittest.TestCase):
    def test_startup_log_is_created_before_gui_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch("src.utils.startup.startup_data_directory", return_value=Path(temporary)):
                logger = configure_startup_logging("TestU8Assistant")
                for handler in list(logger.handlers):
                    handler.flush()
                    handler.close()
                    logger.removeHandler(handler)
            log_path = Path(temporary) / "startup.log"
            self.assertTrue(log_path.is_file())
            content = log_path.read_text(encoding="utf-8")
            self.assertIn("stage: process entry", content)
            self.assertIn("pointer_bits:", content)


if __name__ == "__main__":
    unittest.main()
