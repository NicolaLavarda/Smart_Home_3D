from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

from .models import Point2D, SpatialZoneDefinition


@dataclass(frozen=True)
class PerimeterCrossingEvent:
    """Result of a 2.5D trajectory segment intersecting an oriented perimeter polyline."""

    zone_id: str
    segment_index: int
    direction: Literal["a_to_b", "b_to_a"]
    intersection_xz: tuple[float, float]
    normal_xz: tuple[float, float]


class SpatialGeometryEngine:
    """
    Computational geometry engine for 2.5D polygonal areas and oriented perimeter polylines
    in Three.js world space (+X East, +Y Up, +Z South).
    """

    @staticmethod
    def point_in_polygon_2d(px: float, pz: float, vertices: list[Point2D]) -> bool:
        """
        Ray-casting algorithm on the XZ plane.
        Returns True if (px, pz) lies strictly inside or on the boundary of the polygon.
        """
        n = len(vertices)
        if n < 3:
            return False

        inside = False
        j = n - 1
        for i in range(n):
            xi, zi = float(vertices[i].x), float(vertices[i].z)
            xj, zj = float(vertices[j].x), float(vertices[j].z)

            # Check if point is very close to vertex/edge
            if SpatialGeometryEngine._point_to_segment_dist(px, pz, xi, zi, xj, zj) <= 1e-6:
                return True

            intersects = (zi > pz) != (zj > pz)
            if intersects:
                x_intersect = (xj - xi) * (pz - zi) / ((zj - zi) or 1e-12) + xi
                if px < x_intersect:
                    inside = not inside
            j = i
        return inside

    @staticmethod
    def _point_to_segment_dist(
        px: float,
        pz: float,
        ax: float,
        az: float,
        bx: float,
        bz: float,
    ) -> float:
        dx = bx - ax
        dz = bz - az
        len_sq = dx * dx + dz * dz
        if len_sq <= 1e-12:
            return math.hypot(px - ax, pz - az)
        t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / len_sq))
        proj_x = ax + t * dx
        proj_z = az + t * dz
        return math.hypot(px - proj_x, pz - proj_z)

    @classmethod
    def distance_to_polygon_boundary(cls, px: float, pz: float, vertices: list[Point2D]) -> float:
        """Minimum Euclidean distance in meters from (px, pz) to any polygon edge."""
        n = len(vertices)
        if n < 2:
            return float("inf")
        min_d = float("inf")
        for i in range(n):
            a = vertices[i]
            b = vertices[(i + 1) % n]
            d = cls._point_to_segment_dist(px, pz, a.x, a.z, b.x, b.z)
            if d < min_d:
                min_d = d
        return min_d

    @classmethod
    def is_point_in_zone_25d(
        cls,
        x: float,
        y: float,
        z: float,
        zone: SpatialZoneDefinition,
        *,
        currently_inside: bool = False,
    ) -> bool:
        """
        Evaluate 2.5D polygon containment with spatial hysteresis:
        - If `currently_inside` is False (entering), the point must be inside the polygon
          (and at least `hysteresis_m * 0.25` from edge if polygon is large enough, or simply inside).
        - If `currently_inside` is True (staying inside), the point remains inside even if it
          drifts slightly outside the edge by up to `zone.hysteresis_m`.
        """
        if zone.geometry_type != "polygon" or len(zone.vertices) < 3:
            return False

        y_tol = float(zone.hysteresis_m) if currently_inside else 0.0
        if y < (zone.y_min - y_tol) or y > (zone.y_max + y_tol):
            return False

        raw_inside = cls.point_in_polygon_2d(x, z, zone.vertices)
        if raw_inside:
            return True

        if currently_inside and zone.hysteresis_m > 0.0:
            edge_dist = cls.distance_to_polygon_boundary(x, z, zone.vertices)
            if edge_dist <= zone.hysteresis_m:
                return True

        return False

    @staticmethod
    def compute_segment_normal_xz(
        ax: float,
        az: float,
        bx: float,
        bz: float,
        *,
        flipped: bool = False,
    ) -> tuple[float, float]:
        """
        Compute unit normal vector on the XZ plane for segment A -> B.
        By convention, A -> B direction has normal (-dz, +dx) / ||AB||
        (pointing to the left of A->B in top-down view where +X is right and +Z is down).
        """
        dx = bx - ax
        dz = bz - az
        length = math.hypot(dx, dz)
        if length <= 1e-9:
            return (0.0, 1.0)
        nx = -dz / length
        nz = dx / length
        if flipped:
            return (-nx, -nz)
        return (nx, nz)

    @classmethod
    def check_perimeter_crossing(
        cls,
        prev_xyz: tuple[float, float, float],
        curr_xyz: tuple[float, float, float],
        zone: SpatialZoneDefinition,
    ) -> Optional[PerimeterCrossingEvent]:
        """
        Check if displacement segment `prev_xyz -> curr_xyz` crosses any segment of `zone`.
        Works for both `perimeter` polylines and closed `polygon` boundaries.
        Returns PerimeterCrossingEvent with direction:
        - "a_to_b" if trajectory moves along the positive normal direction (+n)
        - "b_to_a" if trajectory moves against the normal direction (-n)
        """
        verts = zone.vertices
        if len(verts) < 2:
            return None

        px0, py0, pz0 = float(prev_xyz[0]), float(prev_xyz[1]), float(prev_xyz[2])
        px1, py1, pz1 = float(curr_xyz[0]), float(curr_xyz[1]), float(curr_xyz[2])

        mid_y = 0.5 * (py0 + py1)
        if mid_y < (zone.y_min - 0.35) or mid_y > (zone.y_max + 0.35):
            return None

        move_dx = px1 - px0
        move_dz = pz1 - pz0
        if math.hypot(move_dx, move_dz) <= 1e-5:
            return None

        seg_count = len(verts) - 1 if zone.geometry_type == "perimeter" else len(verts)
        for idx in range(seg_count):
            a = verts[idx]
            b = verts[(idx + 1) % len(verts)]
            hit = cls._intersect_segments_2d(px0, pz0, px1, pz1, a.x, a.z, b.x, b.z)
            if hit is None:
                continue

            ix, iz = hit
            nx, nz = cls.compute_segment_normal_xz(
                a.x,
                a.z,
                b.x,
                b.z,
                flipped=zone.normal_flipped,
            )
            dot_n = move_dx * nx + move_dz * nz
            direction: Literal["a_to_b", "b_to_a"] = "a_to_b" if dot_n >= 0.0 else "b_to_a"
            return PerimeterCrossingEvent(
                zone_id=zone.zone_id,
                segment_index=idx,
                direction=direction,
                intersection_xz=(ix, iz),
                normal_xz=(nx, nz),
            )
        return None

    @staticmethod
    def _intersect_segments_2d(
        p0x: float,
        p0z: float,
        p1x: float,
        p1z: float,
        q0x: float,
        q0z: float,
        q1x: float,
        q1z: float,
    ) -> Optional[tuple[float, float]]:
        """
        Exact 2D line segment intersection between P0->P1 and Q0->Q1.
        Returns intersection point (ix, iz) if segments intersect, else None.
        """
        rx = p1x - p0x
        rz = p1z - p0z
        sx = q1x - q0x
        sz = q1z - q0z

        r_cross_s = rx * sz - rz * sx
        if abs(r_cross_s) <= 1e-10:
            return None

        qp_x = q0x - p0x
        qp_z = q0z - p0z

        t = (qp_x * sz - qp_z * sx) / r_cross_s
        u = (qp_x * rz - qp_z * rx) / r_cross_s

        if -1e-6 <= t <= 1.0 + 1e-6 and -1e-6 <= u <= 1.0 + 1e-6:
            return (p0x + t * rx, p0z + t * rz)
        return None
