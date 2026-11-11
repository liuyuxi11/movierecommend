# Movie Recommend Frontend

This directory contains the static Vue-free frontend for the movie recommendation demo. It uses browser JavaScript and can run without a build step.

## Run

From the repository root:

```powershell
python -m http.server 8001 --directory frontend
```

Open `http://127.0.0.1:8001`. Set `API_BASE_URL` and `DATA_MODE` in `js/config.js` to use the FastAPI backend. `auto` probes the backend and falls back to the bundled mock service; `real` requires the backend; `mock` always uses local demo data.

## Recommendation Display

The recommendation page displays up to 20 results, ordered by `position`. Each result includes its movie details, source (`als_rerank`, `popular_fallback`, or `legacy`) and, for current batches, a 0-1 list ranking score. The score is not a movie rating, probability, or cross-list quality measure.

The backend trains ALS offline and publishes candidate JSONL. Celery reads those candidates to refresh a user's result after rating submission, combines their offline order with current rating genre preferences and a popularity list, and writes the result to MySQL and Redis. This refresh does not train ALS in the request path. See [recommendation-worker.md](../docs/recommendation-worker.md) and [api_contract.md](../backend/app/api/api_contract.md) for the current contracts.

## Verification

Run the frontend mock smoke test from the repository root:

```powershell
node frontend/tests/smoke_test.js
```

The smoke test covers mock authentication, ratings, favorites, recommendation result count and shape, and movie APIs. It does not connect to MySQL, Redis, Celery, or Spark.
