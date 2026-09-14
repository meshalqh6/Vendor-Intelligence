"""Next-action matrix lookup: (classification, risk) -> recommended action + control."""


def next_action(store, classification, risk):
    cell = store.next_actions.get(classification, {}).get(risk)
    if not cell:
        return {"recommended_action": "Review manually.", "system_control": "Hold."}
    return {
        "recommended_action": cell["recommended_action"],
        "system_control": cell["system_control"],
    }
