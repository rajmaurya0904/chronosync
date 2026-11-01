"""Allow ``python -m chronosync``."""

import sys

from .cli import main

sys.exit(main())
