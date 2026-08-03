"""Back-compat shim. Prefer ``app.db`` for new code."""

from app.db import *  # noqa: F403
from app.db import __all__  # noqa: F401
