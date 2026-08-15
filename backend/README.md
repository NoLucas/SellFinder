# SellFinder Backend

FastAPI service for the application platform (agent C) — implements the
contract in `/shared/contracts/04_api_contract.yaml`.

Old item-level prediction endpoints (`prediction_api.json` era) were removed
per `RECONCILIATION.md` — see that file for what was kept, discarded, and
what's still open. Only a minimal skeleton (`/api/v1/health`, error envelope,
settings) remains while the new contract's endpoints are built out.

## Endpoints

- `GET /api/v1/health` — service status

## Run locally

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Test

```bash
cd backend
pytest
```
