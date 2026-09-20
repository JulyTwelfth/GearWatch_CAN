import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_search_filter_open_detail_view_history_and_visit_retailer(
    page: Page,
    live_server_url: str,
) -> None:
    page.goto(live_server_url)
    page.get_by_label("Product name").fill("Fixture Alpine Shell")
    page.get_by_label("Size").fill("medium")
    page.get_by_label("Colour").fill("black sapphire")
    page.get_by_label("Minimum discount").select_option("20")
    page.get_by_label("Inventory").select_option("Available")
    page.get_by_role("button", name="Search saved checks").click()

    expect(page).to_have_url(re.compile(r"q=Fixture\+Alpine\+Shell"))
    expect(page.get_by_role("heading", name="1 matching offer")).to_be_visible()
    expect(page.get_by_text("$300.00 CAD").first).to_be_visible()
    expect(page.get_by_role("cell", name="Available", exact=True)).to_be_visible()

    page.get_by_role("link", name="Fixture Alpine Shell").click()
    expect(page).to_have_url(f"{live_server_url}/products/1")
    expect(page.get_by_role("heading", name="Current saved offers")).to_be_visible()
    expect(page.get_by_role("heading", name="Price and inventory history")).to_be_visible()
    expect(page.locator(".price-chart svg").first).to_be_visible()
    expect(page.get_by_text("$350.00", exact=True)).to_be_visible()
    expect(page.get_by_text("Out of Stock", exact=True).first).to_be_visible()
    expect(page.get_by_text("Last checked:", exact=True)).to_be_visible()

    with page.expect_popup() as popup_info:
        page.get_by_role("link", name="Visit retailer").first.click()
    retailer_page = popup_info.value
    expect(
        retailer_page.get_by_role("heading", name="Fixture retailer destination")
    ).to_be_visible()
    expect(retailer_page).to_have_url(
        "https://retailer.example/products/fixture-alpine-shell"
    )


def test_out_of_stock_filter(page: Page, live_server_url: str) -> None:
    page.goto(live_server_url)
    page.get_by_label("Inventory").select_option("Out of Stock")
    page.get_by_role("button", name="Search saved checks").click()

    expect(page.get_by_role("heading", name="1 matching offer")).to_be_visible()
    expect(page.get_by_text("Solitude")).to_be_visible()
    expect(page.get_by_role("cell", name="Out of Stock", exact=True)).to_be_visible()
    expect(page.get_by_role("cell", name="Available", exact=True)).to_have_count(0)


def test_no_results_page(page: Page, live_server_url: str) -> None:
    page.goto(live_server_url)
    page.get_by_label("Product name").fill("Product That Does Not Exist")
    page.get_by_role("button", name="Search saved checks").click()

    expect(page.get_by_role("heading", name="No matching saved offers")).to_be_visible()
    expect(page.get_by_text("Last checked:", exact=True)).to_be_visible()
    expect(page.locator(".last-checked")).to_contain_text("No saved check available")


def test_system_error_page(page: Page, live_server_url: str) -> None:
    page.goto(live_server_url)
    page.get_by_label("Product name").fill("system-error")
    page.get_by_role("button", name="Search saved checks").click()

    expect(
        page.get_by_role("heading", name="Search temporarily unavailable")
    ).to_be_visible()
    expect(page.get_by_role("link", name="Return to search")).to_be_visible()
    expect(page.get_by_text("Last checked:", exact=True)).to_be_visible()


def test_missing_product_page(page: Page, live_server_url: str) -> None:
    response = page.goto(f"{live_server_url}/products/999")

    assert response is not None
    assert response.status == 404
    expect(page.get_by_role("heading", name="Product not found")).to_be_visible()
    expect(page.get_by_role("link", name="Return to search")).to_be_visible()
