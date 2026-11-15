from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import numpy as np
import trimesh

from spatial_server.domain.models import Ray3D
from .interfaces import ISpatialRaycaster

logger = logging.getLogger(__name__)


@dataclass
class GroundHitResult:
    point: tuple[float, float, float]
    distance_m: float
    used_fallback_plane: bool


class TrimeshGroundRaycaster(ISpatialRaycaster):
    """
    Loads walkable ground collider meshes (`collider_role: "ground"`) from `house_optimized.glb`
    using `scene_manifest.json` as SSoT and accelerates 3D ray-triangle intersection.
    """

    def __init__(
        self,
        glb_path: Path,
        manifest_path: Path,
        min_distance_m: float = 0.3,
        max_distance_m: float = 60.0,
    ) -> None:
        self.glb_path = glb_path
        self.manifest_path = manifest_path
        self.min_distance_m = min_distance_m
        self.max_distance_m = max_distance_m

        self.ground_collider_names: set[str] = set()
        self.matched_nodes: list[str] = []
        self.ground_mesh: Optional[trimesh.Trimesh] = None
        self._load_ground_meshes()

    def _load_ground_meshes(self) -> None:
        if self.manifest_path.exists():
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            self.ground_collider_names = {
                str(item["object_name"])
                for item in manifest.get("ground_colliders", [])
                if "object_name" in item
            }

        if not self.glb_path.exists():
            logger.warning("GLB file missing at %s; using Y=0 plane fallback.", self.glb_path)
            return

        scene = trimesh.load(str(self.glb_path), force="scene")
        if not isinstance(scene, trimesh.Scene):
            if isinstance(scene, trimesh.Trimesh):
                self.ground_mesh = scene
            return

        meshes: list[trimesh.Trimesh] = []
        for node_name in scene.graph.nodes_geometry:
            transform, geom_name = scene.graph[node_name]
            is_ground = self._is_ground_node_name(node_name, geom_name)
            if not is_ground:
                continue

            base_geom = scene.geometry.get(geom_name)
            if not isinstance(base_geom, trimesh.Trimesh) or len(base_geom.faces) == 0:
                continue

            transformed = base_geom.copy()
            transformed.apply_transform(transform)
            meshes.append(transformed)
            self.matched_nodes.append(node_name)

        if meshes:
            self.ground_mesh = trimesh.util.concatenate(meshes)
            logger.info(
                "Loaded %d ground collider meshes (%d triangles) from %s",
                len(meshes),
                len(self.ground_mesh.faces),
                self.glb_path.name,
            )
        else:
            logger.warning("No matching ground collider nodes found in %s; plane fallback active.", self.glb_path.name)

    def _is_ground_node_name(self, node_name: str, geom_name: str) -> bool:
        if not self.ground_collider_names:
            return False
        if node_name in self.ground_collider_names or geom_name in self.ground_collider_names:
            return True
        # Handle glTF primitive suffixes like `Driveway_Gravel_0`
        for target in self.ground_collider_names:
            if node_name.startswith(target) or geom_name.startswith(target):
                return True
        return False

    def intersect_ground_detailed(self, ray: Ray3D, fallback_plane_y: float = 0.0) -> Optional[GroundHitResult]:
        origin = np.array(ray.origin, dtype=np.float64)
        direction = np.array(ray.direction, dtype=np.float64)
        norm = float(np.linalg.norm(direction))
        if norm < 1e-9:
            return None
        direction = direction / norm

        if self.ground_mesh is not None:
            locations, _idx_ray, _idx_tri = self.ground_mesh.ray.intersects_location(
                ray_origins=origin.reshape((1, 3)),
                ray_directions=direction.reshape((1, 3)),
                multiple_hits=True,
            )
            if len(locations) > 0:
                dists = np.linalg.norm(locations - origin, axis=1)
                valid_mask = (dists >= self.min_distance_m) & (dists <= self.max_distance_m)
                if np.any(valid_mask):
                    valid_locs = locations[valid_mask]
                    valid_dists = dists[valid_mask]
                    best_i = int(np.argmin(valid_dists))
                    pt = valid_locs[best_i]
                    return GroundHitResult(
                        point=(float(pt[0]), float(pt[1]), float(pt[2])),
                        distance_m=float(valid_dists[best_i]),
                        used_fallback_plane=False,
                    )

        # Fallback: flat horizontal ground plane y = fallback_plane_y
        if abs(direction[1]) > 1e-5:
            t = (fallback_plane_y - origin[1]) / direction[1]
            if self.min_distance_m <= t <= self.max_distance_m:
                pt = origin + t * direction
                return GroundHitResult(
                    point=(float(pt[0]), float(pt[1]), float(pt[2])),
                    distance_m=float(t),
                    used_fallback_plane=True,
                )
        return None

    def intersect_ground(self, ray: Ray3D) -> Optional[tuple[float, float, float]]:
        hit = self.intersect_ground_detailed(ray)
        return hit.point if hit is not None else None

