#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
genmap3.py

Génère une carte HTML interactive pour les résultats de l'élection de Montréal 2025 :
- Districts : contours noirs, transparents
- Sections de vote : colorées selon le parti gagnant pour le poste sélectionné
- Dropdown pour choisir le poste (tous les postes disponibles dans le CSV),
  avec les noms issus de postes.csv sous la forme : "<type> <poste>"
- Popup détaillé sur clic d'une section, incluant les pourcentages de vote
- Bannière subtile en bas à droite avec deux images et des noms

Dépendances : pandas
"""

import json
import base64
import unicodedata
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd


# --- Configuration des chemins ---

CSV_PATH = Path("RapportFinal__20251105.csv")
POSTES_CSV_PATH = Path("postes.csv")
DISTRICTS_GEOJSON_PATH = Path("geojson/districts.geojson")
SECTIONS_GEOJSON_PATH = Path("geojson/sections.geojson")
METRO_GEOJSON_PATH_1 = Path("geojson/metro_route_1.geojson")
METRO_GEOJSON_PATH_2 = Path("geojson/metro_route_2.geojson")
METRO_GEOJSON_PATH_4 = Path("geojson/metro_route_4.geojson")
METRO_GEOJSON_PATH_5 = Path("geojson/metro_route_5.geojson")
OUTPUT_HTML = Path("genmap3.html")

WM_TEXT = "Gabriel Fortin · Nicolas Jolicoeur"
WM_IMG1_PATH = Path("./img/gabriel.jpg")
WM_IMG2_PATH = Path("./img/nicolas.png")


# --- Utilitaires ---


def normalize_str(value: Any) -> str:
    """
    Normalise une chaîne en :
    - convertissant en str
    - retirant les caractères de contrôle parasites
    - normalisant les accents (NFC)
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value)
    # retirer BOM et espaces insécables fréquents
    s = s.replace("\ufeff", "").replace("\xa0", " ")
    s = s.strip()
    # normalisation unicode (accents, etc.)
    s = unicodedata.normalize("NFC", s)
    return s


def img_to_data_uri(path: Path) -> Optional[str]:
    """Convertit une image locale en data URI (base64) pour l'inclure dans le HTML."""
    if not path:
        return None
    if not path.exists():
        print(f"⚠️  Image introuvable: {path}")
        return None
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


# --- Construction des données à partir du CSV de résultats ---


def build_results_index(csv_path: Path) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Construit RESULTS_INDEX[poste_code][code_section] = infos pour les popups et la couleur.

    - poste_code : PosteNorm (ex. "0.00", "1.00", "1.10", etc.)
    - code_section : "DDD-SSS" pour matcher CODE_SECTION du GeoJSON des sections
      (ex. "011-037")
    """
    df = pd.read_csv(csv_path, encoding="utf-8")

    # Normaliser Poste (0,00 -> 0.00)
    df["PosteNorm"] = df["Poste"].astype(str).str.replace(",", ".", regex=False)

    # Codes de district/section au format 'DDD-SSS' pour matcher CODE_SECTION du GeoJSON
    df["ElectoralDistrictID"] = pd.to_numeric(df["ElectoralDistrictID"], errors="coerce").astype(int)
    df["DistCode"] = df["ElectoralDistrictID"].astype(str).str.zfill(3)
    df["BureauStr"] = df["Bureau"].astype(str).str.zfill(3)
    df["SectionCode"] = df["DistCode"] + "-" + df["BureauStr"]

    # S'assurer que Votes et totaux sont numériques
    df["Votes"] = pd.to_numeric(df["Votes"], errors="coerce").fillna(0)

    for col in ["TotalValidVotes", "TotalRejectedVotes", "TotalVotes"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    results_index: Dict[str, Dict[str, Dict[str, Any]]] = {}

    # Grouper par poste et section
    group_cols = ["PosteNorm", "SectionCode"]
    for (poste, sec_code), grp in df.groupby(group_cols):
        section_key = sec_code

        # gagnant
        winner_row = grp.sort_values("Votes", ascending=False).iloc[0]

        total_valid = grp["TotalValidVotes"].max() if "TotalValidVotes" in grp.columns else None
        total_rejected = grp["TotalRejectedVotes"].max() if "TotalRejectedVotes" in grp.columns else None
        total_votes = grp["TotalVotes"].max() if "TotalVotes" in grp.columns else None

        # Base de pourcentage : privilégier les votes valides, sinon total
        total_for_pct: Optional[float] = None
        if total_valid is not None and not pd.isna(total_valid) and float(total_valid) > 0:
            total_for_pct = float(total_valid)
        elif total_votes is not None and not pd.isna(total_votes) and float(total_votes) > 0:
            total_for_pct = float(total_votes)

        breakdown = []
        for _, row in grp.iterrows():
            votes = int(row.get("Votes", 0))
            pct: Optional[float] = None
            if total_for_pct is not None and total_for_pct > 0:
                pct = votes * 100.0 / total_for_pct
            breakdown.append(
                {
                    "candidat": normalize_str(row.get("Candidat", "")),
                    "parti": normalize_str(row.get("Parti", "")),
                    "votes": votes,
                    "pct": pct,
                }
            )

        # Pour affichage dans le popup
        district_id = int(grp["ElectoralDistrictID"].iloc[0])
        bureau = str(grp["Bureau"].iloc[0])

        poste_dict = results_index.setdefault(str(poste), {})
        poste_dict[section_key] = {
            "winner_candidate": normalize_str(winner_row.get("Candidat", "")),
            "winner_party": normalize_str(winner_row.get("Parti", "")),
            "winner_votes": int(winner_row.get("Votes", 0)),
            "total_valid": int(total_valid) if total_valid is not None and not pd.isna(total_valid) else None,
            "total_rejected": int(total_rejected) if total_rejected is not None and not pd.isna(total_rejected) else None,
            "total_votes": int(total_votes) if total_votes is not None and not pd.isna(total_votes) else None,
            "district_id": str(district_id),
            "bureau": bureau,
            "breakdown": breakdown,
        }

    return results_index


# --- Chargement des noms de postes ---


def load_poste_labels(postes_csv: Path, poste_codes: Dict[str, Any]) -> Dict[str, str]:
    """
    Charge postes.csv et retourne un mapping:
      poste_code_norm (ex. "0.00", "1.10") -> label pour le dropdown.

    Format d'une entrée dans le dropdown :
      "<type> <poste>"

    Hypothèse sur postes.csv :
      - colonne "no" : numéro de poste (float ex. 0.0, 1.0, 1.1, etc.)
      - colonne "type" : type de poste ("Maire d'arrondissement", "Conseiller de ville", etc.)
      - colonne "poste" : libellé du poste (ex. "Jeanne-Mance")
    On corrige les accents et bizarreries via normalize_str().
    """
    if not postes_csv.exists():
        print(f"⚠️  postes.csv introuvable: {postes_csv} — les codes seront utilisés tels quels.")
        return {code: code for code in poste_codes.keys()}

    df_postes = pd.read_csv(postes_csv, encoding="utf-8")

    labels_raw: Dict[str, str] = {}
    for _, row in df_postes.iterrows():
        no_val = row.get("no")
        if pd.isna(no_val):
            continue
        try:
            f = float(no_val)
        except Exception:
            continue
        code = f"{f:.2f}"  # 1.1 → "1.10", 1.0 → "1.00", etc.

        type_str = normalize_str(row.get("type", ""))
        poste_name = normalize_str(row.get("poste", ""))

        if type_str and poste_name:
            label = f"{type_str} {poste_name}"
        elif type_str:
            label = type_str
        elif poste_name:
            label = poste_name
        else:
            label = code

        labels_raw[code] = label

    # S'assurer qu'on a un label pour tous les codes de RESULTS_INDEX
    final_labels: Dict[str, str] = {}
    for code in poste_codes.keys():
        if code in labels_raw:
            final_labels[code] = labels_raw[code]
        else:
            # fallback: le code lui-même
            final_labels[code] = code

    return final_labels


# --- Génération du HTML Leaflet ---


def generate_html(
    districts_geojson: Dict[str, Any],
    sections_geojson: Dict[str, Any],
    results_index: Dict[str, Dict[str, Dict[str, Any]]],
    poste_labels: Dict[str, str],
    out_html: Path,
    wm_text: str,
    wm_img1_data_uri: Optional[str],
    wm_img2_data_uri: Optional[str],
    metro_geojson_1: Dict[str, Any],
    metro_geojson_2: Dict[str, Any],
    metro_geojson_4: Dict[str, Any],
    metro_geojson_5: Dict[str, Any]
) -> None:
    js_districts = json.dumps(districts_geojson, ensure_ascii=False)
    js_sections = json.dumps(sections_geojson, ensure_ascii=False)
    js_results = json.dumps(results_index, ensure_ascii=False)
    js_poste_labels = json.dumps(poste_labels, ensure_ascii=False)
    js_wm_text = json.dumps(wm_text, ensure_ascii=False)
    js_wm_img1 = json.dumps(wm_img1_data_uri)
    js_wm_img2 = json.dumps(wm_img2_data_uri)
    js_metro_geo_1 = json.dumps(metro_geojson_1, ensure_ascii=False)
    js_metro_geo_2 = json.dumps(metro_geojson_2, ensure_ascii=False)
    js_metro_geo_4 = json.dumps(metro_geojson_4, ensure_ascii=False)
    js_metro_geo_5 = json.dumps(metro_geojson_5, ensure_ascii=False)

    # Template avec placeholders, qu'on remplace ensuite
    html_template = """<!DOCTYPE html>
<html lang=\"fr\">
<head>
  <meta charset=\"utf-8\" />
  <title>Carte des résultats par section et districts</title>
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <link
    rel=\"stylesheet\"
    href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\"
    integrity=\"sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=\"
    crossorigin=\"\"/>
  <style>
    html, body {
      margin: 0; padding: 0; height: 100%; width: 100%;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;
    }
    #map {
      width: 100%;
      height: 100%;
    }
    .poste-control {
      position: absolute;
      top: 10px;
      left: 50px;
      z-index: 1000;
      background: rgba(255,255,255,0.95);
      padding: 6px 10px;
      border-radius: 9999px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15);
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
    }
    .poste-control select {
      font-size: 13px;
      border-radius: 9999px;
      padding: 2px 8px;
      border: 1px solid #ccc;
    }
    @media (max-width: 600px) {
      .poste-control {
        left: 10px;
        right: 10px;
        justify-content: space-between;
      }
    }

    /* Bannière / watermark bottom-right */
    .watermark {
      position: absolute; right: 10px; bottom: 10px; z-index: 1000;
      background: rgba(255,255,255,0.80); backdrop-filter: blur(2px);
      border-radius: 9999px; padding: 6px 10px; display: inline-flex; align-items: center; gap: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15); font: 11px/1.2 system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
      color: #111; opacity: 0.8; transition: opacity .2s ease;
    }
    .watermark:hover { opacity: 1; }
    .wm-avatars { display: inline-flex; align-items: center; gap: 6px; }
    .wm-avatar {
      width: 22px; height: 22px; border-radius: 50%; object-fit: cover;
      box-shadow: 0 0 0 1px rgba(0,0,0,0.1);
    }
    @media (max-width: 560px) {
      .watermark { padding: 4px 8px; font-size: 10px; gap: 4px; }
      .wm-avatar { width: 18px; height: 18px; }
    }
  </style>
</head>
<body>
  <div id=\"map\"></div>
  <div class=\"poste-control\">
    <span>Poste :</span>
    <select id=\"posteSelect\"></select>
  </div>

  <!-- Bannière avec images et noms, en bas à droite -->
  <div id=\"wm\" class=\"watermark\" title=\"Carte des résultats 2025\">
    <div class=\"wm-avatars\" id=\"wmAvatars\"></div>
    <div class=\"wm-text\" id=\"wmText\"></div>
  </div>

  <script
    src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"
    integrity=\"sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=\"
    crossorigin=\"\"></script>
  <script>
    const DATA_DISTRICTS = __DATA_DISTRICTS__;
    const DATA_SECTIONS = __DATA_SECTIONS__;
    const RESULTS_INDEX = __RESULTS_INDEX__;
    const POSTE_LABELS = __POSTE_LABELS__;
    const WM_TEXT = __WM_TEXT__;
    const WM_IMG1 = __WM_IMG1__;
    const WM_IMG2 = __WM_IMG2__;
    const METRO_GEO_1 = __METRO_GEO_1__;
    const METRO_GEO_2 = __METRO_GEO_2__;
    const METRO_GEO_4 = __METRO_GEO_4__;
    const METRO_GEO_5 = __METRO_GEO_5__;

    function partyColor(parti) {
      if (!parti) return "#cccccc";
      const p = String(parti).toLowerCase();
      // Projet Montréal : vert
      if (p.includes("projet montr")) return "#1ebf3a";
      // Ensemble Montréal : mauve
      if (p.includes("ensemble montr")) return "#9b59b6";
      // Transition : orange
      if (p.includes("transition")) return "#f39c12";
      // Action : bleu pâle
      if (p.includes("action")) return "#5dade2";
      return "#cccccc";
    }

    function sectionKeyFromFeature(f) {
      const props = f.properties || {};
      const c = String(props.CODE_SECTION ?? "");
      return c;
    }

    const posteKeys = Object.keys(RESULTS_INDEX).sort();
    let currentPosteKey = posteKeys.length > 0 ? posteKeys[0] : null;

    function currentPosteLabel() {
      if (!currentPosteKey) return "";
      return POSTE_LABELS[currentPosteKey] || currentPosteKey;
    }

    const map = L.map('map');
    const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    // Districts : contours noirs transparents
    function styleDistrict(feature) {
      return {
        color: "#000000",
        weight: 1.2,
        fillColor: "transparent",
        fillOpacity: 0.0
      };
    }

    const districtsLayer = L.geoJSON(DATA_DISTRICTS, {
      style: styleDistrict
    }).addTo(map);

    // Sections : remplies selon le parti gagnant pour le poste choisi
    function styleSection(feature) {
      const key = sectionKeyFromFeature(feature);
      const posteData = currentPosteKey ? RESULTS_INDEX[currentPosteKey] : null;
      const info = posteData ? posteData[key] : null;
      const color = info ? partyColor(info.winner_party) : "#eeeeee";
      return {
        color: "#555",
        weight: 0.5,
        fillColor: color,
        fillOpacity: 0.7
      };
    }

    function buildPopupHtml(info, sectionKey) {
      if (!info) {
        return "<div><strong>Section " + sectionKey + "</strong><br>Aucune donnée pour ce poste.</div>";
      }
      let html = "";
      html += "<div>";
      html += "<strong>District " + (info.district_id ?? "") + " · Bureau " + (info.bureau ?? "") + "</strong><br/>";
      html += "Poste : " + currentPosteLabel() + "<br/><br/>";
      if (info.total_votes != null) {
        html += "Total votes : " + info.total_votes + "<br/>";
      }
      if (info.total_valid != null) {
        html += "Votes valides : " + info.total_valid + "<br/>";
      }
      if (info.total_rejected != null) {
        html += "Votes rejetés : " + info.total_rejected + "<br/>";
      }
      html += "<br/><strong>Résultats par candidat·e</strong><br/>";
      html += "<table style='border-collapse:collapse; font-size:12px; margin-top:4px;'>";
      html += "<thead><tr>";
      html += "<th style='border-bottom:1px solid #ccc; padding:2px 6px; text-align:left;'>Candidat·e</th>";
      html += "<th style='border-bottom:1px solid #ccc; padding:2px 6px; text-align:left;'>Parti</th>";
      html += "<th style='border-bottom:1px solid #ccc; padding:2px 6px; text-align:right;'>Votes</th>";
      html += "<th style='border-bottom:1px solid #ccc; padding:2px 6px; text-align:right;'>%</th>";
      html += "</tr></thead><tbody>";
      (info.breakdown || []).forEach(row => {
        const votes = (row.votes != null) ? row.votes : "";
        let pctStr = "";
        if (row.pct != null) {
          try {
            pctStr = Number(row.pct).toFixed(1) + " %";
          } catch (e) {
            pctStr = "";
          }
        }
        html += "<tr>";
        html += "<td style='padding:2px 6px;'>" + (row.candidat || "") + "</td>";
        html += "<td style='padding:2px 6px;'>" + (row.parti || "") + "</td>";
        html += "<td style='padding:2px 6px; text-align:right;'>" + votes + "</td>";
        html += "<td style='padding:2px 6px; text-align:right;'>" + pctStr + "</td>";
        html += "</tr>";
      });
      html += "</tbody></table>";
      html += "</div>";
      return html;
    }

    function onEachSection(feature, layer) {
      const key = sectionKeyFromFeature(feature);
      layer.on('click', function() {
        const posteData = currentPosteKey ? RESULTS_INDEX[currentPosteKey] : null;
        const info = posteData ? posteData[key] : null;
        const html = buildPopupHtml(info, key);
        layer.bindPopup(html, {maxWidth: 360}).openPopup();
      });
    }

    const sectionsLayer = L.geoJSON(DATA_SECTIONS, {
      style: styleSection,
      onEachFeature: onEachSection
    }).addTo(map);

    let genmetro = true
    if (genmetro) {
      const metroLayer1 = L.geoJSON(METRO_GEO_1, {
        style: {
          weight: 7,
          color:  "#005900"
        }
      }).addTo(map);
      const metroLayer2 = L.geoJSON(METRO_GEO_2, {
        style: {
          weight: 7,
          color: "#D95700"
        }
      }).addTo(map);
      const metroLayer4 = L.geoJSON(METRO_GEO_4, {
        style: {
          weight: 7,
          color: "#FFD900"
        }
      }).addTo(map);
      const metroLayer5 = L.geoJSON(METRO_GEO_5, {
        style: {
          weight: 7,
          color: "#0047AB"
        }
    }).addTo(map);
    }
    

    // Adapter la carte à l'étendue
    try {
      map.fitBounds(districtsLayer.getBounds());
    } catch (e) {
      try {
        map.fitBounds(sectionsLayer.getBounds());
      } catch (e2) {
        map.setView([45.55, -73.6], 11);
      }
    }

    // Dropdown de postes
    const sel = document.getElementById('posteSelect');
    posteKeys.forEach(k => {
      const opt = document.createElement('option');
      opt.value = k;
      const label = POSTE_LABELS[k] || k;
      opt.textContent = label;
      sel.appendChild(opt);
    });
    if (currentPosteKey) {
      sel.value = currentPosteKey;
    }

    sel.addEventListener('change', function() {
      currentPosteKey = this.value;
      sectionsLayer.setStyle(styleSection);
      map.closePopup();
    });

    // Initialiser la bannière images + noms
    (function initBanner() {
      const t = document.getElementById('wmText');
      const a = document.getElementById('wmAvatars');
      if (!t || !a) return;
      t.textContent = WM_TEXT || "Gabriel Fortin · Nicolas Jolicoeur";
      if (WM_IMG1) {
        const img1 = document.createElement('img');
        img1.src = WM_IMG1; img1.alt = 'Photo 1'; img1.className = 'wm-avatar';
        a.appendChild(img1);
      }
      if (WM_IMG2) {
        const img2 = document.createElement('img');
        img2.src = WM_IMG2; img2.alt = 'Photo 2'; img2.className = 'wm-avatar';
        a.appendChild(img2);
      }
    })();
  </script>
</body>
</html>"""  # fin template

    html = (
        html_template
        .replace("__DATA_DISTRICTS__", js_districts)
        .replace("__DATA_SECTIONS__", js_sections)
        .replace("__RESULTS_INDEX__", js_results)
        .replace("__POSTE_LABELS__", js_poste_labels)
        .replace("__WM_TEXT__", js_wm_text)
        .replace("__WM_IMG1__", js_wm_img1)
        .replace("__WM_IMG2__", js_wm_img2)
        .replace("__METRO_GEO_1__", js_metro_geo_1)
        .replace("__METRO_GEO_2__", js_metro_geo_2)
        .replace("__METRO_GEO_4__", js_metro_geo_4)
        .replace("__METRO_GEO_5__", js_metro_geo_5)
    )

    out_html.write_text(html, encoding="utf-8")
    print(f"Carte générée : {out_html}")


# --- main ---


def main() -> None:
    # Vérifier les fichiers
    if not CSV_PATH.exists():
        raise SystemExit(f"CSV introuvable : {CSV_PATH}")
    if not POSTES_CSV_PATH.exists():
        raise SystemExit(f"postes.csv introuvable : {POSTES_CSV_PATH}")
    if not DISTRICTS_GEOJSON_PATH.exists():
        raise SystemExit(f"GeoJSON districts introuvable : {DISTRICTS_GEOJSON_PATH}")
    if not SECTIONS_GEOJSON_PATH.exists():
        raise SystemExit(f"GeoJSON sections introuvable : {SECTIONS_GEOJSON_PATH}")

    results_index = build_results_index(CSV_PATH)
    poste_labels = load_poste_labels(POSTES_CSV_PATH, results_index)

    districts_geojson = json.loads(DISTRICTS_GEOJSON_PATH.read_text(encoding="utf-8"))
    sections_geojson = json.loads(SECTIONS_GEOJSON_PATH.read_text(encoding="utf-8"))

    wm_img1_uri = img_to_data_uri(WM_IMG1_PATH)
    wm_img2_uri = img_to_data_uri(WM_IMG2_PATH)

    metro_geojson_1 = json.loads(METRO_GEOJSON_PATH_1.read_text(encoding="utf-8"))
    metro_geojson_2 = json.loads(METRO_GEOJSON_PATH_2.read_text(encoding="utf-8"))
    metro_geojson_4 = json.loads(METRO_GEOJSON_PATH_4.read_text(encoding="utf-8"))
    metro_geojson_5 = json.loads(METRO_GEOJSON_PATH_5.read_text(encoding="utf-8"))

    generate_html(
        districts_geojson,
        sections_geojson,
        results_index,
        poste_labels,
        OUTPUT_HTML,
        WM_TEXT,
        wm_img1_uri,
        wm_img2_uri,
        metro_geojson_1,
        metro_geojson_2,
        metro_geojson_4,
        metro_geojson_5
    )


if __name__ == "__main__":
    main()
