"""Render case/*.stl to case/preview.png from a few angles (matplotlib)."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import stl


def draw(ax, path, elev, azim, title):
    mesh = stl.Mesh.from_file(str(path))
    tris = mesh.vectors
    normals = mesh.normals / (np.linalg.norm(mesh.normals, axis=1, keepdims=True) + 1e-9)
    light = np.array([0.4, -0.5, 0.75])
    shade = 0.35 + 0.65 * np.clip(normals @ light, 0, 1)
    colors = np.c_[shade * 0.95, shade * 0.75, shade * 0.3, np.ones(len(shade))]
    ax.add_collection3d(Poly3DCollection(tris, facecolors=colors, edgecolors="none"))
    lo, hi = tris.min(axis=(0, 1)), tris.max(axis=(0, 1))
    mid, span = (lo + hi) / 2, (hi - lo).max() / 2
    ax.set_xlim(mid[0] - span, mid[0] + span)
    ax.set_ylim(mid[1] - span, mid[1] + span)
    ax.set_zlim(mid[2] - span, mid[2] + span)
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    ax.set_title(title, fontsize=9)


def main():
    case = Path(__file__).resolve().parents[1] / "case"
    fig = plt.figure(figsize=(14, 10))
    views = [
        ("car_case.stl", 28, -125, "front-left, from above"),
        ("car_case.stl", 28, 55, "rear-right, from above"),
        ("car_case.stl", -35, -60, "from below (open side)"),
        ("car_case.stl", 0, -90, "front view"),
        ("car_case_rear.stl", 28, -125, "rear half with the lap lip"),
        ("car_case_front.stl", 28, 55, "front half"),
    ]
    for i, (name, elev, azim, title) in enumerate(views, 1):
        draw(fig.add_subplot(2, 3, i, projection="3d"), case / name, elev, azim, title)
    fig.tight_layout()
    fig.savefig(case / "preview.png", dpi=110)
    print("wrote", case / "preview.png")


if __name__ == "__main__":
    main()
