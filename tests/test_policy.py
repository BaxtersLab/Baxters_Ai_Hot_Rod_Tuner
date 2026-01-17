import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hotrod_tuner import __version__


def test_version():
    assert __version__ == "0.0.1"
