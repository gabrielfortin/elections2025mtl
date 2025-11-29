import argparse
import json
import base64
from pathlib import Path
from typing import Optional

import folium
import pandas as pd
from branca.element import Element

# Couleur par défaut si on ne reconnait pas le parti
DEFAULT_COLOR = "#cccccc"


def color_for_party(parti: str) -> str:
    """Retourne une couleur en fonction du parti."""
    if not isinstance(parti, str):
        return DEFAULT_COLOR
    text = parti.lower()
    if "projet montr" in text:
        return "#1b9e77"  # vert
    if "ensemble" in text:
        return "#BD5EDB"  # orange
    if "action montr" in text:
        return "#3DA1E0"  # mauve
    if "indépendant" in text or "independant" in text:
        return "#999999"  # gris
    return DEFAULT_COLOR


def img_to_data_uri(path: Optional[str]) -> Optional[str]:
    """Convertit une image locale en data URI (base64) pour l'inclure dans le HTML."""
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


def load_results(csv_path: Path):
    """Charge le CSV et calcule les gagnants par (district, poste)."""
    df = pd.read_csv(csv_path)

    # Normaliser les codes de poste (ex.: "0,00" -> "0.00")
    df["PosteNorm"] = df["Poste"].astype(str).str.replace(",", ".", regex=False)

    # S'assurer que les votes sont numériques
    df["Votes"] = pd.to_numeric(df["Votes"], errors="coerce").fillna(0)

    # ElectoralDistrictID en string pour matcher plus facilement avec le GeoJSON
    df["ElectoralDistrictID"] = df["ElectoralDistrictID"].astype(str)

    # Trouver les gagnants par district + poste
    winners = (
        df.sort_values("Votes", ascending=False)
          .groupby(["ElectoralDistrictID", "PosteNorm"])
          .first()
          .reset_index()
    )

    postes_disponibles = sorted(winners["PosteNorm"].unique().tolist())
    return winners, postes_disponibles


def build_winner_index(winners: pd.DataFrame):
    """Construit un index {(district_id, poste): {...infos...}}."""
    idx = winners.set_index(["ElectoralDistrictID", "PosteNorm"]).to_dict("index")
    return idx


def inject_results_in_geojson(
    geojson_data: dict,
    winner_index: dict,
    poste: str,
    id_field: str,
):
    """Injecte dans chaque feature du GeoJSON les infos du gagnant pour le poste donné."""
    for feat in geojson_data.get("features", []):
        props = feat.setdefault("properties", {})
        district_raw = props.get(id_field)
        if district_raw is None:
            continue

        district_id = str(district_raw)
        key = (district_id, poste)
        res = winner_index.get(key)

        if res is None:
            props.setdefault("winner_candidate", "N/A")
            props.setdefault("winner_party", "N/A")
            props.setdefault("winner_votes", 0)
        else:
            props["winner_candidate"] = res.get("Candidat", "N/A")
            props["winner_party"] = res.get("Parti", "N/A")
            props["winner_votes"] = int(res.get("Votes", 0))


def add_watermark(map_obj: folium.Map,
                  wm_text: str = "Gabriel Fortin · Nicolas Jolicoeur",
                  wm_img1_data_uri: Optional[str] = None,
                  wm_img2_data_uri: Optional[str] = None) -> None:
    """Ajoute un watermark en bas à gauche avec texte + 2 petites photos (data URI)."""
    js_wm_text = json.dumps(wm_text, ensure_ascii=False)
    js_wm_img1 = json.dumps(wm_img1_data_uri)
    js_wm_img2 = json.dumps(wm_img2_data_uri)

    html = f"""
<style>
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
}}
</style>

<div id="wm" class="watermark" title="Carte des résultats 2025">
  <div class="wm-avatars" id="wmAvatars"></div>
  <div class="wm-text" id="wmText"></div>
</div>

<script>
  const WM_TEXT = {js_wm_text};
  const WM_IMG1 = {js_wm_img1};
  const WM_IMG2 = {js_wm_img2};

  (function initWatermark() {{
    const t = document.getElementById('wmText');
    const a = document.getElementById('wmAvatars');
    if (!t || !a) return;
    t.textContent = WM_TEXT || "Gabriel Fortin · Nicolas Jolicoeur";
    if (WM_IMG1) {{
      const img1 = document.createElement('img');
      img1.src = WM_IMG1; img1.alt = 'Photo 1'; img1.className = 'wm-avatar';
      a.appendChild(img1);
    }}
    if (WM_IMG2) {{
      const img2 = document.createElement('img');
      img2.src = WM_IMG2; img2.alt = 'Photo 2'; img2.className = 'wm-avatar';
      a.appendChild(img2);
    }}
  }})();
</script>
"""

    map_obj.get_root().html.add_child(Element(html))


def make_map(
    csv_path: Path,
    geojson_path: Path,
    output_html: Path,
    poste: Optional[str] = None,
    id_field: str = "district_id",
    wm_text: str = "Gabriel Fortin · Nicolas Jolicoeur",
    wm_img1_data_uri: Optional[str] = None,
    wm_img2_data_uri: Optional[str] = None,
):
    # Charger résultats et gagnants
    winners, postes_disponibles = load_results(csv_path)
    winner_index = build_winner_index(winners)

    # Choix du poste
    if poste is None:
        # Par défaut, on prend le premier poste disponible
        poste = postes_disponibles[0]
        print(f"[INFO] Aucun poste spécifié, utilisation de poste = {poste}")
    else:
        # Normaliser (0,00 -> 0.00)
        poste = str(poste).replace(",", ".", 1)

    if poste not in postes_disponibles:
        print(f"[AVERTISSEMENT] Poste {poste} introuvable dans le CSV.")
        print(f"Postes disponibles : {', '.join(postes_disponibles)}")

    # Charger le GeoJSON
    with open(geojson_path, "r", encoding="utf-8") as f:
        geojson_data = json.load(f)

    # Injecter les résultats (gagnant) dans les propriétés du GeoJSON
    inject_results_in_geojson(geojson_data, winner_index, poste, id_field)

    # Carte Folium centrée approximativement sur Montréal
    m = folium.Map(location=[45.55, -73.6], zoom_start=11, tiles="cartodbpositron")

    # Style des polygones
    def style_function(feature):
        props = feature.get("properties", {})
        parti = props.get("winner_party")
        color = color_for_party(parti)
        return {
            "fillOpacity": 0.6,
            "weight": 1,
            "color": "black",
            "fillColor": color,
        }

    # Infobulle (tooltip) affichée au survol
    tooltip = folium.GeoJsonTooltip(
        fields=[id_field, "winner_candidate", "winner_party", "winner_votes"],
        aliases=["District :", "Candidat·e :", "Parti :", "Votes :"],
        localize=True,
        sticky=True,
    )

    folium.GeoJson(
        geojson_data,
        name=f"Poste {poste}",
        style_function=style_function,
        tooltip=tooltip,
    ).add_to(m)

    folium.LayerControl().add_to(m)

    # Ajout du watermark en bas à gauche
    add_watermark(
        m,
        wm_text=wm_text,
        wm_img1_data_uri=wm_img1_data_uri,
        wm_img2_data_uri=wm_img2_data_uri,
    )

    # Sauvegarder la carte
    m.save(str(output_html))
    print(f"Carte générée : {output_html}")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Génère une carte interactive des résultats à partir du CSV "
            "RapportFinal__20251105.csv"
        )
    )
    parser.add_argument(
        "csv",
        help="Chemin vers le CSV de résultats (ex.: RapportFinal__20251105.csv)",
    )
    parser.add_argument(
        "geojson",
        help="Chemin vers le GeoJSON des districts (doit contenir un champ id de district)",
    )
    parser.add_argument(
        "outhtml",
        help="Chemin du fichier HTML de sortie (ex.: carte_electorale.html)",
    )
    parser.add_argument(
        "--poste",
        help="Code du poste (ex: 0.00, 1.00, etc.). Si omis, prend le premier disponible.",
        default=None,
    )
    parser.add_argument(
        "--id-field",
        help="Nom du champ dans le GeoJSON correspondant à ElectoralDistrictID (par défaut: district_id)",
        default="district_id",
    )
    parser.add_argument(
        "--wm-text",
        help="Texte du watermark (par défaut: 'Gabriel Fortin · Nicolas Jolicoeur')",
        default="Gabriel Fortin · Nicolas Jolicoeur",
    )
    parser.add_argument(
        "--wm-img1",
        help="Chemin de la première petite photo (PNG/JPG)",
        default=None,
    )
    parser.add_argument(
        "--wm-img2",
        help="Chemin de la deuxième petite photo (PNG/JPG)",
        default=None,
    )

    args = parser.parse_args()

    csv_path = Path(args.csv)
    geojson_path = Path(args.geojson)
    output_html = Path(args.outhtml)

    wm_img1_uri = img_to_data_uri(args.wm_img1)
    wm_img2_uri = img_to_data_uri(args.wm_img2)

    make_map(
        csv_path=csv_path,
        geojson_path=geojson_path,
        output_html=output_html,
        poste=args.poste,
        id_field=args.id_field,
        wm_text=args.wm_text,
        wm_img1_data_uri=wm_img1_uri,
        wm_img2_data_uri=wm_img2_uri,
    )


if __name__ == "__main__":
    main()
