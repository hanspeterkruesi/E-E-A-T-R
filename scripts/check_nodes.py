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

def send_alert(node_id, node_name, node_url, reason="nicht erreichbar"):
    if not EMAIL_USER or not ALERT_RECIPIENT:
        print(f"E-Mail-Konfiguration fehlt für {node_id}")
        return
    
    msg = EmailMessage()
    msg.set_subject(f"[E-E-A-T-R ALERT] Node {node_id} ({node_name}) suspendiert")
    msg.set_from(EMAIL_USER)
    msg.set_content(
        f"Achtung,\n\n"
        f"Der Node {node_id} - {node_name} ({node_url}) hat den Integritäts-Check über 48 Stunden nicht bestanden (Grund: {reason}).\n"
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
            is_healthy = False
            failure_reason = "nicht erreichbar"
            
            try:
                response = requests.get(url, timeout=15, headers={"User-Agent": "EEATR-Wachhund/1.0"})
                if response.status_code == 200:
                    html_content = response.text
                    
                    # Integritäts-Check: Prüfen ob Website erreichbar UND das JSON-LD / Protokoll vorhanden ist
                    # Wir suchen nach der spezifischen Node-ID und dem Verweis auf die Protokoll-Domain
                    has_node_id = node_id.lower() in html_content.lower()
                    has_domain_ref = "e-e-a-t-r.com" in html_content.lower()
                    
                    if has_node_id and has_domain_ref:
                        is_healthy = True
                    else:
                        failure_reason = "JSON-LD Schema oder Protokoll-Verweis im Quellcode nicht gefunden"
                        print(f"WARNUNG: Node {node_id} ist online, aber die Protokoll-Signatur fehlt!")
                else:
                    failure_reason = f"HTTP Status Code {response.status_code}"
            except requests.exceptions.RequestException as e:
                failure_reason = f"Verbindungsfehler: {e}"
            
            if is_healthy:
                # Reset beim Erfolg: Wenn alles passt, löschen wir den Ausfall-Marker
                if "first_failed_at" in node:
                    del node["first_failed_at"]
                    updated = True
            else:
                # Node ist entweder offline oder der Quellcode ist nicht mehr valide
                if "first_failed_at" not in node:
                    node["first_failed_at"] = now.isoformat()
                    updated = True
                    print(f"Erster Fehler für {node_id} registriert am {node['first_failed_at']} (Grund: {failure_reason})")
                else:
                    first_failed = datetime.fromisoformat(node["first_failed_at"])
                    time_diff = now - first_failed
                    
                    if time_diff >= timedelta(hours=48):
                        node["status"] = "suspended"
                        del node["first_failed_at"]
                        updated = True
                        send_alert(node_id, node.get("name"), url, reason=failure_reason)
                        print(f"Node {node_id} nach >48h auf 'suspended' gesetzt.")
                    else:
                        print(f"Node {node_id} fehlerhaft, aber die 48-Stunden-Frist läuft noch (seit {time_diff}).")

    if updated:
        data["last_updated"] = today_str
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("Registry erfolgreich aktualisiert.")
    else:
        print("Keine Statusänderungen erforderlich.")

if __name__ == "__main__":
    check_registry()
