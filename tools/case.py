"""3D-printable hood for the car: a rounded shell that sits over the plywood
chassis, the motors, the L298N and the Nucleo, with wheel cutouts, a USB
slot at the front, a vent and cable opening at the rear, roof vents over
the motor driver, a window over the Nucleo's buttons and LEDs, and two
grooves for the zip ties that hold it down.

Writes case/car_case.stl (one piece, 155 x 220 x 66 mm, needs a bed that
long) and case/car_case_front.stl + car_case_rear.stl (the same hood split
at the wheel arches with a 10 mm lap joint and two M3 holes, each half about
155 x 115 mm). Print upside down (roof on the bed), no supports needed.

Frame: x across the car (right is +), y along it (front is +), z up, with
z = 0 at the top surface of the plywood plate and y = 0 at the wheel axle.
Every dimension is in millimetres and lives in the PARAMS block.

    pip install manifold3d numpy-stl
    python tools/case.py
"""

from pathlib import Path

from manifold3d import Manifold
import numpy as np
import stl

PARAMS = dict(
    inner_w=150.0,        # plate is 127 wide plus ~8 mm of tabs each side
    rear=58.0,            # inner wall behind the axle (heatsink ends at ~51)
    front=157.0,          # inner wall ahead of the axle (Nucleo ends at ~151)
    inner_h=55.0,         # above the plate; wheel top ~44, heatsink ~40
    wall=2.4,
    roof=2.4,
    skirt=8.0,            # walls reach this far below the plate's top surface
    corner_r=8.0,         # rounded vertical and roof edges
    wheel_r=32.5,         # 65 mm wheels
    wheel_clear=5.5,
    axle_z=11.0,          # axle height above the plate (TT motor on its side)
    usb_x=-16.0,          # micro-USB on the ST-LINK end, left of centre
    split_y=50.0,         # where the two-piece version is cut
    seg=96,               # circle resolution
)


def rounded_box(w, length, y0, z0, h, r, seg):
    """Box with rounded vertical edges and a rounded roof edge, spanning
    x in [-w/2, w/2], y in [y0, y0 + length], z in [z0, z0 + h]."""
    xs = (-w / 2 + r, w / 2 - r)
    ys = (y0 + r, y0 + length - r)
    parts = []
    for x in xs:
        for y in ys:
            parts.append(Manifold.cylinder(h - r, r, circular_segments=seg)
                         .translate([x, y, z0]))
            parts.append(Manifold.sphere(r, circular_segments=seg)
                         .translate([x, y, z0 + h - r]))
    return Manifold.batch_hull(parts)


def box(x0, x1, y0, y1, z0, z1):
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def build(p):
    t, roof, r, seg = p["wall"], p["roof"], p["corner_r"], p["seg"]
    outer_w = p["inner_w"] + 2 * t
    y0 = -p["rear"] - t
    length = p["rear"] + p["front"] + 2 * t
    z0 = -p["skirt"]
    outer_h = p["skirt"] + p["inner_h"] + roof

    shell = rounded_box(outer_w, length, y0, z0, outer_h, r, seg)
    cavity = rounded_box(p["inner_w"], length - 2 * t, y0 + t, z0 - 50,
                         outer_h - roof + 50, max(r - t, 1.0), seg)
    shell = shell - cavity

    # Wheel arches through both side walls, from below the skirt to the
    # top of the wheel, with a rounded top.
    arch_r = p["wheel_r"] + p["wheel_clear"]
    arch = (Manifold.cylinder(outer_w + 20, arch_r, circular_segments=seg)
            .rotate([0, 90, 0]).translate([-outer_w / 2 - 10, 0, p["axle_z"]]))
    arch = arch + box(-outer_w / 2 - 10, outer_w / 2 + 10, -arch_r, arch_r,
                      z0 - 1, p["axle_z"])
    shell = shell - arch

    # Front: micro-USB slot (ST-LINK, left of centre) and a notch for wires.
    front_y = p["front"]
    shell = shell - box(p["usb_x"] - 22, p["usb_x"] + 22, front_y - 1,
                        front_y + t + 1, 6, 36)
    shell = shell - box(18, 32, front_y - 1, front_y + t + 1, z0 - 1, 14)

    # Rear: opening for the heatsink's air and the motor and power wires.
    rear_y = -p["rear"]
    shell = shell - box(-40, 40, rear_y - t - 1, rear_y + 1, 4, 38)

    # Roof vents over the motor driver, and a window over the Nucleo's
    # buttons and LEDs (its rear end sits ~14 mm ahead of the axle).
    z_roof = p["inner_h"] - 1
    for y in np.arange(-44, 0, 9.0):
        shell = shell - box(-35, 35, y, y + 3.5, z_roof, z_roof + roof + 2)
    window = box(-35, 35, 12, 34, z_roof, z_roof + roof + 2)
    shell = shell - window

    # Two shallow grooves around the hood for the zip ties that hold it on.
    for y in (62.0, 122.0):
        ring = box(-outer_w, outer_w, y - 3, y + 3, z0 - 1, z0 + outer_h + 1)
        inside = box(-outer_w / 2 + 1.2, outer_w / 2 - 1.2, y - 4, y + 4,
                     z0 - 2, z0 + outer_h - 1.2)
        shell = shell - (ring - inside)
    return shell


def split(shell, p):
    """Rear and front halves with a lap joint: the rear half carries a lip
    that slides inside the front half, with two M3 holes through both."""
    t, r, seg = p["wall"], p["corner_r"], p["seg"]
    outer_w = p["inner_w"] + 2 * t
    y0 = -p["rear"] - t
    length = p["rear"] + p["front"] + 2 * t
    z0 = -p["skirt"]
    outer_h = p["skirt"] + p["inner_h"] + p["roof"]
    clear, lip_t, lip_len = 0.3, 1.6, 10.0
    ys = p["split_y"]
    lip_outer = rounded_box(outer_w - 2 * (t + clear), length - 2 * (t + clear),
                            y0 + t + clear, z0, outer_h - t - clear,
                            max(r - t - clear, 1.0), seg)
    lip_inner = rounded_box(outer_w - 2 * (t + clear + lip_t),
                            length - 2 * (t + clear + lip_t),
                            y0 + t + clear + lip_t, z0 - 50,
                            outer_h - t - clear - lip_t + 50,
                            max(r - t - clear - lip_t, 1.0), seg)
    lip = (lip_outer - lip_inner) ^ box(-outer_w, outer_w, ys, ys + lip_len,
                                        z0 - 1, z0 + outer_h + 1)
    screws = Manifold.batch_boolean([
        Manifold.cylinder(outer_w + 20, 1.6, circular_segments=32)
        .rotate([0, 90, 0]).translate([-outer_w / 2 - 10, ys + lip_len / 2, 30])
    ], 0)
    half_rear = shell ^ box(-outer_w, outer_w, y0 - 1, ys, z0 - 1, z0 + outer_h + 1)
    half_front = shell ^ box(-outer_w, outer_w, ys, y0 + length + 1,
                             z0 - 1, z0 + outer_h + 1)
    return (half_rear + lip) - screws, half_front - screws


def save(manifold, path):
    mesh = manifold.to_mesh()
    verts = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
    tris = np.asarray(mesh.tri_verts, dtype=np.int64)
    data = np.zeros(len(tris), dtype=stl.Mesh.dtype)
    data["vectors"] = verts[tris]
    out = stl.Mesh(data)
    out.save(str(path))
    lo = manifold.bounding_box()
    print(f"{path.name}: {len(tris)} triangles, "
          f"{lo[3] - lo[0]:.1f} x {lo[4] - lo[1]:.1f} x {lo[5] - lo[2]:.1f} mm, "
          f"{manifold.volume() / 1000:.1f} cm3 of plastic, status {manifold.status()}")


def main():
    out = Path(__file__).resolve().parents[1] / "case"
    out.mkdir(exist_ok=True)
    shell = build(PARAMS)
    save(shell, out / "car_case.stl")
    rear, front = split(shell, PARAMS)
    save(rear, out / "car_case_rear.stl")
    save(front, out / "car_case_front.stl")


if __name__ == "__main__":
    main()
