from flask import Flask, render_template, jsonify, request, send_file
from pathlib import Path
from datetime import datetime, date
import json, io, csv, os, urllib.request, urllib.parse, urllib.error

APP_DIR = Path(__file__).resolve().parent

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or ""

app = Flask(__name__, template_folder="templates", static_folder="static")

STATUTS = ["A créer", "En cours", "Caisse prête", "Annulée"]
TYPES_CAISSE = ["PLEINE CP TYPE 15", "PLEINE CP TYPE 16", "PLEINE BOIS TYPE 15", "PLEINE BOIS TYPE 16"]
DEFAULT_PRICES = {
    "cp_m2": 45.0,
    "barres_ml": 4.0,
    "chevrons_ml": 6.0,
    "consommables": 15.0,
    "taux_horaire": 45.0,
    "heures": 2.0,
    "frais_generaux": 10.0,
    "marge": 20.0,
}

CAISSE_FIELDS = [
    "id", "statut", "numero_dossier", "numero_colis", "client", "reference",
    "destination", "charge_projet", "type_caisse", "longueur", "largeur",
    "hauteur", "poids_net", "delai_demande", "date_prevue", "observations",
    "caissier", "atelier", "commentaire_atelier", "prix_achat",
    "prix_cession", "created_at", "updated_at"
]


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def today_iso():
    return date.today().isoformat()


def _as_text(value, default=""):
    if value is None:
        return default
    return str(value)


def num(v):
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return 0.0


def r1(v):
    return round(v, 1)


def supabase_rest_request(method, table, query="", payload=None, prefer=None):
    """Appel Supabase REST sans SDK, comme ESI Tickets."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Variables Render manquantes : SUPABASE_URL ou SUPABASE_SERVICE_KEY")

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if query:
        url += "?" + query.lstrip("?")

    data = None
    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer
    elif method.upper() in ("POST", "PATCH", "DELETE"):
        headers["Prefer"] = "return=representation"

    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if not body:
                return None
            return json.loads(body)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        print(f"[SUPABASE ERROR] {method} {url} -> HTTP {e.code} {e.reason} {body}")
        raise RuntimeError(f"Erreur Supabase HTTP {e.code}: {body or e.reason}")


def clean_caisse_row(caisse):
    """Garde uniquement les colonnes connues de la table Supabase."""
    row = {}
    for key in CAISSE_FIELDS:
        if key in caisse:
            row[key] = _as_text(caisse.get(key))
    return row


def normalize_caisse(row):
    """Retour compatible avec le frontend existant."""
    c = {k: (row.get(k) if row.get(k) is not None else "") for k in CAISSE_FIELDS}
    c.setdefault("statut", "A créer")
    c.setdefault("atelier", "Secobois")
    return c


def list_caisses():
    rows = supabase_rest_request(
        "GET",
        "caisses",
        "select=*&order=created_at.desc"
    ) or []
    return [normalize_caisse(r) for r in rows]


def get_prices():
    try:
        rows = supabase_rest_request(
            "GET",
            "caisserie_settings",
            "select=value&key=eq.prices&limit=1"
        ) or []
        if rows:
            value = rows[0].get("value") or {}
            prices = DEFAULT_PRICES.copy()
            prices.update(value)
            return prices
    except Exception as e:
        print("[SUPABASE SETTINGS] Lecture prix impossible :", e)
    return DEFAULT_PRICES.copy()


def save_prices(prices):
    current = DEFAULT_PRICES.copy()
    current.update({k: num(v) for k, v in prices.items()})
    supabase_rest_request(
        "POST",
        "caisserie_settings",
        "on_conflict=key",
        [{"key": "prices", "value": current}],
        prefer="resolution=merge-duplicates,return=minimal"
    )
    return current


def next_id(prefix="CAI"):
    rows = supabase_rest_request(
        "GET",
        "caisses",
        f"select=id&id=like.{urllib.parse.quote(prefix + '-*', safe='*-')}&order=id.desc&limit=5000"
    ) or []
    nums = []
    for row in rows:
        try:
            nums.append(int(str(row.get("id", "")).split("-")[1]))
        except Exception:
            pass
    return f"{prefix}-{(max(nums) if nums else 0) + 1:03d}"


def find_caisse(caisse_id):
    safe_id = urllib.parse.quote(caisse_id, safe="")
    rows = supabase_rest_request(
        "GET",
        "caisses",
        f"select=*&id=eq.{safe_id}&limit=1"
    ) or []
    if not rows:
        return None
    return normalize_caisse(rows[0])


def insert_caisse(caisse):
    row = clean_caisse_row(caisse)
    result = supabase_rest_request(
        "POST",
        "caisses",
        "on_conflict=id",
        [row],
        prefer="resolution=merge-duplicates,return=representation"
    ) or []
    return normalize_caisse(result[0]) if result else caisse


def update_caisse(caisse_id, updates):
    safe_id = urllib.parse.quote(caisse_id, safe="")
    updates = {k: _as_text(v) for k, v in updates.items() if k in CAISSE_FIELDS and k not in ["id", "created_at"]}
    updates["updated_at"] = now_iso()
    result = supabase_rest_request(
        "PATCH",
        "caisses",
        f"id=eq.{safe_id}",
        updates,
        prefer="return=representation"
    ) or []
    return normalize_caisse(result[0]) if result else find_caisse(caisse_id)


def replace_demo_data(caisses):
    """Remplace les données uniquement pour le bouton de démo."""
    supabase_rest_request("DELETE", "caisses", "id=not.is.null", prefer="return=minimal")
    if caisses:
        supabase_rest_request("POST", "caisses", "", [clean_caisse_row(c) for c in caisses], prefer="return=minimal")


def compute_debit(caisse):
    """Débit issu de la maquette : modèle PLEINE CP TYPE 16 / alias PLEIN CP TYPE 16."""
    type_caisse = (caisse.get("type_caisse") or caisse.get("type_emballage") or "").upper()
    if type_caisse not in ["PLEINE CP TYPE 16", "PLEIN CP TYPE 16"]:
        return {"ok": False, "message": "Débit automatique non paramétré pour ce type de caisse.", "dims_ext": {}, "lignes": []}

    L = num(caisse.get("longueur"))
    W = num(caisse.get("largeur"))
    H = num(caisse.get("hauteur"))
    B4, C4, D4, E4, C5, E5 = 10, 1.5, 4, 1.5, 1, 2.7

    dims_ext = {
        "longueur": r1(L + E4 + E4 + E5 + E5),
        "largeur": r1(W + E4 + E4 + E5 + E5),
        "hauteur": r1(H + E4 + E4 + E5 + B4),
    }
    cover_l = r1(L + E5 + E5 + C5 + C5)
    cover_w = r1(W + E5 + E5 + C5 + C5)
    cote_h = r1(H + C4 + D4)

    lignes = [
        {"famille": "CP", "piece": "PLATEAU", "quantite": 1, "longueur": L, "largeur": W, "epaisseur": C4},
        {"famille": "CP", "piece": "COUVERCLE", "quantite": 1, "longueur": cover_l, "largeur": cover_w, "epaisseur": C5},
        {"famille": "CP", "piece": "COTES", "quantite": 2, "longueur": cover_l, "largeur": cote_h, "epaisseur": C5},
        {"famille": "CP", "piece": "BOUTS", "quantite": 2, "longueur": W, "largeur": cote_h, "epaisseur": C5},
        {"famille": "BARRES", "piece": "SEMELLES", "quantite": 4, "longueur": cover_w, "largeur": 5, "epaisseur": B4},
        {"famille": "BARRES", "piece": "CHEMINS EXT", "quantite": 3, "longueur": L, "largeur": 6, "epaisseur": D4},
        {"famille": "BARRES", "piece": "BARRES L COUV", "quantite": 2, "longueur": cover_l, "largeur": B4, "epaisseur": E5},
        {"famille": "BARRES", "piece": "BARRES L COTES", "quantite": 4, "longueur": cover_l, "largeur": B4, "epaisseur": E5},
        {"famille": "BARRES", "piece": "BARRES L", "quantite": 4, "longueur": L, "largeur": B4, "epaisseur": E5},
        {"famille": "BARRES", "piece": "BARRES H", "quantite": 4, "longueur": r1(cote_h - 20), "largeur": B4, "epaisseur": E5},
    ]
    return {"ok": True, "dims_ext": dims_ext, "lignes": lignes}


def material_totals(caisse):
    debit = compute_debit(caisse)
    totals = {"cp_m2": 0.0, "barres_ml": 0.0, "chevrons_ml": 0.0, "autres": 0.0}
    for l in debit.get("lignes", []):
        famille = (l.get("famille") or "").upper()
        q = num(l.get("quantite"))
        lo = num(l.get("longueur"))
        la = num(l.get("largeur"))
        if famille == "CP":
            totals["cp_m2"] += q * lo * la / 10000
        elif famille == "BARRES":
            totals["barres_ml"] += q * lo / 100
        elif famille == "CHEVRONS":
            totals["chevrons_ml"] += q * lo / 100
        else:
            totals["autres"] += q
    return {k: round(v, 2) for k, v in totals.items()}


def quote(caisse, prices=None):
    prices = prices or get_prices()
    mat = material_totals(caisse)
    cp = mat["cp_m2"] * num(prices.get("cp_m2"))
    barres = mat["barres_ml"] * num(prices.get("barres_ml"))
    chevrons = mat["chevrons_ml"] * num(prices.get("chevrons_ml"))
    consommables = num(prices.get("consommables"))
    mo = num(prices.get("heures")) * num(prices.get("taux_horaire"))
    sous_total = cp + barres + chevrons + consommables + mo
    frais = sous_total * num(prices.get("frais_generaux")) / 100
    revient = sous_total + frais
    marge = revient * num(prices.get("marge")) / 100
    cession = revient + marge
    return {
        "matieres": mat,
        "prix_achat": round(revient, 2),
        "prix_cession": round(cession, 2),
        "detail": {
            "cp": round(cp, 2),
            "barres": round(barres, 2),
            "chevrons": round(chevrons, 2),
            "consommables": round(consommables, 2),
            "main_oeuvre": round(mo, 2),
            "frais": round(frais, 2),
            "marge": round(marge, 2),
        },
    }


@app.route("/")
def accueil():
    return render_template("accueil.html")


@app.route("/emballage")
def emballage():
    return render_template("emballage.html", types=TYPES_CAISSE)


@app.route("/devis")
def devis():
    return render_template("devis.html", types=TYPES_CAISSE)


@app.route("/caisserie")
def caisserie():
    return render_template("caisserie.html")


@app.route("/superviseur")
def superviseur():
    return render_template("superviseur.html")


@app.route("/planning")
def planning():
    return render_template("planning.html")


@app.route("/api/caisses")
def api_list_caisses():
    return jsonify(list_caisses())


@app.route("/api/caisses", methods=["POST"])
def api_create_caisse():
    payload = request.get_json(silent=True) or request.form.to_dict()
    caisse = {
        "id": next_id("CAI"),
        "statut": "A créer",
        "numero_dossier": payload.get("numero_dossier", ""),
        "numero_colis": payload.get("numero_colis", ""),
        "client": payload.get("client", ""),
        "reference": payload.get("reference", ""),
        "destination": payload.get("destination", ""),
        "charge_projet": payload.get("charge_projet", ""),
        "type_caisse": payload.get("type_caisse", "PLEINE CP TYPE 16"),
        "longueur": payload.get("longueur", ""),
        "largeur": payload.get("largeur", ""),
        "hauteur": payload.get("hauteur", ""),
        "poids_net": payload.get("poids_net", ""),
        "delai_demande": payload.get("delai_demande", ""),
        "date_prevue": payload.get("date_prevue", payload.get("delai_demande", "")),
        "observations": payload.get("observations", ""),
        "caissier": payload.get("caissier", ""),
        "atelier": payload.get("atelier", "Secobois"),
        "commentaire_atelier": payload.get("commentaire_atelier", ""),
        "prix_achat": payload.get("prix_achat", ""),
        "prix_cession": payload.get("prix_cession", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    created = insert_caisse(caisse)
    return jsonify({"ok": True, "id": created["id"], "caisse": created})


@app.route("/api/caisses/<caisse_id>", methods=["GET"])
def api_get_caisse(caisse_id):
    caisse = find_caisse(caisse_id)
    if not caisse:
        return jsonify({"error": "Caisse introuvable"}), 404
    return jsonify(caisse)


@app.route("/api/caisses/<caisse_id>", methods=["PUT"])
def api_update_caisse(caisse_id):
    if not find_caisse(caisse_id):
        return jsonify({"error": "Caisse introuvable"}), 404
    payload = request.get_json(silent=True) or {}
    updated = update_caisse(caisse_id, payload)
    return jsonify({"ok": True, "caisse": updated})


@app.route("/api/caisses/<caisse_id>/status", methods=["PATCH"])
def api_status(caisse_id):
    if not find_caisse(caisse_id):
        return jsonify({"error": "Caisse introuvable"}), 404
    statut = (request.get_json(silent=True) or {}).get("statut", "A créer")
    if statut not in STATUTS:
        return jsonify({"error": "Statut invalide"}), 400
    updated = update_caisse(caisse_id, {"statut": statut})
    return jsonify({"ok": True, "caisse": updated})


@app.route("/api/caisses/<caisse_id>/debit")
def api_debit(caisse_id):
    caisse = find_caisse(caisse_id)
    if not caisse:
        return jsonify({"error": "Caisse introuvable"}), 404
    return jsonify(compute_debit(caisse))


@app.route("/api/devis", methods=["POST"])
def api_devis():
    payload = request.get_json(silent=True) or {}
    return jsonify(quote(payload, get_prices()))


@app.route("/api/prices", methods=["GET", "POST"])
def api_prices():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        return jsonify(save_prices(payload))
    return jsonify(get_prices())


@app.route("/api/stats")
def api_stats():
    caisses = list_caisses()
    stats = {
        "total": len(caisses),
        "a_creer": 0,
        "en_cours": 0,
        "pretes": 0,
        "annulees": 0,
        "matieres": {"cp_m2": 0, "barres_ml": 0, "chevrons_ml": 0, "autres": 0},
        "par_type": {},
        "retards": 0,
    }
    today = today_iso()

    for c in caisses:
        st = c.get("statut")
        if st == "A créer":
            stats["a_creer"] += 1
        if st == "En cours":
            stats["en_cours"] += 1
        if st == "Caisse prête":
            stats["pretes"] += 1
        if st == "Annulée":
            stats["annulees"] += 1

        type_label = c.get("type_caisse") or "Non renseigné"
        stats["par_type"][type_label] = stats["par_type"].get(type_label, 0) + 1

        if st == "Caisse prête":
            mt = material_totals(c)
            for k in stats["matieres"]:
                stats["matieres"][k] += mt[k]

        if c.get("delai_demande") and st not in ["Caisse prête", "Annulée"] and c.get("delai_demande") < today:
            stats["retards"] += 1

    stats["matieres"] = {k: round(v, 2) for k, v in stats["matieres"].items()}
    return jsonify(stats)


@app.route("/api/export/csv")
def api_export_csv():
    caisses = list_caisses()
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["ID", "Statut", "Dossier", "Colis", "Client", "Chargé projet", "Type", "Dimensions", "Délai", "Caissier", "Prix achat", "Prix cession"])
    for c in caisses:
        writer.writerow([
            c.get("id"),
            c.get("statut"),
            c.get("numero_dossier"),
            c.get("numero_colis"),
            c.get("client"),
            c.get("charge_projet"),
            c.get("type_caisse"),
            f"{c.get('longueur')} x {c.get('largeur')} x {c.get('hauteur')}",
            c.get("delai_demande"),
            c.get("caissier"),
            c.get("prix_achat"),
            c.get("prix_cession"),
        ])
    mem = io.BytesIO(out.getvalue().encode("utf-8-sig"))
    return send_file(mem, as_attachment=True, download_name="esi_caisserie.csv", mimetype="text/csv")


@app.route("/api/demo", methods=["POST"])
def api_demo():
    examples = [
        {"numero_dossier": "D-2026-001", "numero_colis": "1", "client": "Musée Exemple", "charge_projet": "Martin", "type_caisse": "PLEINE CP TYPE 16", "longueur": "120", "largeur": "80", "hauteur": "100", "delai_demande": today_iso(), "statut": "A créer", "atelier": "Secobois"},
        {"numero_dossier": "D-2026-002", "numero_colis": "2", "client": "Galerie Test", "charge_projet": "Julie", "type_caisse": "PLEINE CP TYPE 16", "longueur": "90", "largeur": "60", "hauteur": "45", "delai_demande": today_iso(), "statut": "En cours", "caissier": "Marc", "atelier": "Arckx"},
    ]
    caisses = []
    for i, e in enumerate(examples, 1):
        e.update({
            "id": f"CAI-{i:03d}",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "reference": "",
            "destination": "",
            "poids_net": "",
            "date_prevue": e.get("delai_demande"),
            "observations": "",
            "commentaire_atelier": "",
            "prix_achat": "",
            "prix_cession": "",
        })
        caisses.append(e)
    replace_demo_data(caisses)
    save_prices(DEFAULT_PRICES.copy())
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5051, debug=True)
