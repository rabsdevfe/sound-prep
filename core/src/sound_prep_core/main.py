"""Sidecar entrypoint: ``python -m sound_prep_core``.

The core takes all its input from stdin (see ADR 0001), so any command-line argument is refused
before anything else happens. Protocol output goes to a private copy of the original stdout; fd 1
and ``sys.stdout`` are pointed at stderr so nothing a dependency prints can corrupt the stream.
"""

import logging
import os
import sys

from sound_prep_core.adapters.ipc.server import serve
from sound_prep_core.composition import build_handler_factory


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        print("sound-prep core takes no arguments; send requests on stdin", file=sys.stderr)
        return 2
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")
    protocol_out = os.fdopen(os.dup(1), "wb", buffering=0)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    try:
        return serve(sys.stdin.buffer, protocol_out, build_handler_factory(os.environ))
    finally:
        protocol_out.close()
