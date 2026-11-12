from marketplace_handoff import HandoffRequest, decide_handoff


def test_ready_asset_includes_buyer_updates_when_enabled() -> None:
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

    included = decide_handoff(request, include_buyer_updates=True)
    excluded = decide_handoff(request, include_buyer_updates=False)

    assert included.state == "handed_off"
    assert included.included_update_ids == ["update-delivery-note"]
    assert excluded.included_update_ids == []


def test_draft_asset_waits_even_when_updates_are_enabled() -> None:
    request = HandoffRequest.model_validate(
        {
            "order_id": "order-1843",
            "asset": {
                "asset_id": "asset-icons",
                "seller_id": "seller-27",
                "name": "Icon pack",
                "status": "draft",
            },
        }
    )

    result = decide_handoff(request, include_buyer_updates=True)

    assert result.state == "waiting_for_asset"
    assert result.included_update_ids == []
