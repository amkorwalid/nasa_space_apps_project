"""
Surface d'eau mensuelle d'un reservoir avec Sentinel-1 (VV) dans Google Earth Engine.
Meme methode que la detection NISAR (Contrat 5), mais calculee sur les serveurs
de Google : rien a telecharger, historique complet depuis 2015.

Sortie : data/processed/monthly_area_s1.csv (Contrat 2, sensor = S1)

Avant la premiere utilisation :
    python -m pip install earthengine-api numpy shapely
    earthengine authenticate
Il faut un projet Google Cloud active pour Earth Engine (gratuit pour un usage non commercial).

Utilisation :
    python sentinel1_gee.py al_massira.geojson --id MAR_0001 --project MON_PROJET_GEE
    python sentinel1_gee.py al_massira.geojson --id MAR_0001 --project MON_PROJET_GEE --start 2015-01 --end 2026-11
    python sentinel1_gee.py al_massira.geojson --id MAR_0001 --project MON_PROJET_GEE --start 2026-01 --end 2026-11 --images
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.request

import numpy as np
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

FALLBACK_DB = -18.0                 # seuil de secours VV, a fixer avec l'equipe apres les tests
SEUIL_PLAUSIBLE = (-24.0, -13.0)    # un seuil d'Otsu hors de cette plage est remplace par le secours
MARGE_ZONE_M = 500                  # l'eau est cherchee jusqu'a 500 m autour du contour
MARGE_TERRE_M = 1000                # terre gardee autour du lac pour l'histogramme
ECHELLE_M = 10                      # taille de pixel du calcul = pixel natif de Sentinel-1 GRD
TACHE_MIN_PX = 100                  # taches d'eau isolees de moins de 100 pixels (1 ha) supprimees
HIST = (-35.0, 0.0, 140)            # histogramme VV : min, max, nombre de classes
LOT = 24                            # nombre de mois traites par requete
COLONNES = ["reservoir_id", "month", "sensor", "area_km2", "n_obs", "quality"]
DEBUT = time.time()


def etape(message):
    print(f"[{time.time() - DEBUT:5.0f} s] {message}", flush=True)


# ----------------------------------------------------------------------------
# Lecture du polygone (memes regles que polygone.py)
# ----------------------------------------------------------------------------
def profondeur(c):
    n = 0
    while isinstance(c, list) and c:
        n += 1
        c = c[0]
    return n


def lire_forme(chemin):
    data = json.load(open(chemin, encoding="utf-8"))
    if data.get("type") == "FeatureCollection":
        geoms = [f["geometry"] for f in data["features"] if f.get("geometry")]
    elif data.get("type") == "Feature":
        geoms = [data["geometry"]]
    else:
        geoms = [data]
    formes = []
    for g in geoms:
        if g.get("type") in ("Polygon", "MultiPolygon"):
            vrai = {3: "Polygon", 4: "MultiPolygon"}.get(profondeur(g["coordinates"]))
            if vrai and vrai != g["type"]:
                g = {"type": vrai, "coordinates": g["coordinates"]}
        f = shape(g)
        formes.append(f if f.is_valid else f.buffer(0))
    if not formes:
        sys.exit("Aucune geometrie dans le fichier GeoJSON.")
    forme = unary_union(formes) if len(formes) > 1 else formes[0]
    # Contour allege (environ 20 m) : Earth Engine refuse les requetes trop lourdes
    return forme.simplify(0.0002)


# ----------------------------------------------------------------------------
# Otsu a partir d'un histogramme
# ----------------------------------------------------------------------------
def otsu_histogramme(centres, comptes):
    """Seuil d'Otsu sur un histogramme. Renvoie (seuil, 'otsu' ou 'secours')."""
    comptes = np.asarray(comptes, float)
    centres = np.asarray(centres, float)
    total = comptes.sum()
    if total <= 0:
        return FALLBACK_DB, "secours"
    w0 = np.cumsum(comptes)
    w1 = total - w0
    s0 = np.cumsum(comptes * centres)
    with np.errstate(divide="ignore", invalid="ignore"):
        m0 = s0 / w0
        m1 = (s0[-1] - s0) / w1
        variance = w0 * w1 * (m0 - m1) ** 2
    variance[~np.isfinite(variance)] = -1
    i = int(np.argmax(variance))
    if i + 1 >= len(centres):
        return FALLBACK_DB, "secours"
    seuil = float((centres[i] + centres[i + 1]) / 2)
    if not (SEUIL_PLAUSIBLE[0] <= seuil <= SEUIL_PLAUSIBLE[1]):
        return FALLBACK_DB, "secours"
    return seuil, "otsu"


def liste_mois(debut, fin):
    a, m = int(debut[:4]), int(debut[5:7])
    af, mf = int(fin[:4]), int(fin[5:7])
    mois = []
    while (a, m) <= (af, mf):
        mois.append(f"{a}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return mois


def fusionner_csv(chemin, lignes):
    tout = {}
    if os.path.isfile(chemin):
        with open(chemin, newline="", encoding="utf-8") as f:
            for l in csv.DictReader(f):
                tout[(l["reservoir_id"], l["month"], l["sensor"])] = l
    for l in lignes:
        tout[(l["reservoir_id"], l["month"], l["sensor"])] = l
    os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLONNES)
        w.writeheader()
        w.writerows(sorted(tout.values(), key=lambda l: (l["reservoir_id"], l["month"])))


# ----------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Surface d'eau mensuelle Sentinel-1 (Earth Engine)")
    p.add_argument("geojson")
    p.add_argument("--id", required=True, help="identifiant du reservoir, ex. MAR_0001")
    p.add_argument("--project", default=os.environ.get("GEE_PROJECT"),
                   help="identifiant du projet Google Cloud active pour Earth Engine")
    p.add_argument("--start", default="2015-01", help="premier mois, AAAA-MM")
    p.add_argument("--end", default=time.strftime("%Y-%m"), help="dernier mois, AAAA-MM")
    p.add_argument("--orbite", type=int, default=None,
                   help="orbite relative Sentinel-1 a utiliser (par defaut : la plus frequente)")
    p.add_argument("--images", action="store_true",
                   help="enregistre aussi une image par mois (apercu radar + eau, et PNG web)")
    p.add_argument("--taille", type=int, default=3000,
                   help="largeur des images en pixels (3000 = environ 10 m par pixel pour un lac de 30 km)")
    p.add_argument("--sortie", default=os.path.join("data", "processed", "monthly_area_s1.csv"))
    a = p.parse_args()
    if not a.project:
        sys.exit("Indique ton projet Earth Engine avec --project (ou la variable GEE_PROJECT).")

    import ee

    etape("Connexion a Earth Engine...")
    ee.Initialize(project=a.project)

    forme = lire_forme(a.geojson)
    lac = ee.Geometry(mapping(forme))
    zone = lac.buffer(MARGE_ZONE_M)                       # ou l'eau est cherchee
    fenetre = lac.bounds().buffer(MARGE_TERRE_M).bounds()  # eau + terre, pour l'histogramme

    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD")
          .filterBounds(lac)
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
          .select("VV"))

    # Une seule orbite relative : meme angle de vue pour toutes les dates
    orbites = s1.aggregate_histogram("relativeOrbitNumber_start").getInfo()
    if not orbites:
        sys.exit("Aucune image Sentinel-1 sur cette zone.")
    etape("Images par orbite relative : " + ", ".join(f"{int(float(k))}: {int(v)}" for k, v in sorted(orbites.items())))
    orbite = a.orbite if a.orbite is not None else int(float(max(orbites, key=orbites.get)))
    s1 = s1.filter(ee.Filter.eq("relativeOrbitNumber_start", orbite))
    etape(f"Orbite utilisee : {orbite}")

    def image_du_mois(d0):
        col = s1.filterDate(d0, d0.advance(1, "month"))
        # mediane du mois puis filtre median 5x5 (Contrat 5)
        img = col.median().focal_median(radius=2, kernelType="square", units="pixels")
        return col, img

    def histogramme(mois):
        d0 = ee.Date(ee.String(mois).cat("-01"))
        col, img = image_du_mois(d0)
        n = col.size()
        hist = ee.Algorithms.If(
            n.gt(0),
            ee.Array(img.reduceRegion(ee.Reducer.fixedHistogram(*HIST), fenetre, ECHELLE_M,
                                      maxPixels=1e9).get("VV")).toList(),
            [],
        )
        return ee.Dictionary({"month": mois, "n_obs": n, "hist": hist})

    def eau_du_mois(mois, seuil):
        """Image VV filtree du mois et masque d'eau (1 = eau) limite a la zone de recherche."""
        d0 = ee.Date(ee.String(mois).cat("-01"))
        _, img = image_du_mois(d0)
        eau = img.lt(ee.Number(seuil))
        eau = eau.focal_min(1, "square", "pixels").focal_max(1, "square", "pixels")   # ouverture 3x3
        # Supprime les petites taches isolees (fausses detections eparpillees)
        taille = eau.selfMask().connectedPixelCount(TACHE_MIN_PX + 1, True)
        eau = eau.selfMask().updateMask(taille.gte(TACHE_MIN_PX)).unmask(0)
        return img, eau.clip(zone)

    def enregistrer_images(mois, seuil, limites):
        """Telecharge trois PNG : radar seul, apercu (radar + eau en bleu) et image web (eau seule, fond transparent)."""
        img, eau = eau_du_mois(mois, seuil)
        # Le masque d'eau est fige sur la grille du calcul de surface (ECHELLE_M),
        # pour que le bleu de l'image corresponde exactement au chiffre du CSV.
        eau = eau.reproject(ee.Projection("EPSG:4326").atScale(ECHELLE_M))
        bleu = eau.selfMask().visualize(palette=["1e78dc"])
        apercu = img.visualize(min=-25, max=0).blend(bleu)
        base = {"region": fenetre, "dimensions": a.taille, "format": "png", "crs": "EPSG:4326"}
        # Image radar seule (avant le masque), puis la meme avec l'eau en bleu
        urllib.request.urlretrieve(img.visualize(min=-25, max=0).getThumbURL(base),
                                   os.path.join(d_radar, f"{a.id}_{mois}.png"))
        urllib.request.urlretrieve(apercu.getThumbURL(base),
                                   os.path.join(d_apercus, f"{a.id}_{mois}.png"))
        cle = f"{a.id}_{mois}"
        urllib.request.urlretrieve(bleu.getThumbURL(base), os.path.join(d_web, cle + ".png"))
        index[cle] = {"bounds": limites}

    def aire(paire):
        paire = ee.List(paire)
        _, eau = eau_du_mois(paire.get(0), paire.get(1))
        m2 = eau.multiply(ee.Image.pixelArea()).reduceRegion(
            ee.Reducer.sum(), zone, ECHELLE_M, maxPixels=1e9).get("VV")
        return ee.Dictionary({"month": paire.get(0), "area_m2": m2})

    # Dossiers et limites des images (separes des images NISAR pour ne pas les ecraser)
    racine = os.path.dirname(a.sortie) or "."
    d_apercus, d_web = os.path.join(racine, "quicklooks_s1"), os.path.join(racine, "extents_s1")
    d_radar = os.path.join(racine, "radar_s1")
    f_index = os.path.join(d_web, "index.json")
    index, limites = {}, None
    if a.images:
        os.makedirs(d_apercus, exist_ok=True)
        os.makedirs(d_radar, exist_ok=True)
        os.makedirs(d_web, exist_ok=True)
        if os.path.isfile(f_index):
            index = json.load(open(f_index, encoding="utf-8"))
        coins = fenetre.coordinates().getInfo()[0]
        lons, lats = [c[0] for c in coins], [c[1] for c in coins]
        limites = [[round(min(lons), 6), round(min(lats), 6)], [round(max(lons), 6), round(max(lats), 6)]]

    mois = liste_mois(a.start, a.end)
    etape(f"{len(mois)} mois a traiter, de {mois[0]} a {mois[-1]}")
    lignes = []
    for i in range(0, len(mois), LOT):
        lot = mois[i:i + LOT]
        infos = ee.List(lot).map(histogramme).getInfo()
        seuils = {}
        for info in infos:
            if info["n_obs"] > 0 and info["hist"]:
                h = np.array(info["hist"], float)
                centres = h[:, 0] + (HIST[1] - HIST[0]) / HIST[2] / 2
                seuils[info["month"]] = otsu_histogramme(centres, h[:, 1]) + (info["n_obs"],)
        if seuils:
            paires = [[m, s[0]] for m, s in seuils.items()]
            for r in ee.List(paires).map(aire).getInfo():
                seuil, methode, n_obs = seuils[r["month"]]
                if methode == "secours":
                    qualite = "partial"
                else:
                    qualite = "good" if n_obs >= 2 else "partial"
                lignes.append({"reservoir_id": a.id, "month": r["month"], "sensor": "S1",
                               "area_km2": round((r["area_m2"] or 0) / 1e6, 3),
                               "n_obs": n_obs, "quality": qualite})
                print(f"        {r['month']} : {lignes[-1]['area_km2']:8.2f} km2, "
                      f"{n_obs} image(s), seuil {seuil:.1f} dB ({methode})")
                if a.images:
                    try:
                        enregistrer_images(r["month"], seuil, limites)
                    except Exception as e:
                        print(f"          image non enregistree pour {r['month']} : {e}")
        if a.images:
            with open(f_index, "w", encoding="utf-8") as f:
                json.dump(index, f, indent=1)
        fusionner_csv(a.sortie, lignes)
        etape(f"{min(i + LOT, len(mois))}/{len(mois)} mois traites")

    etape(f"Termine : {len(lignes)} mois avec donnees, enregistres dans {a.sortie}")
    if a.images:
        etape(f"Images : radar seul dans {d_radar}, radar + eau dans {d_apercus}, images web dans {d_web}")


if __name__ == "__main__":
    main()