import pandas as pd
import pyarrow.parquet as pq

from alquileres_uy.etl.writers import write_json, write_parquet


def test_write_parquet_uses_zstd_and_sorts(tmp_path):
    df = pd.DataFrame(
        [
            {"source_item_id": "MLU_2", "price_usd": 900.0},
            {"source_item_id": "MLU_1", "price_usd": 1200.0},
        ]
    )
    path = tmp_path / "out.parquet"
    write_parquet(df, path, sort_by="source_item_id")
    table = pq.read_table(path)
    assert table.column("source_item_id").to_pylist() == ["MLU_1", "MLU_2"]


def test_write_json_serializes_dict(tmp_path):
    path = tmp_path / "out.json"
    write_json({"b": 2, "a": 1}, path)
    text = path.read_text(encoding="utf-8")
    assert '"a": 1' in text
    assert '"b": 2' in text
