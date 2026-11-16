import json, os, math, requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

URL = "https://alerts.org.ua/odeska-oblast/"
GROUP_ID = "r8g2-1"                       # группа 2.1
TOPIC = os.environ["NTFY_TOPIC"]
TZ = ZoneInfo("Europe/Kyiv")
WARN_MIN = 30                             # за сколько минут предупреждать
STATE_FILE = "state.json"

def fetch():
    html = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")
    day = soup.select_one("#shedule")["data-time"]
    g = soup.select_one(f'.js-group[data-group-id="{GROUP_ID}"]')
    periods = [{"start": d["data-start"].strip(),
                "end": d["data-end"].strip(),
                "status": "ON" if d.select_one("b.on") else "OFF"}
               for d in g.select(".period > div")]
    return day, periods

def transitions(day, periods):
    base = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=TZ)
    out = []
    for prev, cur in zip(periods, periods[1:]):
        if prev["status"] != cur["status"]:
            h, m = map(int, cur["start"].split(":"))
            out.append((base + timedelta(hours=h, minutes=m), cur["status"]))
    return out

def notify(title, message, priority=3):
    requests.post("https://ntfy.sh", timeout=20, json={
        "topic": TOPIC, "title": title, "message": message,
        "priority": priority, "tags": ["bulb"]})

def summary(periods):
    return "\n".join(f'{p["start"]}–{p["end"]}  {p["status"]}' for p in periods)

def main():
    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
    day, periods = fetch()
    sig = json.dumps(periods, sort_keys=True)
    now = datetime.now(TZ)

    # график изменился
    if state.get("day") != day:
        notify(f"Новий графік на {day} (група 2.1)", summary(periods))
        state["sent"] = []
    elif state.get("sig") != sig:
        notify(f"Графік змінився ({day}, група 2.1)", summary(periods), priority=4)
        state["sent"] = []

    # напоминания за 30 минут до переключения
    sent = set(state.get("sent", []))
    for t, status in transitions(day, periods):
        key = f"{day}-{t:%H:%M}-{status}"
        left = t - now
        if timedelta(0) < left <= timedelta(minutes=WARN_MIN) and key not in sent:
            mins = math.ceil(left.total_seconds() / 60)
            if status == "OFF":
                title = f"🔌 Світло зникне о {t:%H:%M}"
            else:
                title = f"💡 Світло з'явиться о {t:%H:%M}"
            notify(title, f"Через ~{mins} хв (група 2.1)", priority=4)
            sent.add(key)

    state.update(day=day, sig=sig, sent=sorted(sent))
    json.dump(state, open(STATE_FILE, "w"), ensure_ascii=False, indent=1)

main()
