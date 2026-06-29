"""Backend entrypoint.

Kept for backwards compatibility (``uvicorn main:app``). The application is
defined in :mod:`app.main`; run the production server with::

    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from app.main import app  # noqa: F401
