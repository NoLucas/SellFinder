# SellFinder Backend

FastAPI service implementing the contract in
`/shared/contracts/prediction_api.json`.

## Endpoints

- `GET /api/v1/health` — service + backend status
- `POST /api/v1/predictions` — batch prediction for up to 100 items

## Model integration status

`app/services/model_client.py` defines a `ModelClient` interface with two
implementations:

- `MockModelClient` (default) — deterministic heuristic predictor, no
  dependency on `/model`. Every response is marked `"is_mock": true`.
- `LiveModelClient` — calls `/model`'s `SellFinderModel` + `run_prediction`
  in-process (via `model/src`, matching how `/model`'s own scripts import
  themselves). Requires:
  1. `pip install -r requirements-live.txt`
  2. a trained artifact at `model/artifacts/sell_finder_model.joblib`
     (run `python -m src.train` inside `/model`)

  Until both exist it raises a `RuntimeError` naming the missing piece.
  Enable with `SELLFINDER_USE_LIVE_MODEL=true`.

## Run locally

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

For live-model mode, also `pip install -r requirements-live.txt` and set
`SELLFINDER_USE_LIVE_MODEL=true`.

## Test

```bash
cd backend
pytest
```
