# Scripts

Esta carpeta contiene entrypoints ejecutables para ingesta, ETL, entrenamiento y tareas operativas.

La lógica reutilizable debe permanecer dentro del paquete `alquileres_uy`.

## Ingesta MercadoLibre (Fase 1)

Antes de ejecutar cualquiera de estos scripts, instalar las dependencias de ingesta:

```bash
pip install -r requirements-ingest.txt
```

### `run_source_gate.py`

Valida si MercadoLibre es una fuente técnicamente viable. Ejecuta una búsqueda, un multiget de 20 ítems y consultas de descripción, y mide cobertura de campos esenciales.

```bash
python scripts/run_source_gate.py
```

Exit codes:

- `0` — APPROVED
- `1` — error inesperado
- `2` — REJECTED
- `3` — INCONCLUSIVE

El token, si existe, se toma únicamente de la variable de entorno `MELI_ACCESS_TOKEN` y nunca se registra ni imprime. Solo se reintenta con token si la búsqueda anónima devolvió `401` o `403`.

### `run_ingestion.py`

Corrida de ingesta completa. Solo debe ejecutarse si el source gate devolvió `0`.

```bash
python scripts/run_ingestion.py --max-items 100
python scripts/run_ingestion.py --max-items 5000
```

Flags:

- `--max-items` (default 5000)
- `--requests-per-second` (default 2)
- `--timeout` (default 20)
- `--max-attempts` (default 5)
- `--output-dir` (default `data/raw/mercadolibre`)
- `--database-path` (default `data/ingestion.sqlite`)
- `--dry-run` — valida configuración y muestra el plan de consultas sin llamadas de red ni escritura de datos.

En PowerShell funciona en una sola línea:

```powershell
python scripts/run_ingestion.py --max-items 5000 --requests-per-second 2 --timeout 20
```

La ingesta real se ejecuta **localmente**. GitHub Actions nunca llama a MercadoLibre.
