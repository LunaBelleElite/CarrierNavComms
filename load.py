import os
import sys
import re
import json
import time
import glob
import threading
import requests
from datetime import datetime, timezone
from tkinter import ttk, StringVar, BooleanVar, Label, Toplevel, Canvas

try:
    from config import config as edmc_config
except ImportError:
    edmc_config = None

# ---------------------------------------------------------------------------
# Image Cache & Advanced Inara Scraper
# ---------------------------------------------------------------------------
IMAGE_CACHE = {}


def get_carrier_image(inara_url):
    """Scrapes the carrier image/badge from Inara."""
    if not inara_url or not inara_url.startswith("http"):
        return None

    clean_url = inara_url.split("?")[0]
    if any(clean_url.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]):
        return inara_url

    if inara_url in IMAGE_CACHE:
        return IMAGE_CACHE[inara_url]

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CarrierNavComms/1.0"}
        r = requests.get(inara_url, headers=headers, timeout=5)
        if r.status_code == 200:
            html = r.text
            img_url = None

            data_matches = re.findall(
                r'(?:src|href)=["\']([^"\']*/data/(?:fleetcarrier|carrier|stations|gallery|users|ships|images)[^"\']+\.(?:png|jpg|jpeg|webp))["\']',
                html,
                re.IGNORECASE
            )
            if data_matches:
                img_url = data_matches[0]

            if not img_url:
                any_data_matches = re.findall(
                    r'(?:src|href)=["\']([^"\']*/data/[^"\']+\.(?:png|jpg|jpeg|webp))["\']',
                    html,
                    re.IGNORECASE
                )
                if any_data_matches:
                    img_url = any_data_matches[0]

            if not img_url:
                og_match = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
                if og_match:
                    candidate = og_match.group(1)
                    if not any(bad in candidate.lower() for bad in ["inara-logo", "inara_logo", "logo-social", "site-logo"]):
                        img_url = candidate

            if img_url:
                if img_url.startswith("//"):
                    img_url = f"https:{img_url}"
                elif img_url.startswith("/"):
                    img_url = f"https://inara.cz{img_url}"

                IMAGE_CACHE[inara_url] = img_url
                return img_url

            print(f"[CarrierNavComms] No scrapeable image found on Inara page: {inara_url}")
        else:
            print(f"[CarrierNavComms] Inara page returned HTTP {r.status_code} for: {inara_url}")

    except Exception as e:
        print(f"[CarrierNavComms] Inara image scrape warning: {e}")

    return None


# ---------------------------------------------------------------------------
# Dynamic mynotebook.Frame Helper
# ---------------------------------------------------------------------------
def get_mynotebook_frame(notebook):
    """Dynamically fetches EDMC's mynotebook.Frame without breaking startup."""
    if "mynotebook" in sys.modules and hasattr(sys.modules["mynotebook"], "Frame"):
        return sys.modules["mynotebook"].Frame(notebook)

    nb_module_name = getattr(notebook.__class__, "__module__", None)
    if nb_module_name and nb_module_name in sys.modules:
        mod = sys.modules[nb_module_name]
        if hasattr(mod, "Frame"):
            return mod.Frame(notebook)

    for mod_name, mod in list(sys.modules.items()):
        if "mynotebook" in mod_name and hasattr(mod, "Frame"):
            return mod.Frame(notebook)

    if hasattr(sys, "_MEIPASS") and sys._MEIPASS not in sys.path:
        sys.path.insert(0, sys._MEIPASS)
    if hasattr(sys, "executable"):
        exe_dir = os.path.dirname(sys.executable)
        if exe_dir and exe_dir not in sys.path:
            sys.path.insert(0, exe_dir)

    try:
        import mynotebook as NB
        return NB.Frame(notebook)
    except Exception as e:
        print(f"[CarrierNavComms] Warning: Could not instantiate mynotebook.Frame: {e}")
        return ttk.Frame(notebook)


# ---------------------------------------------------------------------------
# Hover Tooltip Helper
# ---------------------------------------------------------------------------
class Tooltip:
    """Shows a small hover popup with explanatory text for a settings widget."""

    def __init__(self, widget, text, wraplength=280):
        self.widget = widget
        self.text = text
        self.wraplength = wraplength
        self.tip_window = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip_window = tw = Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        Label(
            tw, text=self.text, justify="left", background="#ffffe0",
            foreground="#000000", relief="solid", borderwidth=1,
            wraplength=self.wraplength, padx=6, pady=4
        ).pack()

    def hide(self, _event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


# ---------------------------------------------------------------------------
# Configuration & File Management
# ---------------------------------------------------------------------------
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

current_system = "Unknown System"
current_carrier_name = ""
current_station_name = ""
current_carrier_id = ""
current_market_id = ""

# Jumps requested while the player is aboard the carrier get their normal completion
# message from the live "CarrierJump" event. If the player leaves before the jump fires,
# that event never appears in their journal at all (Frontier only logs it to whoever is
# docked at the time) -- so this tracks jumps awaiting confirmation and falls back to a
# CarrierLocation-based message if "CarrierJump" doesn't show up shortly after arrival.
pending_jumps = {}
pending_jumps_lock = threading.Lock()
JUMP_FALLBACK_DELAY_SECONDS = 90

# Last known system for each carrier, sourced from its own "CarrierLocation" events
# rather than the player's ship location -- the player can be docked, remote, or
# elsewhere entirely, so their own tracked system isn't a reliable stand-in for
# where the carrier itself actually is (e.g. for the "Remaining In" cancel message).
carrier_current_system = {}

# The system each carrier occupied *before* its most recent move. "CarrierJump" carries
# only the destination, and "CarrierLocation" (which does carry the new system) arrives
# roughly a minute BEFORE it -- so by the time a Jump Complete message is built,
# carrier_current_system already holds the destination. This keeps the outgoing value.
carrier_previous_system = {}

# Running tally of first discoveries/first mapped bodies since the last exploration
# data sale (of any kind, not just at a carrier -- Universal Cartographics resets this
# game-side on any sale). Fed live by "Scan" (WasDiscovered/WasMapped) and
# "SAAScanComplete" events, and reset on "Died" (exploration data is lost on death) or
# on a sale. pending_mapped_candidates tracks bodies seen with WasMapped=False that
# haven't been DSS-mapped yet, keyed by (SystemAddress, BodyID) -- a body only counts
# toward the first-mapped tally once its matching SAAScanComplete actually arrives.
# pending_discovered_bodies dedupes first-discovery counting: Elite Dangerous can emit
# multiple "Scan" events for the same body in the same session (e.g. re-honking it, or a
# NavBeaconDetail scan following an earlier Detailed scan) and WasDiscovered can still
# read False on the repeat -- without this, the same body gets counted more than once.
# pending_belt_systems_counted caps belt cluster (asteroid ring cluster) discoveries at
# 1 per system instead of 1 per cluster -- a single ring can have dozens of individually
# scannable clusters, which otherwise buries the actual planet/star discovery count.
pending_first_discoveries = 0
pending_first_mapped = 0
pending_mapped_candidates = {}
pending_discovered_bodies = set()
pending_belt_systems_counted = set()


def apply_exploration_event(entry):
    """Updates the running first-discovery/first-mapped tally from a single journal entry."""
    global pending_first_discoveries, pending_first_mapped

    event = entry.get("event")

    if event == "Scan":
        system_addr = entry.get("SystemAddress")
        body_id = entry.get("BodyID")
        body_key = (system_addr, body_id) if system_addr is not None and body_id is not None else None
        is_belt_cluster = "Belt Cluster" in entry.get("BodyName", "")

        if entry.get("WasDiscovered") is False:
            if body_key is None or body_key not in pending_discovered_bodies:
                if body_key is not None:
                    pending_discovered_bodies.add(body_key)

                if is_belt_cluster:
                    if system_addr is not None and system_addr not in pending_belt_systems_counted:
                        pending_belt_systems_counted.add(system_addr)
                        pending_first_discoveries += 1
                    # else: this system's belt clusters were already counted once, skip
                else:
                    pending_first_discoveries += 1

        if entry.get("WasMapped") is False and body_key is not None:
            pending_mapped_candidates[body_key] = True

    elif event == "SAAScanComplete":
        system_addr = entry.get("SystemAddress")
        body_id = entry.get("BodyID")
        if (system_addr, body_id) in pending_mapped_candidates:
            del pending_mapped_candidates[(system_addr, body_id)]
            pending_first_mapped += 1

    elif event == "Died":
        pending_first_discoveries = 0
        pending_first_mapped = 0
        pending_mapped_candidates.clear()
        pending_discovered_bodies.clear()
        pending_belt_systems_counted.clear()

    elif event in ("SellExplorationData", "MultiSellExplorationData"):
        pending_first_discoveries = 0
        pending_first_mapped = 0
        pending_mapped_candidates.clear()
        pending_discovered_bodies.clear()
        pending_belt_systems_counted.clear()


def reconstruct_exploration_tally_from_logs():
    """Replays recent journal files to seed the first-discovery/first-mapped tally on
    plugin startup, so exploring done while EDMC wasn't running is still counted."""
    journal_dir = get_journal_directory()
    if not journal_dir:
        return

    log_files = sorted(glob.glob(os.path.join(journal_dir, "Journal.*.log")), key=os.path.getmtime)
    if not log_files:
        return

    # The current/live session file is included deliberately. EDMC does not replay a
    # journal's existing contents to plugins on startup -- it builds its own state and
    # hands plugins a single synthesized StartUp event -- so anything scanned before
    # EDMC launched would otherwise be counted by nobody. If EDMC does deliver some of
    # these events again live, the per-body dedup in apply_exploration_event absorbs it.
    older_logs = log_files[-30:]

    relevant_markers = ("\"event\":\"Scan\"", "\"event\":\"SAAScanComplete\"", "\"event\":\"Died\"",
                         "\"event\":\"SellExplorationData\"", "\"event\":\"MultiSellExplorationData\"")

    for log_path in older_logs:
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not any(marker in line for marker in relevant_markers):
                        continue
                    try:
                        apply_exploration_event(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

    print(f"[CarrierNavComms] Seeded exploration tally from recent journals: "
          f"{pending_first_discoveries} first discoveries, {pending_first_mapped} first mapped, pending sale.")


def clear_pending_jump(carrier_key):
    """Cancels and removes any pending fallback jump-complete timer for a carrier."""
    with pending_jumps_lock:
        old = pending_jumps.pop(carrier_key, None)
        if old and old.get("timer"):
            old["timer"].cancel()


def load_config():
    """Loads configuration settings from config.json."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[CarrierNavComms] Error loading config: {e}")
    return {}


def save_config(config_data):
    """Saves updated configuration data to config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
    except Exception as e:
        print(f"[CarrierNavComms] Error saving config: {e}")


# ---------------------------------------------------------------------------
# Deep Journal Pre-Scanner & Manual Fetch Helper
# ---------------------------------------------------------------------------
def get_journal_directory():
    """Resolves true journal folder using EDMC settings, OneDrive fallback, and default path."""
    if edmc_config and hasattr(edmc_config, "get_str"):
        jdir = edmc_config.get_str("journaldir")
        if jdir and os.path.exists(jdir):
            return jdir

    user_profile = os.environ.get("USERPROFILE", "")
    possible_paths = [
        os.path.join(user_profile, "Saved Games", "Frontier Developments", "Elite Dangerous"),
        os.path.join(user_profile, "OneDrive", "Saved Games", "Frontier Developments", "Elite Dangerous")
    ]

    for p in possible_paths:
        if os.path.exists(p):
            return p

    return None


def fetch_carrier_details_from_logs(callsign):
    """Scans recent journal files for a given carrier callsign, returning (numeric_id, owner_cmdr).

    CarrierStats only ever appears in the owning commander's own journal, so a match there lets us
    also read that journal's Commander name to confidently identify the carrier's owner. A match via
    a plain Docked event doesn't prove ownership, so it's kept only as a fallback while every file is
    checked for a definitive CarrierStats match — the owner may not have docked with the carrier
    recently (e.g. it's off running trades unattended), so CarrierStats can be several sessions back.
    """
    if not callsign:
        return None, None

    journal_dir = get_journal_directory()
    if not journal_dir:
        return None, None

    log_files = sorted(glob.glob(os.path.join(journal_dir, "Journal.*.log")), key=os.path.getmtime, reverse=True)
    if not log_files:
        return None, None

    search_term = callsign.strip().upper()
    fallback_id = None

    # Scan the last 25 journal files for maximum coverage
    for log_path in log_files[:25]:
        try:
            commander_name = None
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "CarrierStats" not in line and "Docked" not in line and '"Commander"' not in line and "LoadGame" not in line:
                        continue
                    try:
                        data = json.loads(line)
                        event = data.get("event")

                        if event == "Commander":
                            name = data.get("Name", "").strip()
                            if name:
                                commander_name = name

                        elif event == "LoadGame":
                            name = data.get("Commander", "").strip()
                            if name:
                                commander_name = name

                        elif event == "CarrierStats":
                            c_sign = data.get("Callsign", "").strip().upper()
                            c_id = str(data.get("CarrierID", "") or "").strip()
                            if search_term == c_sign or search_term in c_sign:
                                if c_id:
                                    return c_id, commander_name

                        elif event == "Docked" and data.get("StationType") == "FleetCarrier":
                            st_name = data.get("StationName", "").strip().upper()
                            m_id = str(data.get("MarketID", "") or "").strip()
                            if search_term == st_name or search_term in st_name:
                                if m_id and not fallback_id:
                                    fallback_id = m_id

                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

    return (fallback_id, None) if fallback_id else (None, None)


def fetch_carrier_id_from_logs(callsign):
    """Backward-compatible wrapper returning only the numeric ID."""
    numeric_id, _ = fetch_carrier_details_from_logs(callsign)
    return numeric_id


def seed_dock_state_from_logs():
    """Seeds the dock state (market id, station name) from the newest journal file.

    EDMC does not replay journal history to plugins on startup, so if it is launched while
    the player is already docked, no Docked event ever arrives and sales would match no
    carrier. The newest journal is replayed in file order with the same rules journal_entry
    applies live; Undocked and Shutdown clear the state.
    """
    global current_market_id, current_station_name

    journal_dir = get_journal_directory()
    if not journal_dir:
        return

    try:
        log_files = sorted(glob.glob(os.path.join(journal_dir, "Journal.*.log")),
                           key=os.path.getmtime, reverse=True)
    except OSError:
        return
    if not log_files:
        return

    market_id = ""
    station_name = ""
    wanted = ("Docked", "Location", "CarrierJump", "Undocked", "Shutdown")
    try:
        with open(log_files[0], "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not any(w in line for w in wanted):
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                ev = data.get("event")
                if ev in ("Undocked", "Shutdown"):
                    market_id = ""
                    station_name = ""
                elif ev == "Docked" or (ev in ("Location", "CarrierJump") and data.get("Docked")):
                    mid = str(data.get("MarketID") or "").strip()
                    if mid:
                        market_id = mid
                        if data.get("StationName"):
                            station_name = data.get("StationName")
                    elif ev == "Docked":
                        market_id = ""
                elif ev == "Location":
                    market_id = ""
                    station_name = ""
    except OSError:
        return

    current_market_id = market_id
    if station_name:
        current_station_name = station_name
    print(f"[CarrierNavComms] Seeded dock state from the newest journal (market id: '{market_id or 'none'}').")


def seed_carrier_systems_from_logs():
    """Seeds each carrier's current and previous system from past "CarrierLocation" events.

    EDMC does not replay journal history to plugins on startup, so if it is launched while
    the game is already running, the "CarrierLocation" written just after LoadGame is never
    delivered and the plugin has no idea where any carrier is. Two systems are recovered
    rather than one: if EDMC starts after a jump's arrival "CarrierLocation" is written but
    before "CarrierJump", the newest logged system is the destination and the one before it
    is the departure system the message actually needs.
    """
    config = load_config()
    carriers = config.get("carrier_surveillance", {}).get("carriers", {})
    if not carriers:
        return

    journal_dir = get_journal_directory()
    if not journal_dir:
        print("[CarrierNavComms] Journal directory not found.")
        return

    log_files = sorted(glob.glob(os.path.join(journal_dir, "Journal.*.log")), key=os.path.getmtime, reverse=True)
    if not log_files:
        return

    # Numeric ID -> carrier key, for the carriers that still need systems resolved.
    wanted = {}
    for target_key, cdata in carriers.items():
        if not isinstance(cdata, dict):
            continue
        num_id = str(cdata.get("numeric_id", "") or "").strip()
        if num_id:
            wanted[num_id] = target_key

    if not wanted:
        return

    found = {}  # numeric ID -> [newest system, previous system]

    for log_path in log_files[:15]:
        if len(found) == len(wanted) and all(len(v) >= 2 for v in found.values()):
            break
        try:
            hits = []
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "CarrierLocation" not in line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("event") != "CarrierLocation" or data.get("CarrierType") != "FleetCarrier":
                        continue
                    num_id = str(data.get("CarrierID", "") or "").strip()
                    star_sys = (data.get("StarSystem", "") or "").strip()
                    if num_id in wanted and star_sys:
                        hits.append((num_id, star_sys))

            # Lines within a log are oldest-first; walk this file's hits newest-first.
            for num_id, star_sys in reversed(hits):
                seen = found.setdefault(num_id, [])
                if len(seen) >= 2:
                    continue
                if seen and seen[-1].upper() == star_sys.upper():
                    continue
                seen.append(star_sys)
        except Exception as e:
            print(f"[CarrierNavComms] Could not read journal '{os.path.basename(log_path)}': {e}")

    for num_id, systems in found.items():
        target_key = wanted[num_id]
        carrier_current_system[target_key] = systems[0]
        if len(systems) > 1:
            carrier_previous_system[target_key] = systems[1]
        print(f"[CarrierNavComms] Seeded '{target_key}' location from logs: now '{systems[0]}'"
              + (f", previously '{systems[1]}'." if len(systems) > 1 else ", no earlier system found."))


def deep_scan_journals_for_carrier_ids():
    """Scans the last 15 journal logs to guarantee mapping callsigns to numeric IDs on startup."""
    config = load_config()
    carriers = config.get("carrier_surveillance", {}).get("carriers", {})
    if not carriers:
        return

    journal_dir = get_journal_directory()
    if not journal_dir:
        print("[CarrierNavComms] Journal directory not found.")
        return

    log_files = sorted(glob.glob(os.path.join(journal_dir, "Journal.*.log")), key=os.path.getmtime, reverse=True)
    if not log_files:
        return

    recent_logs = log_files[:15]
    updated = False
    # Logs are walked newest-first. Once a carrier's ID is resolved from the most recent
    # log that mentions it, skip it -- otherwise each older log kept overwriting the value,
    # so the OLDEST (most stale) entry was the one that ultimately won.
    resolved_keys = set()

    for log_path in recent_logs:
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "CarrierStats" not in line and "Docked" not in line:
                        continue

                    try:
                        data = json.loads(line)
                        event = data.get("event")

                        if event == "CarrierStats":
                            callsign = data.get("Callsign", "").strip().upper()
                            num_id = str(data.get("CarrierID", "") or "").strip()

                            for target_key, cdata in carriers.items():
                                if target_key in resolved_keys:
                                    continue
                                key_upper = target_key.strip().upper()
                                if key_upper == callsign or key_upper in callsign:
                                    if not num_id:
                                        continue
                                    resolved_keys.add(target_key)
                                    if str(cdata.get("numeric_id", "")).strip() != num_id:
                                        cdata["numeric_id"] = num_id
                                        updated = True
                                        print(f"[CarrierNavComms] Mapped '{target_key}' to Numeric ID '{num_id}' via CarrierStats in log.")

                        elif event == "Docked" and data.get("StationType") == "FleetCarrier":
                            callsign = data.get("StationName", "").strip().upper()
                            market_id = str(data.get("MarketID", "") or "").strip()

                            for target_key, cdata in carriers.items():
                                if target_key in resolved_keys:
                                    continue
                                key_upper = target_key.strip().upper()
                                if key_upper == callsign or key_upper in callsign:
                                    if not market_id:
                                        continue
                                    resolved_keys.add(target_key)
                                    if str(cdata.get("numeric_id", "")).strip() != market_id:
                                        cdata["numeric_id"] = market_id
                                        updated = True
                                        print(f"[CarrierNavComms] Mapped '{target_key}' to Numeric ID '{market_id}' via Docked in log.")

                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"[CarrierNavComms] Error scanning log file '{log_path}': {e}")

    if updated:
        config["carrier_surveillance"]["carriers"] = carriers
        save_config(config)
        print("[CarrierNavComms] Successfully updated config with scanned Fleet Carrier IDs.")


# ---------------------------------------------------------------------------
# Webhook & Broadcast Logic
# ---------------------------------------------------------------------------
def broadcast_surveillance_embed(webhook_urls, embed_data, sender_name="Fleet Carrier", inara_url=""):
    """Sends webhook payload to all specified Discord webhook URLs."""
    if not webhook_urls:
        return False, "No webhook URLs provided"

    if inara_url:
        carrier_img = get_carrier_image(inara_url)
        if carrier_img:
            embed_data["image"] = {"url": carrier_img}

        if inara_url.startswith("http"):
            existing_desc = embed_data.get("description", "")
            embed_data["description"] = re.sub(
                r'^(#{1,3})\s*(.+)$',
                lambda m: f"{m.group(1)} [{m.group(2)}]({inara_url})",
                existing_desc,
                count=1,
                flags=re.MULTILINE
            )

    embed_data["footer"] = {
        "text": "This message was sent by CarrierNavComms"
    }
    embed_data["timestamp"] = datetime.now(timezone.utc).isoformat()

    payload = {
        "username": sender_name,
        "embeds": [embed_data]
    }

    success_count = 0
    errors = []

    for url in webhook_urls:
        clean_url = url.strip() if isinstance(url, str) else ""
        if clean_url:
            try:
                r = requests.post(clean_url, json=payload, timeout=5)
                if r.status_code in [200, 204]:
                    success_count += 1
                else:
                    errors.append(f"HTTP {r.status_code}")
            except Exception as e:
                errors.append(str(e))

    if success_count > 0:
        return True, f"Sent to {success_count} webhook(s)"
    else:
        err_msg = ", ".join(errors) if errors else "Failed to send"
        return False, err_msg


def generate_embed_from_config(embed_key, active_cmdr, c_display, **kwargs):
    """Generates embed using templates from config.json."""
    config = load_config()
    embeds_cfg = config.get("embeds", {})
    tmpl = embeds_cfg.get(embed_key, {})

    sample_timestamp = kwargs.get("jump_timestamp", int(time.time()) + 900)

    fallbacks = {
        "jump_scheduled": {
            "title": "# 🚀 Fleet Carrier Jump Scheduled",
            "color": 15844367,
            "description": "Commander {cmdr} scheduled a jump from {from_system} to {destination} ({body}). Departure: <t:{jump_timestamp}:F> (<t:{jump_timestamp}:R>)."
        },
        "jump_cancelled": {
            "title": "# ❌ Fleet Carrier Jump Cancelled",
            "color": 15158332,
            "description": "Commander {cmdr} cancelled the scheduled jump for {carrier}."
        },
        "jump_complete": {
            "title": "# ✅ Fleet Carrier Jump Complete",
            "color": 3066993,
            "description": "{carrier} has successfully arrived in system {destination}."
        },
        "jump_complete_remote": {
            "title": "# ✅ Fleet Carrier Jump Complete",
            "color": 3066993,
            "description": "{carrier} has successfully arrived in system {destination}."
        },
        "tritium_deposited": {
            "title": "# ⛽ Tritium Deposited",
            "color": 3066993,
            "description": "Commander {cmdr} deposited {quantity}t of Tritium into {carrier}."
        },
        "carrier_sell_order": {
            "title": "# 📊 Carrier Market Sell Order",
            "color": 10181046,
            "description": "{carrier} is now selling {item} for {price} CR/ton ({quantity} available).\n\nPlease check Carrier sell order before starting this order.\nOrder was requested <t:{order_timestamp}:R>"
        },
        "carrier_buy_order": {
            "title": "# 📊 Carrier Market Buy Order",
            "color": 10181046,
            "description": "{carrier} is now buying {item} for {price} CR/ton ({quantity} requested).\n\nPlease check Carrier buy order before starting this order.\nOrder was requested <t:{order_timestamp}:R>"
        },
        "trade_sale": {
            "title": "# 📦 Carrier Market Sale",
            "color": 3066993,
            "description": "Commander {cmdr} sold {quantity}x {item} to {carrier} for {total_price} CR."
        },
        "trade_purchase": {
            "title": "# 📦 Carrier Market Purchase",
            "color": 15105570,
            "description": "Commander {cmdr} purchased {quantity}x {item} from {carrier} for {total_price} CR."
        },
        "cartographics": {
            "title": "# 🌌 Universal Cartographics Turn-In",
            "color": 3447003,
            "description": "Commander {cmdr} turned in exploration data for {systems} systems at {carrier} for {total_earned} CR ({first_discoveries} First Discoveries, {first_mapped} First Mapped, {bonus} CR bonus).{data_note}"
        },
        "exobiology": {
            "title": "# 🧬 Vista Genomics Turn-In",
            "color": 10181046,
            "description": "Commander {cmdr} turned in exobiology data at {carrier} for {total_earned} CR ({first_discoveries} First Discoveries)."
        }
    }

    fallback = fallbacks.get(embed_key, {"title": "# 🧪 Test Notification", "color": 3066993, "description": "Test message"})

    title = tmpl.get("title", fallback["title"])
    color = tmpl.get("color", fallback["color"])
    raw_desc = tmpl.get("description", fallback["description"])

    format_data = {
        "cmdr": active_cmdr,
        "carrier": c_display,
        "from_system": kwargs.get("from_system", "Shinrarta Dezhra"),
        "current_system": kwargs.get("current_system", kwargs.get("from_system", "Shinrarta Dezhra")),
        "destination": kwargs.get("destination", "Sol"),
        "body": kwargs.get("body", "Earth orbit"),
        "jump_timestamp": sample_timestamp,
        "quantity": kwargs.get("quantity", "100"),
        "item": kwargs.get("item", "Tritium"),
        "price": kwargs.get("price", "1,000"),
        "total_price": kwargs.get("total_price", "25,000,000"),
        "total_earned": kwargs.get("total_earned", "12,500,000"),
        "first_discoveries": kwargs.get("first_discoveries", "3"),
        "first_mapped": kwargs.get("first_mapped", "2"),
        "systems": kwargs.get("systems", "3"),
        "bonus": kwargs.get("bonus", "0"),
        "order_timestamp": kwargs.get("order_timestamp", int(time.time())),
        "data_note": kwargs.get("data_note", "")
    }

    try:
        description = raw_desc.format(**format_data)
    except Exception as e:
        print(f"[CarrierNavComms] Placeholder formatting warning for {embed_key}: {e}")
        description = raw_desc

    embed = {
        "color": color,
        "description": description
    }

    return embed


# ---------------------------------------------------------------------------
# EDMC Plugin Entrypoints
# ---------------------------------------------------------------------------
def plugin_start3(plugin_dir):
    """Initializes plugin at EDMC startup."""
    deep_scan_journals_for_carrier_ids()
    seed_carrier_systems_from_logs()
    seed_dock_state_from_logs()
    reconstruct_exploration_tally_from_logs()
    print("[CarrierNavComms] Plugin loaded successfully.")
    return "CarrierNavComms"


def plugin_app(parent):
    """Builds EDMC main window interface."""
    label = Label(parent, text="CarrierNavComms Active")
    return label


# ---------------------------------------------------------------------------
# Plugin Settings UI
# ---------------------------------------------------------------------------
def plugin_prefs(notebook, cmdr, is_beta):
    """Builds the EDMC settings tab UI."""
    config = load_config()
    surveillance = config.get("carrier_surveillance", {})
    carriers_dict = surveillance.get("carriers", {})

    frame = get_mynotebook_frame(notebook)

    enabled_var = BooleanVar(value=surveillance.get("enabled", True))
    chk_enabled = ttk.Checkbutton(frame, text="Enable Carrier Surveillance Notifications", variable=enabled_var)
    chk_enabled.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)
    Tooltip(chk_enabled, "Turn all Discord notifications for your tracked Fleet Carriers on or off.")

    lbl_title = ttk.Label(frame, text="Configured Fleet Carriers", font=("Helvetica", 10, "bold"))
    lbl_title.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 2))

    # Carrier cards are tall, so more than two of them ran off the bottom of the settings
    # window -- and EDMC does not scroll plugin preference tabs, which left later carriers
    # completely unreachable. Tkinter has no scrollable frame, so the cards now live in a
    # fixed-height Canvas that scrolls. Only the container changes: carriers_container
    # keeps its name and role, so all the card-building code below is untouched. The
    # enable checkbox (row 0) and the Add button (row 3) stay outside it, staying pinned.
    scroll_host = ttk.Frame(frame)
    scroll_host.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)
    scroll_host.grid_rowconfigure(0, weight=1)
    scroll_host.grid_columnconfigure(0, weight=1)

    canvas_opts = {"height": 300, "highlightthickness": 0, "bd": 0}  # replaced by _size_viewport()
    try:
        # A Canvas is a plain tk widget and won't inherit EDMC's theme, so its default
        # background would show through beneath the cards whenever the list is short.
        themed_bg = ttk.Style().lookup("TFrame", "background")
        if themed_bg:
            canvas_opts["background"] = themed_bg
    except Exception:
        pass

    carriers_canvas = Canvas(scroll_host, **canvas_opts)
    carriers_canvas.grid(row=0, column=0, sticky="nsew")

    carriers_scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=carriers_canvas.yview)
    carriers_scrollbar.grid(row=0, column=1, sticky="ns")
    carriers_canvas.configure(yscrollcommand=carriers_scrollbar.set)

    carriers_container = ttk.Frame(carriers_canvas)
    carriers_container.grid_columnconfigure(0, weight=1)
    carriers_window = carriers_canvas.create_window((0, 0), window=carriers_container, anchor="nw")

    # How many carrier cards should be visible before the list starts scrolling.
    VISIBLE_CARDS = 2
    _viewport_height = {"value": None}

    def _size_viewport():
        """Sizes the scroll viewport to fit VISIBLE_CARDS cards.

        The card height is measured at runtime rather than hardcoded -- it depends on the
        EDMC theme, font, and display scaling, and a guessed pixel value was wrong enough
        to show only a single carrier.
        """
        cards = carriers_container.winfo_children()
        if not cards:
            return
        card_height = max(c.winfo_reqheight() for c in cards) + 10  # + the grid pady
        desired = card_height * VISIBLE_CARDS
        # Never let the list alone push the settings window off a smaller screen.
        desired = max(200, min(desired, int(carriers_canvas.winfo_screenheight() * 0.6)))
        if _viewport_height["value"] != desired:
            _viewport_height["value"] = desired
            carriers_canvas.configure(height=desired)

    def _sync_scrollregion(_event=None):
        carriers_canvas.configure(scrollregion=carriers_canvas.bbox("all"))
        _size_viewport()
        # A Canvas defaults to a fixed ~378px width regardless of its contents, which would
        # clip the cards horizontally (there is no horizontal scrollbar). Grow it to fit the
        # widest card. Grow-only, so this can't oscillate against the width sync below.
        needed_width = carriers_container.winfo_reqwidth()
        if needed_width > carriers_canvas.winfo_reqwidth():
            carriers_canvas.configure(width=needed_width)

    def _sync_inner_width(event):
        carriers_canvas.itemconfigure(carriers_window, width=event.width)

    carriers_container.bind("<Configure>", _sync_scrollregion)
    carriers_canvas.bind("<Configure>", _sync_inner_width)

    # Wheel events go to whatever widget sits under the pointer (an Entry, a Label, ...),
    # so a binding on the canvas alone would never fire. Bind globally only while the
    # pointer is over the list, and drop it on leave/destroy so the binding can't outlive
    # this settings tab and hijack scrolling elsewhere in EDMC.
    def _on_mousewheel(event):
        carriers_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _grab_wheel(_event=None):
        carriers_canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _release_wheel(_event=None):
        carriers_canvas.unbind_all("<MouseWheel>")

    carriers_canvas.bind("<Enter>", _grab_wheel)
    carriers_canvas.bind("<Leave>", _release_wheel)
    carriers_canvas.bind("<Destroy>", _release_wheel)

    carrier_rows = []

    def render_carrier_cards():
        for widget in carriers_container.winfo_children():
            widget.destroy()

        carrier_rows.clear()
        card_idx = 0

        for cid, cdata in list(carriers_dict.items()):
            c_name = cdata.get("name", "") if isinstance(cdata, dict) else ""
            c_num_id = str(cdata.get("numeric_id", "") if isinstance(cdata, dict) else "")

            wh_raw = cdata.get("webhooks", []) if isinstance(cdata, dict) else []
            if isinstance(wh_raw, str):
                wh_list = [u.strip() for u in wh_raw.split(",") if u.strip()]
            elif isinstance(wh_raw, list):
                wh_list = [str(u).strip() for u in wh_raw if str(u).strip()]
            else:
                wh_list = []

            c_inara = cdata.get("inara_url", "") if isinstance(cdata, dict) else ""
            c_owner = cdata.get("owner_cmdr", "") if isinstance(cdata, dict) else ""

            card = ttk.LabelFrame(carriers_container, text=f" Fleet Carrier ({cid if cid else 'New'}) ")
            card.grid(row=card_idx, column=0, sticky="we", padx=5, pady=5)

            v_id = StringVar(value=cid)
            v_num_id = StringVar(value=c_num_id)
            v_name = StringVar(value=c_name)
            v_inara = StringVar(value=c_inara)
            v_owner = StringVar(value=c_owner)

            r1 = ttk.Frame(card)
            r1.pack(fill="x", expand=True, padx=5, pady=2)

            ttk.Label(r1, text="Callsign (ID):").pack(side="left", padx=(0, 2))
            ent_id = ttk.Entry(r1, textvariable=v_id, width=10)
            ent_id.pack(side="left", padx=(0, 8))
            Tooltip(ent_id, "Your Fleet Carrier's callsign (e.g. A1B-2C3), shown on the carrier management panel in-game. Enter this first.")

            ttk.Label(r1, text="Numeric ID:").pack(side="left", padx=(0, 2))
            ent_num_id = ttk.Entry(r1, textvariable=v_num_id, width=13)
            ent_num_id.pack(side="left", padx=(0, 4))
            Tooltip(ent_num_id, "Auto-filled by the Fetch ID button. Enter the Callsign first, then click Fetch ID. If Fetch ID finds nothing, dock with the carrier in-game once so it appears in your journal logs, then try Fetch ID again.")

            status_lbl = ttk.Label(card, text="", font=("Helvetica", 8))

            def run_fetch_id(target_callsign_var, num_id_var, owner_var, lbl):
                callsign = target_callsign_var.get().strip()
                if not callsign:
                    lbl.pack(fill="x", padx=10, pady=(2, 5))
                    lbl.config(text="Please enter a Callsign (ID) first.", foreground="red")
                    return

                lbl.pack(fill="x", padx=10, pady=(2, 5))
                lbl.config(text=f"Scanning recent journals for '{callsign}'...", foreground="blue")

                found_id, found_owner = fetch_carrier_details_from_logs(callsign)
                if found_id:
                    num_id_var.set(found_id)
                    if found_owner:
                        owner_var.set(found_owner)
                        lbl.config(text=f"Success! Found Numeric ID: {found_id} (Owner: {found_owner})", foreground="green")
                    else:
                        lbl.config(text=f"Success! Found Numeric ID: {found_id}", foreground="green")
                else:
                    lbl.config(
                        text=f"No ID found in recent logs for '{callsign}'. Try opening Carrier Services in-game.",
                        foreground="orange"
                    )

            btn_fetch = ttk.Button(r1, text="Fetch ID", width=9, command=lambda cv=v_id, nv=v_num_id, ov=v_owner, sl=status_lbl: run_fetch_id(cv, nv, ov, sl))
            btn_fetch.pack(side="left", padx=(0, 10))
            Tooltip(btn_fetch, "Scans your recent journal logs for this Callsign's Numeric ID and, if you're the owner, your Commander name. If no match is found, dock with the carrier once in-game and try again.")

            ttk.Label(r1, text="Name:").pack(side="left", padx=(0, 2))
            ent_name = ttk.Entry(r1, textvariable=v_name, width=16)
            ent_name.pack(side="left", padx=(0, 8))
            Tooltip(ent_name, "Enter your Fleet Carrier's actual registered name exactly as shown in-game on the Carrier Management panel — not a nickname. This is shown in Discord messages alongside the Callsign.")

            ttk.Label(r1, text="Inara URL:").pack(side="left", padx=(0, 2))
            ent_inara = ttk.Entry(r1, textvariable=v_inara, width=22)
            ent_inara.pack(side="left", padx=(0, 8))
            Tooltip(ent_inara, "Optional: this carrier's Inara.cz page. Used for the carrier image and to link the message heading to your Inara listing.")

            r1b = ttk.Frame(card)
            r1b.pack(fill="x", expand=True, padx=5, pady=2)

            ttk.Label(r1b, text="Owner Commander Name:").pack(side="left", padx=(0, 2))
            ent_owner = ttk.Entry(r1b, textvariable=v_owner, width=20, state="readonly")
            ent_owner.pack(side="left", padx=(0, 8))
            Tooltip(ent_owner, "Read-only — auto-filled only by Fetch ID, and only when run by the carrier's actual owner. Blank is normal otherwise. Jump and Sell/Buy Order messages only send from the owner's install, preventing duplicates from crew.")

            def make_del_cmd(target_key):
                def remove_card():
                    if target_key in carriers_dict:
                        del carriers_dict[target_key]
                    render_carrier_cards()
                return remove_card

            btn_del = ttk.Button(r1, text="Delete", width=7, command=make_del_cmd(cid))
            btn_del.pack(side="right", padx=2)
            Tooltip(btn_del, "Removes this Fleet Carrier and all of its settings.")

            wh_container = ttk.LabelFrame(card, text=" Discord Webhook Channels ")
            wh_container.pack(fill="x", expand=True, padx=5, pady=5)

            webhook_vars = []

            # Every piece of per-carrier state below is passed in explicitly rather than
            # captured from the enclosing scope. These functions are redefined once per
            # carrier by this loop, so a bare closure would late-bind to the LAST carrier's
            # widgets and list -- making Add/Remove on one card silently edit another card.
            def render_webhook_rows(container=wh_container, vars_list=webhook_vars):
                for w_widget in container.winfo_children():
                    w_widget.destroy()

                for idx, wh_var in enumerate(vars_list):
                    w_row = ttk.Frame(container)
                    w_row.pack(fill="x", expand=True, padx=2, pady=2)

                    ttk.Label(w_row, text=f"Channel {idx+1}:", width=10).pack(side="left", padx=(0, 5))
                    w_ent = ttk.Entry(w_row, textvariable=wh_var, width=65)
                    w_ent.pack(side="left", fill="x", expand=True, padx=(0, 5))
                    Tooltip(w_ent, "A Discord webhook URL. Every message for this carrier is sent to all webhooks listed here.")

                    def make_remove_wh(var_to_remove, c=container, vl=vars_list):
                        def remove_wh():
                            if var_to_remove in vl:
                                vl.remove(var_to_remove)
                            render_webhook_rows(c, vl)
                        return remove_wh

                    btn_remove_wh = ttk.Button(w_row, text="Remove", width=8, command=make_remove_wh(wh_var))
                    btn_remove_wh.pack(side="right")
                    Tooltip(btn_remove_wh, "Removes this webhook from the list.")

                btn_add_wh = ttk.Button(
                    container, text="+ Add New Webhook",
                    command=lambda c=container, vl=vars_list: add_webhook_row("", c, vl)
                )
                btn_add_wh.pack(anchor="w", padx=2, pady=5)
                Tooltip(btn_add_wh, "Add another Discord channel to receive this carrier's messages.")

            def add_webhook_row(url_val="", container=wh_container, vars_list=webhook_vars):
                vars_list.append(StringVar(value=url_val))
                render_webhook_rows(container, vars_list)

            if wh_list:
                for w in wh_list:
                    webhook_vars.append(StringVar(value=w))
            else:
                webhook_vars.append(StringVar(value=""))

            render_webhook_rows()

            OWNER_ONLY_TEST_KEYS = ("jump_scheduled", "jump_cancelled", "jump_complete", "carrier_sell_order", "carrier_buy_order")

            def run_single_test(embed_key, name_var, id_var, wh_list_vars, inara_var, owner_var, lbl):
                lbl.pack(fill="x", padx=10, pady=(2, 5))

                if embed_key in OWNER_ONLY_TEST_KEYS:
                    configured_owner = owner_var.get().strip()
                    active_cmdr_check = (cmdr or "").strip()
                    if not configured_owner or active_cmdr_check.upper() != configured_owner.upper():
                        lbl.config(
                            text=f"Skipped ({embed_key}): this is a Carrier Owner Only message. It won't send unless Fetch ID has confirmed you as the owner.",
                            foreground="orange"
                        )
                        return False

                lbl.config(text=f"Sending {embed_key} test...", foreground="blue")

                urls = [var.get().strip() for var in wh_list_vars if var.get().strip()]
                c_display = f"{name_var.get()} ({id_var.get()})" if name_var.get() else f"Fleet Carrier ({id_var.get()})"
                active_cmdr = cmdr or "CMDR Commander"

                embed = generate_embed_from_config(embed_key, active_cmdr, c_display)
                ok, msg = broadcast_surveillance_embed(
                    urls, embed, sender_name=name_var.get() or "Fleet Carrier", inara_url=inara_var.get()
                )
                if ok:
                    lbl.config(text=f"Success ({embed_key})! {msg}", foreground="green")
                else:
                    lbl.config(text=f"Error ({embed_key}): {msg}", foreground="red")
                return ok

            test_btn_tip = "Sends a sample version of this message to the webhook(s) above, so you can preview the formatting."
            owner_test_btn_tip = "Carrier Owner Only. Sends only if Fetch ID confirmed you as owner and Elite Dangerous is running as that CMDR — otherwise it's skipped, matching real behavior."

            r_btn_owner_label = ttk.Frame(card)
            r_btn_owner_label.pack(fill="x", expand=True, padx=5, pady=(4, 0))
            lbl_owner_tests = ttk.Label(r_btn_owner_label, text="Owner-Only Tests (requires Elite Dangerous running):", font=("Helvetica", 8, "bold"))
            lbl_owner_tests.pack(side="left")
            Tooltip(lbl_owner_tests, "These buttons only send if Fetch ID has confirmed you as this carrier's owner AND Elite Dangerous is currently running with that commander logged in.")

            r_btn1 = ttk.Frame(card)
            r_btn1.pack(fill="x", expand=True, padx=5, pady=(0, 2))

            btn_jump_sched = ttk.Button(r_btn1, text="Jump Scheduled", width=14, command=lambda nv=v_name, iv=v_id, wvs=webhook_vars, inv=v_inara, ov=v_owner, sl=status_lbl: run_single_test("jump_scheduled", nv, iv, wvs, inv, ov, sl))
            btn_jump_sched.pack(side="left", padx=2)
            Tooltip(btn_jump_sched, owner_test_btn_tip)

            btn_jump_cancel = ttk.Button(r_btn1, text="Jump Cancelled", width=14, command=lambda nv=v_name, iv=v_id, wvs=webhook_vars, inv=v_inara, ov=v_owner, sl=status_lbl: run_single_test("jump_cancelled", nv, iv, wvs, inv, ov, sl))
            btn_jump_cancel.pack(side="left", padx=2)
            Tooltip(btn_jump_cancel, owner_test_btn_tip)

            btn_jump_complete = ttk.Button(r_btn1, text="Jump Complete", width=14, command=lambda nv=v_name, iv=v_id, wvs=webhook_vars, inv=v_inara, ov=v_owner, sl=status_lbl: run_single_test("jump_complete", nv, iv, wvs, inv, ov, sl))
            btn_jump_complete.pack(side="left", padx=2)
            Tooltip(btn_jump_complete, owner_test_btn_tip)

            btn_sell_order = ttk.Button(r_btn1, text="Sell Order", width=14, command=lambda nv=v_name, iv=v_id, wvs=webhook_vars, inv=v_inara, ov=v_owner, sl=status_lbl: run_single_test("carrier_sell_order", nv, iv, wvs, inv, ov, sl))
            btn_sell_order.pack(side="left", padx=2)
            Tooltip(btn_sell_order, owner_test_btn_tip)

            btn_buy_order = ttk.Button(r_btn1, text="Buy Order", width=14, command=lambda nv=v_name, iv=v_id, wvs=webhook_vars, inv=v_inara, ov=v_owner, sl=status_lbl: run_single_test("carrier_buy_order", nv, iv, wvs, inv, ov, sl))
            btn_buy_order.pack(side="left", padx=2)
            Tooltip(btn_buy_order, owner_test_btn_tip)

            r_btn_any_label = ttk.Frame(card)
            r_btn_any_label.pack(fill="x", expand=True, padx=5, pady=(2, 0))
            ttk.Label(r_btn_any_label, text="Any Commander Tests:", font=("Helvetica", 8, "bold")).pack(side="left")

            r_btn2 = ttk.Frame(card)
            r_btn2.pack(fill="x", expand=True, padx=5, pady=(0, 4))

            btn_tritium = ttk.Button(r_btn2, text="Tritium Deposited", width=14, command=lambda nv=v_name, iv=v_id, wvs=webhook_vars, inv=v_inara, ov=v_owner, sl=status_lbl: run_single_test("tritium_deposited", nv, iv, wvs, inv, ov, sl))
            btn_tritium.pack(side="left", padx=2)
            Tooltip(btn_tritium, test_btn_tip)

            btn_trade_sale = ttk.Button(r_btn2, text="Trade Sale", width=14, command=lambda nv=v_name, iv=v_id, wvs=webhook_vars, inv=v_inara, ov=v_owner, sl=status_lbl: run_single_test("trade_sale", nv, iv, wvs, inv, ov, sl))
            btn_trade_sale.pack(side="left", padx=2)
            Tooltip(btn_trade_sale, test_btn_tip)

            btn_trade_purchase = ttk.Button(r_btn2, text="Trade Purchase", width=14, command=lambda nv=v_name, iv=v_id, wvs=webhook_vars, inv=v_inara, ov=v_owner, sl=status_lbl: run_single_test("trade_purchase", nv, iv, wvs, inv, ov, sl))
            btn_trade_purchase.pack(side="left", padx=2)
            Tooltip(btn_trade_purchase, test_btn_tip)

            btn_cartographics = ttk.Button(r_btn2, text="Cartographics", width=14, command=lambda nv=v_name, iv=v_id, wvs=webhook_vars, inv=v_inara, ov=v_owner, sl=status_lbl: run_single_test("cartographics", nv, iv, wvs, inv, ov, sl))
            btn_cartographics.pack(side="left", padx=2)
            Tooltip(btn_cartographics, test_btn_tip)

            btn_exobiology = ttk.Button(r_btn2, text="Exobiology", width=14, command=lambda nv=v_name, iv=v_id, wvs=webhook_vars, inv=v_inara, ov=v_owner, sl=status_lbl: run_single_test("exobiology", nv, iv, wvs, inv, ov, sl))
            btn_exobiology.pack(side="left", padx=2)
            Tooltip(btn_exobiology, test_btn_tip)

            carrier_rows.append({
                "v_id": v_id,
                "v_num_id": v_num_id,
                "v_name": v_name,
                "webhook_vars": webhook_vars,
                "v_inara": v_inara,
                "v_owner": v_owner
            })
            card_idx += 1

    render_carrier_cards()
    carriers_canvas.update_idletasks()
    _size_viewport()
    carriers_canvas.yview_moveto(0)

    def add_new_carrier():
        # Find an unused placeholder key. Using len()+1 alone could collide with an
        # existing NEWn card after an earlier card was deleted, silently replacing it.
        idx = len(carriers_dict) + 1
        new_key = f"NEW{idx}"
        while new_key in carriers_dict:
            idx += 1
            new_key = f"NEW{idx}"
        carriers_dict[new_key] = {"name": "New Fleet Carrier", "numeric_id": "", "webhooks": [""], "inara_url": "", "owner_cmdr": ""}
        render_carrier_cards()

    btn_add = ttk.Button(frame, text="+ Add Fleet Carrier", command=add_new_carrier)
    btn_add.grid(row=3, column=0, sticky="w", padx=10, pady=10)
    Tooltip(btn_add, "Add a new Fleet Carrier to track.")

    frame.enabled_var = enabled_var
    frame.carrier_rows = carrier_rows
    prefs_changed.frame = frame

    return frame


def prefs_changed(cmdr, is_beta):
    """Saves settings when user clicks Apply or OK in EDMC."""
    config = load_config()
    frame = getattr(prefs_changed, "frame", None)

    if not frame:
        return

    surveillance_enabled = getattr(frame, "enabled_var", BooleanVar()).get()
    carrier_rows = getattr(frame, "carrier_rows", [])

    updated_carriers = {}

    for row in carrier_rows:
        cid = row["v_id"].get().strip().upper()
        cnum_id = row["v_num_id"].get().strip()
        cname = row["v_name"].get().strip()
        cinara = row["v_inara"].get().strip()
        cowner = row["v_owner"].get().strip()

        wh_list = [var.get().strip() for var in row["webhook_vars"] if var.get().strip()]

        # "NEWn" is the placeholder key given to a freshly added card. A real Elite
        # Dangerous callsign is always in XXX-XXX form, so a row still carrying the
        # placeholder means no Callsign was ever entered -- don't save it as a carrier.
        if cid and re.fullmatch(r"NEW\d+", cid):
            print(f"[CarrierNavComms] Skipping unconfigured Fleet Carrier card '{cid}' (no Callsign entered).")
            continue

        if cid:
            updated_carriers[cid] = {
                "name": cname if cname else f"Carrier {cid}",
                "numeric_id": cnum_id,
                "webhooks": wh_list,
                "inara_url": cinara,
                "owner_cmdr": cowner
            }

    config["carrier_surveillance"] = {
        "enabled": surveillance_enabled,
        "carriers": updated_carriers
    }
    save_config(config)


# ---------------------------------------------------------------------------
# ED Journal Event Processing
# ---------------------------------------------------------------------------
def journal_entry(cmdr, is_beta, system, station, entry, state):
    """Processes real-time journal events from Elite Dangerous."""
    global current_system, current_carrier_name, current_station_name, current_carrier_id, current_market_id

    event = entry.get("event")
    if not event:
        return

    if event == "Undocked":
        current_carrier_id = ""
        current_station_name = ""
        current_carrier_name = ""
        current_market_id = ""
        print("[CarrierNavComms] Player undocked; cleared active dock state.")
        return

    if event == "Docked":
        current_market_id = str(entry.get("MarketID") or "").strip()
    elif event in ("Location", "CarrierJump"):
        # A session that STARTS docked writes Location (Docked true) and no Docked event;
        # a carrier jump while aboard writes CarrierJump the same way.
        if entry.get("Docked"):
            docked_market_id = str(entry.get("MarketID") or "").strip()
            if docked_market_id:
                current_market_id = docked_market_id
                if entry.get("StationName"):
                    current_station_name = entry.get("StationName")
        elif event == "Location":
            current_market_id = ""

    # First-discovery/first-mapped tally bookkeeping. This runs unconditionally, regardless
    # of surveillance settings or carrier matching, because Universal Cartographics resets
    # the underlying game data on ANY sale -- whether at a Fleet Carrier or a regular
    # station -- so the tally has to track that too or it'll drift out of sync.
    first_discoveries_this_sale = pending_first_discoveries
    first_mapped_this_sale = pending_first_mapped
    if event in ("Scan", "SAAScanComplete", "Died", "SellExplorationData", "MultiSellExplorationData"):
        apply_exploration_event(entry)

    # Scan/SAAScanComplete fire hundreds of times per system honk and contribute nothing
    # beyond the tally above (no station, callsign, or system fields we track), so stop
    # here instead of re-reading and re-parsing config.json for every scanned body --
    # that file I/O is what would be felt on a lower-end machine while exploring.
    if event in ("Scan", "SAAScanComplete"):
        return

    config = load_config()
    surveillance = config.get("carrier_surveillance", {})
    if not surveillance.get("enabled", True):
        return

    carriers_dict = surveillance.get("carriers", {})
    if not carriers_dict:
        return

    # Catch CarrierStats directly during live session. This only ever appears in the owning
    # commander's own journal, so the live 'cmdr' value here is a confident owner identification.
    if event == "CarrierStats":
        c_callsign = entry.get("Callsign", "").strip().upper()
        c_num_id = str(entry.get("CarrierID", "") or "").strip()
        if c_callsign in carriers_dict and c_num_id:
            cdata = carriers_dict[c_callsign]
            changed = False
            if str(cdata.get("numeric_id", "")) != c_num_id:
                cdata["numeric_id"] = c_num_id
                changed = True
                print(f"[CarrierNavComms] Live paired Callsign '{c_callsign}' to Numeric ID '{c_num_id}'.")
            if cmdr and cdata.get("owner_cmdr", "").strip().upper() != cmdr.strip().upper():
                cdata["owner_cmdr"] = cmdr.strip()
                changed = True
                print(f"[CarrierNavComms] Live confirmed CMDR '{cmdr}' as owner of Callsign '{c_callsign}'.")
            if changed:
                save_config(config)

    # Catch CarrierLocation directly during live session. This fires for every carrier
    # jump regardless of whether the player is aboard, so it's the fallback signal for
    # "Jump Complete" when the real CarrierJump event (owner-only, requires being docked
    # at the time) never shows up. It also fires ~1 minute *before* CarrierJump even when
    # the owner is aboard, so it never fires the fallback immediately -- it only starts a
    # short timer, which the real CarrierJump event (handled further below) cancels.
    if event == "CarrierLocation" and entry.get("CarrierType") == "FleetCarrier":
        loc_carrier_id = str(entry.get("CarrierID", "") or "").strip()
        loc_system = (entry.get("StarSystem", "") or "").strip()
        if loc_carrier_id and loc_system:
            for target_id, cdata in carriers_dict.items():
                if not isinstance(cdata, dict):
                    continue
                if str(cdata.get("numeric_id", "")).strip() != loc_carrier_id:
                    continue

                prior_system = carrier_current_system.get(target_id)
                if prior_system and prior_system.upper() != loc_system.upper():
                    carrier_previous_system[target_id] = prior_system
                carrier_current_system[target_id] = loc_system

                with pending_jumps_lock:
                    pending = pending_jumps.get(target_id)
                    if pending and pending.get("timer") is None and pending["destination"].upper() == loc_system.upper():
                        def fire_fallback(key=target_id, p=pending, arrived_system=loc_system):
                            embed = generate_embed_from_config(
                                "jump_complete_remote", p["cmdr"], p["display_name"],
                                from_system=carrier_previous_system.get(key) or "Unknown",
                                destination=arrived_system
                            )
                            broadcast_surveillance_embed(p["webhooks"], embed, sender_name=p["display_name"], inara_url=p["inara_url"])
                            print(f"[CarrierNavComms] Sent fallback Jump Complete for '{key}' (CarrierJump event never arrived).")
                            with pending_jumps_lock:
                                pending_jumps.pop(key, None)

                        t = threading.Timer(JUMP_FALLBACK_DELAY_SECONDS, fire_fallback)
                        t.daemon = True
                        pending["timer"] = t
                        t.start()
                break

    event_callsign = entry.get("Callsign", "")
    event_station = entry.get("StationName") or station or ""
    event_carrier_name = entry.get("Name", "")
    event_market_id = str(entry.get("MarketID") or entry.get("CarrierID") or "").strip()

    if event_callsign:
        current_carrier_id = event_callsign
    if event_station:
        current_station_name = event_station
    if event_carrier_name and "Carrier" in event:
        current_carrier_name = event_carrier_name

    if event in ["Location", "FSDJump", "CarrierJump"]:
        star_sys = entry.get("StarSystem")
        if star_sys:
            current_system = star_sys

    relevant_events = [
        "CarrierJumpRequest", "CarrierJumpCancelled", "CarrierJump",
        "CarrierDepositFuel", "CarrierTradeOrder", "MarketSell", "MarketBuy",
        "SellExplorationData", "MultiSellExplorationData",
        "SellMicroData", "SellOrganics", "SellOrganicData"
    ]

    if event not in relevant_events:
        return

    # Most of these events carry no MarketID (SellOrganicData is the exception and
    # does), so use the event's own MarketID when present and fall back to the
    # actively-tracked dock MarketID otherwise.
    no_market_id_events = [
        "SellExplorationData", "MultiSellExplorationData",
        "SellMicroData", "SellOrganics", "SellOrganicData"
    ]
    if event in no_market_id_events:
        event_market_id = str(entry.get("MarketID") or "").strip() or current_market_id

    # Events that must match a carrier by exact numeric ID only. Name/callsign text
    # matching can go stale between dock state updates (e.g. EDMC restarted while
    # already docked, so no Undocked ever cleared it), which caused activity at
    # unrelated stations to be reported as carrier activity. Every event listed here
    # always has a reliable numeric ID available, so the text fallback buys nothing.
    numeric_only_events = no_market_id_events + ["MarketSell", "MarketBuy"]

    print(f"[CarrierNavComms] Processing event '{event}' (Market/Carrier ID: '{event_market_id}')")

    search_sources = [
        current_carrier_id,
        current_station_name,
        current_carrier_name,
        event_callsign,
        event_station,
        event_carrier_name
    ]
    combined_search_text = " ".join([s.strip().upper() for s in search_sources if s]).strip()

    matched_carrier_key = None
    display_carrier_name = ""
    matched_inara_url = ""
    matched_owner_cmdr = ""

    for target_id, cdata in carriers_dict.items():
        if not target_id:
            continue

        cfg_id = target_id.strip().upper()
        cfg_name = (cdata.get("name", "") if isinstance(cdata, dict) else "").strip().upper()
        cfg_num_id = str(cdata.get("numeric_id", "") if isinstance(cdata, dict) else "").strip()

        num_matched = cfg_num_id and event_market_id and (cfg_num_id == event_market_id)
        id_matched = event not in numeric_only_events and cfg_id and (cfg_id in combined_search_text)
        name_matched = event not in numeric_only_events and cfg_name and (cfg_name in combined_search_text)

        if num_matched or id_matched or name_matched:
            matched_carrier_key = target_id
            saved_name = cdata.get("name", "") if isinstance(cdata, dict) else ""
            display_carrier_name = f"{saved_name} ({target_id})" if saved_name else f"Fleet Carrier ({target_id})"
            matched_inara_url = cdata.get("inara_url", "") if isinstance(cdata, dict) else ""
            matched_owner_cmdr = (cdata.get("owner_cmdr", "") if isinstance(cdata, dict) else "").strip()

            if event_market_id and not cfg_num_id:
                cdata["numeric_id"] = event_market_id
                save_config(config)
                print(f"[CarrierNavComms] Auto-populated numeric ID '{event_market_id}' for '{target_id}'")
            break

    if not matched_carrier_key:
        print(f"[CarrierNavComms] Skipping event '{event}': Event ID '{event_market_id}' / location '{combined_search_text}' does not match any configured carrier.")
        return

    carrier_obj = carriers_dict.get(matched_carrier_key, {})
    raw_wh = carrier_obj.get("webhooks", []) if isinstance(carrier_obj, dict) else carrier_obj
    if isinstance(raw_wh, list):
        carrier_wh_list = [str(u).strip() for u in raw_wh if str(u).strip()]
    elif isinstance(raw_wh, str) and raw_wh:
        carrier_wh_list = [u.strip() for u in raw_wh.split(",") if u.strip()]
    else:
        carrier_wh_list = []

    if not carrier_wh_list:
        print(f"[CarrierNavComms] Warning: No webhooks set for carrier '{matched_carrier_key}'")
        return

    owner_only_events = ["CarrierJumpRequest", "CarrierJumpCancelled", "CarrierJump", "CarrierTradeOrder"]
    if event in owner_only_events:
        if not matched_owner_cmdr:
            print(f"[CarrierNavComms] Skipping event '{event}': No Owner Commander Name configured for '{matched_carrier_key}'. Set it (or use Fetch ID) to enable this message.")
            return
        if not cmdr or cmdr.strip().upper() != matched_owner_cmdr.upper():
            print(f"[CarrierNavComms] Skipping event '{event}': CMDR '{cmdr}' is not the configured owner ('{matched_owner_cmdr}') of '{matched_carrier_key}'.")
            return

    # 1. Carrier Jump Scheduled
    if event == "CarrierJumpRequest":
        departure_time = entry.get("DepartureTime")
        jump_ts = int(time.time()) + 900
        if departure_time:
            try:
                dt = datetime.strptime(departure_time, "%Y-%m-%dT%H:%M:%SZ")
                jump_ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
            except ValueError:
                pass

        # The carrier's own system, not the player's. A jump can be scheduled remotely
        # from the ship's right-hand panel, in which case the player may be nowhere near
        # the carrier. "CarrierJumpRequest" itself only carries the destination.
        jump_from_system = carrier_current_system.get(matched_carrier_key) or "Unknown"
        embed = generate_embed_from_config(
            "jump_scheduled", cmdr, display_carrier_name,
            from_system=jump_from_system,
            destination=entry.get("SystemName", "Unknown"),
            body=entry.get("Body", "Space"),
            jump_timestamp=jump_ts
        )
        broadcast_surveillance_embed(carrier_wh_list, embed, sender_name=display_carrier_name, inara_url=matched_inara_url)

        clear_pending_jump(matched_carrier_key)
        with pending_jumps_lock:
            pending_jumps[matched_carrier_key] = {
                "destination": entry.get("SystemName", ""),
                "cmdr": cmdr,
                "display_name": display_carrier_name,
                "inara_url": matched_inara_url,
                "webhooks": carrier_wh_list,
                "timer": None
            }

    # 2. Carrier Jump Cancelled
    elif event == "CarrierJumpCancelled":
        embed = generate_embed_from_config(
            "jump_cancelled", cmdr, display_carrier_name,
            destination=entry.get("SystemName", "Unknown"),
            current_system=carrier_current_system.get(matched_carrier_key) or system or current_system
        )
        broadcast_surveillance_embed(carrier_wh_list, embed, sender_name=display_carrier_name, inara_url=matched_inara_url)
        clear_pending_jump(matched_carrier_key)

    # 3. Carrier Jump Complete
    elif event == "CarrierJump":
        embed = generate_embed_from_config(
            "jump_complete", cmdr, display_carrier_name,
            from_system=carrier_previous_system.get(matched_carrier_key) or "Unknown",
            destination=entry.get("StarSystem", system or "Unknown System"),
            body=entry.get("Body", "Space")
        )
        broadcast_surveillance_embed(carrier_wh_list, embed, sender_name=display_carrier_name, inara_url=matched_inara_url)
        clear_pending_jump(matched_carrier_key)

    # 4. Tritium Deposited
    elif event == "CarrierDepositFuel":
        amount = entry.get("Amount", 0)
        embed = generate_embed_from_config(
            "tritium_deposited", cmdr, display_carrier_name,
            quantity=f"{amount:,}"
        )
        broadcast_surveillance_embed(carrier_wh_list, embed, sender_name=display_carrier_name, inara_url=matched_inara_url)

    # 5. Market Order Set (Sell or Buy)
    elif event == "CarrierTradeOrder":
        if entry.get("CancelTrade"):
            return

        item = entry.get("Commodity_Localised", entry.get("Commodity", "Commodities"))
        price = entry.get("Price", 0)

        order_ts = int(time.time())
        raw_timestamp = entry.get("timestamp")
        if raw_timestamp:
            try:
                dt = datetime.strptime(raw_timestamp, "%Y-%m-%dT%H:%M:%SZ")
                order_ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
            except ValueError:
                pass

        if "SaleOrder" in entry:
            quantity = entry.get("SaleOrder", 0)
            embed = generate_embed_from_config(
                "carrier_sell_order", cmdr, display_carrier_name,
                item=item, price=f"{price:,}", quantity=f"{quantity:,}", order_timestamp=order_ts
            )
        elif "PurchaseOrder" in entry:
            quantity = entry.get("PurchaseOrder", 0)
            embed = generate_embed_from_config(
                "carrier_buy_order", cmdr, display_carrier_name,
                item=item, price=f"{price:,}", quantity=f"{quantity:,}", order_timestamp=order_ts
            )
        else:
            return

        broadcast_surveillance_embed(carrier_wh_list, embed, sender_name=display_carrier_name, inara_url=matched_inara_url)

    # 6. Market Sales
    elif event == "MarketSell":
        item = entry.get("Type_Localised", entry.get("Type", "Commodities"))
        count = entry.get("Count", 0)
        total_price = entry.get("TotalSale", 0)
        embed = generate_embed_from_config(
            "trade_sale", cmdr, display_carrier_name,
            quantity=f"{count:,}", item=item, total_price=f"{total_price:,}"
        )
        broadcast_surveillance_embed(carrier_wh_list, embed, sender_name=display_carrier_name, inara_url=matched_inara_url)

    # 7. Market Purchases
    elif event == "MarketBuy":
        item = entry.get("Type_Localised", entry.get("Type", "Commodities"))
        count = entry.get("Count", 0)
        total_price = entry.get("TotalCost", 0)
        embed = generate_embed_from_config(
            "trade_purchase", cmdr, display_carrier_name,
            quantity=f"{count:,}", item=item, total_price=f"{total_price:,}"
        )
        broadcast_surveillance_embed(carrier_wh_list, embed, sender_name=display_carrier_name, inara_url=matched_inara_url)

    # 8. Exploration Data
    elif event in ["SellExplorationData", "MultiSellExplorationData"]:
        total_earned = entry.get("TotalEarnings", 0)
        discovered_list = entry.get("Discovered", [])
        systems_count = len(discovered_list) if isinstance(discovered_list, list) else 0
        bonus = entry.get("Bonus", 0)
        base_value = entry.get("BaseValue", 0)
        data_note = ""

        # Elite occasionally writes a partially-zeroed sale event: an empty "Discovered"
        # list with "TotalEarnings" and "Bonus" both 0, while "BaseValue" still holds the
        # real figure. Seen once in 83 sales (2026-09-07), where the credits actually paid
        # were BaseValue plus a bonus the event never recorded -- reporting it verbatim
        # announced a 0 CR payout for a sale worth 5.7 million. Only recover when the event
        # is structurally broken like this: a legitimately zero payout, where carrier tax
        # took the lot, still lists the systems it sold.
        if not total_earned and not systems_count and base_value:
            total_earned_str = f"~{base_value:,}"
            systems_str = "Unknown"
            bonus_str = "Unknown"
            data_note = ("\n\n-# \u26a0\ufe0f Elite logged this sale incompletely. The payout is "
                         "estimated from its base value, and the system and bonus figures "
                         "were not recorded.")
            print(f"[CarrierNavComms] Sale event had no TotalEarnings; estimated payout from BaseValue ({base_value}).")
        else:
            total_earned_str = f"{total_earned:,}"
            systems_str = f"{systems_count:,}"
            bonus_str = f"{bonus:,}"

        # first_discoveries_this_sale / first_mapped_this_sale are the exact counts tallied
        # live from "Scan" (WasDiscovered) and "SAAScanComplete" events since the last sale,
        # captured just before this same event reset the running tally back to zero above.
        embed = generate_embed_from_config(
            "cartographics", cmdr, display_carrier_name,
            total_earned=total_earned_str, systems=systems_str, bonus=bonus_str,
            first_discoveries=f"{first_discoveries_this_sale:,}", first_mapped=f"{first_mapped_this_sale:,}",
            data_note=data_note
        )
        broadcast_surveillance_embed(carrier_wh_list, embed, sender_name=display_carrier_name, inara_url=matched_inara_url)

# 9. Exobiology Data
    elif event in ["SellMicroData", "SellOrganics", "SellOrganicData"]:
        bio_data = entry.get("BioData", [])
        total_earned = entry.get("TotalEarnings", entry.get("Price", 0))
        first_discoveries = 0
        
        if isinstance(bio_data, list):
            calculated_total = 0
            for bio in bio_data:
                # Sum base value and bonus if available
                value = bio.get("Value", bio.get("BaseProfit", 0))
                bonus = bio.get("Bonus", 0)
                calculated_total += (value + bonus)

                if bio.get("FirstDiscovered", False) or bonus > 0:
                    first_discoveries += 1

            if total_earned == 0:
                total_earned = calculated_total

        embed = generate_embed_from_config(
            "exobiology", cmdr, display_carrier_name,
            total_earned=f"{total_earned:,}", first_discoveries=f"{first_discoveries:,}"
        )
        broadcast_surveillance_embed(carrier_wh_list, embed, sender_name=display_carrier_name, inara_url=matched_inara_url)