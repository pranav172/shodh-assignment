if ticket["category"] is None:
    return "manual_review"
if ticket["urgent"]:
    return "priority"
if ticket["waiting_minutes"] >= 25:
    return "escalation"
return "normal"
