# SPDX-License-Identifier: GPL-3.0-or-later
#
# Copyright (C) 2026 iwashi
#
# This file is part of Auto Hide Bones.
#
#  Auto Hide Bones is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 3
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.

import os
import bpy
import bpy.utils.previews
from bpy.types import Operator
from bpy.props import BoolProperty, EnumProperty, StringProperty

# カスタムアイコン
_preview_collections = {}

def _get_icon():
    pcoll = _preview_collections.get("main")
    if pcoll and "AUTOHIDE" in pcoll:
        return {"icon_value": pcoll["AUTOHIDE"].icon_id}
    return {"icon": "BONE_DATA"}


def _get_prefs():
    for key in (__name__, __package__ or ""):
        entry = bpy.context.preferences.addons.get(key)
        if entry:
            return entry.preferences
    return None


def _get_hide_mode():
    prefs = _get_prefs()
    return prefs.hide_mode if prefs else "BONES"


# ----------------------------------------------------------------
#  Hide / Restore helpers
# ----------------------------------------------------------------

def _overlay_attr(hide_mode):
    return "show_overlays" if hide_mode == "OVERLAYS" else "show_bones"


def _get_view3d_space(context):
    space = getattr(context, "space_data", None)
    if not space or getattr(space, "type", None) != "VIEW_3D":
        return None
    if not hasattr(space, "overlay"):
        return None
    return space


def _hide_overlays(context, hide_mode, *, all_viewports=False):
    """Hide bones/overlays and return set of spaces that were visible."""
    attr = _overlay_attr(hide_mode)
    hidden = set()

    if all_viewports:
        for area in context.screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            if getattr(space, "type", None) != "VIEW_3D" or not hasattr(space, "overlay"):
                continue
            if getattr(space.overlay, attr, False):
                hidden.add(space)
                setattr(space.overlay, attr, False)
    else:
        space = _get_view3d_space(context)
        if space and getattr(space.overlay, attr, False):
            hidden.add(space)
            setattr(space.overlay, attr, False)

    return hidden


def _restore_overlays(hidden_spaces, hide_mode):
    """Restore previously hidden overlays."""
    attr = _overlay_attr(hide_mode)
    for space in hidden_spaces:
        try:
            setattr(space.overlay, attr, True)
        except ReferenceError:
            pass


# ----------------------------------------------------------------
#  Operators
# ----------------------------------------------------------------

class AUTOHIDE_OT_on_play(Operator):
    bl_idname = "autohide.on_play"
    bl_label = "Auto Hide on Play"
    bl_description = "Hide armature and play animation. Restore visibility when stopped"
    bl_options = {"REGISTER"}

    def modal(self, context, event):
        if event.type == "TIMER" and not context.screen.is_animation_playing:
            self._restore(context)
            return {"FINISHED"}
        return {"PASS_THROUGH"}

    def invoke(self, context, _event):
        # 再生中なら停止して終了
        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()
            return {"FINISHED"}

        # 自動非表示が有効かつポーズモードなら非表示にする
        should_hide = (
            getattr(context.scene, "autohide_enabled", False)
            and context.mode == "POSE"
        )
        if should_hide:
            self._hide_mode = _get_hide_mode()
            self._original_visibility = _hide_overlays(
                context, self._hide_mode, all_viewports=True
            )

        # 再生開始（常に1回だけ呼ぶ）
        bpy.ops.screen.animation_play()

        # 非表示にしたスペースがあればモーダル監視を開始
        if should_hide and self._original_visibility:
            wm = context.window_manager
            self._timer = wm.event_timer_add(0.1, window=context.window)
            wm.modal_handler_add(self)
            return {"RUNNING_MODAL"}

        return {"FINISHED"}

    def _restore(self, context):
        _restore_overlays(self._original_visibility, self._hide_mode)
        self._original_visibility = set()
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

    def cancel(self, context):
        self._restore(context)
        return {"CANCELLED"}


class AUTOHIDE_OT_on_transform(Operator):
    bl_idname = "autohide.on_transform"
    bl_label = "Auto Hide on Transform"
    bl_description = "Hide armature during transform operation"
    bl_options = {"REGISTER"}

    mode: StringProperty(default="MOVE")

    def modal(self, context, event):
        if event.type in {"RIGHTMOUSE", "ESC"}:
            _restore_overlays(self._original_visibility, self._hide_mode)
            return {"FINISHED", "PASS_THROUGH"}
        if event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER"} and event.value == "RELEASE":
            _restore_overlays(self._original_visibility, self._hide_mode)
            return {"FINISHED", "PASS_THROUGH"}
        return {"PASS_THROUGH"}

    def cancel(self, _context):
        _restore_overlays(self._original_visibility, self._hide_mode)

    def invoke(self, context, _event):
        if not getattr(context.scene, "autohide_enabled", False):
            return self._run_transform()

        self._hide_mode = _get_hide_mode()
        self._original_visibility = _hide_overlays(context, self._hide_mode)

        result = self._run_transform()
        if "CANCELLED" in result:
            _restore_overlays(self._original_visibility, self._hide_mode)
            self._original_visibility = set()
            return result

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    _TRANSFORM_OPS = {
        "MOVE": bpy.ops.transform.translate,
        "ROTATE": bpy.ops.transform.rotate,
        "SCALE": bpy.ops.transform.resize,
    }

    def _run_transform(self):
        op = self._TRANSFORM_OPS.get(self.mode)
        if not op:
            return {"CANCELLED"}
        try:
            return op("INVOKE_DEFAULT")
        except RuntimeError:
            return {"CANCELLED"}


class AUTOHIDE_OT_toggle(Operator):
    bl_idname = "autohide.toggle"
    bl_label = "Toggle Auto Hide"
    bl_description = "Toggle Auto Hide on/off"

    def execute(self, context):
        context.scene.autohide_enabled = not context.scene.autohide_enabled
        for area in context.screen.areas:
            area.tag_redraw()
        return {"FINISHED"}


# ----------------------------------------------------------------
#  Addon Preferences
# ----------------------------------------------------------------

def _get_user_kmi(km_name, operator_idname):
    """user keyconfig から指定オペレーターの kmi を取得"""
    kc = bpy.context.window_manager.keyconfigs.user
    km = kc.keymaps.get(km_name)
    if not km:
        return None
    for kmi in km.keymap_items:
        if kmi.idname == operator_idname:
            return kmi
    return None


def _draw_kmi_row(layout, km_name, operator_idname, label):
    """NodePie 風の kmi 行描画"""
    kmi = _get_user_kmi(km_name, operator_idname)
    if not kmi:
        layout.label(text=f"{label} (not found)")
        return

    # ラベル行
    row = layout.row(align=True)
    row.scale_y = 0.8
    row.label(text=label)

    # kmi 行
    row = layout.row(align=True)
    row.active = kmi.active
    sub = row.row(align=True)
    sub.prop(kmi, "active", text="")
    sub = row.row(align=True)
    sub.scale_x = 0.5
    sub.prop(kmi, "type", full_event=True, text="")


class AutoHideBonesPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    hide_mode: EnumProperty(
        name="Hide Mode",
        items=[
            ("BONES", "Bones Only", "Hide bones only"),
            ("OVERLAYS", "All Overlays", "Hide all overlays"),
        ],
        default="BONES",
    )

    def draw(self, _context):
        layout = self.layout

        # --- Hide Mode セクション ---
        main_col = layout.column(align=True)
        header_box = main_col.box()
        header_row = header_box.row(align=True)
        header_row.scale_y = 0.85
        sub = header_row.row(align=True)
        sub.alignment = "CENTER"
        sub.label(text="Hide Mode")
        body_box = main_col.box()
        body_box.row().prop(self, "hide_mode", expand=True)

        # --- Keymap セクション ---
        row = layout.row()

        def _draw_km_column(parent, km_name, title):
            main_col = parent.column(align=True)
            header_box = main_col.box()
            hr = header_box.row(align=True)
            hr.scale_y = 0.85
            sub = hr.row(align=True)
            sub.alignment = "CENTER"
            sub.label(text=title)
            body_box = main_col.box()
            col = body_box.column()
            col.scale_y = 0.9
            _draw_kmi_row(col, km_name, "autohide.on_play", "Play / Stop:")
            col.separator()
            _draw_kmi_row(col, km_name, "autohide.toggle", "Auto Hide ON/OFF:")

        _draw_km_column(row, "Pose", "Keymap (Pose)")
        _draw_km_column(row, "Animation", "Keymap (Animation)")


# ----------------------------------------------------------------
#  UI
# ----------------------------------------------------------------

def _draw_viewport_header(self, context):
    if context.mode != "POSE":
        return
    layout = self.layout
    layout.separator()
    layout.operator("autohide.toggle", text="",
                    depress=context.scene.autohide_enabled,
                    **_get_icon())


# ----------------------------------------------------------------
#  Keymaps
# ----------------------------------------------------------------

_addon_keymaps = []


def _register_keymaps():
    kc = bpy.context.window_manager.keyconfigs.addon
    if not kc:
        return

    # Pose Mode
    km = kc.keymaps.new(name="Pose", space_type="EMPTY")
    kmi = km.keymap_items.new("autohide.on_play", "SPACE", "PRESS")
    _addon_keymaps.append((km, kmi))
    for key, mode in (("G", "MOVE"), ("R", "ROTATE"), ("S", "SCALE")):
        kmi = km.keymap_items.new("autohide.on_transform", key, "PRESS")
        kmi.properties.mode = mode
        _addon_keymaps.append((km, kmi))
    kmi = km.keymap_items.new("autohide.toggle", "C", "PRESS", alt=True)
    _addon_keymaps.append((km, kmi))

    # Animation (Timeline / Dopesheet / Graph Editor etc.)
    km_anim = kc.keymaps.new(name="Animation", space_type="EMPTY")
    kmi = km_anim.keymap_items.new("autohide.on_play", "SPACE", "PRESS")
    _addon_keymaps.append((km_anim, kmi))
    kmi = km_anim.keymap_items.new("autohide.toggle", "C", "PRESS", alt=True)
    _addon_keymaps.append((km_anim, kmi))


# ----------------------------------------------------------------
#  Registration
# ----------------------------------------------------------------

_CLASSES = (
    AUTOHIDE_OT_on_play,
    AUTOHIDE_OT_on_transform,
    AUTOHIDE_OT_toggle,
    AutoHideBonesPreferences,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)

    pcoll = bpy.utils.previews.new()
    icon_dir = os.path.join(os.path.dirname(__file__), "icon")
    pcoll.load("AUTOHIDE", os.path.join(icon_dir, "AUTOHIDE.png"), "IMAGE")
    _preview_collections["main"] = pcoll

    bpy.types.Scene.autohide_enabled = BoolProperty(
        name="Auto Hide Bones",
        description="Auto hide bones during playback and transform",
        default=False,
    )
    bpy.types.VIEW3D_MT_editor_menus.append(_draw_viewport_header)

    _register_keymaps()


def unregister():
    for km, kmi in _addon_keymaps:
        km.keymap_items.remove(kmi)
    _addon_keymaps.clear()

    bpy.types.VIEW3D_MT_editor_menus.remove(_draw_viewport_header)

    if hasattr(bpy.types.Scene, "autohide_enabled"):
        del bpy.types.Scene.autohide_enabled

    for pcoll in _preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    _preview_collections.clear()

    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
