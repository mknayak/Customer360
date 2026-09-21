from Enterprise.Simulator.scenario_engine import ScenarioConfig, ScenarioGenerator


def test_scenario_generation_is_deterministic_and_meets_scale_floor():
    config = ScenarioConfig(seed=7, customers=10_000, products=100, sites=5, journeys=20)
    first = ScenarioGenerator(config).dataset()
    second = ScenarioGenerator(config).dataset()

    assert first == second
    assert len(first["customers"]) == 10_000
    assert len(first["products"]) == 100
    assert len(first["sites"]) == 5
    assert len(first["journeys"]) == 20
    assert all(event["correlation_id"] == journey["correlation_id"] for journey in first["journeys"] for event in journey["events"])
    assert all(event["event_id"] and event["schema_version"] == 1 and event["payload"]["customer_id"] == journey["customer_id"] for journey in first["journeys"] for event in journey["events"])


def test_scenario_modes_change_behavior():
    base = ScenarioConfig(seed=11, scenario="normal", journeys=500)
    uplift = ScenarioConfig(seed=11, scenario="promotion_uplift", journeys=500)
    degraded = ScenarioConfig(seed=11, scenario="website_degradation", journeys=500)
    feedback = ScenarioConfig(seed=11, scenario="feedback_spike", journeys=20)

    base_outcomes = [journey["outcome"] for journey in ScenarioGenerator(base).journeys()]
    uplift_outcomes = [journey["outcome"] for journey in ScenarioGenerator(uplift).journeys()]
    degraded_outcomes = [journey["outcome"] for journey in ScenarioGenerator(degraded).journeys()]

    assert uplift_outcomes.count("purchase") > base_outcomes.count("purchase")
    assert degraded_outcomes.count("failure") > base_outcomes.count("failure")
    assert all(any(event["event_type"] == "FeedbackSubmitted" for event in journey["events"]) for journey in ScenarioGenerator(feedback).journeys())