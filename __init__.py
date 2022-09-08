# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import bpy
from bpy.types import Operator
from bpy.types import Scene
from bpy.props import BoolProperty, StringProperty
import bmesh

bl_info = {
    "name": "GN Indices Viewer",
    "author": "Ash",
    "version": (0, 1),
    "blender": (2, 95, 0),
    "location": "View3D > View",
    "description": "Display indices of active object",
    "warning": "",
    "doc_url": "",
    "category": "3D View",
}


class FakeModeSet(bpy.types.Operator):
    """Lock Object Mode"""

    bl_idname = "object.mode_set"
    bl_label = "Fake Mode Set Operator to lock current mode"
    mode: StringProperty()  # So it doesn't get angry when buttons from UI
    toggle: BoolProperty()  # try to pass stuff to it

    def execute(self, context):
        return {'FINISHED'}


class VIEW_OT_GNIndexViewer(Operator):
    bl_idname = "view.gn_viewer"
    bl_label = "GN Indices Viewer"
    bl_description = "See indices of verts, edges and faces simply"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'BLOCKING'}

    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D'

    def node_tree_changed_handler(self, scene, depsgraph):
        # create scene update handler
        if depsgraph.id_type_updated('NODETREE'):
            scene.gn_viewer_update = True

    def __init__(self):
        # stays active for life of session
        bpy.app.handlers.depsgraph_update_post.append(self.node_tree_changed_handler)

    def invoke(self, context, event):
        if context.view_layer.objects.active and context.view_layer.objects.active.type == 'MESH':
            self.execute(context)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'ERROR_INVALID_INPUT'}, "No suitable object found")
            return {'FINISHED'}

    def execute(self, context):

        bpy.ops.object.mode_set(mode='OBJECT')

        # get/set overlay settings
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        self.show_extra_indices_old = space.overlay.show_extra_indices
                        self.gizmo_object_rotate_old = space.show_gizmo_object_rotate
                        self.gizmo_object_scale_old = space.show_gizmo_object_scale
                        self.gizmo_object_translate_old = space.show_gizmo_object_translate
                        space.overlay.show_extra_indices = True
                        space.show_gizmo_object_rotate = False
                        space.show_gizmo_object_scale = False
                        space.show_gizmo_object_translate = False

        # check/set dev
        self.show_developer_ui_old = bpy.context.preferences.view.show_developer_ui
        if bpy.context.preferences.view.show_developer_ui is False:
            bpy.context.preferences.view.show_developer_ui = True

        # make new collection to copy objects to
        self.gn_viewer_coll = bpy.data.collections.new("GN Viewer")
        context.scene.collection.children.link(self.gn_viewer_coll)

        # get active object
        self.orig_obj = context.view_layer.objects.active

        # get first evaluated mesh and create object
        depsgraph = context.evaluated_depsgraph_get()
        self.gn_viewer_mesh = self.orig_obj.evaluated_get(depsgraph).data.copy()
        gn_viewer_object = bpy.data.objects.new("GN Viewer", self.gn_viewer_mesh)
        self.gn_viewer_coll.objects.link(gn_viewer_object)
        gn_viewer_object.select_set(True)

        bpy.ops.object.mode_set(mode='EDIT')
        self.orig_obj.hide_set(True)
        self.bm_viewer = bmesh.from_edit_mesh(self.gn_viewer_mesh)
        bpy.utils.register_class(FakeModeSet)
        context.scene.gn_viewer_update = False

        bpy.context.workspace.status_text_set_internal("Select item to view index number - Right click or ESC to end")

        return {'FINISHED'}

    def modal(self, context, event):

        if event.type == 'RIGHTMOUSE' or event.type == 'ESC':
            # end viewing if RIGHTMOUSE or ESC
            if event.value == 'PRESS':
                self.cleanup(context)
                return {'FINISHED'}
            return {'PASS_THROUGH'}

        else:
            context.view_layer.objects.active = self.orig_obj
            if context.scene.gn_viewer_update is True:
                self.update_eval_obj()
                context.scene.gn_viewer_update = False
            return {'PASS_THROUGH'}

    def update_eval_obj(self):
        # create evaluated object from active object
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_mesh = self.orig_obj.evaluated_get(depsgraph).data.copy()

        self.bm_viewer.clear()
        self.bm_viewer.from_mesh(eval_mesh)
        bmesh.update_edit_mesh(self.gn_viewer_mesh)

    def cleanup(self, context):
        # remove object and collection and enter object mode

        bpy.utils.unregister_class(FakeModeSet)

        # reset overlay settings
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.overlay.show_extra_indices = self.show_extra_indices_old
                        space.show_gizmo_object_rotate = self.gizmo_object_rotate_old
                        space.show_gizmo_object_scale = self.gizmo_object_scale_old
                        space.show_gizmo_object_translate = self.gizmo_object_translate_old

        bpy.context.preferences.view.show_developer_ui = self.show_developer_ui_old

        bpy.ops.object.mode_set(mode='OBJECT')

        # remove any objects and data
        for obj in self.gn_viewer_coll.objects:
            mesh = obj.data
            bpy.data.objects.remove(obj)
            bpy.data.meshes.remove(mesh)

        # remove temp collection
        bpy.data.collections.remove(self.gn_viewer_coll)

        # activate original object
        self.orig_obj.hide_set(False)
        self.orig_obj.select_set(True)
        context.view_layer.objects.active = self.orig_obj

        bpy.context.workspace.status_text_set_internal(None)

        # remove handler
        bpy.app.handlers.depsgraph_update_post.remove(self.node_tree_changed_handler)


def add_menu(self, context):
    self.layout.operator("view.gn_viewer", text='GN Index Viewer', icon='STICKY_UVS_DISABLE')


def register():
    bpy.utils.register_class(VIEW_OT_GNIndexViewer)
    bpy.types.VIEW3D_MT_view.append(add_menu)
    Scene.gn_viewer_update = BoolProperty(name="GN Viewer Update", description="Background flag for GN Viewer", default=False)


def unregister():
    bpy.utils.unregister_class(VIEW_OT_GNIndexViewer)
    bpy.types.VIEW3D_MT_view.remove(add_menu)
    del Scene.gn_viewer_update
