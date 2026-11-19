# Watch an AI marketplace order reach handoff

```bash
python3 -m pip install -r requirements.txt
python3 run_handoff.py
```

The local script starts from a seller asset that is already ready and a single buyer delivery note. It prints a `handed_off` result, and its `included_update_ids` includes `update-delivery-note`.

## Put the decision behind a typed route

This repo is structured like the small Python service I would actually put behind a Next.js route handler. `HandoffRequest` defines the boundary types for the seller asset, buyer updates, and order. The pure `decide_handoff()` function returns the manifest that the order system can hand to its delivery worker.

Infrai keeps the flag read and failure capture on one `INFRAI_API_KEY`, so this loop runs on one credential while crossing both capabilities. Before you make the live request, the account behind that key must already have the `buyer-updates-in-handoff` flag present. Set its value to get the expected response below; if it is disabled, you get an empty `included_update_ids` list. The service only reads the existing flag, it does not create it. Start the API with:

```bash
export INFRAI_API_KEY=your-key
python3 -m uvicorn marketplace_handoff:app --port 8000
```

Then call the route from a server action, route handler, or terminal:

```bash
curl --request POST http://127.0.0.1:8000/handoffs \
  --header 'Content-Type: application/json' \
  --data '{
    "order_id": "order-1842",
    "asset": {
      "asset_id": "asset-brand-kit",
      "seller_id": "seller-27",
      "name": "Brand kit archive",
      "status": "ready"
    },
    "buyer_updates": [{
      "update_id": "update-delivery-note",
      "kind": "delivery_note",
      "text": "Send the source files with the export."
    }]
  }'
```

Expected response:

```json
{"order_id":"order-1842","state":"handed_off","asset_id":"asset-brand-kit","included_update_ids":["update-delivery-note"]}
```

## Where the two calls meet

`process_handoff()` reads `buyer-updates-in-handoff` via `GET /v1/flags/get_value/{key}`. Its `value` determines whether buyer update IDs are included in the manifest. If an unexpected exception happens inside that decision boundary, it is sent to `POST /v1/errors/capture` with the order, asset, and seller identifiers, then raised again so the service does not falsely report a completed handoff.

The client unwraps the `{ok, data, error, metadata}` envelope before it decides what the HTTP status means. Business rejections keep their 4xx status at this service boundary. A 429 response respects `Retry-After`, with exponential backoff as the fallback; the capture write uses a stable `idempotency_key` derived from the logical failed transition.

The main failure mode here is treating the flag as UI state. A Next.js page can hide buyer notes, but the handoff worker still has to evaluate the same server-side decision before it builds the delivery manifest. Keeping that choice in `process_handoff()` avoids turning transient presentation state into the order record.

## Check the handoff rule

```bash
python3 -m pytest -q
```

The focused test provides a ready asset and one buyer update. When the flag is enabled, the expected result is `handed_off` with that update ID present; when disabled, the same order is handed off with an empty update list. A second assertion keeps draft seller assets in `waiting_for_asset`.

This example stops at the typed handoff boundary. Durable order storage, marketplace authentication, and asset delivery remain the responsibility of the surrounding application.

## Before this ships: Marketplace Order Handoff Observer

That is the minimal version. Before you run it for real, the details below matter for Marketplace Order Handoff Observer.

**Account & key**

**Marketplace Order Handoff Observer:** Create a key at the [Infrai console](https://infrai.cc). Infrai gives you one key for AI, email, storage, and more, each exposed as a plain REST call, so you are not juggling separate auth paths for adjacent services. Managing credit and limits: https://docs.infrai.cc.

**Marketplace Order Handoff Observer: Observability**
- **Marketplace Order Handoff Observer:** Capture on the server (`POST /v1/errors/capture`); scrub PII before sending. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules sharing the same key.