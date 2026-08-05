"""Guards for atomic publication of the ETL workdir."""

from __future__ import annotations

import pytest

from alquileres_uy.etl.config import EtlConfig
from alquileres_uy.etl.pipeline import EtlPipeline, _publish_workdir_atomically


def _config(tmp_path, etl_fixture_run, exchange_rate_path, aliases_path):
    return EtlConfig(
        input_run_dirs=(etl_fixture_run,),
        exchange_rate_path=exchange_rate_path,
        neighborhood_aliases_path=aliases_path,
        output_dir=tmp_path / "out",
        fixture_mode=True,
    )


def test_successful_run_leaves_only_the_final_dir(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    result = EtlPipeline(
        _config(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    ).run()
    assert result.workdir.exists()
    tmp_dirs = list(result.workdir.parent.glob("*.tmp"))
    assert tmp_dirs == []


def test_rename_failure_cleans_tmp(
    monkeypatch, tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    from alquileres_uy.etl import pipeline as pipeline_module

    def _boom(tmp, final):
        raise RuntimeError("rename boom")

    monkeypatch.setattr(pipeline_module, "_publish_workdir_atomically", _boom)
    with pytest.raises(RuntimeError, match="rename boom"):
        EtlPipeline(
            _config(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
        ).run()
    output_dir = tmp_path / "out"
    if output_dir.exists():
        tmp_leftovers = list(output_dir.glob("*.tmp"))
        assert tmp_leftovers == []


def test_publish_helper_refuses_overwriting_existing_final(tmp_path):
    src = tmp_path / "src.tmp"
    src.mkdir()
    (src / "a.txt").write_text("hello", encoding="utf-8")
    final = tmp_path / "final"
    final.mkdir()
    with pytest.raises(FileExistsError):
        _publish_workdir_atomically(src, final)


def test_publish_helper_moves_when_final_absent(tmp_path):
    src = tmp_path / "src.tmp"
    src.mkdir()
    (src / "a.txt").write_text("hi", encoding="utf-8")
    final = tmp_path / "final"
    _publish_workdir_atomically(src, final)
    assert not src.exists()
    assert (final / "a.txt").read_text(encoding="utf-8") == "hi"


def test_write_failure_leaves_no_output_dir(
    monkeypatch, tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    from alquileres_uy.etl import pipeline as pipeline_module

    original = pipeline_module.write_parquet
    call_counter = {"n": 0}

    def _fail_second(*args, **kwargs):
        call_counter["n"] += 1
        if call_counter["n"] == 2:
            raise RuntimeError("parquet boom")
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline_module, "write_parquet", _fail_second)
    with pytest.raises(RuntimeError, match="parquet boom"):
        EtlPipeline(
            _config(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
        ).run()
    output_dir = tmp_path / "out"
    if output_dir.exists():
        assert list(output_dir.iterdir()) == []


def test_second_run_uses_different_workdir(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    first = EtlPipeline(
        _config(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    ).run()
    second = EtlPipeline(
        _config(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    ).run()
    assert first.workdir != second.workdir


def test_no_stale_tmp_after_run(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    EtlPipeline(
        _config(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    ).run()
    assert list((tmp_path / "out").glob("*.tmp")) == []
