
def fetch_mal_list_logic(status: str | None = None):
    valid_statuses = {"watching", "completed", "on_hold", "dropped", "plan_to_watch"}
    normalized_status = None
    if status:
        s = status.lower().replace(" ", "_").replace("-", "_")
        if s == "current":
            normalized_status = "watching"
        elif s == "planning":
            normalized_status = "plan_to_watch"
        elif s == "paused":
            normalized_status = "on_hold"
        elif s in valid_statuses:
            normalized_status = s
        elif s == "all":
            normalized_status = None
        else:
            normalized_status = s # Fallback to whatever user typed
    return normalized_status

test_cases = [
    ("ALL", None),
    ("all", None),
    ("All", None),
    ("current", "watching"),
    ("planning", "plan_to_watch"),
    ("completed", "completed"),
    ("RANDOM", "random"),
    (None, None),
]

for status_input, expected in test_cases:
    result = fetch_mal_list_logic(status_input)
    print(f"Input: {status_input!r} -> Result: {result!r} (Expected: {expected!r})")
    assert result == expected
print("\nAll tests passed!")
