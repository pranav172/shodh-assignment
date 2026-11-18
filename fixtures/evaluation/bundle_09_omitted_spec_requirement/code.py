if ticket["category"] is None:
    return "manual_review"
if ticket["urgent"]:
    return "priority"
if ticket["waiting_minutes"] >= 30:
    return "escalation"
return "normal"
