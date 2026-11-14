"""
Piste B - detection d'eau NISAR (etapes 3 a 7 du guide, Contrat 5).

Entree  : les fichiers fenetre_<date>.npz ecrits par polygone.py
Sorties :
    data/processed/monthly_area_nisar.csv          (Contrat 2, une ligne par reservoir-mois)
    data/processed/scene_areas_nisar.csv           (une ligne par scene, pour le controle)
    data/processed/extents/<id>_<AAAA-MM>.png      (eau en bleu, fond transparent, EPSG:4326)
    data/processed/extents/index.json              (limites de chaque PNG)
    data/processed/quicklooks/<id>_<date>.png      (image radar + contour de l'eau, a verifier a l'oeil)

Installation :
    python -m pip install numpy scipy scikit-image rasterio matplotlib pillow

Utilisation :
    python detect_water.py --id MAR_0001
    python detect_water.py --id MAR_0001 --hv            (regle HV en plus, pour le sable sec)
    python detect_water.py --id MAR_0001 --fichiers "fenetre_2026-10*.npz"
"""

import argparse
import csv
import glob
import json
import os
import re
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import array_bounds, from_origin
from rasterio.warp import Resampling, calculate_default_transform, reproject
from scipy.ndimage import binary_dilation, binary_opening, label, median_filter
from skimage.filters import threshold_otsu

FALLBACK_DB = -18.0          # seuil de secours, a fixer avec la piste C apres les tests
SEUIL_PLAUSIBLE = (-30.0, -10.0)   # un seuil d'Otsu hors de cette plage est juge non fiable
MARGE_ZONE_M = 500           # l'eau est cherchee jusqu'a 500 m autour du contour du lac
MASQUE_INVALIDE = (0, 255)   # valeurs de la couche "mask" du GCOV a exclure (a confirmer dans gcov_notes.md)
BLEU = (30, 120, 220, 200)   # couleur de l'eau dans les PNG web


def charger(chemin):
    d = np.load(chemin, allow_pickle=False)
    hh, x, y = d["hh_db"], d["x"], d["y"]
    hv = d["hv_db"] if "hv_db" in d.files and d["hv_db"].shape == hh.shape else None
    masque = d["mask"] if "mask" in d.files and d["mask"].shape == hh.shape else None
    inside = d["inside"]
    if y[0] < y[-1]:                      # on veut le nord en haut
        y = y[::-1]
        hh, inside = hh[::-1], inside[::-1]
        hv = hv[::-1] if hv is not None else None
        masque = masque[::-1] if masque is not None else None
    date = str(d["date"]) if "date" in d.files else ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        m = re.search(r"(\d{4}-\d{2}(-\d{2})?)", os.path.basename(chemin))
        date = m.group(1) if m else ""
    return {"hh": hh, "hv": hv, "masque": masque, "inside": inside, "x": x, "y": y,
            "epsg": int(d["epsg"]), "date": date, "fichier": chemin}


def seuil_otsu(valeurs):
    """Seuil d'Otsu, ou seuil de secours s'il n'est pas plausible."""
    try:
        t = float(threshold_otsu(valeurs))
    except ValueError:
        return FALLBACK_DB, "secours"
    if not (SEUIL_PLAUSIBLE[0] <= t <= SEUIL_PLAUSIBLE[1]):
        return FALLBACK_DB, "secours"
    return t, "otsu"


def detecter(s, regle_hv, ignorer_masque=False):
    """Contrat 5 : filtre median 5x5, Otsu sur HH, zone de recherche, ouverture 3x3,
    suppression des taches de moins de 10 pixels."""
    dx, dy = abs(s["x"][1] - s["x"][0]), abs(s["y"][1] - s["y"][0])
    fini = np.isfinite(s["hh"])
    valide = fini.copy()
    if s["masque"] is not None and not ignorer_masque:
        valide &= ~np.isin(s["masque"], MASQUE_INVALIDE)
    if not valide.any():
        sys.exit(f"Aucun pixel valide dans {s['fichier']} : la scene ne couvre pas la zone.")
    hh = median_filter(np.where(valide, s["hh"], np.nanmedian(s["hh"][valide])), size=5)

    seuil, methode = seuil_otsu(hh[valide])
    zone = binary_dilation(s["inside"], iterations=max(1, int(round(MARGE_ZONE_M / dx))))
    eau = (hh < seuil) & zone & valide

    if regle_hv and s["hv"] is not None:
        ok_hv = valide & np.isfinite(s["hv"])
        hv = median_filter(np.where(ok_hv, s["hv"], np.nanmedian(s["hv"][ok_hv])), size=5)
        seuil_hv, _ = seuil_otsu(hv[ok_hv])
        if seuil_hv == FALLBACK_DB:
            seuil_hv = FALLBACK_DB - 6          # HV est plus faible que HH
        eau &= hv < seuil_hv

    eau = binary_opening(eau, structure=np.ones((3, 3), bool))
    etiquettes, _ = label(eau)                      # supprime les taches de moins de 10 pixels
    tailles = np.bincount(etiquettes.ravel())
    eau = eau & (tailles[etiquettes] >= 10)
    diag = f"hors scene {100 * (~fini[zone]).mean():.0f} %"
    if s["masque"] is not None:
        valeurs, comptes = np.unique(s["masque"][zone], return_counts=True)
        detail = ", ".join(f"{int(v)}: {100 * c / zone.sum():.0f} %" for v, c in zip(valeurs, comptes))
        diag += f" | valeurs du masque GCOV dans la zone -> {detail}"
    return {
        "diag": diag,
        "eau": eau, "hh": hh, "zone": zone, "valide": valide, "seuil": seuil, "methode": methode,
        "aire_km2": float(eau.sum() * dx * dy / 1e6),
        "part_valide": float(valide[zone].mean()) if zone.any() else 0.0,
        "dx": dx, "dy": dy,
    }


def apercu(s, r, chemin, titre):
    plt.figure(figsize=(9, 6))
    plt.imshow(r["hh"], cmap="gray", vmin=-30, vmax=0)
    bleu = np.zeros(r["eau"].shape + (4,))
    bleu[r["eau"]] = (0.12, 0.47, 0.86, 0.75)          # eau remplie en bleu
    plt.imshow(bleu, interpolation="nearest")
    plt.contour(r["zone"], levels=[0.5], colors="red", linewidths=0.6, linestyles="dashed")
    plt.title(titre)
    plt.axis("off")
    plt.savefig(chemin, dpi=140, bbox_inches="tight")
    plt.close()


def png_web(eau, s, dx, dy, chemin):
    """Masque -> PNG transparent en EPSG:4326. Renvoie [[minLon, minLat], [maxLon, maxLat]]."""
    h, w = eau.shape
    src_tr = from_origin(s["x"][0] - dx / 2, s["y"][0] + dy / 2, dx, dy)
    src_crs, dst_crs = CRS.from_epsg(s["epsg"]), CRS.from_epsg(4326)
    gauche, bas, droite, haut = array_bounds(h, w, src_tr)
    dst_tr, dw, dh = calculate_default_transform(src_crs, dst_crs, w, h, gauche, bas, droite, haut)
    dst = np.zeros((dh, dw), np.uint8)
    reproject(eau.astype(np.uint8), dst, src_transform=src_tr, src_crs=src_crs,
              dst_transform=dst_tr, dst_crs=dst_crs, resampling=Resampling.nearest)
    rgba = np.zeros((dh, dw, 4), np.uint8)
    rgba[dst == 1] = BLEU
    Image.fromarray(rgba, "RGBA").save(chemin)
    o, sud, e, n = array_bounds(dh, dw, dst_tr)
    return [[round(o, 6), round(sud, 6)], [round(e, 6), round(n, 6)]]


def fusionner_csv(chemin, lignes, cles, colonnes):
    tout = {}
    if os.path.isfile(chemin):
        with open(chemin, newline="", encoding="utf-8") as f:
            for l in csv.DictReader(f):
                tout[tuple(l[k] for k in cles)] = l
    for l in lignes:
        tout[tuple(str(l[k]) for k in cles)] = l
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=colonnes)
        w.writeheader()
        w.writerows(sorted(tout.values(), key=lambda l: tuple(str(l[k]) for k in cles)))


def main():
    p = argparse.ArgumentParser(description="Detection d'eau NISAR sur les fenetres .npz")
    p.add_argument("--id", required=True, help="identifiant du reservoir, ex. MAR_0001")
    p.add_argument("--fichiers", default="fenetre_*.npz", help="motif des fichiers a traiter")
    p.add_argument("--hv", action="store_true", help="l'eau doit aussi etre sombre en HV")
    p.add_argument("--ignorer-masque", action="store_true",
                   help="n'utilise pas la couche mask du GCOV (pour tester si elle est mal interpretee)")
    p.add_argument("--data", default=os.path.join("data", "processed"))
    a = p.parse_args()

    chemins = sorted(glob.glob(a.fichiers))
    if not chemins:
        sys.exit(f"Aucun fichier ne correspond a {a.fichiers}")
    d_ext, d_ql = os.path.join(a.data, "extents"), os.path.join(a.data, "quicklooks")
    os.makedirs(d_ext, exist_ok=True)
    os.makedirs(d_ql, exist_ok=True)

    # ---- Detection scene par scene -----------------------------------------
    par_mois, lignes_scenes = defaultdict(list), []
    for chemin in chemins:
        s = charger(chemin)
        if len(s["date"]) < 7:
            print("Date introuvable, fichier ignore :", chemin)
            continue
        r = detecter(s, a.hv, a.ignorer_masque)
        print(f"{s['date']} : seuil {r['seuil']:.1f} dB ({r['methode']}), "
              f"eau {r['aire_km2']:.2f} km2, pixels valides {100 * r['part_valide']:.0f} %")
        print("      diagnostic :", r["diag"])
        apercu(s, r, os.path.join(d_ql, f"{a.id}_{s['date']}.png"),
               f"{a.id} {s['date']} - eau {r['aire_km2']:.1f} km2 (seuil {r['seuil']:.1f} dB)")
        lignes_scenes.append({"reservoir_id": a.id, "date": s["date"], "area_km2": round(r["aire_km2"], 3),
                              "threshold_db": round(r["seuil"], 2), "threshold_method": r["methode"],
                              "valid_fraction": round(r["part_valide"], 3)})
        par_mois[s["date"][:7]].append((s, r))
    fusionner_csv(os.path.join(a.data, "scene_areas_nisar.csv"), lignes_scenes, ["reservoir_id", "date"],
                  ["reservoir_id", "date", "area_km2", "threshold_db", "threshold_method", "valid_fraction"])

    # ---- Composite mensuel : eau si detectee dans au moins 50 % des scenes --
    f_index = os.path.join(d_ext, "index.json")
    index = json.load(open(f_index, encoding="utf-8")) if os.path.isfile(f_index) else {}
    lignes_mois = []
    for mois, scenes in sorted(par_mois.items()):
        forme = scenes[0][1]["eau"].shape
        memes = [(s, r) for s, r in scenes if r["eau"].shape == forme]
        if len(memes) < len(scenes):
            print(f"  {mois} : {len(scenes) - len(memes)} scene(s) sur une autre grille ignoree(s) "
                  "(utilise la meme orbite pour toutes les dates)")
        pile = np.stack([r["eau"] for _, r in memes])
        composite = pile.mean(axis=0) >= 0.5
        s0, r0 = memes[0]
        aire = float(composite.sum() * r0["dx"] * r0["dy"] / 1e6)
        part_valide = float(np.mean([r["part_valide"] for _, r in memes]))
        secours = any(r["methode"] == "secours" for _, r in memes)
        if part_valide < 0.7:
            qualite = "bad"
        elif len(memes) < 2 or part_valide < 0.9 or secours:
            qualite = "partial"
        else:
            qualite = "good"
        cle = f"{a.id}_{mois}"
        index[cle] = {"bounds": png_web(composite, s0, r0["dx"], r0["dy"], os.path.join(d_ext, cle + ".png"))}
        lignes_mois.append({"reservoir_id": a.id, "month": mois, "sensor": "NISAR",
                            "area_km2": round(aire, 3), "n_obs": len(memes), "quality": qualite})
        print(f"  {mois} : {aire:.2f} km2 sur {len(memes)} scene(s), qualite {qualite}")

    with open(f_index, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1)
    fusionner_csv(os.path.join(a.data, "monthly_area_nisar.csv"), lignes_mois,
                  ["reservoir_id", "month", "sensor"],
                  ["reservoir_id", "month", "sensor", "area_km2", "n_obs", "quality"])
    print(f"Termine. Verifie a l'oeil les images de {d_ql}")


if __name__ == "__main__":
    main()