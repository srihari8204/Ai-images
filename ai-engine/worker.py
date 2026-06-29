"""Worker process launcher (design folder entrypoint).

Delegates to the importable package so the RQ task path
``ai_engine.worker.run_job`` and ``python worker.py`` both work.
"""

from ai_engine.worker import main, run_job  # noqa: F401

if __name__ == "__main__":
    main()
