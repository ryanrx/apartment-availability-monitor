import os
import json
from playwright.sync_api import sync_playwright
import requests

STATE_FILE = "units_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(units):
    with open(STATE_FILE, "w") as f:
        json.dump(units, f, indent=2)

def scrape_units(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Timeout: 60 seconds
        page.goto(url, timeout=60000)
        page.wait_for_selector("text=Residence", timeout=60000)
        
        table_container = page.query_selector("div:has-text('Residence') + div > div")
        if not table_container:
            browser.close()
            raise Exception("Could not find floorplans table container")

        rows = table_container.query_selector_all("div")
        units = {}
        for row in rows:
            try:
                cells = row.query_selector_all("div")
                if len(cells) < 2:
                    continue

                unit = cells[0].inner_text().strip()
                bed_bath = cells[1].inner_text().strip()
                rent = cells[2].inner_text().strip() if len(cells) > 2 else ""
                available = cells[3].inner_text().strip() if len(cells) > 3 else ""
                concessions = cells[4].inner_text().strip() if len(cells) > 4 else ""
                net_rent = cells[5].inner_text().strip() if len(cells) > 5 else ""

                # Only track 1-bedroom units
                if bed_bath.startswith("1/"):
                    units[unit] = {
                        "bed_bath": bed_bath,
                        "rent": rent,
                        "available": available,
                        "concessions": concessions,
                        "net_rent": net_rent
                    }
            except Exception as e:
                print(f"Skipping a row due to error: {e}")

        browser.close()
    return units

def detect_changes(prev_units, units):
    messages = []

    # New or updated units
    for unit_id, info in units.items():
        if unit_id not in prev_units:
            messages.append(f":new: New 1-bedroom unit {unit_id} available at {info['rent']} (Available: {info['available']})")
        else:
            prev_info = prev_units[unit_id]
            if info["rent"] != prev_info["rent"]:
                messages.append(f":money_with_wings: Price changed for {unit_id}: {prev_info['rent']} → {info['rent']}")
            if info["concessions"] != prev_info["concessions"]:
                messages.append(f":gift: Concessions updated for {unit_id}: {info['concessions']}")

    # Removed units
    for unit_id in prev_units:
        if unit_id not in units:
            messages.append(f":x: Unit {unit_id} is no longer available")

    return messages

def send_slack(messages, webhook):
    if messages:
        payload = {"text": "\n".join(messages)}
        res = requests.post(webhook, json=payload)
        if res.status_code != 200:
            print(f"Error sending Slack message: {res.text}")

# ===== MAIN =====
def main():
    url = os.getenv("APARTMENT_URL")
    slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
    
    if not url or not slack_webhook:
        raise Exception("APARTMENT_URL or SLACK_WEBHOOK_URL environment variable not set")

    prev_units = load_state()
    units = scrape_units(url)
    messages = detect_changes(prev_units, units)
    send_slack(messages, slack_webhook)
    save_state(units)

    print(f"Done. Found {len(units)} 1-bedroom units.")

if __name__ == "__main__":
    main()
