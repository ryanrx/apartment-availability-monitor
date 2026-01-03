import os
import json
from playwright.sync_api import sync_playwright
import requests

STATE_FILE = "units_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            print(f"Loaded state file with {len(data)} units")
            return data

    print("No existing state file found (first run)")
    return {}

def save_state(units):
    with open(STATE_FILE, "w") as f:
        json.dump(units, f, indent=2)

def scrape_units(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(url, timeout=60000)
        page.wait_for_selector("text=Residence", timeout=60000)

        rows = page.query_selector_all("div:has-text('Residence') + div > div")
        if not rows:
            browser.close()
            raise Exception("Could not find any floorplan rows after waiting")

        units = {}
        for row in rows:
            try:
                cells = row.query_selector_all("div")
                text_cells = [c.inner_text().strip() for c in cells]
                if len(text_cells) < 2:
                    continue

                unit = text_cells[0]
                bed_bath = text_cells[1]
                rent = text_cells[2] if len(text_cells) > 2 else ""
                available = text_cells[3] if len(text_cells) > 3 else ""
                concessions = text_cells[4] if len(text_cells) > 4 else ""
                net_rent = text_cells[5] if len(text_cells) > 5 else ""

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

    # New units
    for unit_id, info in units.items():
        if unit_id not in prev_units:
            msg = (
                f":new: New 1-bedroom unit {unit_id}\n"
                f"Bed/Bath: {info['bed_bath']}\n"
                f"Rent: {info['rent']}\n"
                f"Available: {info['available']}\n"
                f"Concessions: {info['concessions']}\n"
                f"Net Rent: {info['net_rent']}"
            )
            messages.append(msg)

        else:
            prev_info = prev_units[unit_id]
            # Price changed
            if info["rent"] != prev_info["rent"]:
                msg = (
                    f":money_with_wings: Price changed for {unit_id}\n"
                    f"Bed/Bath: {info['bed_bath']}\n"
                    f"Previous Rent: {prev_info['rent']}\n"
                    f"New Rent: {info['rent']}\n"
                    f"Available: {info['available']}\n"
                    f"Concessions: {info['concessions']}\n"
                    f"Net Rent: {info['net_rent']}"
                )
                messages.append(msg)

            # Concessions changed
            if info["concessions"] != prev_info["concessions"]:
                msg = (
                    f":gift: Concessions updated for {unit_id}\n"
                    f"Bed/Bath: {info['bed_bath']}\n"
                    f"Rent: {info['rent']}\n"
                    f"Previous Concessions: {prev_info['concessions']}\n"
                    f"New Concessions: {info['concessions']}\n"
                    f"Net Rent: {info['net_rent']}"
                )
                messages.append(msg)

    # Removed units
    for unit_id, prev_info in prev_units.items():
        if unit_id not in units:
            msg = (
                f":x: Unit {unit_id} is no longer available\n"
                f"Bed/Bath: {prev_info['bed_bath']}\n"
                f"Rent: {prev_info['rent']}\n"
                f"Available: {prev_info['available']}\n"
                f"Concessions: {prev_info['concessions']}\n"
                f"Net Rent: {prev_info['net_rent']}"
            )
            messages.append(msg)

    return ["\n" + m for m in messages]

def send_slack(messages, webhook):
    if messages:
        payload = {"text": "\n".join(messages)}
        res = requests.post(webhook, json=payload)
        if res.status_code != 200:
            print(f"Error sending Slack message: {res.text}")
        else:
            print(f"Sent {len(messages)} alert(s) to Slack")

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
