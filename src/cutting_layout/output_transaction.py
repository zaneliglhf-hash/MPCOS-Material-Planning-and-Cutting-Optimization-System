import os
from pathlib import Path
import shutil
import tempfile
from types import TracebackType
from uuid import uuid4


class OutputTransaction:
    """Stage a complete output directory and publish it with one swap."""

    def __init__(self, target: Path):
        self.target = Path(target)
        self.target.parent.mkdir(parents=True, exist_ok=True)
        if self.target.exists() and not self.target.is_dir():
            raise ValueError(f"output target is not a directory: {self.target}")
        self.staging_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{self.target.name}-staging-",
                dir=self.target.parent,
            )
        )
        self._committed = False

    def __enter__(self) -> "OutputTransaction":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.staging_dir.exists():
            shutil.rmtree(self.staging_dir, ignore_errors=True)

    def commit(self) -> None:
        if self._committed:
            raise RuntimeError("output transaction is already committed")
        if not self.staging_dir.is_dir():
            raise RuntimeError("output staging directory is missing")

        backup = self.target.parent / f".{self.target.name}-backup-{uuid4().hex}"
        had_target = self.target.exists()
        if had_target:
            os.replace(self.target, backup)

        try:
            os.replace(self.staging_dir, self.target)
        except Exception:
            if had_target and backup.exists() and not self.target.exists():
                os.replace(backup, self.target)
            raise

        self._committed = True
        if backup.exists():
            shutil.rmtree(backup)

