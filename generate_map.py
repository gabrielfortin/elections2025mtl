#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_map_with_csv.py

Ajouts récents :
- Districts en contour seulement (transparent)
- Coloration des sections par parti gagnant (poste sélectionnable dans l'UI)
- Sélecteur de poste (dropdown) dans la page
- Watermark en bas à gauche : texte + petites photos (optionnelles)

Arguments utiles :
  --winner-poste 0                Poste initial pour la coloration (ex.: 0 = Mairie)
  --poste-alias poste_alias.json  Mapping {"0":"Mairie de la Ville", ...}
  --wm-text "Texte watermark"     (défaut: "Gabriel Fortin · Nicolas Jolicoeur")
  --wm-img1 chemin.jpg/png        Première petite photo
  --wm-img2 chemin.jpg/png        Deuxième petite photo
"""

import argparse
import json
import re
import base64
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any

import pandas as pd

# Essayer requests (sinon fallback urllib)
try:
    import requests
    HAVE_REQ = True
except Exception:
    HAVE_REQ = False
    import urllib.request

DEFAULT_DISTRICTS_URL = (
    "https://montreal-prod.storage.googleapis.com/resources/fa1f8cfc-cdbf-42fd-9979-32c16b68b5ca/"
    "districts-electoraux-2025.json?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=test-datapusher-delete%40amplus-data.iam.gserviceaccount.com%2F20251111%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20251111T202957Z&X-Goog-Expires=604800&X-Goog-SignedHeaders=host&x-goog-signature=47fbfaff9cedbc69a330a54128ea11bcf181cece74ddeec815c3496564c03d3aa663d0d3fc783e8a8df724b20ff128f981481638e24264b42b5c8aa7688f972712afc7bbbf159c3248ece8c0d9d82eb2e4c54d37e115212323368316190f755fffb8906d450778f93b8b86e8a472798810ef9e6bfc9b0c1e4b8d8c084abb654eac5b991aaa0cd8b00749eff387ecef007addc5a1d11b4200bcd1ffa82dc6edb57a41f8691d2d39786af6db1ba038ae5d9a7341376e8226f4bfeba8438c12905c8225f1903eb89246f05d5e988f8278f696b174aa574926ef86b65f84d3542f13546d8fc86ae9ddd1fe7947cbffa4805ba792be35518f49141a507641ed0335d9"
)

DEFAULT_SECTIONS_URL = (
    "https://montreal-prod.storage.googleapis.com/resources/8b0097ff-5c7b-48b1-8ee1-320d385f820c/"
    "section-vote-2025.json?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=test-datapusher-delete%40amplus-data.iam.gserviceaccount.com%2F20251111%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20251111T203534Z&X-Goog-Expires=604800&X-Goog-SignedHeaders=host&x-goog-signature=901d0968c8746cf9ab6315569651472c743243a55d3c12ec1f530c481d285f33729ef79cee0be5b44cc074dac71ff0c734ff54123d60606aee110b81635907829b4cda1528449b9b398589b540408abcf4581abc8f4d3d4a1686f9bbad60ffae590e43d94e31112a0f6e5632ab15ee9c5d6675c58177f9331c476fb0c02b88c9b5a1ab92aa2fd90c8b1259824092b898c71710f6e3d95110eeda341e0a20172dcdd61771e75f8153c5789fbcb89b39159cec9266cf8c65c3bf9aa16342059fe9273e7e1410a53842ff355a167ead15ab016c32373b9aaf0890859df36c775eb133cb9c304d9f1ecc32722d7d56d0374dbb6c49bf0dbb8f1efc909a04fe3f79eb"
)

# --- Utilitaires I/O ---

def is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")

def fetch_json(path_or_url: str) -> Dict[str, Any]:
    if is_url(path_or_url):
        if HAVE_REQ:
            r = requests.get(path_or_url, timeout=60)
            r.raise_for_status()
            return r.json()
        else:
            with urllib.request.urlopen(path_or_url, timeout=60) as resp:
                data = resp.read().decode("utf-8", errors="ignore")
                return json.loads(data)
    else:
        return json.loads(Path(path_or_url).read_text(encoding="utf-8"))

def img_to_data_uri(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        print(f"⚠️  Image introuvable: {p}")
        return None
    suffix = p.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"

# --- Normalisations ---

def norm_digits(x: Any) -> str:
    """Garde uniquement les chiffres et supprime les zéros de tête."""
    return re.sub(r'\D+', '', str(x)).lstrip('0')

def norm_bureau3(x: Any) -> str:
    """Conserve 3 chiffres (zéro-padding à gauche), sur la fin de la chaîne numérique."""
    s = re.sub(r'\D+', '', str(x))
    return (s[-3:] if s else "").zfill(3)

# --- Construction de l'index des résultats ---

def build_results_index(csv_path: str, only_poste: Optional[List[float]] = None) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    results[(dist_id_norm, bureau_norm)][poste_key_str] = {
        'total_valid': int, 'rejected': int, 'total': int,
        'rows': [ {nom, parti, votes, pct}, ... ] (triés par votes desc)
    }
    """
    df = pd.read_csv(csv_path, dtype={"DistrictID": "Int64", "District": str, "Bureau": str, "Poste": float})

    df["DistrictID_norm"] = df["DistrictID"].apply(norm_digits)
    df["Bureau_norm"]     = df["Bureau"].apply(norm_bureau3)

    if only_poste:
        df = df[df["Poste"].isin(only_poste)]

    results: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for (d, b, p), g in df.groupby(["DistrictID_norm", "Bureau_norm", "Poste"], dropna=False):
        total_valid = int(g["TotalValidVotes"].iloc[0]) if "TotalValidVotes" in g else int(g["Votes"].sum())
        rejected    = int(g["TotalRejectedVotes"].iloc[0]) if "TotalRejectedVotes" in g else 0
        total       = int(g["TotalVotes"].iloc[0]) if "TotalVotes" in g else (total_valid + rejected)

        rows = []
        for _, r in g.iterrows():
            votes = int(r["Votes"])
            pct = (100.0 * votes / total_valid) if total_valid > 0 else 0.0
            rows.append({
                "nom":   str(r["Candidat"]) if pd.notna(r["Candidat"]) else "",
                "parti": str(r.get("Parti", "")) if pd.notna(r.get("Parti", "")) else "",
                "votes": votes,
                "pct":   round(pct, 2),
            })
        rows.sort(key=lambda x: x["votes"], reverse=True)

        pkey = str(int(p)) if float(p).is_integer() else str(p)

        key = (d, b)
        results.setdefault(key, {})
        results[key][pkey] = {
            "total_valid": total_valid,
            "rejected":    rejected,
            "total":       total,
            "rows":        rows
        }

    return results

# --- Heuristiques pour extraire (DistrictID, Bureau) du GeoJSON ---

DISTRICT_KEYS = [
    "DISTRICTID", "DISTRICT_ID", "DISTRICT", "NO_DISTRICT", "ID_DISTRICT",
    "ARRON_DIST", "ARRDIST", "ARR", "ID_ARR", "ID_ARRONDISSEMENT"
]
BUREAU_KEYS = [
    "SECTION", "BUREAU", "NO_SECTION", "NO_BUREAU", "SECT_VOTE", "SECTION_VOTE", "SECTION_ID"
]

def make_html(
    districts_geojson: Dict[str, Any],
    sections_geojson: Dict[str, Any],
    results_index: Dict[Tuple[str, str], Dict[str, Any]],
    out_html: Path,
    only_poste: Optional[List[float]] = None,
    winner_poste_key: str = "0",
    poste_aliases: Optional[Dict[str, str]] = None,
    wm_text: str = "Gabriel Fortin · Nicolas Jolicoeur",
    wm_img1_data_uri: Optional[str] = None,
    wm_img2_data_uri: Optional[str] = None,
) -> None:
    # Sérialiser
    js_districts = json.dumps(districts_geojson, ensure_ascii=False)
    js_sections  = json.dumps(sections_geojson, ensure_ascii=False)

    # Aplatir l’index -> { "dist|bureau": {...} }
    flat: Dict[str, Any] = {}
    for (d, b), postes in results_index.items():
        flat[f"{d}|{b}"] = postes

    js_results = json.dumps(flat, ensure_ascii=False)
    js_only    = json.dumps(only_poste if only_poste else [], ensure_ascii=False)
    js_winner  = json.dumps(winner_poste_key, ensure_ascii=False)
    js_aliases = json.dumps(poste_aliases or {}, ensure_ascii=False)
    js_wm_text = json.dumps(wm_text, ensure_ascii=False)
    js_wm_img1 = json.dumps(wm_img1_data_uri, ensure_ascii=False)
    js_wm_img2 = json.dumps(wm_img2_data_uri, ensure_ascii=False)

    html = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Carte — Résultats 2025 par section de vote</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    html, body, #map {{ height: 100%; margin: 0; padding: 0; }}
    #map {{ width: 100%; height: 100vh; }}
    .legend {{
      background: #fff; line-height: 1.5em; padding: 6px 10px; border-radius: 8px;
      font-size: 14px; box-shadow: 0 0 4px rgba(0,0,0,0.2);
    }}
    .toolbar {{
      position: absolute; top: 10px; left: 10px; z-index: 1000;
      background: #fff; padding: 8px 10px; border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15); font: 14px/1.3 system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
      display: flex; gap: 8px; align-items: center;
    }}
    .toolbar label {{ font-weight: 600; }}
    .popup-title {{ font-weight: 600; margin-bottom: 6px; }}
    .poste-title {{ margin-top:8px; font-weight:600; }}
    .popup-table {{ border-collapse: collapse; width: 100%; }}
    .popup-table th, .popup-table td {{
      border-bottom: 1px solid #eee; padding: 4px 6px; text-align: left; font-size: 13px;
    }}
    /* Watermark bottom-left */
    .watermark {{
      position: absolute; left: 10px; bottom: 10px; z-index: 1000;
      background: rgba(255,255,255,0.88); backdrop-filter: blur(2px);
      border-radius: 9999px; padding: 6px 10px; display: inline-flex; align-items: center; gap: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15); font: 12px/1.2 system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
      color: #111; transition: opacity .2s ease;
    }}
    .watermark:hover {{ opacity: 1; }}
    .wm-avatars {{ display: inline-flex; align-items: center; gap: 6px; }}
    .wm-avatar {{
      width: 24px; height: 24px; border-radius: 50%; object-fit: cover;
      box-shadow: 0 0 0 1px rgba(0,0,0,0.1);
    }}
    @media (max-width: 560px) {{
      .watermark {{ padding: 5px 8px; font-size: 11px; gap: 6px; }}
      .wm-avatar {{ width: 20px; height: 20px; }}
    }}
  </style>
</head>
<body>
<div id="map"></div>
<div class="toolbar">
  <label for="posteSelect">Colorer par&nbsp;:</label>
  <select id="posteSelect"></select>
</div>
<!-- Watermark -->
<div id="wm" class="watermark" title="Carte des résultats 2025">
  <div class="wm-avatars" id="wmAvatars"></div>
  <div class="wm-text" id="wmText"></div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  // Données embarquées
  const DATA_DISTRICTS = {js_districts};
  const DATA_SECTIONS  = {js_sections};
  const RESULTS_INDEX  = {js_results};
  const ONLY_POSTE     = {js_only};
  let   WINNER_POSTE_KEY = {js_winner};
  const POSTE_ALIASES  = {js_aliases};

  // Watermark data
  const WM_TEXT  = {js_wm_text};
  const WM_IMG1  = {js_wm_img1};
  const WM_IMG2  = {js_wm_img2};

  // Init watermark
  (function initWatermark() {{
    const t = document.getElementById('wmText');
    const a = document.getElementById('wmAvatars');
    t.textContent = WM_TEXT || "Gabriel Fortin · Nicolas Jolicoeur";
    if (WM_IMG1) {{
      const img1 = document.createElement('img');
      img1.src = WM_IMG1; img1.alt = "Photo 1"; img1.className = "wm-avatar";
      a.appendChild(img1);
    }}
    if (WM_IMG2) {{
      const img2 = document.createElement('img');
      img2.src = WM_IMG2; img2.alt = "Photo 2"; img2.className = "wm-avatar";
      a.appendChild(img2);
    }}
  }})();

  function normDigits(x) {{ return String(x ?? '').replace(/\\D+/g,'').replace(/^0+/, ''); }}
  function normBureau3(x) {{
    const s = String(x ?? '').replace(/\\D+/g,'');
    return (s.slice(-3) || '').padStart(3,'0');
  }}

  const DISTRICT_KEYS = {json.dumps(DISTRICT_KEYS)};
  const BUREAU_KEYS   = {json.dumps(BUREAU_KEYS)};

  function extractDistBureau(props) {{
    let dist = null, bure = null;
    for (const k of DISTRICT_KEYS) {{
      if (props[k] != null) {{ dist = normDigits(props[k]); break; }}
    }}
    for (const k of BUREAU_KEYS) {{
      if (props[k] != null) {{ bure = normBureau3(props[k]); break; }}
    }}
    if (dist && bure) return [dist, bure];

    const digits = [];
    for (const k in props) {{
      const s = String(props[k] ?? '').replace(/\\D+/g,'');
      if (s) digits.push(s);
    }}
    let d=null, b=null;
    for (const s of digits) {{
      if (!d && s.length<=3) d = s.replace(/^0+/, '');
      if (!b && s.length===3) b = s;
      if (d && b) return [d,b];
    }}
    return [null, null];
  }}

  const PARTY_COLORS = {{
    "PMELR": "#2e7d32",
    "EMES":  "#6a1b9a",
    "TMECS": "#ef6c00",
    "OTHER": "#9e9e9e"
  }};

  function getWinnerInfo(postes, posteKeyStr) {{
    if (!postes) return null;
    let info = postes[posteKeyStr];
    if (!info) {{
      const alt = String(parseFloat(posteKeyStr));
      info = postes[alt];
    }}
    if (!info || !Array.isArray(info.rows) || !info.rows.length) return null;
    const sorted = [...info.rows].sort((a,b)=>b.votes - a.votes);
    const top = sorted[0];
    return {{
      parti: (top.parti || "").trim().toUpperCase(),
      nom: top.nom,
      votes: top.votes,
      total_valid: info.total_valid
    }};
  }}

  function colorForParty(p) {{
    if (!p) return PARTY_COLORS.OTHER;
    return PARTY_COLORS[p] || PARTY_COLORS.OTHER;
  }}

  function sectionFillColor(props) {{
    const [dist, bure] = extractDistBureau(props);
    if (!dist || !bure) return PARTY_COLORS.OTHER;
    const key = dist + "|" + bure;
    const postes = RESULTS_INDEX[key];
    const win = getWinnerInfo(postes, WINNER_POSTE_KEY);
    if (!win) return PARTY_COLORS.OTHER;
    return colorForParty(win.parti);
  }}

  // Districts: contour uniquement (transparent)
  function styleDistricts(_) {{
    return {{ color: '#1e40af', weight: 1.5, fillOpacity: 0, fill: false, dashArray: '3, 3' }};
  }}
  function styleSections(f) {{
    const fill = sectionFillColor(f.properties || {{}});
    return {{ color: '#333', weight: 1, fillColor: fill, fillOpacity: 0.35 }};
  }}

  function buildPosteTable(posteCode, info) {{
    if (!info || !Array.isArray(info.rows)) {{
      return `<div style="color:#a00;">Données indisponibles pour le poste ${'{'}posteCode{'}'}</div>`;
    }}
    const head = `
      <div class="poste-title">Poste ${'{'}posteCode{'}'}</div>
      <table class="popup-table">
        <thead><tr><th>Candidat</th><th style="text-align:right;">%</th><th style="text-align:right;">Voix</th></tr></thead>
        <tbody>
    `;
    const rows = info.rows.map(r => `
      <tr>
        <td>${'{'}r.nom{'}'}${'{'}r.parti ? ' ('+r.parti+')' : ''{'}'}</td>
        <td style="text-align:right;">${'{'}(r.pct ?? 0).toFixed(2){'}'}&nbsp;%</td>
        <td style="text-align:right;">${'{'}r.votes{'}'}</td>
      </tr>
    `).join('');
    const foot = `
        </tbody>
      </table>
      <div style="margin-top:6px;font-size:12px;color:#555;">
        <em>Valides:</em> ${'{'}info.total_valid ?? 0{'}'} &nbsp; | &nbsp;
        <em>Rejetés:</em> ${'{'}info.rejected ?? 0{'}'} &nbsp; | &nbsp;
        <em>Total:</em> ${'{'}info.total ?? 0{'}'}
      </div>
    `;
    return head + rows + foot;
  }}

  function posteLabel(k) {{
    return POSTE_ALIASES[k] || `Poste ${'{'}k{'}'}`;
  }}

  function popupHTML(props) {{
    const [dist, bure] = extractDistBureau(props);
    const title = (props.NOM || props.name || 'Section') + (bure ? (' — ' + bure) : '');
    const key = (dist && bure) ? (dist + '|' + bure) : null;
    let body = '';

    if (key && RESULTS_INDEX[key]) {{
      const postes = RESULTS_INDEX[key];

      const keyStrs = Object.keys(postes).sort((a,b)=>parseFloat(a)-parseFloat(b));
      const filteredStrs = (ONLY_POSTE && ONLY_POSTE.length)
        ? keyStrs.filter(k => ONLY_POSTE.includes(parseFloat(k)))
        : keyStrs;

      if (!filteredStrs.length) {{
        body = '<div style="color:#a00;">Aucun poste sélectionné pour cette section.</div>';
      }} else {{
        const win = getWinnerInfo(postes, WINNER_POSTE_KEY);
        const tag = win ? `<div style="margin:4px 0 6px 0;"><b>Gagnant (${ '{'}posteLabel(WINNER_POSTE_KEY){'}' }):</b> ${'{'}win.nom{'}'} (${ '{'}win.parti{'}'}) — ${ '{'}(100*win.votes/Math.max(1,win.total_valid)).toFixed(1){'}'}%</div>` : '';
        body = tag + filteredStrs.map(k => {{
          const info = postes[k];
          if (!info || !info.rows) {{
            return `<div style="color:#a00;">Données manquantes pour ${'{'}posteLabel(k){'}'}</div>`;
          }}
          return buildPosteTable(`${'{'}posteLabel(k){'}'}`, info);
        }}).join('');
      }}
    }} else {{
      body = '<div style="color:#a00;">Résultats introuvables pour cette section.</div>';
    }}

    let meta = '';
    const showKeys = ['ARRONDISSEMENT','DISTRICT','DISTRICT_ID','SECTION','BUREAU','NO_SECTION','NO_BUREAU'];
    for (const k in props) {{
      if (showKeys.includes(k) && props[k] != null) meta += `<b>${'{'}k{'}'}:</b> ${'{'}props[k]{'}'}<br/>`;
    }}

    return `
      <div class="popup-title">${'{'}title{'}'}</div>
      ${'{'}body{'}'}
      <div style="margin-top:8px;">${'{'}meta{'}'}</div>
    `;
  }}

  const map = L.map('map').setView([45.508888, -73.561668], 12);

  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 19,
    attribution: '© OpenStreetMap'
  }}).addTo(map);

  const layerDistricts = L.geoJSON(DATA_DISTRICTS, {{
    style: styleDistricts,
    onEachFeature: (f, layer) => {{
      const p = f.properties || {{}};
      layer.bindPopup(() => {{
        let html = '<div class="popup-title">District</div>';
        for (const k in p) html += `<b>${'{'}k{'}'}:</b> ${'{'}p[k]{'}'}<br/>`;
        return html;
      }});
    }}
  }});

  const layerSections = L.geoJSON(DATA_SECTIONS, {{
    style: styleSections,
    onEachFeature: (f, layer) => {{
      const p = f.properties || {{}};
      layer.bindPopup(() => popupHTML(p), {{maxWidth: 520}});
      layer.on('popupopen', () => layer.setStyle({{weight:2, color:'#222', fillOpacity: 0.45}}));
      layer.on('popupclose', () => layer.setStyle(styleSections(f)));
    }}
  }});

  L.control.layers(null, {{
    "Districts électoraux": layerDistricts,
    "Sections de vote (colorées)": layerSections
  }}, {{collapsed:false}}).addTo(map);

  layerDistricts.addTo(map);
  layerSections.addTo(map);

  try {{
    const bounds = L.featureGroup([layerDistricts, layerSections]).getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, {{padding:[20,20]}});
  }} catch(e) {{ console.warn("fitBounds error:", e); }}

  // Légende
  const legend = L.control({{ position: 'bottomright' }});
  legend.onAdd = () => {{
    const div = L.DomUtil.create('div','legend');
    const current = POSTE_ALIASES[WINNER_POSTE_KEY] || ('Poste ' + WINNER_POSTE_KEY);
    div.innerHTML = `
      <b>Gagnant (${ '{'}current{'}' })</b><br/>
      <span style="color:#2e7d32;">&#9632;</span> PMELR<br/>
      <span style="color:#6a1b9a;">&#9632;</span> EMES<br/>
      <span style="color:#ef6c00;">&#9632;</span> TMECS<br/>
      <span style="color:#9e9e9e;">&#9632;</span> Autre / inconnu
    `;
    return div;
  }};
  legend.addTo(map);

  // --- Sélecteur de poste ---
  function collectAllPosteKeys() {{
    const set = new Set();
    for (const key in RESULTS_INDEX) {{
      for (const pk in RESULTS_INDEX[key]) set.add(pk);
    }}
    return Array.from(set).sort((a,b)=>parseFloat(a)-parseFloat(b));
  }}

  function refreshLegend() {{
    legend.remove();
    legend.addTo(map);
  }}

  function repaintSections() {{
    layerSections.setStyle(styleSections);
  }}

  function populatePosteSelect() {{
    const select = document.getElementById('posteSelect');
    const keys = collectAllPosteKeys();
    select.innerHTML = '';
    for (const k of keys) {{
      const opt = document.createElement('option');
      opt.value = k;
      opt.textContent = POSTE_ALIASES[k] || `Poste ${'{'}k{'}'}`;
      if (String(k) === String(WINNER_POSTE_KEY)) opt.selected = true;
      select.appendChild(opt);
    }}
    select.addEventListener('change', (e) => {{
      WINNER_POSTE_KEY = e.target.value;
      repaintSections();
      refreshLegend();
    }});
  }}

  populatePosteSelect();
</script>
</body>
</html>
"""
    out_html.write_text(html, encoding="utf-8")
    print(f"✅ HTML généré : {out_html.resolve()}")

def main():
    ap = argparse.ArgumentParser(description="Génère une carte HTML avec résultats 2025 embarqués (CSV schéma 2021).")
    ap.add_argument("--csv", required=True, help="CSV résultats 2025 (même colonnes que 2021).")
    ap.add_argument("--outhtml", default="map.html", help="Fichier HTML de sortie.")
    ap.add_argument("--districts", default=DEFAULT_DISTRICTS_URL, help="GeoJSON districts (URL ou chemin local).")
    ap.add_argument("--sections",  default=DEFAULT_SECTIONS_URL,   help="GeoJSON sections (URL ou chemin local).")
    ap.add_argument("--only-poste", nargs="*", type=float, help="Filtrer certains postes dans les popups (ex: --only-poste 0 1 19)")
    ap.add_argument("--winner-poste", default="0", help="Poste initial pour la coloration (ex: 0 pour Mairie).")
    ap.add_argument("--poste-alias", default=None, help="Chemin JSON: mapping 'code_poste(str)' -> 'label lisible'")
    ap.add_argument("--wm-text", default="Gabriel Fortin · Nicolas Jolicoeur", help="Texte du watermark")
    ap.add_argument("--wm-img1", default=None, help="Chemin de la première petite photo (PNG/JPG)")
    ap.add_argument("--wm-img2", default=None, help="Chemin de la deuxième petite photo (PNG/JPG)")
    args = ap.parse_args()

    # Lire les GeoJSON
    districts_geojson = fetch_json(args.districts)
    sections_geojson  = fetch_json(args.sections)

    # Indexer les résultats depuis le CSV
    results_index = build_results_index(args.csv, args.only_poste)

    # Normaliser winner poste -> clé string
    try:
        as_float = float(str(args.winner_poste))
        winner_key = str(int(as_float)) if as_float.is_integer() else str(as_float)
    except Exception:
        winner_key = str(args.winner_poste)

    # Charger alias si fourni
    poste_aliases = None
    if args.poste_alias:
        p = Path(args.poste_alias)
        if p.exists():
            try:
                poste_aliases = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                print("⚠️  Impossible de lire --poste-alias comme JSON; ignoré.")

    # Images watermark en data URI
    wm_img1_uri = img_to_data_uri(args.wm_img1)
    wm_img2_uri = img_to_data_uri(args.wm_img2)

    # Générer le HTML autonome
    make_html(
        districts_geojson, sections_geojson, results_index,
        Path(args.outhtml), args.only_poste, winner_key, poste_aliases,
        wm_text=args.wm_text, wm_img1_data_uri=wm_img1_uri, wm_img2_data_uri=wm_img2_uri
    )

if __name__ == "__main__":
    main()
