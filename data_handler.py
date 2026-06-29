import os
import csv
from datetime import datetime
import heapq
from typing import Dict, Iterator, Any
from events import MarketEvent

class DataHandler:
    """
    Streams historical data from CSV/Parquet files chronologically.
    Memory-efficient using generator-based merging.
    """
    def __init__(self, file_paths: Dict[str, str]):
        """
        file_paths: Dict mapping symbol names to their file paths.
        e.g., {'AAPL': 'data/AAPL.csv', 'MSFT': 'data/MSFT.csv'}
        """
        self.file_paths = file_paths

    def _csv_generator(self, symbol: str, file_path: str) -> Iterator[MarketEvent]:
        with open(file_path, 'r', newline='') as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
            except StopIteration:
                return

            # Find timestamp column index
            ts_idx = None
            for i, key in enumerate(headers):
                if key.lower() in ['timestamp', 'date', 'datetime', 'time']:
                    ts_idx = i
                    break
            if ts_idx is None:
                raise ValueError(f"No timestamp column found in {file_path}")

            # Identify numeric column indices and names to avoid dictionary creation inside loop
            col_mappings = []
            for i, col in enumerate(headers):
                if i == ts_idx:
                    continue
                col_mappings.append((i, col))

            for row in reader:
                if not row:
                    continue
                raw_ts = row[ts_idx]
                try:
                    dt = datetime.fromisoformat(raw_ts)
                except ValueError:
                    import pandas as pd
                    dt = pd.to_datetime(raw_ts).to_pydatetime()

                # Parse numeric fields directly
                data = {}
                for idx, col_name in col_mappings:
                    val = row[idx]
                    try:
                        data[col_name] = float(val)
                    except ValueError:
                        data[col_name] = val

                yield MarketEvent(timestamp=dt, symbol=symbol, data=data)

    def _parquet_generator(self, symbol: str, file_path: str) -> Iterator[MarketEvent]:
        try:
            import pyarrow.parquet as pq
            import pandas as pd
        except ImportError:
            raise ImportError("pyarrow and pandas are required to read Parquet files.")

        parquet_file = pq.ParquetFile(file_path)
        for batch in parquet_file.iter_batches(batch_size=10000):
            df = batch.to_pandas()
            ts_key = None
            for key in ['timestamp', 'Timestamp', 'date', 'Date', 'datetime', 'DateTime', 'time', 'Time']:
                if key in df.columns:
                    ts_key = key
                    break
            if not ts_key:
                raise ValueError(f"No timestamp column found in {file_path}")

            df[ts_key] = pd.to_datetime(df[ts_key])

            for _, row in df.iterrows():
                dt = row[ts_key].to_pydatetime()
                data = {}
                for col in df.columns:
                    if col == ts_key:
                        continue
                    val = row[col]
                    if hasattr(val, 'item'):
                        val = val.item()
                    data[col] = val

                yield MarketEvent(timestamp=dt, symbol=symbol, data=data)

    def stream_data(self) -> Iterator[MarketEvent]:
        """
        Creates generators for all files and merges them chronologically using heapq.merge.
        """
        generators = []
        for symbol, path in self.file_paths.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f"Data file not found for {symbol} at {path}")

            if path.endswith('.parquet') or path.endswith('.pq'):
                gen = self._parquet_generator(symbol, path)
            else:
                gen = self._csv_generator(symbol, path)
            generators.append(gen)

        # Merge generators sorted by event timestamp.
        # heapq.merge is lazy, keeping memory footprint minimal.
        for event in heapq.merge(*generators, key=lambda ev: ev.timestamp):
            yield event
