import io
from typing import List, Dict, Any
import pyarrow as pa
import pyarrow.parquet as pq

class ParquetWriter:
    """
    Utility to serialize Python dictionaries into Parquet format
    so they can be written to MinIO by the pipeline.
    """

    @staticmethod
    def dictionaries_to_parquet_bytes(data: List[Dict[str, Any]], schema: pa.Schema = None) -> bytes:
        """
        Converts a list of dicts to a Parquet file in memory and returns the bytes.
        """
        if not data:
            return b""
        
        # Convert dicts to pyarrow Table
        # In production this should handle chunking for large datasets
        table = pa.Table.from_pylist(data, schema=schema)
        
        # Write to in-memory buffer
        buffer = io.BytesIO()
        pq.write_table(table, buffer)
        
        return buffer.getvalue()
