"""The server's progress reporter: ``percent`` is emitted only when given."""

import json

from sound_prep_core.adapters.ipc.messages import IpcMessage, to_line
from sound_prep_core.adapters.ipc.server import _Reporter
from sound_prep_core.domain.ports import ProgressStage


def test_percent_is_emitted_only_when_given() -> None:
    sent: list[IpcMessage] = []
    reporter = _Reporter("p1", sent.append)
    reporter.report(ProgressStage.SEPARATING, 42)
    reporter.report(ProgressStage.DOWNLOADING)
    first, second = (json.loads(to_line(m)) for m in sent)
    assert first == {"v": 1, "id": "p1", "type": "progress", "stage": "separating", "percent": 42}
    assert "percent" not in second
