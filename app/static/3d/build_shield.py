"""Build the Hyson Detector 3D emblem in Blender (headless) and export it as GLB for the three.js viewer.

Run:  blender --background --factory-startup --python build_shield.py -- <out_dir>
Objects are named so the web viewer can animate them: Shield, Inner, Rim, Check, Ring, Tx_00..Tx_11 (Tx_07 = fraud).
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

OUT = Path(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else Path(__file__).parent
OUT.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def mat(name, color, metallic=0.0, rough=0.4, emission=None, strength=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Roughness"].default_value = rough
    if emission:
        p.inputs["Emission Color"].default_value = (*emission, 1)
        p.inputs["Emission Strength"].default_value = strength
    if alpha < 1:
        p.inputs["Alpha"].default_value = alpha
    return m


def srgb(hex_):
    h = hex_.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


NAVY, BLUE, TEAL, GOLD, RED, ICE = map(srgb, ["#0B2545", "#1E5BD8", "#0E9F8A", "#C8A24A", "#D92D20", "#DCE7FB"])


def shield_outline(w=1.0, h=1.25, n=48):
    """Classic shield: flat-ish top with small shoulders, sides curving to a point."""
    pts = []
    top = h * 0.55
    for i in range(n + 1):                      # right side, top -> bottom point
        t = i / n
        x = w * (1 - t ** 2.2) * (1 - 0.08 * math.sin(math.pi * t))
        y = top - t * (h + top * 0.25)
        pts.append((x, y))
    left = [(-x, y) for x, y in reversed(pts[1:-1])]
    arch = [(w * (1 - 2 * k / 12), top + 0.06 * math.sin(math.pi * k / 12)) for k in range(1, 12)]
    return [(w, top)] + pts[1:] + left + [(-w, top)] + list(reversed(arch))[::-1][::-1]


def extrude_outline(name, pts, depth, z0, material, bevel=0.04):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    verts = [bm.verts.new((x, y, z0)) for x, y in pts]
    face = bm.faces.new(verts)
    bmesh.ops.recalc_face_normals(bm, faces=[face])
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=moved, vec=Vector((0, 0, depth)))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    ob.data.materials.append(material)
    bv = ob.modifiers.new("bevel", "BEVEL")
    bv.width, bv.segments, bv.limit_method = bevel, 4, "ANGLE"
    ob.modifiers.new("wn", "WEIGHTED_NORMAL")
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


m_navy = mat("Navy", NAVY, metallic=0.85, rough=0.28)
m_blue = mat("Blue", BLUE, metallic=0.75, rough=0.22)
m_gold = mat("Gold", GOLD, metallic=1.0, rough=0.25)
m_check = mat("Check", TEAL, metallic=0.2, rough=0.3, emission=TEAL, strength=2.5)
m_tx = mat("Tx", ICE, metallic=0.1, rough=0.35, emission=BLUE, strength=0.4)
m_fraud = mat("Fraud", RED, metallic=0.1, rough=0.3, emission=RED, strength=3.0)
m_ring = mat("RingMat", GOLD, metallic=1.0, rough=0.3)

outline = shield_outline()
rim = extrude_outline("Rim", [(x * 1.07, y * 1.05) for x, y in outline], 0.30, -0.18, m_gold, bevel=0.05)
body = extrude_outline("Shield", outline, 0.34, -0.15, m_navy, bevel=0.06)
inner = extrude_outline("Inner", [(x * 0.80, y * 0.80 - 0.02) for x, y in outline], 0.10, 0.17, m_blue, bevel=0.035)

# check mark: a thick tube along a polyline
curve = bpy.data.curves.new("CheckCurve", "CURVE")
curve.dimensions = "3D"
spl = curve.splines.new("POLY")
pts = [(-0.38, -0.02, 0.33), (-0.10, -0.32, 0.33), (0.42, 0.30, 0.33)]
spl.points.add(len(pts) - 1)
for p, co in zip(spl.points, pts):
    p.co = (*co, 1)
curve.bevel_depth, curve.bevel_resolution = 0.075, 6
curve.use_fill_caps = True
check = bpy.data.objects.new("Check", curve)
scene.collection.objects.link(check)
check.data.materials.append(m_check)

# orbit ring of transactions (empty parent so the web viewer rotates one node)
ring = bpy.data.objects.new("Ring", None)
scene.collection.objects.link(ring)
ring.rotation_euler = (math.radians(72), 0, math.radians(8))
bpy.ops.mesh.primitive_torus_add(major_radius=1.75, minor_radius=0.012, major_segments=128, minor_segments=8)
torus = bpy.context.active_object
torus.name = "RingTrack"
torus.data.materials.append(m_ring)
torus.parent = ring
N = 12
for i in range(N):
    a = 2 * math.pi * i / N
    bpy.ops.mesh.primitive_cube_add(size=0.16, location=(1.75 * math.cos(a), 1.75 * math.sin(a), 0))
    cube = bpy.context.active_object
    cube.name = f"Tx_{i:02d}"
    cube.rotation_euler = (0.4, 0.3, a)
    bv = cube.modifiers.new("bevel", "BEVEL")
    bv.width, bv.segments = 0.025, 3
    cube.data.materials.append(m_fraud if i == 7 else m_tx)
    cube.parent = ring

# convert curves / apply modifiers so the GLB is plain meshes
bpy.ops.object.select_all(action="DESELECT")
for ob in list(scene.objects):
    if ob.type in ("MESH", "CURVE"):
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        if ob.type == "CURVE":
            bpy.ops.object.convert(target="MESH")
        else:
            for md in list(ob.modifiers):
                bpy.ops.object.modifier_apply(modifier=md.name)
        ob.select_set(False)

glb = OUT / "hyson_shield.glb"
bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", export_apply=True, export_yup=True)
print("EXPORTED", glb, glb.stat().st_size)

# preview render (EEVEE) so we can check the look
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
scene.collection.objects.link(cam)
cam.location = (2.6, -4.6, 2.2)
cam.rotation_euler = (Vector((0, 0, 0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = cam
for loc, energy in [((3, -3, 4), 900), ((-4, -2, 2), 400), ((0, 4, 3), 600)]:
    li = bpy.data.objects.new("Light", bpy.data.lights.new("L", "AREA"))
    li.data.energy, li.data.size = energy, 3
    li.location = loc
    li.rotation_euler = (Vector((0, 0, 0)) - li.location).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(li)
world = bpy.data.worlds.new("W")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.92, 0.94, 0.97, 1)
scene.world = world
try:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
except TypeError:
    scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 720, 720
scene.render.filepath = str(OUT / "preview.png")
bpy.ops.render.render(write_still=True)
print("PREVIEW", OUT / "preview.png")
