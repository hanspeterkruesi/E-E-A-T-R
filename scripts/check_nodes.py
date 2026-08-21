import json
import os
import smtplib
from email.message import EmailMessage
import requests
from datetime import datetime, timedelta

EMAIL_HOST = os.environ.get("EMAIL_HOST")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
ALERT_RECIPIENT = os.environ.get("ALERT_RECIPIENT")

REGISTRY_PATH = "registry.json"

def send_alert(node_id, node_name, node_url):
    if not EMAIL_USER or not ALERT_RECIPIENT:
        print(f"E-Mail-Konfiguration fehlt für {node_id}")
        return
    
    msg = EmailMessage()
    msg.set_subject(f"[E-E-A-T-R ALERT] Node {node_id} ({node_name}) suspendiert")
    msg.set_from(EMAIL_USER)
    msg.set_content(
        f"Achtung,\n\n"
        f"Der Node {node_id} - {node_name} ({node_url}) war bei 2 Prüfungen innerhalb von 48 Stunden nicht erreichbar.\n"
        f"Der Status in der Registry wurde automatisch auf 'suspended' gesetzt.\n\n"
        f"Dein E-E-A-T-R Wachhund-Skript"
    )
    
    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
    print(f"Alert-Mail für {node_id} versendet.")

def check_registry():
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    updated = False
    now = datetime.utcnow()
    today_str = now.strftime("%Y-%m-%d")

    for node in data.get("nodes", []):
        node_id = node.get("node_id")
        
        if node_id == "NODE-001":
            continue
            
        url = node.get("url")
        current_status = node.get("status")
        
        if current_status in ["active", "verified"]:
            is_reachable = False
            try:
                response = requests.get(url, timeout=15, headers={"User-Agent": "EEATR-Wachhund/1.0"})
                if response.status_code == 200:
                    is_reachable = True
            except requests.exceptions.RequestException:
                is_reachable = False
            
            if is_reachable:
                # Reset beim Erfolg: Wenn er wieder da ist, löschen wir den Ausfall-Marker
                if "first_failed_at" in node:
                    del node["first_failed_at"]
                    updated = True
            else:
                # Node ist nicht erreichbar
                if "first_failed_at" not in node:
                    # Erster Ausfall registriert
                    node["first_failed_at"] = now.isoformat()
                    updated = True
                    print(f"Erster Ausfall für {node_id} registriert am {node['first_failed_at']}")
                else:
                    # Es gab schon einen früheren Ausfall. Prüfen, ob 48 Stunden vergangen sind.
                    first_failed = datetime.fromisoformat(node["first_failed_at"])
                    time_diff = now - first_failed
                    
                    if time_diff >= timedelta(hours=48):
                        # 48 Stunden überschritten und immer noch offline -> Suspended!
                        node["status"] = "suspended"
                        del node["first_failed_at"] # Aufräumen
                        updated = True
                        send_alert(node_id, node.get("name"), url)
                        print(f"Node {node_id} nach >48h auf 'suspended' gesetzt.")
                    else:
                        print(f"Node {node_id} ist offline, aber die 48-Stunden-Frist läuft noch (seit {time_diff}).")

    if updated:
        data["last_updated"] = today_str
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("Registry erfolgreich aktualisiert.")
    else:
        print("Keine Statusänderungen erforderlich.")

if __name__ == "__main__":
    check_registry()
