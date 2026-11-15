import numpy as np
import matplotlib.pyplot as plt

d = np.load("fenetre_2026-08.npz")
print(d.files)                 # liste des tableaux
hh = d["hh_db"]
print(hh.shape, np.nanmin(hh), np.nanmax(hh))

plt.imshow(hh, cmap="gray", vmin=-30, vmax=0)
plt.colorbar(label="HH (dB)")
plt.show()