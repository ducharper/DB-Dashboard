"""Compatibility entry point; the application launcher lives in dashboard."""
import sys
from dashboard import launcher

if __name__ == '__main__':
    launcher.main(launcher.parse_args().port)
else:
    # Preserve imports and patch targets used by existing launcher integrations.
    sys.modules[__name__] = launcher
