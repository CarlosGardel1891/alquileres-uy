# Scripts

Esta carpeta contiene entrypoints ejecutables para ingesta, ETL, entrenamiento y tareas operativas.

La lógica reutilizable debe permanecer dentro del paquete `alquileres_uy`.

## Ingesta MercadoLibre (Fase 1)

Antes de ejecutar cualquiera de estos scripts, instalar las dependencias de ingesta:

```bash
pip install -r requirements-ingest.txt
```

### `run_source_gate.py`

Valida si MercadoLibre es una fuente técnicamente viable. Construye internamente **dos** `MercadoLibreClient` distintos: uno anónimo (siempre usado primero) y uno autenticado que sólo se instancia si `MELI_ACCESS_TOKEN` está seteado. La sesión HTTP anónima nunca se reutiliza para llamadas con token.

```bash
python scripts/run_source_gate.py
```

Exit codes:

- `0` — APPROVED (y emite `source_gate_approval.json` junto al `coverage.json`).
- `1` — error inesperado.
- `2` — REJECTED.
- `3` — INCONCLUSIVE.

El token, si existe, se toma únicamente de `MELI_ACCESS_TOKEN` y nunca se registra, imprime ni guarda en artefactos. Sólo se reintenta con token si la búsqueda anónima devolvió `401` o `403`.

### `run_ingestion.py`

Corrida de ingesta completa. **Sólo puede ejecutarse con** un `source_gate_approval.json` producido por un source gate `APPROVED`.

```bash
# Placeholder — reemplazar PATH por el approval real de tu corrida APPROVED
python scripts/run_ingestion.py --gate-approval PATH --dry-run
python scripts/run_ingestion.py --gate-approval PATH --max-items 100
python scripts/run_ingestion.py --gate-approval PATH --max-items 5000
```

Flags:

- `--gate-approval` **(obligatorio)** — ruta al `source_gate_approval.json`.
- `--max-items` (default 5000)
- `--requests-per-second` (default 2)
- `--timeout` (default 20)
- `--max-attempts` (default 5)
- `--output-dir` (default `data/raw/mercadolibre`)
- `--database-path` (default `data/ingestion.sqlite`)
- `--dry-run` — valida configuración y muestra el plan de consultas sin llamadas de red ni escritura de datos. También requiere `--gate-approval` para generar un plan basado en categorías verificadas.

Sin `--gate-approval` (o con un approval corrupto/tampered) el comando termina en exit code `2`, sin llamadas de red, sin SQLite y sin carpeta de corrida.

En PowerShell funciona en una sola línea:

```powershell
python scripts/run_ingestion.py --gate-approval PATH --max-items 5000 --requests-per-second 2 --timeout 20
```

La ingesta real se ejecuta **localmente**. GitHub Actions nunca llama a MercadoLibre.
