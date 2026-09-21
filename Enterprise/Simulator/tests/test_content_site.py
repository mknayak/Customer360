from pathlib import Path


SIMULATOR_ROOT = Path(__file__).parents[1]


def test_content_site_contains_required_pages_and_activity_contract():
    html = (SIMULATOR_ROOT / "content.html").read_text(encoding="utf-8")
    script = (SIMULATOR_ROOT / "content.js").read_text(encoding="utf-8")

    for page_id in ("about", "products", "news", "blog", "stories", "sustainability", "company-information"):
        assert f'id="{page_id}"' in html
    for event_type in ("PageVisit", "ContentView", "Search", "TimeOnPage", "Exit"):
        assert f"'{event_type}'" in script
    assert "correlation_id: sessionId" in script
    assert "schema_version: 1" in script


def test_content_site_is_served_by_the_simulator_root():
    assert (SIMULATOR_ROOT / "content.html").is_file()
    assert (SIMULATOR_ROOT / "content.css").is_file()
    assert (SIMULATOR_ROOT / "content.js").is_file()


def test_simulator_exposes_configurable_user_visit_simulation():
    html = (SIMULATOR_ROOT / "index.html").read_text(encoding="utf-8")
    script = (SIMULATOR_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'data-tab="user-visits"' in html
    assert 'id="simulate-user-visits"' in html
    for flow in ("random", "anonymous_browse", "anonymous_login_browse", "product_cart_abandon", "checkout_success", "checkout_failed"):
        assert f'value="{flow}"' in html
    for control in ("user-visit-count", "user-visit-pages", "user-visit-dwell", "user-visit-search-rate", "user-visit-content-rate"):
        assert f'id="{control}"' in html
    assert "async function simulateUserVisits()" in script
    for event_type in ("PageVisit", "UserLogin", "ContentView", "Search", "TimeOnPage", "ProductViewed", "CartCreated", "CheckoutStarted", "PaymentFailed", "OrderCreated", "Exit"):
        assert f"'{event_type}'" in script
    assert "}, sessionId);" in script