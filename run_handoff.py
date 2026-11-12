"""Run the marketplace handoff decision locally without starting the service."""

from marketplace_handoff import HandoffRequest, build_local_processor


request = HandoffRequest.model_validate(
    {
        "order_id": "order-1842",
        "asset": {
            "asset_id": "asset-brand-kit",
            "seller_id": "seller-27",
            "name": "Brand kit archive",
            "status": "ready",
        },
        "buyer_updates": [
            {
                "update_id": "update-delivery-note",
                "kind": "delivery_note",
                "text": "Send the source files with the export.",
            }
        ],
    }
)

if __name__ == "__main__":
    result = build_local_processor(flag_value=True)(request)
    print(result.model_dump_json(indent=2))
