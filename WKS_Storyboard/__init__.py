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

import importlib
import inspect
import itertools
import logging
import math
import os
import pkgutil
import re
import sys
from importlib.machinery import ModuleSpec

import bpy
from bl_keymap_utils.io import keyconfig_init_from_data
from bpy.app.handlers import persistent
from bpy.types import Menu, Operator, Panel, UIList
from mathutils import Euler, Vector

APPTEMPLATE_DIR = "bl_app_templates_user"
APPTEMPLATE_NAME = "WKS_Storyboard"
SCRIPT_INTERNAL_NAME = "wks_storyboard.py"
SHOT_CTRL_NAME = "SHOT_CTRL"
SHOT_MARKER_NAME_PREFIX = "SHOT_"
STROKE_NAME_PREFIX = "pen-"
CAMERA_NAME_PREFIX = "cam-"
TIME_RE = re.compile(
    r"""
    (?:
      (?P<min>\d+):
    )?
    (?P<sec>\d+)
    (?:\+(?P<frame>\d+))?
    """,
    re.VERBOSE
)

LOCATION_PATH_PATTERN = r'pose.bones["{}"].location'

logger = logging.getLogger(__name__)


@persistent
def load_factory_startup_handler(dummy):
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


@persistent
def load_post_handler(dummy):
    reload_embedded_script()


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

    if shot_ctrl_rig.animation_data is None:
        shot_ctrl_rig.animation_data_create()

    action = shot_ctrl_rig.animation_data.action
    if action is None:
        action = bpy.data.actions.new(rig_name)
        action.use_fake_user = True
        shot_ctrl_rig.animation_data.action = action
    action.name = rig_name

    return shot_ctrl_rig


def get_shot_ctrl_bone(shot_ctrl_rig, shot_name) -> bpy.types.Bone:
    """
    Returns control bone for shot SHOT_NAME within SHOT_CTRL_RIG. If nonexistent, SHOT_CTRL_RIG will be activated and
    control bone created in Edit Mode.

    :param shot_ctrl_rig:
    :param shot_name:
    :return:
    """
    rig_data: bpy.types.Armature = shot_ctrl_rig.data
    bone = next((bone for bone in rig_data.bones if bone.name == shot_name), None)
    if bone is None:
        context = bpy.context
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
        stroke_name = STROKE_NAME_PREFIX + shot_name
        stroke_data = bpy.data.grease_pencils.new(stroke_name)
        stroke_obj = bpy.data.objects.new(stroke_name, stroke_data)
        coll.objects.link(stroke_obj)

    return stroke_obj


def get_camera_obj(coll, shot_name) -> bpy.types.Object:
    camera_obj = next((obj for obj in coll.objects if obj.type == "CAMERA"), None)
    if camera_obj is None:
        camera_name = CAMERA_NAME_PREFIX + shot_name
        camera_data = bpy.data.cameras.new(camera_name)
        camera_obj = bpy.data.objects.new(camera_name, camera_data)
        coll.objects.link(camera_obj)

        camera_obj.rotation_mode = "XYZ"
        camera_obj.location += Vector((0.0, -10.0, 0.0))
        camera_obj.rotation_euler.rotate(Euler((math.radians(90), 0.0, 0.0)))

    return camera_obj


def get_shot_duration(scene, marker):
    shot_frame = marker.frame
    marker_next_shot = get_shot(scene, frame=shot_frame, offset=1)
    frame_diff = (marker_next_shot.frame if marker_next_shot else scene.frame_end) - shot_frame
    return frame_diff


def get_shot_marker_iterator(scene):
    sort_key = (lambda m: m.frame)
    marker_list = filter((lambda m: m.name.startswith(SHOT_MARKER_NAME_PREFIX)), scene.timeline_markers)
    marker_iterator = sorted(marker_list, key=sort_key)
    return marker_iterator


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
    before, after = [], []
    group_key = (lambda m: m.frame <= frame_ref)
    marker_iterator = get_shot_marker_iterator(scene)
    for v, i in itertools.groupby(marker_iterator, key=group_key):
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

    scene.frame_set(marker_shot.frame)
    adjust_preview_range(scene, marker_shot)

    coll = get_shot_obj_collection(scene, other_shot_name)
    l_coll = get_layer_collection(context.view_layer, coll.name)
    if l_coll is not None:
        l_coll.exclude = False
        context.view_layer.active_layer_collection = l_coll

    for obj in context.selected_objects:
        obj.select_set(False)


def activate_shot_objects(context, shot_name):
    scene = context.scene
    coll = get_shot_obj_collection(scene, shot_name)

    stroke_obj = get_stroke_obj(coll, shot_name)
    camera_obj = get_camera_obj(coll, shot_name)
    set_active_stroke_obj(context, stroke_obj)
    scene.camera = camera_obj


def create_shot_name(scene, base_name=None):
    """
    Create first non-conflicting shot name from BASE_NAME.

    :param scene:
    :param base_name:
    :return:
    """
    if base_name is None:
        shot_number = len(scene.timeline_markers) + 1
        base_name = "{:03}".format(shot_number)

    shot_name = SHOT_MARKER_NAME_PREFIX + base_name
    index = 1
    while scene.timeline_markers.get(shot_name, None) is not None:
        shot_name = SHOT_MARKER_NAME_PREFIX + base_name + "-{:02}".format(index)
        index += 1

    return shot_name


def update_shot_name(marker, base_name):
    if base_name.startswith(SHOT_MARKER_NAME_PREFIX):
        base_name = base_name[len(SHOT_MARKER_NAME_PREFIX):]
    shot_name_new = SHOT_MARKER_NAME_PREFIX + base_name
    shot_name = marker.name
    if shot_name_new == shot_name:
        return

    scene = bpy.context.scene
    shot_marker_other = scene.timeline_markers.get(shot_name_new, None)
    if shot_marker_other is not None:
        base_name_other = get_shot_base_name(base_name)
        shot_name_other = create_shot_name(scene, base_name_other)
        update_shot_name(shot_marker_other, shot_name_other)

    coll = get_shot_obj_collection(scene, shot_name)
    coll.name = shot_name_new

    shot_ctrl_rig = get_shot_ctrl_rig(scene)
    bone = get_shot_ctrl_bone(shot_ctrl_rig, shot_name)
    bone.name = shot_name_new

    stroke_obj = get_stroke_obj(coll, shot_name)
    stroke_obj.name = STROKE_NAME_PREFIX + shot_name_new
    camera_obj = get_camera_obj(coll, shot_name)
    camera_obj.name = CAMERA_NAME_PREFIX + shot_name_new

    marker.name = shot_name_new


def get_shot_base_name(shot_name: str):
    base_name = shot_name[len(SHOT_MARKER_NAME_PREFIX):] if shot_name.startswith(SHOT_MARKER_NAME_PREFIX) \
        else shot_name
    mo = re.search(r"-\d+$", base_name)
    return base_name[:mo.start()] if mo else base_name


def set_active_stroke_obj(context, stroke_obj):
    if context.active_object is not None:
        bpy.ops.object.mode_set(mode="OBJECT")
    stroke_obj.select_set(True)
    context.view_layer.objects.active = stroke_obj


def parent_to_shot_controller(context, shot_name, obj_list):
    """
    Parent objects in OBJ_LIST to the controller for shot SHOT_NAME.

    :param context:
    :param shot_name:
    :param obj_list:
    """
    scene = context.scene
    shot_ctrl_rig = get_shot_ctrl_rig(scene)
    bone = get_shot_ctrl_bone(shot_ctrl_rig, shot_name)
    for obj in obj_list:
        obj.parent = shot_ctrl_rig
        obj.parent_type = "BONE"
        obj.parent_bone = bone.name


def adjust_shot_transitions(scene, first_shot_marker):
    first_shot_frame = first_shot_marker.frame if first_shot_marker is not None else scene.frame_start

    shot_ctrl_rig = get_shot_ctrl_rig(scene)
    action = shot_ctrl_rig.animation_data.action

    marker_iterator = get_shot_marker_iterator(scene)
    for shot_marker in filter((lambda m: m.frame >= first_shot_frame), marker_iterator):
        shot_name = shot_marker.name
        shot_duration = get_shot_duration(scene, shot_marker)
        action_group = action.groups.get(shot_name)
        if action_group is None:
            action.groups.new(shot_name)

        bone = get_shot_ctrl_bone(shot_ctrl_rig, shot_name)
        bone_loc_data_path = LOCATION_PATH_PATTERN.format(bone.name)
        for axis_index in range(3):
            fcurve_x = action.fcurves.find(bone_loc_data_path, index=axis_index)
            if fcurve_x is None:
                fcurve_x = action.fcurves.new(bone_loc_data_path, index=axis_index, action_group=shot_name)
            keyframe_count = len(fcurve_x.keyframe_points)
            if keyframe_count < 3:
                fcurve_x.keyframe_points.add(3 - keyframe_count)
                for point_index in range(3):
                    fcurve_x.keyframe_points[point_index].interpolation = "CONSTANT"
            for point_index, point in enumerate(fcurve_x.keyframe_points):
                if point_index in (0, 2):
                    # throw shot controller far off the camera before and after its duration
                    point.co = (-1 if point_index == 0 else shot_marker.frame + shot_duration, 100000)
                elif point_index == 1:
                    point.co = (shot_marker.frame, 0)
                else:
                    fcurve_x.keyframe_points.remove(point, fast=True)


def adjust_preview_range(scene, marker_shot=None):
    """
    Adjust preview range as means of isolating individual shot. If MARKER_SHOT is None, defaults to current shot.

    :param scene:
    :param marker_shot:
    """
    # skip if not in preview (shot-isolation) mode, it will calc when activated
    if not scene.use_preview_range:
        return

    if marker_shot is None:
        marker_shot = get_shot(scene)
    shot_frame = marker_shot.frame
    marker_next_shot = get_shot(scene, frame=shot_frame, offset=1)
    shot_frame_end = (marker_next_shot.frame if marker_next_shot else scene.frame_end)

    scene.frame_preview_start = shot_frame
    scene.frame_preview_end = shot_frame_end


def filter_shot_marker_list(self, context):
    scene = context.scene
    marker_list = scene.timeline_markers
    helper_funcs = bpy.types.UI_UL_list

    # Create bitmask for all objects
    flt_flags = [self.bitflag_filter_item] * len(marker_list)

    # Filter by marker name.
    for idx, marker in enumerate(marker_list):
        if marker.name.startswith(SHOT_MARKER_NAME_PREFIX):
            flt_flags[idx] |= self.SHOT_FILTER
        else:
            flt_flags[idx] &= ~self.bitflag_filter_item

    flt_neworder = helper_funcs.sort_items_by_name(marker_list, "name")
    return flt_flags, flt_neworder


class WKS_OT_shot_offset(Operator):
    bl_idname = "wks_shot.shot_offset"
    bl_label = "Shot Offset"
    bl_description = "Jump to another shot relative to current one."
    bl_options = {"REGISTER", "UNDO"}

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


class WKS_OT_shot_goto(Operator):
    bl_idname = "wks_shot.shot_goto"
    bl_label = "Go to Shot"
    bl_description = "Jump to another shot at specified frame."
    bl_options = {"REGISTER", "UNDO"}

    target_frame: bpy.props.IntProperty(name="Target Frame", description="Frame contained by target shot.", default=0)

    def execute(self, context):
        scene = context.scene
        shot_name = get_shot(scene, frame=self.target_frame)
        if shot_name is None:
            self.report({"INFO"}, "No shot containing specified frame.")
        else:
            set_active_shot(context, shot_name)
            activate_shot_objects(context, shot_name.name)

        return {"FINISHED"}


def get_fps(scene):
    return scene.render.fps / scene.render.fps_base


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

            fps_real = get_fps(scene)
            frame_end_min = frame_new_shot + fps_real
            if scene.frame_end < frame_end_min:
                scene.frame_end = frame_end_min

            adjust_shot_transitions(scene, marker_shot)

        return {"FINISHED"}

    def get_frame_new_shot(self, scene: bpy.types.Scene, marker_shot: bpy.types.TimelineMarker) -> int:
        if marker_shot:
            fps_real = get_fps(scene)
            frame_current_shot = marker_shot.frame
            frame_new_shot = max(frame_current_shot + fps_real, scene.frame_current)
            frame_end_min = frame_new_shot + fps_real
            marker_other_shot = get_shot(scene, frame=frame_end_min - 1)
            if marker_other_shot != marker_shot:
                self.report({"WARNING"}, "Not enough excess duration to create a new shot here. "
                                         "Any given shot must be at least one second long.")
                frame_new_shot = None
            elif scene.frame_end < frame_end_min:
                scene.frame_end = frame_end_min
        else:
            frame_new_shot = scene.frame_start

        return frame_new_shot


class WKS_OT_shot_reparent_objects(Operator):
    bl_idname = "wks_shot.reparent_objects"
    bl_label = "Reparent Current Shot Objects"
    bl_description = "Reparent objects within current shot's collection to its controller. Necessary for proper shot " \
                     "switching in playback."
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        marker_shot = get_shot(context.scene)
        if marker_shot is not None:
            set_active_shot(context, marker_shot, current=True)
            shot_name = marker_shot.name
            coll = get_shot_obj_collection(context.scene, shot_name)

            parent_to_shot_controller(context, shot_name, coll.all_objects)

        return {"FINISHED"}


class WKS_UL_shot_markers(UIList):
    bl_idname = "WKS_UL_shot_markers"

    SHOT_FILTER = 1 << 0

    def filter_items(self, context, data, propname: str):
        flt_flags, flt_neworder = filter_shot_marker_list(self, context)
        return flt_flags, flt_neworder

    def draw_item(self, context, layout, data, item, icon: int, active_data, active_propname: str, index: int = 0,
                  flt_flag: int = 0):
        scene: bpy.types.Scene = data
        marker: bpy.types.TimelineMarker = item
        if scene.frame_current == marker.frame:
            icon = 'RADIOBUT_ON'
        else:
            icon = 'RADIOBUT_OFF'

        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            op = row.operator('wks_shot.shot_goto', text='', icon=icon, emboss=False)
            op.target_frame = marker.frame

            row.prop(marker, "wks_shot_name", text="")
            row.prop(marker, "wks_shot_duration", text="")
        elif self.layout_type in {"GRID"}:
            layout.alignment = "CENTER"
            layout.label(text="", icon_value=icon)


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


class VIEW3D_PT_wks_shot(Panel):
    bl_idname = 'VIEW3D_PT_wks_shot'
    bl_label = 'WKS Shot'
    bl_category = ''
    bl_space_type = 'VIEW_3D'
    bl_ui_units_x = 10
    bl_region_type = 'HEADER'

    def draw(self, context):
        layout = self.layout
        draw_panel(context, layout)


class VIEW3D_PT_UI_wks_storyboard(Panel):
    bl_idname = "VIEW3D_PT_UI_wks_storyboard"
    bl_label = "Storyboard"
    bl_category = "WKS"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.label(text="Shots:")
        draw_navbar(row)
        draw_panel(context, layout)


classes = [
    WKS_OT_shot_offset,
    WKS_OT_shot_goto,
    WKS_OT_shot_new,
    WKS_OT_shot_reparent_objects,
    WKS_UL_shot_markers,
    VIEW3D_MT_PIE_wks_storyboard,
    VIEW3D_PT_wks_shot,
    VIEW3D_PT_UI_wks_storyboard,
]


def header_panel(self, context: bpy.types.Context):
    layout: bpy.types.UILayout = self.layout
    layout.separator(factor=0.25)
    layout.popover(VIEW3D_PT_wks_shot.bl_idname, text='Shots', )
    draw_navbar(layout)
    layout.separator(factor=0.25)


def draw_navbar(layout):
    op = layout.prop(bpy.context.scene, "wks_shot_isolate", text="", icon="OUTLINER_OB_CAMERA")
    op = layout.operator("wks_shot.shot_offset", text="", icon="TRIA_LEFT")
    op.offset = -1
    op = layout.operator("wks_shot.shot_offset", text="", icon="TRIA_RIGHT")
    op.offset = 1
    layout.operator("wks_shot.new", text="", icon="ADD")


def draw_panel(context, layout):
    scene = context.scene
    layout.template_list(WKS_UL_shot_markers.bl_idname, "", scene, "timeline_markers", scene, "wks_shot_index",
                         rows=10)
    layout.operator("wks_shot.reparent_objects")


def get_apptemplate_path():
    apptemplate_path = None
    module_spec: importlib.machinery.ModuleSpec = importlib.util.find_spec(APPTEMPLATE_DIR)
    if module_spec:
        module_path_list = [p for p in module_spec.submodule_search_locations]
        for pkg in pkgutil.iter_modules(module_path_list):
            if pkg.name.startswith(APPTEMPLATE_NAME):
                apptemplate_path = os.path.join(pkg.module_finder.path, pkg.name)

    return apptemplate_path


def get_apptemplate_script_path():
    script_path = None
    apptemplate_path = get_apptemplate_path()
    if apptemplate_path is not None:
        script_path = os.path.join(apptemplate_path, "__init__.py")

    return script_path


def reload_embedded_script():
    area = bpy.context.screen.areas[-1]
    prev_area_type = area.type
    area.type = "TEXT_EDITOR"
    text_editor = area.spaces.active

    script_obj = bpy.data.texts.get(SCRIPT_INTERNAL_NAME)
    script_path = None

    # if there's no text block or real file is not found, find script path
    if script_obj is None or not os.path.isfile(script_obj.filepath):
        script_path = get_apptemplate_script_path()

    # if text block exist but modified, reload
    if script_obj is not None and script_obj.is_modified and script_path is None:
        override_context = bpy.context.copy()
        override_context["area"] = area
        bpy.ops.text.reload(override_context, "EXEC_AREA")

    # if script path is found
    if script_path is not None and os.path.isfile(script_path):
        # create or modify existing text block
        if script_obj is None:
            script_obj = bpy.data.texts.load(script_path, internal=False)
            script_obj.use_fake_user = True
            script_obj.use_module = True
            script_obj.name = SCRIPT_INTERNAL_NAME
        else:
            script_obj.filepath = script_path

    if script_obj is not None:
        text_editor.text = script_obj

    area.type = prev_area_type


def register_wks_keymap():
    apptemplate_path = get_apptemplate_path()
    sys.path.append(apptemplate_path)
    from app_lib.Blender2DKeymap import KeyMap
    sys.path.remove(apptemplate_path)

    wm = bpy.context.window_manager
    kc_active = wm.keyconfigs.active  # modify preset
    keyconfig_init_from_data(kc_active, KeyMap.keyconfig_data)
    kc_addon = wm.keyconfigs.addon  # insert keymap item to addon
    if kc_addon:
        km = kc_addon.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new("wm.call_menu_pie", type="E", value="PRESS")
        kmi.properties.name = VIEW3D_MT_PIE_wks_storyboard.bl_idname
        kmi.active = True


def prop_shot_duration_get(self):
    scene = bpy.context.scene
    frame_diff = get_shot_duration(scene, self)

    fps = get_fps(scene)
    d_minute, d_second = divmod(frame_diff, fps * 60)
    d_second, d_frame = divmod(d_second, fps)
    duration_str = "{:02}:{:02}+{:02}".format(int(d_minute), int(d_second), int(d_frame))
    return duration_str


def prop_shot_duration_set(self, value):
    mo = TIME_RE.match(value)
    if mo is None:
        return

    min_str, sec_str, frame_str = mo.groups()
    scene = bpy.context.scene
    fps = get_fps(scene)
    duration_min = (int(min_str) * fps * 60) if min_str else 0
    duration_sec = (int(sec_str) * fps) if sec_str else 0
    duration = (int(frame_str) if frame_str else 0) + duration_sec + duration_min

    prev_duration = get_shot_duration(scene, self)
    delta_duration = duration - prev_duration
    shot_frame = self.frame

    # move all shots behind shot modified
    marker_iterator = get_shot_marker_iterator(scene)
    for marker in filter((lambda m: m.frame > shot_frame), marker_iterator):
        marker.frame += delta_duration
    scene.frame_end += delta_duration

    is_current_or_next_shot = shot_frame <= scene.frame_current
    is_next_shot = shot_frame + prev_duration <= scene.frame_current
    if is_next_shot:
        scene.frame_current += delta_duration
    if is_current_or_next_shot:
        adjust_preview_range(scene)

    adjust_shot_transitions(scene, self)


def prop_shot_name_get(self):
    return self.name[len(SHOT_MARKER_NAME_PREFIX):]


def prop_shot_name_set(self, value):
    update_shot_name(self, value)


def prop_shot_isolate_get(self):
    return self.use_preview_range


def prop_shot_isolate_set(self, value):
    scene: bpy.types.Scene = self
    self.use_preview_range = value
    if value:
        adjust_preview_range(scene)


def register():
    logger.debug("Registering module")
    if load_post_handler not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_factory_startup_post.append(load_factory_startup_handler)
        bpy.app.handlers.load_post.append(load_post_handler)
    class_name_list = [name for name, _ in inspect.getmembers(bpy.types) if name.find("_wks_") != -1]
    if VIEW3D_PT_wks_shot.bl_idname not in class_name_list:
        bpy.types.Scene.wks_shot_index = bpy.props.IntProperty(
            name="Shot Index", description="Index into marker-based shot list used in WKS_Storyboard app template",
            default=0, min=0, options={"HIDDEN", "SKIP_SAVE"})
        bpy.types.Scene.wks_shot_isolate = bpy.props.BoolProperty(
            name="Shot Isolate", description="Use preview range to isolate playback to shot currently worked on",
            get=prop_shot_isolate_get, set=prop_shot_isolate_set, options={"SKIP_SAVE"})
        bpy.types.TimelineMarker.wks_shot_name = bpy.props.StringProperty(
            name="Shot Name", get=prop_shot_name_get, set=prop_shot_name_set, options={"SKIP_SAVE"})
        bpy.types.TimelineMarker.wks_shot_duration = bpy.props.StringProperty(
            name="Shot Duration", get=prop_shot_duration_get, set=prop_shot_duration_set, options={"SKIP_SAVE"})
        bpy.types.VIEW3D_MT_editor_menus.prepend(header_panel)
        bpy.types.DOPESHEET_MT_editor_menus.prepend(header_panel)
        bpy.types.SEQUENCER_MT_editor_menus.prepend(header_panel)
        for cls in classes:
            bpy.utils.register_class(cls)

    register_wks_keymap()


def unregister():
    logger.debug("Unregistering module")
    if load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_factory_startup_post.remove(load_factory_startup_handler)
        bpy.app.handlers.load_post.remove(load_post_handler)
    class_name_list = [name for name, _ in inspect.getmembers(bpy.types) if name.find("_wks_") != -1]
    if VIEW3D_PT_wks_shot.bl_idname in class_name_list:
        del bpy.types.Scene.wks_shot_index
        del bpy.types.Scene.wks_shot_isolate
        del bpy.types.TimelineMarker.wks_shot_name
        del bpy.types.TimelineMarker.wks_shot_duration
        bpy.types.VIEW3D_MT_editor_menus.remove(header_panel)
        bpy.types.DOPESHEET_MT_editor_menus.remove(header_panel)
        bpy.types.SEQUENCER_MT_editor_menus.remove(header_panel)
        for cls in classes:
            bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
