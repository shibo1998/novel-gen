from app.services.context_budget import ContextBudgetManager, ContextSlice


def test_context_budget_groups_by_priority_not_category():
    manager = ContextBudgetManager(model="gpt-4o")
    manager.usable_budget = 20
    slices = [
        ContextSlice("constraint_card", "hard constraint", "critical", token_count=30),
        ContextSlice("historical_events", "history", "low", token_count=10),
    ]

    allocated, report = manager.allocate(slices, chapter_number=1)

    assert "constraint_card" in [item.category for item in allocated]
    assert "constraint_card" in report.critical_slices
    assert "historical_events" in report.dropped_categories


def test_due_foreshadowings_survive_exhausted_context_budget():
    manager = ContextBudgetManager(model="gpt-4o")
    manager.usable_budget = 1
    slices = [
        ContextSlice("due_foreshadowings", "must resolve", "critical", token_count=20),
        ContextSlice("active_foreshadowings", "future setup", "high", token_count=20),
    ]

    allocated, report = manager.allocate(slices, chapter_number=20)

    assert "due_foreshadowings" in [item.category for item in allocated]
    assert "due_foreshadowings" in report.critical_slices
    assert "active_foreshadowings" in report.dropped_categories
