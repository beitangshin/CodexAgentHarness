"""Frozen Master entry point also runs managed Codex terminal subprocesses."""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        from codex_agent_harness.managed import main as managed_main

        managed_main()
    else:
        from codex_agent_harness.master import main as master_main

        master_main()


if __name__ == "__main__":
    main()
