import io
import pyarrow as pa
import pyarrow.parquet as pq
from django.test import SimpleTestCase
from apps.pipeline.services.parquet_writer import ParquetWriter

class ParquetWriterTests(SimpleTestCase):
    def test_dictionaries_to_parquet_bytes_empty(self):
        """Test with an empty list."""
        result = ParquetWriter.dictionaries_to_parquet_bytes([])
        self.assertEqual(result, b"")

    def test_dictionaries_to_parquet_bytes_none(self):
        """Test with None as input."""
        result = ParquetWriter.dictionaries_to_parquet_bytes(None)
        self.assertEqual(result, b"")

    def test_dictionaries_to_parquet_bytes_valid_data(self):
        """Test with a simple list of valid dictionaries."""
        data = [{"id": 1, "name": "test1"}, {"id": 2, "name": "test2"}]
        result = ParquetWriter.dictionaries_to_parquet_bytes(data)
        
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)
        
        # Read back to verify
        buffer = io.BytesIO(result)
        table = pq.read_table(buffer)
        
        self.assertEqual(table.num_rows, 2)
        self.assertEqual(table.column_names, ["id", "name"])
        
        result_data = table.to_pylist()
        self.assertEqual(result_data, data)

    def test_dictionaries_to_parquet_bytes_with_schema(self):
        """Test with a valid pyarrow schema."""
        data = [{"id": 1, "name": "test1"}, {"id": 2, "name": "test2"}]
        schema = pa.schema([
            pa.field("id", pa.int64()),
            pa.field("name", pa.string())
        ])
        
        result = ParquetWriter.dictionaries_to_parquet_bytes(data, schema=schema)
        
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)
        
        buffer = io.BytesIO(result)
        table = pq.read_table(buffer)
        
        self.assertEqual(table.schema, schema)
        self.assertEqual(table.num_rows, 2)
        result_data = table.to_pylist()
        self.assertEqual(result_data, data)

    def test_dictionaries_to_parquet_bytes_missing_keys(self):
        """Test where some dictionaries have missing keys. PyArrow should inject None."""
        data = [{"id": 1, "name": "test1"}, {"id": 2}]
        result = ParquetWriter.dictionaries_to_parquet_bytes(data)
        
        buffer = io.BytesIO(result)
        table = pq.read_table(buffer)
        result_data = table.to_pylist()
        
        expected_data = [{"id": 1, "name": "test1"}, {"id": 2, "name": None}]
        self.assertEqual(result_data, expected_data)

    def test_dictionaries_to_parquet_bytes_complex_types(self):
        """Test with lists and nested dicts."""
        data = [
            {"id": 1, "tags": ["a", "b"], "metadata": {"key": "value"}},
            {"id": 2, "tags": ["c"], "metadata": {"key": "other"}}
        ]
        result = ParquetWriter.dictionaries_to_parquet_bytes(data)
        
        buffer = io.BytesIO(result)
        table = pq.read_table(buffer)
        result_data = table.to_pylist()
        
        # Depending on how pyarrow parses dicts, it might represent 'metadata' as struct
        # We can just verify it is identical when returned
        self.assertEqual(result_data, data)

    def test_dictionaries_to_parquet_bytes_schema_mismatch(self):
        """Test when data has a field not in the schema (pyarrow should drop or raise depending on version/config)."""
        data = [{"id": 1, "name": "test1", "extra": "drop_me"}]
        schema = pa.schema([
            pa.field("id", pa.int64()),
            pa.field("name", pa.string())
        ])
        
        # Pyarrow Table.from_pylist with schema will ignore the extra field or raise TypeError.
        # Normally it handles it by ignoring fields not in schema if schema is explicitly provided.
        # But wait, actually it might fail. Let's let it run and if it fails, we handle it.
        # For pyarrow, extra fields in dicts are ignored if schema is specified.
        result = ParquetWriter.dictionaries_to_parquet_bytes(data, schema=schema)
        buffer = io.BytesIO(result)
        table = pq.read_table(buffer)
        
        self.assertEqual(table.column_names, ["id", "name"])

    def test_dictionaries_to_parquet_bytes_wrong_type(self):
        """Test passing an invalid type, should raise an exception."""
        with self.assertRaises((TypeError, KeyError)):
            # Passing a single dict instead of a list of dicts
            ParquetWriter.dictionaries_to_parquet_bytes({"id": 1})
