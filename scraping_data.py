from playwright.sync_api import sync_playwright
import json
import time

BASE_URL = "https://www.gcu.ac.uk"

# Subjects to keep — focused CS corpus
CS_SUBJECTS = {
    "Computing",
    "Computer Networks & Security",
    "Applied Computer Games",
    "SCEBE Learning and Teaching",   # e.g. Academic Writing for Masters
}

def dismiss_consent(page):
    try:
        btn = page.locator("button:has-text('Allow all')").first
        btn.wait_for(state="visible", timeout=8000)
        btn.click()
        page.wait_for_selector("button:has-text('Allow all')",
                               state="hidden", timeout=8000)
        print("Consent dismissed.")
    except:
        print("No consent popup.")

def wait_for_table(page):
    page.wait_for_selector("th:has-text('Code')", timeout=15000)

def build_url(href):
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return BASE_URL + href

def is_rpl_module(module):
    """SSE RPL modules are admin placeholders with no real content."""
    return (
        module["code"].startswith("MMRP") or
        module["code"].startswith("M3RP") or
        "RPL Module" in module["title"]
    )

def extract_modules_from_page(page):
    modules = []
    rows = page.locator("table tbody tr").all()
    for row in rows:
        cells = row.locator("td").all()
        if len(cells) < 4:
            continue
        title_cell = cells[0]
        link = title_cell.locator("a").first
        href = link.get_attribute("href") if link.count() > 0 else ""
        module = {
            "title":   title_cell.inner_text().strip(),
            "url":     build_url(href),
            "code":    cells[1].inner_text().strip() if len(cells) > 1 else "",
            "level":   cells[2].inner_text().strip() if len(cells) > 2 else "",
            "credits": cells[3].inner_text().strip() if len(cells) > 3 else "",
            "subject": cells[4].inner_text().strip() if len(cells) > 4 else "",
            "school":  cells[5].inner_text().strip() if len(cells) > 5 else "",
        }
        modules.append(module)
    return modules

def get_module_detail(page, url):
    if not url:
        return {}
    try:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=15000)
        content = page.inner_text("main") if page.locator("main").count() > 0 \
                  else page.inner_text("body")
        return {"detail": content.strip()}
    except Exception as e:
        print(f"  Failed: {e}")
        return {}

def go_to_next_page(page):
    for selector in [
        "a:has-text('next')",
        "a[rel='next']",
        "li.next a",
        ".pagination li:last-child a",
        "a:has-text('»')",
    ]:
        try:
            btn = page.locator(selector).first
            if btn.count() > 0 and btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_load_state("networkidle", timeout=10000)
                wait_for_table(page)
                return True
        except:
            continue
    return False

def deduplicate(modules):
    """Keep only one entry per module title — prefer the one with a URL."""
    seen_titles = {}
    for m in modules:
        title = m["title"].lower().strip()
        if title not in seen_titles:
            seen_titles[title] = m
        else:
            # Prefer the entry that has a URL
            if m["url"] and not seen_titles[title]["url"]:
                seen_titles[title] = m
    return list(seen_titles.values())

def scrape_cs_modules(fetch_details=False):
    all_modules = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("Loading module catalogue...")
        page.goto(
            "https://www.gcu.ac.uk/currentstudents/essentials/modules/all-modules",
            wait_until="domcontentloaded"
        )

        dismiss_consent(page)
        page.wait_for_load_state("networkidle", timeout=15000)
        wait_for_table(page)

        current_page = 1
        while True:
            modules = extract_modules_from_page(page)

            filtered = [
                m for m in modules
                if m["level"] == "11"
                and m["school"] == "School of Science & Engineering"
                and m["subject"] in CS_SUBJECTS
                and not is_rpl_module(m)
            ]

            if filtered:
                print(f"Page {current_page}: {len(filtered)} CS modules found.")

            all_modules.extend(filtered)

            if not go_to_next_page(page):
                break
            current_page += 1

        browser.close()

    # Deduplicate by title
    before = len(all_modules)
    all_modules = deduplicate(all_modules)
    print(f"\nDeduplication: {before} → {len(all_modules)} unique modules.")

    # Fetch detail pages
    if fetch_details:
        print("\nFetching detail pages...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            dismiss_consent(page)

            for i, mod in enumerate(all_modules):
                print(f"  [{i+1}/{len(all_modules)}] {mod['title'][:55]}")
                detail = get_module_detail(page, mod["url"])
                mod.update(detail)
                time.sleep(1)  # polite delay

            browser.close()

    return all_modules


if __name__ == "__main__":
    # Step 1: Run without details to confirm clean list
    modules = scrape_cs_modules(fetch_details=True)

    print(f"\n✅ Final corpus: {len(modules)} unique CS modules")
    print("\nFull list:")
    for m in modules:
        print(f"  [{m['code']}] {m['title']} — {m['subject']}")

    with open("gcu_modules_cs_with_details.json", "w") as f:
        json.dump(modules, f, indent=2)
    print("\nSaved to gcu_modules_cs_with_details.json")