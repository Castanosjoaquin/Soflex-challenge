import asyncio
from pathlib import Path

from app.calls.action_log import ActionLog
from app.calls.service import CallService
from app.dispatch.store import DispatchStore
from app.engine.models import Line, Mode
from app.readers.rules.reader import RulesReader
from app.transcript.models import Speaker


def test_concurrent_turns_keep_relato_order(tmp_path: Path) -> None:
    db = tmp_path / "log.db"
    service = CallService(RulesReader(), ActionLog(db), DispatchStore(db), Mode.SIMULADO)
    call_id = service.open(Line.L911).call_id

    async def burst() -> None:
        await asyncio.gather(
            *(service.add_turn(call_id, Speaker.LLAMANTE, f"turno {i}") for i in range(20))
        )

    asyncio.run(burst())
    turns = service.get(call_id).turns
    assert [t.index for t in turns] == list(range(20))
    assert [t.text for t in turns] == [f"turno {i}" for i in range(20)]
