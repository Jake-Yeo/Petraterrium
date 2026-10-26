from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


class RowWriter:
    def __init__(self, path: Path, schema: pa.Schema, batch_size: int = 100_000):
        self.path = path
        self.schema = schema
        self.batch_size = batch_size
        self.rows = []
        self.writer = pq.ParquetWriter(path, schema, compression="zstd")
        self.count = 0

    def add(self, row: dict) -> None:
        self.rows.append(row)
        if len(self.rows) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self.rows:
            return
        table = pa.Table.from_pylist(self.rows, schema=self.schema)
        self.writer.write_table(table)
        self.count += len(self.rows)
        self.rows = []

    def close(self) -> int:
        self.flush()
        self.writer.close()
        return self.count

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.close()


def write_rows(path: Path, rows: list[dict], schema: pa.Schema | None = None) -> int:
    if schema is None:
        table = pa.Table.from_pylist(rows)
    else:
        table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path, compression="zstd")
    return table.num_rows
