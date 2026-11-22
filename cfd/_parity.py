"""Numba ray-parity kernel (moved from research/sidepod_region/voxelize_fast.py)."""
import numpy as np
from numba import njit


@njit(cache=True)
def parity(tri, A, B, C, nA, nB, nC):
    """tri (n,3,3) in (a,b,c) order; rays along c through cell centres (A[i], B[j])."""
    hits = [[0.0 for _ in range(0)] for _ in range(nA * nB)]
    da = A[1] - A[0]; db = B[1] - B[0]
    for t in range(tri.shape[0]):
        p0, p1, p2 = tri[t, 0], tri[t, 1], tri[t, 2]
        amin = min(p0[0], p1[0], p2[0]); amax = max(p0[0], p1[0], p2[0])
        bmin = min(p0[1], p1[1], p2[1]); bmax = max(p0[1], p1[1], p2[1])
        i0 = max(0, int(np.ceil((amin - A[0]) / da))); i1 = min(nA - 1, int(np.floor((amax - A[0]) / da)))
        j0 = max(0, int(np.ceil((bmin - B[0]) / db))); j1 = min(nB - 1, int(np.floor((bmax - B[0]) / db)))
        d = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])
        if abs(d) < 1e-14:
            continue
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                a = A[i] + 1e-7; b = B[j] + 1.3e-7
                u = ((p1[0] - a) * (p2[1] - b) - (p2[0] - a) * (p1[1] - b)) / d
                v = ((p2[0] - a) * (p0[1] - b) - (p0[0] - a) * (p2[1] - b)) / d
                w = 1 - u - v
                if u < 0 or v < 0 or w < 0:
                    continue
                hits[i * nB + j].append(u * p0[2] + v * p1[2] + w * p2[2])
    out = np.zeros((nA, nB, nC), np.bool_)
    c0 = C[0]; dc = C[1] - C[0]
    for i in range(nA):
        for j in range(nB):
            h = np.array(hits[i * nB + j]); h.sort()
            m = []
            for k in range(h.size):
                if len(m) == 0 or h[k] - m[-1] > 1e-6:
                    m.append(h[k])
            for k in range(0, len(m) - 1, 2):
                k0 = max(0, int(np.ceil((m[k] - c0) / dc))); k1 = min(nC - 1, int(np.floor((m[k + 1] - c0) / dc)))
                for c in range(k0, k1 + 1):
                    out[i, j, c] = True
    return out
