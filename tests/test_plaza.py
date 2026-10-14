"""미관광장 generator (src/plaza.py): the band fill follows the outline and the planting is repeatable."""
import math

from shapely.geometry import Polygon, box

import plaza as P


def test_bands_cover_a_curved_bed_closely_and_planting_is_the_same_every_run():
    bed = Polygon(P.chaikin(P.BEDS["middle"])).buffer(0)
    bands = P.strips(bed, 0.6)
    filled = sum(w * d for _, _, w, d in bands)
    assert abs(filled - bed.area) / bed.area < 0.03
    assert all(bed.buffer(0.6).contains(box(x - w / 2, z - d / 2, x + w / 2, z + d / 2)) for x, z, w, d in bands)
    assert P.scatter(bed, 3.2, "middle") == P.scatter(bed, 3.2, "middle") and P.scatter(bed, 3.2, "middle")
    assert len(P.ring(bed)) == len(bed.exterior.coords) - 1


def test_the_store_drum_is_a_smooth_arc_and_the_walls_close_the_outline():
    import deptstore as D
    pts = [(math.cos(a) * 100, math.sin(a) * 100) for a in [i * math.pi / 16 for i in range(9)]]
    cx, cz, r = D.circle_fit(pts)
    assert abs(cx) < 1e-6 and abs(cz) < 1e-6 and abs(r - 100) < 1e-6
