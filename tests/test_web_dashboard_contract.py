from pathlib import Path
WEB_ROOT = Path(__file__).parents[1] / "src" / "powersite_sentinel" / "web"


def test_live_dashboard_keeps_site_dom_nodes_persistent() -> None:
    script = (WEB_ROOT / "app.js").read_text()

    assert "const siteViews = new Map();" in script
    assert "sitesRoot.replaceChildren()" not in script
    assert "updateSiteView(view" in script
    assert "setInterval(() => refresh(false), LIVE_REFRESH_MS);" in script


def test_site_inspector_and_flight_recorder_coexist() -> None:
    html = (WEB_ROOT / "index.html").read_text()

    assert 'class="site-details"' in html
    assert "SITE INSPECTOR" in html
    assert 'class="controller-list"' in html
    assert 'class="site-metrics"' in html
    assert 'class="forensic-panel"' in html
    assert "Flight recorder" in html
    assert '/assets/site-inspector.css' in html
