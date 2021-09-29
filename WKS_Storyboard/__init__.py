# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# Initialization script for WKS Storyboard template

import itertools
import logging
import math
import os
import sys

import bpy
from bl_keymap_utils.io import keyconfig_init_from_data
from bpy.app.handlers import persistent
from bpy.types import Menu, Operator
from mathutils import Euler, Vector

SHOT_CTRL_NAME = "SHOT_CTRL"

logger = logging.getLogger(__name__)


@persistent
def load_handler(dummy):
    import bpy

    # 2D Animation
    screen = bpy.data.screens['2D Animation']
    if screen:
        for area in screen.areas:
            # Set Tool settings as default in properties panel.
            if area.type == 'PROPERTIES':
                for space in area.spaces:
                    if space.type != 'PROPERTIES':
                        continue
                    space.context = 'TOOL'

            # Open sidebar in Dopesheet.
            elif area.type == 'DOPESHEET_EDITOR':
                for space in area.spaces:
                    if space.type != 'DOPESHEET_EDITOR':
                        continue
                    space.show_region_ui = True

    # 2D Full Canvas
    screen = bpy.data.screens['2D Full Canvas']
    if screen:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type != 'VIEW_3D':
                        continue
                    space.shading.type = 'MATERIAL'
                    space.shading.use_scene_world = True

    # Grease pencil object
    scene = bpy.data.scenes[0]
    if scene:
        scene.tool_settings.use_keyframe_insert_auto = True
        for ob in scene.objects:
            if ob.type == 'GPENCIL':
                gpd = ob.data
                gpd.onion_keyframe_type = 'ALL'


def get_shot_ctrl_collection(scene) -> bpy.types.Collection:
    shot_ctrl_collection = next((coll for coll in scene.collection.children
                                 if coll.name.endswith(SHOT_CTRL_NAME)), None)
    coll_name = scene.name + '_' + SHOT_CTRL_NAME
    if shot_ctrl_collection is None:
        shot_ctrl_collection = bpy.data.collections.new(coll_name)
        scene.collection.children.link(shot_ctrl_collection)

    if shot_ctrl_collection.name != coll_name:
        shot_ctrl_collection.name = coll_name

    return shot_ctrl_collection


def get_shot_ctrl_rig(scene) -> bpy.types.Armature:
    shot_ctrl_rig = next((obj for obj in scene.objects
                          if obj.name.endswith(SHOT_CTRL_NAME) and obj.type == "ARMATURE"), None)
    rig_name = scene.name + "_" + SHOT_CTRL_NAME
    if shot_ctrl_rig is None:
        rig_data = bpy.data.armatures.new(rig_name)
        rig_data.display_type = "WIRE"
        shot_ctrl_rig = bpy.data.objects.new(rig_name, rig_data)

    coll = get_shot_ctrl_collection(scene)
    if shot_ctrl_rig.name not in coll.objects:
        coll.objects.link(shot_ctrl_rig)

    if shot_ctrl_rig.name != rig_name:
        shot_ctrl_rig.name = rig_name
        shot_ctrl_rig.data.name = rig_name

    return shot_ctrl_rig


def get_shot_ctrl_bone(context, shot_ctrl_rig, shot_name) -> bpy.types.Bone:
    """
    Returns control bone for shot SHOT_NAME within SHOT_CTRL_RIG. If nonexistent, SHOT_CTRL_RIG will be activated and
    control bone created in Edit Mode.

    :param context:
    :param shot_ctrl_rig:
    :param shot_name:
    :return:
    """
    rig_data: bpy.types.Armature = shot_ctrl_rig.data
    bone = next((bone for bone in rig_data.bones if bone.name == shot_name), None)
    if bone is None:
        if context.active_object:
            bpy.ops.object.mode_set(mode="OBJECT")
        context.view_layer.objects.active = shot_ctrl_rig

        bpy.ops.object.mode_set(mode="EDIT")
        bone_list = [edit_bone for edit_bone in rig_data.edit_bones if edit_bone.name == shot_name]
        if len(bone_list) > 0:
            edit_bone = bone_list[0]
        else:
            edit_bone = rig_data.edit_bones.new(shot_name)
        edit_bone.head = Vector((0.0, -1.0, 0.0))
        edit_bone.tail = Vector((0.0, 0.0, 0.0))
        bpy.ops.object.mode_set(mode="OBJECT")
    bone = rig_data.bones[shot_name]

    return bone


def get_shot_obj_collection(scene, shot_name) -> bpy.types.Collection:
    shot_obj_collection = next((coll for coll in scene.collection.children if coll.name == shot_name), None)
    if shot_obj_collection is None:
        shot_obj_collection = bpy.data.collections.new(shot_name)
        scene.collection.children.link(shot_obj_collection)

    return shot_obj_collection


def get_layer_collection(view_layer, coll_name) -> bpy.types.LayerCollection:
    """
    Returns view layer-specific wrapper for collection named COLL_NAME.

    :param view_layer:
    :param coll_name:
    :return:
    """
    l_coll = None
    l_coll_list = [view_layer.layer_collection]
    while len(l_coll_list) > 0:
        curr_l_coll = l_coll_list.pop()
        if curr_l_coll.collection.name == coll_name:
            l_coll = curr_l_coll
            break
        l_coll_list.extend(curr_l_coll.children)

    return l_coll


def get_stroke_obj(coll, shot_name) -> bpy.types.Object:
    stroke_obj = next((obj for obj in coll.objects if obj.type == "GPENCIL"), None)
    if stroke_obj is None:
        stroke_name = "pen-" + shot_name
        stroke_data = bpy.data.grease_pencils.new(stroke_name)
        stroke_obj = bpy.data.objects.new(stroke_name, stroke_data)
        coll.objects.link(stroke_obj)

    return stroke_obj


def get_camera_obj(coll, shot_name) -> bpy.types.Object:
    camera_obj = next((obj for obj in coll.objects if obj.type == "CAMERA"), None)
    if camera_obj is None:
        camera_name = "cam-" + shot_name
        camera_data = bpy.data.cameras.new(camera_name)
        camera_obj = bpy.data.objects.new(camera_name, camera_data)
        coll.objects.link(camera_obj)

        camera_obj.rotation_mode = "XYZ"
        camera_obj.location += Vector((0.0, -10.0, 0.0))
        camera_obj.rotation_euler.rotate(Euler((math.radians(90), 0.0, 0.0)))

    return camera_obj


def get_shot(scene, frame=None, offset=0) -> bpy.types.TimelineMarker:
    """
    Returns marker object for current shot, or None where 'current' is defined as shot with marker before and nearest
    with frame number FRAME if specified, or current frame otherwise. OFFSET will get the shot before or after current
    one.

    :param scene:
    :param frame:
    :param offset:
    :return:
    """
    frame_ref = frame or scene.frame_current
    sort_key = (lambda m: m.frame)
    group_key = (lambda m: m.frame <= frame_ref)
    before, after = [], []
    for v, i in itertools.groupby(sorted(scene.timeline_markers, key=sort_key), key=group_key):
        if v:
            before.extend(i)
        else:
            after.extend(i)

    marker_obj = None
    offset -= 1
    if -len(before) <= offset < 0:
        marker_obj = before[offset]
    elif 0 <= offset < len(after):
        marker_obj = after[offset]

    if logger.level <= logging.DEBUG:
        if marker_obj is None:
            logger.debug("Marker not found")
        else:
            logger.debug("Found marker: {}".format(marker_obj.name))
    return marker_obj


def set_active_shot(context, marker_shot, current=False):
    """
    Set the shot marked by MARKER_SHOT as the active one. If the shot to be activated is the current one, set CURRENT
    to True: previous shot will not be checked and hidden.

    :param context:
    :param marker_shot:
    :param current:
    """
    other_shot_name = marker_shot.name
    scene = context.scene
    if not current:
        marker_current_shot = get_shot(scene)
        if marker_current_shot is not None and marker_current_shot != marker_shot:
            shot_name = marker_current_shot.name
            l_coll = get_layer_collection(context.view_layer, shot_name)
            if l_coll is not None:
                l_coll.exclude = True

    scene.frame_set(marker_shot.frame)

    coll = get_shot_obj_collection(scene, other_shot_name)
    l_coll = get_layer_collection(context.view_layer, coll.name)
    if l_coll is not None:
        l_coll.exclude = False
        context.view_layer.active_layer_collection = l_coll


def activate_shot_objects(context, shot_name):
    scene = context.scene
    coll = get_shot_obj_collection(scene, shot_name)

    stroke_obj = get_stroke_obj(coll, shot_name)
    camera_obj = get_camera_obj(coll, shot_name)
    set_active_stroke_obj(context, stroke_obj)
    scene.camera = camera_obj


def create_shot_name(scene):
    shot_number = len(scene.timeline_markers) + 1
    return "SHOT_{:03}".format(shot_number)


def set_active_stroke_obj(context, stroke_obj):
    if context.active_object is not None:
        bpy.ops.object.mode_set(mode="OBJECT")
    context.view_layer.objects.active = stroke_obj
    bpy.ops.object.mode_set(mode="PAINT_GPENCIL")


def parent_to_shot_controller(context, shot_name, obj_list):
    """
    Parent objects in OBJ_LIST to the controller for shot SHOT_NAME.

    :param context:
    :param shot_name:
    :param obj_list:
    """
    scene = context.scene
    shot_ctrl_rig = get_shot_ctrl_rig(scene)
    bone = get_shot_ctrl_bone(context, shot_ctrl_rig, shot_name)
    for obj in obj_list:
        obj.parent = shot_ctrl_rig
        obj.parent_type = "BONE"
        obj.parent_bone = bone.name


class WKS_OT_shot_offset(Operator):
    bl_idname = "wks_shot.shot_offset"
    bl_label = "Shot Offset"
    bl_description = "Jump to another shot relative to current one."
    bl_options = {"REGISTER"}

    offset: bpy.props.IntProperty(name="Jump Offset", description="Offset relative to current shot.", default=1)

    def execute(self, context):
        scene = context.scene
        shot_name = get_shot(scene, offset=self.offset)
        if shot_name is None:
            self.report({"INFO"}, "No other shot to jump to.")
        else:
            set_active_shot(context, shot_name)
            activate_shot_objects(context, shot_name.name)

        return {"FINISHED"}


class WKS_OT_shot_new(Operator):
    bl_idname = "wks_shot.new"
    bl_label = "New Shot"
    bl_description = "Create a new shot. Current shot must have enough duration for both itself and the new shot " \
                     "(min. duration: 1 second)."
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        logger.info("CREATING SHOT")

        scene = context.scene
        coll = get_shot_ctrl_collection(scene)  # create collection for shot controller before ones for any shot
        marker_shot = get_shot(scene)
        frame_new_shot = self.get_frame_new_shot(scene, marker_shot)

        if frame_new_shot is not None:
            name_new_shot = create_shot_name(scene)
            marker_new_shot = scene.timeline_markers.new(name_new_shot, frame=frame_new_shot)
            set_active_shot(context, marker_new_shot)

            coll = get_shot_obj_collection(scene, name_new_shot)
            stroke_obj = get_stroke_obj(coll, name_new_shot)
            camera_obj = get_camera_obj(coll, name_new_shot)
            obj_list = (stroke_obj, camera_obj)
            parent_to_shot_controller(context, name_new_shot, obj_list)

            marker_new_shot.camera = camera_obj
            activate_shot_objects(context, name_new_shot)

        return {"FINISHED"}

    def get_frame_new_shot(self, scene: bpy.types.Scene, marker_shot: bpy.types.TimelineMarker) -> int:
        if marker_shot:
            frame_current_shot = marker_shot.frame
            frame_new_shot = max(frame_current_shot + scene.render.fps, scene.frame_current)
            marker_other_shot = get_shot(scene, frame=frame_new_shot + scene.render.fps - 1)
            if marker_other_shot != marker_shot:
                self.report({"WARNING"}, "Not enough excess duration to create a new shot here. "
                                         "Any given shot must be at least one second long.")
                frame_new_shot = None
        else:
            frame_new_shot = scene.frame_start

        return frame_new_shot


class WKS_OT_shot_reparent_objects(Operator):
    bl_idname = "wks_shot.reparent_objects"
    bl_label = "Reparent Objects"
    bl_description = "Reparent objects within a shot-specific Collection to the shot's controller. Necessary for" \
                     " proper shot switching in playback."
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        marker_shot = get_shot(context.scene)
        if marker_shot is not None:
            set_active_shot(context, marker_shot, current=True)
            shot_name = marker_shot.name
            coll = get_shot_obj_collection(context.scene, shot_name)

            parent_to_shot_controller(context, shot_name, coll.all_objects)

        return {"FINISHED"}


# spawn an edit mode selection pie (run while object is in edit mode to get a valid output)
class VIEW3D_MT_PIE_wks_storyboard(Menu):
    bl_idname = "VIEW3D_MT_PIE_wks_storyboard"
    # label is displayed at the center of the pie menu.
    bl_label = "WKS Storyboard Menu"

    def draw(self, context):
        layout = self.layout

        pie = layout.menu_pie()
        op = pie.operator("wks_shot.shot_offset", text="Prev. Shot")
        op.offset = -1
        op = pie.operator("wks_shot.shot_offset", text="Next Shot")
        op.offset = 1
        op = pie.separator()
        column = pie.column()
        column.scale_y = 1.5
        column.operator("wks_shot.reparent_objects")
        op = pie.separator()
        op = pie.separator()
        op = pie.separator()
        op = pie.operator("wks_shot.new")


class VIEW3D_PT_wks_shot(bpy.types.Panel):
    bl_idname = 'VIEW3D_PT_wks_shot'
    bl_label = 'WKS Shot'
    bl_category = ''
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'

    def draw(self, context):
        layout = self.layout
        layout.label(text="PLACEHOLDER")


classes = [
    WKS_OT_shot_offset,
    WKS_OT_shot_new,
    WKS_OT_shot_reparent_objects,
    VIEW3D_MT_PIE_wks_storyboard,
    VIEW3D_PT_wks_shot,
]


def header_panel(self, context: bpy.types.Context):
    layout: bpy.types.UILayout = self.layout
    layout.separator(factor=0.25)
    layout.popover(VIEW3D_PT_wks_shot.bl_idname, text='Shots', )
    op = layout.operator("wks_shot.shot_offset", text="", icon="TRIA_LEFT")
    op.offset = -1
    op = layout.operator("wks_shot.shot_offset", text="", icon="TRIA_RIGHT")
    op.offset = 1
    layout.operator("wks_shot.new", text="", icon="ADD")
    layout.separator(factor=0.25)


def register_wks_keymap():
    file_path = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(file_path)
    from .app_lib.Blender2DKeymap import KeyMap
    sys.path.remove(file_path)

    wm = bpy.context.window_manager
    kc_active = wm.keyconfigs.active  # modify preset
    keyconfig_init_from_data(kc_active, KeyMap.keyconfig_data)
    kc_addon = wm.keyconfigs.addon  # insert keymap item to addon
    if kc_addon:
        km = kc_addon.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new("wm.call_menu_pie", type="E", value="PRESS")
        kmi.properties.name = VIEW3D_MT_PIE_wks_storyboard.bl_idname
        kmi.active = True


def register():
    logger.debug("Registering module")
    bpy.app.handlers.load_factory_startup_post.append(load_handler)
    bpy.types.VIEW3D_MT_editor_menus.append(header_panel)
    for cls in classes:
        bpy.utils.register_class(cls)

    register_wks_keymap()


def unregister():
    logger.debug("Unregistering module")
    bpy.app.handlers.load_factory_startup_post.remove(load_handler)
    bpy.types.VIEW3D_MT_editor_menus.remove(header_panel)
    for cls in classes:
        bpy.utils.unregister_class(cls)
