"""
NISAR GCOV pour un ou plusieurs reservoirs.

1. Lit les zones (GeoJSON : une forme, ou plusieurs avec reservoir_id).
2. Cherche les scenes GCOV de chaque zone et ecrit l'inventaire des scenes
   dans data/processed/scene_inventory.csv (etape 5 du README, pour la piste B).
3. Lit la fenetre HH/HV de la premiere zone sans telecharger la scene entiere.

Installation :
    python -m pip install asf_search earthaccess h5py numpy pyproj shapely rasterio matplotlib

Utilisation :
    python polygone.py al_massira.geojson
    python polygone.py analysis_zones.geojson --inventaire      (inventaire seul, sans connexion Earthdata)
    python polygone.py al_massira.geojson --start 2026-01-01 --end 2026-11-01
    python polygone.py al_massira.geojson --n 5                 (les 5 dates les plus recentes)
    python polygone.py al_massira.geojson --mois 2026-07        (une scene de juillet 2026 -> fenetre_2026-07.npz)
"""

import argparse
import csv
import json
import os
import re
import sys
import time

import numpy as np
from shapely.geometry import shape
from shapely.ops import transform as shp_transform
from shapely.ops import unary_union

GRID = "/science/LSAR/GCOV/grids/frequencyA"
MARGE_M = 1000                 # metres de terre gardes autour du contour
BLOC = 16 * 1024 * 1024        # blocs de lecture reseau (16 Mo)
COLONNES = ["scene_id", "date", "track", "direction", "polarizations",
            "reservoir_id", "frame", "cycle", "url"]
POLARISATIONS = {"SH": "HH", "SV": "VV", "DH": "HH+HV", "DV": "VV+VH", "QP": "HH+HV+VH+VV"}
NOM_SCENE = re.compile(
    r"NISAR_L2_[A-Z]{2}_GCOV_(?P<cycle>\d{3})_(?P<track>\d{3})_(?P<dir>[AD])_(?P<frame>\d{3})_"
    r"(?P<mode>\d{4})_(?P<pol>[A-Z]{4})_[A-Z]_(?P<debut>\d{8})T\d{6}_\d{8}T\d{6}_(?P<crid>[A-Z]\d{5})"
)
DEBUT = time.time()


def etape(message):
    print(f"[{time.time() - DEBUT:5.0f} s] {message}", flush=True)


# ----------------------------------------------------------------------------
# Lecture des zones
# ----------------------------------------------------------------------------
def profondeur(c):
    n = 0
    while isinstance(c, list) and c:
        n += 1
        c = c[0]
    return n


def vers_forme(g):
    """Geometrie GeoJSON -> forme shapely, en corrigeant un type mal declare."""
    if g.get("type") in ("Polygon", "MultiPolygon"):
        vrai = {3: "Polygon", 4: "MultiPolygon"}.get(profondeur(g["coordinates"]))
        if vrai and vrai != g["type"]:
            print(f"Type corrige : '{g['type']}' declare, coordonnees de '{vrai}'")
            g = {"type": vrai, "coordinates": g["coordinates"]}
    forme = shape(g)
    return forme if forme.is_valid else forme.buffer(0)


def lire_zones(chemin):
    """Renvoie une liste de zones : {id, prioritaire, forme}."""
    data = json.load(open(chemin, encoding="utf-8"))
    if data.get("type") == "FeatureCollection":
        features = [f for f in data["features"] if f.get("geometry")]
    elif data.get("type") == "Feature":
        features = [data]
    else:
        features = [{"properties": {}, "geometry": data}]
    if not features:
        sys.exit("Aucune geometrie dans le fichier GeoJSON.")

    defaut = os.path.splitext(os.path.basename(chemin))[0]
    avec_id = [f for f in features if (f.get("properties") or {}).get("reservoir_id")]
    if len(avec_id) != len(features):
        # Pas d'identifiants : tout le fichier = une seule zone
        formes = [vers_forme(f["geometry"]) for f in features]
        forme = unary_union(formes) if len(formes) > 1 else formes[0]
        return [{"id": defaut, "prioritaire": True, "forme": forme}]
    return [
        {
            "id": f["properties"]["reservoir_id"],
            "prioritaire": bool(f["properties"].get("priority", True)),
            "forme": vers_forme(f["geometry"]),
        }
        for f in features
    ]


# ----------------------------------------------------------------------------
# Recherche + inventaire (etape 5)
# ----------------------------------------------------------------------------
def chercher_urls(forme, start, end):
    import asf_search as asf

    results = asf.geo_search(dataset="NISAR", processingLevel="GCOV",
                             intersectsWith=forme.envelope.wkt, start=start, end=end)
    try:
        urls = results.find_urls(extension=".h5", directAccess=False)
    except Exception:
        urls = [r.properties.get("url", "") for r in results]
    urls = sorted({u for u in urls if u.endswith(".h5") and "QA_STATS" not in u})
    if not urls and len(results) > 0:
        print("Resultats sans URL .h5. Proprietes du premier :", results[0].properties)
    return urls


def lignes_inventaire(urls, reservoir_id):
    """Une ligne par acquisition ; si une scene existe en plusieurs versions
    de traitement, on garde la plus recente."""
    par_scene = {}
    for url in urls:
        nom = os.path.basename(url)[:-3]
        m = NOM_SCENE.search(nom)
        if not m:
            print("Nom de scene non reconnu, ignore :", nom)
            continue
        d = m["debut"]
        cle = (m["track"], m["frame"], m["dir"], nom.split("_")[11])
        ligne = {
            "scene_id": nom,
            "date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
            "track": int(m["track"]),
            "direction": "ascending" if m["dir"] == "A" else "descending",
            "polarizations": POLARISATIONS.get(m["pol"][:2], m["pol"]),
            "reservoir_id": reservoir_id,
            "frame": int(m["frame"]),
            "cycle": int(m["cycle"]),
            "url": url,
            "_crid": m["crid"],
        }
        if cle not in par_scene or ligne["_crid"] > par_scene[cle]["_crid"]:
            par_scene[cle] = ligne
    return sorted(par_scene.values(), key=lambda l: l["date"], reverse=True)


def ecrire_inventaire(lignes, chemin):
    """Fusionne avec l'inventaire existant (pas de doublon scene + reservoir)."""
    tout = {}
    if os.path.isfile(chemin):
        with open(chemin, newline="", encoding="utf-8") as f:
            for l in csv.DictReader(f):
                tout[(l["scene_id"], l["reservoir_id"])] = l
    for l in lignes:
        tout[(l["scene_id"], l["reservoir_id"])] = {k: l[k] for k in COLONNES}
    os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
    tri = sorted(tout.values(), key=lambda l: (l["reservoir_id"], str(l["date"])))
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES)
        w.writeheader()
        w.writerows(tri)
    return len(tri)


# ----------------------------------------------------------------------------
# Lecture de la fenetre radar
# ----------------------------------------------------------------------------
def lire_par_bandes(dataset, r0, r1, c0, c1, nom, pas=256):
    sortie = np.empty((r1 - r0, c1 - c0), dtype=dataset.dtype)
    for debut in range(r0, r1, pas):
        fin = min(debut + pas, r1)
        sortie[debut - r0:fin - r0] = dataset[debut:fin, c0:c1]
        print(f"\r        {nom} : {100 * (fin - r0) / (r1 - r0):5.1f} %", end="", flush=True)
    print()
    return sortie


def connexion():
    import earthaccess

    etape("Connexion Earthdata...")
    if os.environ.get("EARTHDATA_TOKEN"):
        earthaccess.login(strategy="environment")
    else:
        earthaccess.login()
    return earthaccess.get_fsspec_https_session()


def lire_fenetre(fs, url, forme, suffixe, date_scene=""):
    import h5py
    import matplotlib.pyplot as plt
    from pyproj import Transformer
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin

    etape("Ouverture du fichier distant : " + os.path.basename(url))
    t0 = time.time()
    with fs.open(url, "rb", cache_type="background", block_size=BLOC) as f, h5py.File(f, "r") as h5:
        if GRID not in h5:
            print(f"Chemin {GRID} introuvable. Contenu du fichier :")
            h5.visit(print)
            sys.exit(1)
        etape(f"fichier ouvert en {time.time() - t0:.0f} s, lecture des coordonnees...")
        x = h5[f"{GRID}/xCoordinates"][:]
        y = h5[f"{GRID}/yCoordinates"][:]
        epsg = int(h5[f"{GRID}/projection"][()])
        to_scene = Transformer.from_crs(4326, epsg, always_xy=True)
        minx, miny, maxx, maxy = to_scene.transform_bounds(*forme.bounds)
        cols = np.where((x >= minx - MARGE_M) & (x <= maxx + MARGE_M))[0]
        rows = np.where((y >= miny - MARGE_M) & (y <= maxy + MARGE_M))[0]
        if len(cols) == 0 or len(rows) == 0:
            sys.exit("La zone ne recouvre pas cette scene. Essaie une autre scene de l'inventaire.")
        r0, r1, c0, c1 = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
        etape(f"lecture de la fenetre : {r1 - r0} lignes x {c1 - c0} colonnes (EPSG {epsg})")
        hh = lire_par_bandes(h5[f"{GRID}/HHHH"], r0, r1, c0, c1, "HH")
        hv = lire_par_bandes(h5[f"{GRID}/HVHV"], r0, r1, c0, c1, "HV") if f"{GRID}/HVHV" in h5 else None
    etape(f"fenetre lue en {time.time() - t0:.0f} s")

    with np.errstate(divide="ignore", invalid="ignore"):
        hh_db = 10 * np.log10(hh)
        hv_db = 10 * np.log10(hv) if hv is not None else np.array([])

    forme_scene = shp_transform(to_scene.transform, forme)
    dx, dy = abs(x[1] - x[0]), abs(y[1] - y[0])
    tr = from_origin(x[c0] - dx / 2, y[r0] + dy / 2, dx, dy)
    inside = geometry_mask([forme_scene], out_shape=hh.shape, transform=tr, invert=True)

    np.savez_compressed(f"fenetre_{suffixe}.npz", hh_db=hh_db, hv_db=hv_db, inside=inside,
                        x=x[c0:c1], y=y[r0:r1], epsg=epsg, scene=os.path.basename(url),
                        date=date_scene)
    plt.figure(figsize=(8, 6))
    plt.imshow(hh_db, cmap="gray", vmin=-30, vmax=0)
    plt.contour(inside, levels=[0.5], colors="red", linewidths=1)
    plt.colorbar(label="HH (dB)")
    plt.title(f"NISAR HH {suffixe}, eau = sombre, contour rouge = zone")
    plt.savefig(f"apercu_{suffixe}.png", dpi=150, bbox_inches="tight")
    plt.close()
    etape(f"enregistre : fenetre_{suffixe}.npz et apercu_{suffixe}.png")


# ----------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Inventaire et lecture NISAR GCOV par zone")
    p.add_argument("geojson", nargs="?", default="al_massira.geojson")
    p.add_argument("--start", default="2026-06-01")
    p.add_argument("--end", default="2026-11-01")
    p.add_argument("--inventaire", action="store_true",
                   help="ecrit seulement l'inventaire, sans lire de scene")
    p.add_argument("--mois", default=None,
                   help="mois a lire, format AAAA-MM (ex. 2026-07) ; remplace --start et --end")
    p.add_argument("--n", type=int, default=1,
                   help="nombre de dates a lire (les plus recentes, meme orbite)")
    p.add_argument("--track", type=int, default=None,
                   help="numero d'orbite a utiliser (par defaut : celle de la scene la plus recente)")
    p.add_argument("--sortie", default=os.path.join("data", "processed", "scene_inventory.csv"))
    a = p.parse_args()

    if a.mois:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", a.mois):
            sys.exit("--mois doit etre au format AAAA-MM, par exemple 2026-07")
        annee, mois = int(a.mois[:4]), int(a.mois[5:])
        a.start = f"{a.mois}-01"
        a.end = f"{annee + 1}-01-01" if mois == 12 else f"{annee}-{mois + 1:02d}-01"

    zones = lire_zones(a.geojson)
    prioritaires = [z for z in zones if z["prioritaire"]]
    etape(f"Etape 1/3 - {len(zones)} zone(s) lue(s), dont {len(prioritaires)} prioritaire(s)")

    etape(f"Etape 2/3 - inventaire des scenes GCOV du {a.start} au {a.end}")
    premieres, total = None, 0
    if not prioritaires:
        sys.exit("Aucune zone prioritaire dans le fichier.")
    for z in prioritaires:
        lignes = lignes_inventaire(chercher_urls(z["forme"], a.start, a.end), z["id"])
        if a.mois:
            lignes = [l for l in lignes if l["date"].startswith(a.mois)]
        total = ecrire_inventaire(lignes, a.sortie)
        etape(f"   {z['id']} : {len(lignes)} scene(s)")
        if premieres is None:
            premieres = lignes
    etape(f"Inventaire enregistre : {a.sortie} ({total} ligne(s) au total)")

    if a.inventaire:
        return
    if not premieres:
        sys.exit(f"Aucune scene GCOV pour {a.mois} sur cette zone." if a.mois
                 else "Aucune scene pour la premiere zone : elargis --start / --end.")
    # Meme orbite et meme direction pour toutes les dates : images comparables
    track = a.track if a.track is not None else premieres[0]["track"]
    serie = [l for l in premieres if l["track"] == track]
    if not serie:
        sys.exit(f"Aucune scene sur l'orbite {track}. Orbites disponibles : "
                 f"{sorted({l['track'] for l in premieres})}")
    serie = serie[:a.n]
    etape(f"Etape 3/3 - lecture de {len(serie)} date(s) sur l'orbite {track} "
          f"({serie[0]['direction']}) pour {prioritaires[0]['id']}")
    fs = connexion()
    for i, l in enumerate(serie, 1):
        etape(f"--- date {i}/{len(serie)} : {l['date']} ---")
        # Avec --mois et une seule date, le fichier porte le nom du mois
        suffixe = a.mois if a.mois and len(serie) == 1 else l["date"]
        lire_fenetre(fs, l["url"], prioritaires[0]["forme"], suffixe, l["date"])
    etape("Termine.")


if __name__ == "__main__":
    main()