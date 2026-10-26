import asyncio
import logging

from . import engine
from .contracts import RunConfig, RunError
from .recorder import RunRecord, RunStore
from .versions import ENGINE_VERSION, config_hash

logger = logging.getLogger(__name__)


class RunService:
    def __init__(self, store: RunStore) -> None:
        self.store = store

    def create(self, config: RunConfig) -> tuple[RunRecord, bool]:
        identity = config_hash(config)
        existing = self.store.get(identity)
        if existing is not None:
            return existing, True
        record = RunRecord(run_id=identity, config=config, config_hash=identity)
        self.store.records[identity] = record
        return record, False

    async def execute(self, record: RunRecord) -> None:
        # TODO(workers): replace the in-process scheduler with Modal later.
        if self.store.get(record.run_id) is not record:
            return
        record.status = "running"
        try:
            for snapshot in engine.simulate(record.config, record.run_id, ENGINE_VERSION):
                if self.store.get(record.run_id) is not record:
                    return
                await record.append(snapshot)
                await asyncio.sleep(0)
            if self.store.get(record.run_id) is record:
                await record.complete()
        except asyncio.CancelledError:
            await record.fail(RunError(code="interrupted", message="Run worker was interrupted"))
            raise
        except Exception as exc:
            logger.exception("Simulation failed: %s", record.run_id)
            await record.fail(
                RunError(code="engine_failure", message=str(exc) or type(exc).__name__)
            )

    async def delete(self, record: RunRecord) -> None:
        if record.status in ("queued", "running"):
            await record.fail(RunError(code="run_deleted", message="Run was deleted"))
        self.store.records.pop(record.run_id, None)
