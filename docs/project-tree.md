# Project tree

Snapshot del árbol del repositorio en `alquileres-uy/` — generado por
`scripts/generate_project_tree.py`.

El script excluye directorios de build, cache, virtualenv, datos crudos
y artefactos porque no forman parte del código versionado:

    .claude, .git, .idea, .mypy_cache, .pytest_cache, .ruff_cache, .venv, .vscode, __pycache__, artifacts, build, data, dist, htmlcov, node_modules, site

Para regenerarlo:

```bash
python scripts/generate_project_tree.py
```

Última actualización: `2026-08-08T18:40:48+00:00`.

```
alquileres-uy/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── release.yml
├── config/
│   ├── etl_production_approval.example.json
│   ├── etl_rules.json
│   ├── exchange_rate.example.json
│   └── neighborhood_aliases.json
├── docs/
│   ├── api.md
│   ├── architecture.md
│   ├── decisions.md
│   ├── demo.md
│   ├── deployment.md
│   ├── etl-data-contract.md
│   ├── etl-quality-rules.md
│   ├── mercadolibre-source-contract.md
│   ├── model-artifact-contract.md
│   ├── model-training-contract.md
│   ├── operations.md
│   ├── portfolio.md
│   ├── project-tree.md
│   └── upgrade.md
├── notebooks/
│   └── README.md
├── scripts/
│   ├── _generate_etl_fixtures.py
│   ├── _generate_model_fixture.py
│   ├── benchmark.py
│   ├── generate_build_info.py
│   ├── generate_project_tree.py
│   ├── README.md
│   ├── release.py
│   ├── run_api.py
│   ├── run_etl.py
│   ├── run_ingestion.py
│   ├── run_source_gate.py
│   ├── smoke_api.py
│   └── train_models.py
├── src/
│   └── alquileres_uy/
│       ├── api/
│       │   ├── routes/
│       │   │   ├── __init__.py
│       │   │   ├── build.py
│       │   │   ├── health.py
│       │   │   ├── model_info.py
│       │   │   ├── predict.py
│       │   │   ├── ready.py
│       │   │   ├── version.py
│       │   │   └── web.py
│       │   ├── schemas/
│       │   │   ├── __init__.py
│       │   │   └── predict.py
│       │   ├── services/
│       │   │   ├── __init__.py
│       │   │   ├── model_loader.py
│       │   │   └── predictor.py
│       │   ├── static/
│       │   │   ├── css/
│       │   │   │   └── styles.css
│       │   │   ├── js/
│       │   │   │   └── app.js
│       │   │   ├── .gitkeep
│       │   │   └── favicon.svg
│       │   ├── templates/
│       │   │   ├── .gitkeep
│       │   │   ├── base.html
│       │   │   └── index.html
│       │   ├── __init__.py
│       │   ├── app.py
│       │   ├── build_info.py
│       │   ├── compatibility.py
│       │   ├── config.py
│       │   ├── dependencies.py
│       │   ├── errors.py
│       │   ├── lifespan.py
│       │   ├── logging_config.py
│       │   ├── metrics.py
│       │   ├── middleware.py
│       │   ├── prediction_service.py
│       │   └── warmup.py
│       ├── etl/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── contracts.py
│       │   ├── currency.py
│       │   ├── deduplication.py
│       │   ├── extractors.py
│       │   ├── lineage.py
│       │   ├── loaders.py
│       │   ├── models.py
│       │   ├── neighborhoods.py
│       │   ├── normalization.py
│       │   ├── pipeline.py
│       │   ├── quality.py
│       │   ├── schemas.py
│       │   ├── source_scope.py
│       │   └── writers.py
│       ├── features/
│       │   └── __init__.py
│       ├── ingest/
│       │   ├── __init__.py
│       │   ├── approval.py
│       │   ├── auth.py
│       │   ├── category_tree.py
│       │   ├── client.py
│       │   ├── config.py
│       │   ├── errors.py
│       │   ├── filesystem.py
│       │   ├── models.py
│       │   ├── query_plan.py
│       │   ├── reporting.py
│       │   ├── repository.py
│       │   ├── service.py
│       │   └── source_gate.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── artifacts.py
│       │   ├── baseline.py
│       │   ├── config.py
│       │   ├── contracts.py
│       │   ├── features.py
│       │   ├── imputation.py
│       │   ├── lightgbm_model.py
│       │   ├── linear.py
│       │   ├── metrics.py
│       │   ├── pipeline.py
│       │   ├── selection.py
│       │   ├── serving.py
│       │   ├── split.py
│       │   └── torch_model.py
│       ├── __init__.py
│       ├── _version.py
│       └── build_info.json
├── tests/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_bootstrap.py
│   │   ├── test_metrics.py
│   │   ├── test_prediction.py
│   │   ├── test_production.py
│   │   ├── test_release_engineering.py
│   │   ├── test_reliability.py
│   │   ├── test_web_ui.py
│   │   ├── test_web_ui_enhancements.py
│   │   └── test_web_ui_polish.py
│   ├── etl/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_aggregation.py
│   │   ├── test_atomic_publication.py
│   │   ├── test_contracts.py
│   │   ├── test_currency.py
│   │   ├── test_data_mode_consistency.py
│   │   ├── test_deduplication.py
│   │   ├── test_dry_run_exit_codes.py
│   │   ├── test_extractors.py
│   │   ├── test_ingest_to_etl_integration.py
│   │   ├── test_lineage.py
│   │   ├── test_lineage_completeness.py
│   │   ├── test_loaders.py
│   │   ├── test_manifest_authority.py
│   │   ├── test_manifest_hash_all_kinds.py
│   │   ├── test_neighborhoods.py
│   │   ├── test_normalization.py
│   │   ├── test_parse_area.py
│   │   ├── test_parse_count.py
│   │   ├── test_pipeline.py
│   │   ├── test_quality.py
│   │   ├── test_schemas.py
│   │   ├── test_strict_mode.py
│   │   ├── test_summary_path_and_timestamps.py
│   │   ├── test_summary_semantic.py
│   │   ├── test_timestamps.py
│   │   └── test_writers.py
│   ├── fixtures/
│   │   ├── etl/
│   │   │   └── raw_run/
│   │   │       ├── descriptions/
│   │   │       │   ├── MLU_TEST_001.json
│   │   │       │   ├── MLU_TEST_002.json
│   │   │       │   └── MLU_TEST_003.json
│   │   │       ├── items/
│   │   │       │   ├── batch_0001.json
│   │   │       │   └── batch_0002.json
│   │   │       ├── ingestion_summary.json
│   │   │       └── manifest.json
│   │   ├── etl_agg_tmp/
│   │   │   ├── agg_a_test_two_observations_preserve0/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── agg_b_test_two_observations_preserve0/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── agg_nw_test_older_observation_does_no0/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── agg_ol_test_older_observation_does_no0/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── agg_x_test_three_observations_aggreg0/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── agg_y_test_three_observations_aggreg0/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   └── agg_z_test_three_observations_aggreg0/
│   │   │       ├── items/
│   │   │       │   └── batch_0001.json
│   │   │       ├── ingestion_summary.json
│   │   │       └── manifest.json
│   │   ├── etl_bad_unit_test_pipeline_unsupported_coun0/
│   │   │   ├── items/
│   │   │   │   └── batch_0001.json
│   │   │   ├── ingestion_summary.json
│   │   │   └── manifest.json
│   │   ├── etl_bad_unit_test_strict_flags_unsupported_0/
│   │   │   ├── items/
│   │   │   │   └── batch_0001.json
│   │   │   ├── ingestion_summary.json
│   │   │   └── manifest.json
│   │   ├── etl_broken_test_dry_run_exit_2_on_manifes0/
│   │   │   ├── items/
│   │   │   │   └── batch_0001.json
│   │   │   ├── ingestion_summary.json
│   │   │   └── manifest.json
│   │   ├── etl_wrong_hash_test_dry_run_exit_2_on_wrong_h0/
│   │   │   ├── items/
│   │   │   │   └── batch_0001.json
│   │   │   ├── ingestion_summary.json
│   │   │   └── manifest.json
│   │   ├── ingest_integration_test_modifying_a_batch_after_t0/
│   │   │   ├── 2026-08-04T220001Z_091d285f/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_1b9343d9/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_1e683833/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_241a4053/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_2f6c44ef/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_3671396b/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_42f877da/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_447a6288/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_47c30690/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_4acc3bc6/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_567e36eb/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_5feb3bb3/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_60834109/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_64806eff/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_6f571c49/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_71b29b0f/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_787d18e9/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_879061ce/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_973422b1/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_984f7fb7/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_9853b2cf/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_98d75ee1/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_a34bfc47/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_c652cb7d/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_c65ba81b/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_c7e0b49f/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_dbc2f5cf/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_dc53dd4a/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_e1d0698c/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_e2719c35/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_eddbe17c/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   └── 2026-08-04T220001Z_f786dc9b/
│   │   │       ├── descriptions/
│   │   │       │   ├── MLU_TEST_001.json
│   │   │       │   ├── MLU_TEST_002.json
│   │   │       │   ├── MLU_TEST_003.json
│   │   │       │   ├── MLU_TEST_004.json
│   │   │       │   └── MLU_TEST_005.json
│   │   │       ├── errors/
│   │   │       ├── items/
│   │   │       │   └── batch_0001.json
│   │   │       ├── searches/
│   │   │       │   ├── query_0001/
│   │   │       │   │   └── page_0001.json
│   │   │       │   └── query_0002/
│   │   │       │       └── page_0001.json
│   │   │       ├── ingestion_summary.json
│   │   │       └── manifest.json
│   │   ├── ingest_integration_test_phase1_manifest_hashes_ma0/
│   │   │   ├── 2026-08-04T220001Z_063dfb8b/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_12a0846c/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_1516412a/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_1e823847/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_2c9ea088/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_3334eb76/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_3b66ae83/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_5da297da/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_622fb39d/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_66108b1a/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_6cda9e8b/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_70494e2f/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_70e2729d/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_78afdf59/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_7bb9b338/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_821b03c1/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_84c2e9d5/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_8bc09980/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_9c01924c/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_a149b580/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_bc01f129/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_bf18f903/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_c29a9524/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_caad5835/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_cd787106/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_d13500e3/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_dcaeac8b/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_e4b7a807/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_ecf6c039/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_f1576e38/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_f36ad9dc/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   └── 2026-08-04T220001Z_f4c663f0/
│   │   │       ├── descriptions/
│   │   │       │   ├── MLU_TEST_001.json
│   │   │       │   ├── MLU_TEST_002.json
│   │   │       │   ├── MLU_TEST_003.json
│   │   │       │   ├── MLU_TEST_004.json
│   │   │       │   └── MLU_TEST_005.json
│   │   │       ├── errors/
│   │   │       ├── items/
│   │   │       │   └── batch_0001.json
│   │   │       ├── searches/
│   │   │       │   ├── query_0001/
│   │   │       │   │   └── page_0001.json
│   │   │       │   └── query_0002/
│   │   │       │       └── page_0001.json
│   │   │       ├── ingestion_summary.json
│   │   │       └── manifest.json
│   │   ├── ingest_integration_test_phase1_manifest_is_readab0/
│   │   │   ├── 2026-08-04T220001Z_04ce17bb/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_1057fc0b/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_16785b39/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_20f97e9c/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_220da631/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_31307aa1/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_3ace9d06/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_40770c7d/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_45ebe11b/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_4c567798/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_5f471385/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_5f6f1528/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_62376299/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_647cc69e/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_717d4cf9/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_763a073d/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_8084153b/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_82c58a42/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_8d486cb5/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_936566a6/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_9c7756be/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_9cef3320/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_a969cd04/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_aceaf0c5/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_baa29f35/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_c40681b4/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_d4b289c2/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_dbde101b/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_df436cbe/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_e3393b3f/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_f24c2c9d/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   └── 2026-08-04T220001Z_fbd30388/
│   │   │       ├── descriptions/
│   │   │       │   ├── MLU_TEST_001.json
│   │   │       │   ├── MLU_TEST_002.json
│   │   │       │   ├── MLU_TEST_003.json
│   │   │       │   ├── MLU_TEST_004.json
│   │   │       │   └── MLU_TEST_005.json
│   │   │       ├── errors/
│   │   │       ├── items/
│   │   │       │   └── batch_0001.json
│   │   │       ├── searches/
│   │   │       │   ├── query_0001/
│   │   │       │   │   └── page_0001.json
│   │   │       │   └── query_0002/
│   │   │       │       └── page_0001.json
│   │   │       ├── ingestion_summary.json
│   │   │       └── manifest.json
│   │   ├── ingest_integration_test_phase1_summary_counts_mat0/
│   │   │   ├── 2026-08-04T220001Z_0479cf9b/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_0e80afd1/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_144b301b/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_194d5e4f/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_2ca5e785/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_3ca518cb/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_46885107/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_49c80c5b/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_508d0764/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_5abd5afd/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_6d0e79de/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_6d2fe1db/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_6e2218e3/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_7c5d708c/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_7fd2af99/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_875b6d62/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_89003f10/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_8d0e9392/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_8fb2081a/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_910eca64/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_9473e0dc/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_99f1768e/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_aefb2646/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_bce6625f/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_c45484f7/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_cad7033c/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_de531926/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_e31b5525/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_e69e8c0a/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_eb24694a/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_f672bdbb/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   └── 2026-08-04T220001Z_fc14a377/
│   │   │       ├── descriptions/
│   │   │       │   ├── MLU_TEST_001.json
│   │   │       │   ├── MLU_TEST_002.json
│   │   │       │   ├── MLU_TEST_003.json
│   │   │       │   ├── MLU_TEST_004.json
│   │   │       │   └── MLU_TEST_005.json
│   │   │       ├── errors/
│   │   │       ├── items/
│   │   │       │   └── batch_0001.json
│   │   │       ├── searches/
│   │   │       │   ├── query_0001/
│   │   │       │   │   └── page_0001.json
│   │   │       │   └── query_0002/
│   │   │       │       └── page_0001.json
│   │   │       ├── ingestion_summary.json
│   │   │       └── manifest.json
│   │   ├── ingest_integration_test_phase1_summary_path_and_t0/
│   │   │   ├── 2026-08-04T220001Z_0bc192b0/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_0d5a7d61/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_0d855f5d/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_1116601d/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_161812ed/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_19ebe081/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_1d897ded/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_1e73db69/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_1f467a7d/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_202297b5/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_28299ee8/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_39147a92/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_42a9a7b8/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_4d55906a/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_5e6313f4/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_6716ba60/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_6bf8c1ca/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_6f563ae4/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_89df3808/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_8b8590f7/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_9bafc5c7/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_a1804b68/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_a4fcb43a/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_b49c68da/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_d5238891/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_d56eaaac/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_d5e669df/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_dd217048/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_dd6777a7/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_ec6454fb/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   ├── 2026-08-04T220001Z_f97769b4/
│   │   │   │   ├── descriptions/
│   │   │   │   │   ├── MLU_TEST_001.json
│   │   │   │   │   ├── MLU_TEST_002.json
│   │   │   │   │   ├── MLU_TEST_003.json
│   │   │   │   │   ├── MLU_TEST_004.json
│   │   │   │   │   └── MLU_TEST_005.json
│   │   │   │   ├── errors/
│   │   │   │   ├── items/
│   │   │   │   │   └── batch_0001.json
│   │   │   │   ├── searches/
│   │   │   │   │   ├── query_0001/
│   │   │   │   │   │   └── page_0001.json
│   │   │   │   │   └── query_0002/
│   │   │   │   │       └── page_0001.json
│   │   │   │   ├── ingestion_summary.json
│   │   │   │   └── manifest.json
│   │   │   └── 2026-08-04T220001Z_f998b40a/
│   │   │       ├── descriptions/
│   │   │       │   ├── MLU_TEST_001.json
│   │   │       │   ├── MLU_TEST_002.json
│   │   │       │   ├── MLU_TEST_003.json
│   │   │       │   ├── MLU_TEST_004.json
│   │   │       │   └── MLU_TEST_005.json
│   │   │       ├── errors/
│   │   │       ├── items/
│   │   │       │   └── batch_0001.json
│   │   │       ├── searches/
│   │   │       │   ├── query_0001/
│   │   │       │   │   └── page_0001.json
│   │   │       │   └── query_0002/
│   │   │       │       └── page_0001.json
│   │   │       ├── ingestion_summary.json
│   │   │       └── manifest.json
│   │   ├── mercadolibre/
│   │   │   ├── category_root_inmuebles.json
│   │   │   ├── description_success.json
│   │   │   ├── item_multiget_partial_failure.json
│   │   │   ├── item_multiget_success.json
│   │   │   ├── rate_limited.json
│   │   │   ├── search_success.json
│   │   │   ├── site_categories_root.json
│   │   │   └── unauthorized.json
│   │   ├── models/
│   │   │   └── etl_run/
│   │   │       ├── etl_summary.json
│   │   │       ├── lineage.json
│   │   │       ├── model_ready.parquet
│   │   │       └── schema.json
│   │   └── __init__.py
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_approval.py
│   │   ├── test_auth.py
│   │   ├── test_category_tree.py
│   │   ├── test_classify_sample_item.py
│   │   ├── test_cli_run_ingestion.py
│   │   ├── test_client.py
│   │   ├── test_filesystem.py
│   │   ├── test_query_plan.py
│   │   ├── test_repository.py
│   │   ├── test_service.py
│   │   └── test_source_gate.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_approval.py
│   │   ├── test_artifacts_and_serving.py
│   │   ├── test_baseline.py
│   │   ├── test_contracts.py
│   │   ├── test_features.py
│   │   ├── test_final_review.py
│   │   ├── test_lightgbm.py
│   │   ├── test_linear.py
│   │   ├── test_metrics_and_selection.py
│   │   ├── test_pipeline_and_cli.py
│   │   ├── test_review_blockers.py
│   │   ├── test_split.py
│   │   └── test_torch.py
│   ├── __init__.py
│   └── test_package.py
├── .dockerignore
├── .editorconfig
├── .gitattributes
├── .gitignore
├── .pre-commit-config.yaml
├── .python-version
├── CHANGELOG.md
├── CONTRIBUTING.md
├── Dockerfile
├── experiments.md
├── LICENSE
├── pyproject.toml
├── README.md
├── requirements-api.txt
├── requirements-dev.txt
├── requirements-etl.txt
├── requirements-ingest.txt
├── requirements-torch-cpu.txt
└── requirements-train.txt
```
