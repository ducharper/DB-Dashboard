"""Shared paths: application code moves independently of persistent user data."""
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = DASHBOARD_ROOT.parent
DATA_ROOT = PROJECT_ROOT / 'data'
FRONTEND_ROOT = DASHBOARD_ROOT / 'frontend'
