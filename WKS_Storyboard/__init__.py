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
import os
import sys

import bpy
from bl_keymap_utils.io import keyconfig_import_from_data
from bpy.app.handlers import persistent
from bpy.types import Menu, Operator

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


def get_shot(scene, frame=None, offset=0) -> (int, bpy.types.TimelineMarker):
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


def create_shot_name(scene):
    shot_number = len(scene.timeline_markers) + 1
    return "SHOT_{:03}".format(shot_number)


class WKS_OT_shot_offset(Operator):
    bl_idname = "wks_shot.shot_offset"
    bl_label = "Shot Offset"

    previous: bpy.props.BoolProperty(name="Previous Shot", description="Switch to previous shot.", default=False)

    def execute(self, context):
        scene = context.scene
        marker_other_shot = get_shot(scene, offset=-1 if self.previous else 1)
        if marker_other_shot is None:
            self.report({"INFO"}, "No other shot to jump to.")
        else:
            scene.frame_set(marker_other_shot.frame)

        return {"FINISHED"}


class WKS_OT_shot_new(Operator):
    bl_idname = "wks_shot.new"
    bl_label = "New Shot"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        logger.info("CREATING SHOT")
        scene = context.scene
        marker_shot = get_shot(scene)
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

        if frame_new_shot is not None:
            name_new_shot = create_shot_name(scene)
            scene.timeline_markers.new(name_new_shot, frame=frame_new_shot)
            scene.frame_set(frame_new_shot)

        return {"FINISHED"}


# spawn an edit mode selection pie (run while object is in edit mode to get a valid output)
class VIEW3D_MT_PIE_wks_storyboard(Menu):
    # label is displayed at the center of the pie menu.
    bl_label = "WKS Storyboard Menu"

    def draw(self, context):
        layout = self.layout

        pie = layout.menu_pie()
        op = pie.operator("wks_shot.shot_offset", text="Prev. Shot")
        op.previous = True
        op = pie.operator("wks_shot.shot_offset", text="Next Shot")
        op.previous = False
        op = pie.separator()
        op = pie.separator()
        op = pie.separator()
        op = pie.separator()
        op = pie.separator()
        op = pie.operator("wks_shot.new")


classes = [
    WKS_OT_shot_offset,
    WKS_OT_shot_new,
    VIEW3D_MT_PIE_wks_storyboard,
]


def register():
    logger.debug("Registering module")
    bpy.app.handlers.load_factory_startup_post.append(load_handler)
    for cls in classes:
        bpy.utils.register_class(cls)

    file_path = os.path.dirname(os.path.abspath(__file__))
    file_name = os.path.splitext(os.path.basename(__file__))[0]
    sys.path.append(file_path)
    from .app_lib.Blender2DKeymap import KeyMap
    keyconfig_import_from_data(file_name, KeyMap.keyconfig_data)
    sys.path.remove(file_path)

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new("wm.call_menu_pie", type="E", value="PRESS")
        kmi.properties.name = "VIEW3D_MT_PIE_wks_storyboard"
        kmi.active = True

def unregister():
    logger.debug("Unregistering module")
    bpy.app.handlers.load_factory_startup_post.remove(load_handler)
    for cls in classes:
        bpy.utils.unregister_class(cls)
