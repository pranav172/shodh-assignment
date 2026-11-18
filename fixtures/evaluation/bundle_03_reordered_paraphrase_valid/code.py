if ticket.get("category") is None:
    return "manual_review"
if ticket.get("urgent") is True:
    return "priority"
if 30 <= ticket.get("waiting_minutes"):
    return "escalation"
return "normal"
