# NISAR L2 GCOV notes (Track B)

Written automatically by `pipeline/02_search_download.py` from a real file
(`NISAR_L2_PR_GCOV_035_023_D_072_4005_DHDH_A_20261106T191958_20261106T192028_P05036_N_F_J_001`), so the paths below are verified, not guessed.

| Item | Value |
|---|---|
| Grid group | `/science/LSAR/GCOV/grids/frequencyA` |
| Co-pol backscatter | `/science/LSAR/GCOV/grids/frequencyA/HHHH` (linear power, gamma0) |
| Cross-pol backscatter | `/science/LSAR/GCOV/grids/frequencyA/HVHV` |
| Coordinates | `/science/LSAR/GCOV/grids/frequencyA/xCoordinates`, `yCoordinates` (pixel centres, metres) |
| Projection | `/science/LSAR/GCOV/grids/frequencyA/projection` -> EPSG:32629 |
| Pixel spacing | 10.0 m |
| Mask layer | `/science/LSAR/GCOV/grids/frequencyA/mask` |
| Mask values seen in the window | [1] |

## Mask layer attributes

| Attribute | Value |
|---|---|
| `DIMENSION_LIST` | [array([<HDF5 object reference>], dtype=object)
 array([<HDF5 object reference>], dtype=object)] |
| `_FillValue` | 255 |
| `description` | Mask indicating the subswath number associated with valid GCOV samples. A GCOV sample is only considered valid if it is generated from fully-focused radar samples. If at least one radar sample in the averaging set is partially focused or invalid, the corresponding mask pixel will contain the value 0 |
| `grid_mapping` | projection |
| `long_name` | Valid samples subswath mask |
| `valid_min` | 0 |

Water detection treats mask values listed in `config/settings.yaml`
(`detection.nisar.invalid_mask_values`) as invalid (no data / layover / shadow).
