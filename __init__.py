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

# EnumProperty 用キーアイテムリスト（静的に一度だけ生成）
_KEY_ITEMS = [
    (item.identifier, item.name, "", item.value)
    for item in bpy.types.KeyMapItem.bl_rna.properties["type"].enum_items
]


def _get_icon():
    pcoll = _preview_collections.get("main")
    if pcoll and "AUTOHIDE" in pcoll:
        return {"icon_value": pcoll["AUTOHIDE"].icon_id}
    return {"icon": "BONE_DATA"}


# ----------------------------------------------------------------
#  Operators
# ----------------------------------------------------------------

class AUTOHIDE_OT_on_play(Operator):
    bl_idname = "autohide.on_play"
    bl_label = "Auto Hide on Play"
    bl_description = "Hide armature and play animation. Restore visibility when stopped"
    bl_options = {"REGISTER"}

    _timer = None
    _original_visibility = {}

    def modal(self, context, event):
        if event.type == "TIMER" and not context.screen.is_animation_playing:
            self._restore(context)
            return {"FINISHED"}
        return {"PASS_THROUGH"}

    def invoke(self, context, _event):
        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()
            return {"FINISHED"}

        if not getattr(context.scene, "autohide_on_play", True) or context.mode != "POSE":
            bpy.ops.screen.animation_play()
            return {"FINISHED"}

        self._original_visibility = {}
        for area in context.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type != "VIEW_3D":
                    continue
                if hasattr(space, "show_object_viewport_armature"):
                    self._original_visibility[space] = (
                        "show_object_viewport_armature",
                        space.show_object_viewport_armature,
                    )
                    space.show_object_viewport_armature = False
                elif hasattr(space.overlay, "show_armatures"):
                    self._original_visibility[space] = (
                        "overlay.show_armatures",
                        space.overlay.show_armatures,
                    )
                    space.overlay.show_armatures = False

        bpy.ops.screen.animation_play()
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _restore(self, context):
        for space, (attr, val) in self._original_visibility.items():
            try:
                if "." in attr:
                    sub_attr = attr.split(".", 1)[1]
                    setattr(space.overlay, sub_attr, val)
                else:
                    setattr(space, attr, val)
            except (ReferenceError, AttributeError):
                pass
        self._original_visibility = {}
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

    mode: StringProperty(default="TRANSLATE")
    _original_visibility = {}

    def modal(self, context, event):
        if event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER", "RIGHTMOUSE", "ESC"} and event.value == "RELEASE":
            self._restore()
            return {"FINISHED", "PASS_THROUGH"}
        return {"PASS_THROUGH"}

    def invoke(self, context, _event):
        if not getattr(context.scene, "autohide_on_transform", True):
            return self._run_transform(context)

        self._original_visibility = {}
        if context.area and context.area.type == "VIEW_3D":
            space = context.space_data
            if space and space.type == "VIEW_3D" and space.overlay.show_bones:
                self._original_visibility[space] = True
                space.overlay.show_bones = False

        self._run_transform(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _run_transform(self, _context):
        try:
            if self.mode == "TRANSLATE":
                bpy.ops.transform.translate("INVOKE_DEFAULT")
            elif self.mode == "ROTATE":
                bpy.ops.transform.rotate("INVOKE_DEFAULT")
            elif self.mode == "RESIZE":
                bpy.ops.transform.resize("INVOKE_DEFAULT")
        except RuntimeError:
            return {"CANCELLED"}
        return {"FINISHED"}

    def _restore(self):
        for space, was_visible in self._original_visibility.items():
            try:
                space.overlay.show_bones = was_visible
            except ReferenceError:
                pass



class AUTOHIDE_OT_toggle_on_play(Operator):
    bl_idname = "autohide.toggle_on_play"
    bl_label = "Toggle Auto Hide on Play"
    bl_description = "Toggle Auto Hide on Play on/off"

    def execute(self, context):
        context.scene.autohide_on_play = not context.scene.autohide_on_play
        for area in context.screen.areas:
            area.tag_redraw()
        return {"FINISHED"}


class AUTOHIDE_OT_toggle_on_transform(Operator):
    bl_idname = "autohide.toggle_on_transform"
    bl_label = "Toggle Auto Hide on Transform"
    bl_description = "Toggle Auto Hide on Transform on/off"

    def execute(self, context):
        context.scene.autohide_on_transform = not context.scene.autohide_on_transform
        for area in context.screen.areas:
            area.tag_redraw()
        return {"FINISHED"}


# ----------------------------------------------------------------
#  Addon Preferences
# ----------------------------------------------------------------

def _update_play_keymap(self, _context):
    for km_name in ("Pose", "Animation"):
        _sync_play_kmi(km_name, self.play_key, self.play_ctrl, self.play_shift, self.play_alt)


_MOUSE_EVENTS = {
    'LEFTMOUSE', 'MIDDLEMOUSE', 'RIGHTMOUSE',
    'BUTTON4MOUSE', 'BUTTON5MOUSE', 'BUTTON6MOUSE', 'BUTTON7MOUSE',
    'PEN', 'ERASER', 'MOUSEMOVE', 'TRACKPADPAN', 'TRACKPADZOOM',
    'MOUSEROTATE', 'MOUSESMARTZOOM',
    'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'WHEELINMOUSE', 'WHEELOUTMOUSE',
    'WHEELLEFTMOUSE', 'WHEELRIGHTMOUSE',
}


def _set_kmi_key(kmi, key, ctrl, shift, alt):
    """map_type を適切に設定してからキーを変更"""
    if key in _MOUSE_EVENTS:
        kmi.map_type = 'MOUSE'
    else:
        kmi.map_type = 'KEYBOARD'
    kmi.type = key
    kmi.ctrl = ctrl
    kmi.shift = shift
    kmi.alt = alt


def _sync_play_kmi(km_name, key, ctrl, shift, alt):
    # addon keyconfig を更新
    for km_add, kmi in _addon_keymaps:
        if km_add.name == km_name and kmi.idname == "autohide.on_play":
            _set_kmi_key(kmi, key, ctrl, shift, alt)
    # user keyconfig も更新
    kc_user = bpy.context.window_manager.keyconfigs.user
    km = next((k for k in kc_user.keymaps if k.name == km_name), None)
    if km:
        for kmi in km.keymap_items:
            if kmi.idname == "autohide.on_play":
                _set_kmi_key(kmi, key, ctrl, shift, alt)


def _update_toggle_play_keymap(self, _context):
    _sync_toggle_kmi("autohide.toggle_on_play", self.toggle_play_key,
                     self.toggle_play_ctrl, self.toggle_play_shift, self.toggle_play_alt)


def _update_toggle_transform_keymap(self, _context):
    _sync_toggle_kmi("autohide.toggle_on_transform", self.toggle_transform_key,
                     self.toggle_transform_ctrl, self.toggle_transform_shift, self.toggle_transform_alt)


def _sync_toggle_kmi(idname, key, ctrl, shift, alt):
    """toggle 用 kmi を user keyconfig で同期（なければ作成、NONE なら削除）"""
    kc_user = bpy.context.window_manager.keyconfigs.user
    for km_name in ("Pose", "Animation"):
        km = next((k for k in kc_user.keymaps if k.name == km_name), None)
        if not km:
            continue
        existing = next((kmi for kmi in km.keymap_items if kmi.idname == idname), None)
        if key == "NONE":
            if existing:
                km.keymap_items.remove(existing)
        else:
            if existing:
                _set_kmi_key(existing, key, ctrl, shift, alt)
            else:
                kmi = km.keymap_items.new(idname, key, "PRESS",
                                          ctrl=ctrl, shift=shift, alt=alt)


class AutoHideBonesPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    # Auto Hide on Play hotkey
    play_key: EnumProperty(
        name="Key",
        items=_KEY_ITEMS,
        default=221,  # SPACE
        update=_update_play_keymap,
    )
    play_ctrl: BoolProperty(name="Ctrl", update=_update_play_keymap)
    play_shift: BoolProperty(name="Shift", update=_update_play_keymap)
    play_alt: BoolProperty(name="Alt", update=_update_play_keymap)

    # Toggle on Play hotkey
    toggle_play_key: EnumProperty(
        name="Key",
        items=_KEY_ITEMS,
        update=_update_toggle_play_keymap,
    )
    toggle_play_ctrl: BoolProperty(name="Ctrl", update=_update_toggle_play_keymap)
    toggle_play_shift: BoolProperty(name="Shift", update=_update_toggle_play_keymap)
    toggle_play_alt: BoolProperty(name="Alt", update=_update_toggle_play_keymap)

    # Toggle on Transform hotkey
    toggle_transform_key: EnumProperty(
        name="Key",
        items=_KEY_ITEMS,
        update=_update_toggle_transform_keymap,
    )
    toggle_transform_ctrl: BoolProperty(name="Ctrl", update=_update_toggle_transform_keymap)
    toggle_transform_shift: BoolProperty(name="Shift", update=_update_toggle_transform_keymap)
    toggle_transform_alt: BoolProperty(name="Alt", update=_update_toggle_transform_keymap)

    def draw(self, _context):
        layout = self.layout

        box = layout.box()
        box.label(text="Keymaps", icon="KEYINGSET")

        # Auto Hide on Play
        self._draw_hotkey_row(box, "Auto Hide on Play", "play_key", "play_ctrl", "play_shift", "play_alt")
        box.separator()
        # Toggle on Play
        self._draw_hotkey_row(box, "Toggle on Play", "toggle_play_key", "toggle_play_ctrl", "toggle_play_shift", "toggle_play_alt")
        box.separator()
        # Toggle on Transform
        self._draw_hotkey_row(box, "Toggle on Transform", "toggle_transform_key", "toggle_transform_ctrl", "toggle_transform_shift", "toggle_transform_alt")

    def _draw_hotkey_row(self, box, label, key_prop, ctrl_prop, shift_prop, alt_prop):
        split = box.split(factor=0.4)
        split.label(text=label)
        col = split.column(align=True)
        col.prop(self, key_prop, text="", event=True)
        row = col.row(align=True)
        row.prop(self, ctrl_prop, text="Ctrl", toggle=True)
        row.prop(self, shift_prop, text="Shift", toggle=True)
        row.prop(self, alt_prop, text="Alt", toggle=True)



# ----------------------------------------------------------------
#  UI
# ----------------------------------------------------------------

def _draw_playback_controls(self, context):
    self.layout.prop(context.scene, "autohide_on_play", text="Auto Hide", **_get_icon())


def _draw_viewport_header(self, context):
    if context.mode != "POSE":
        return
    layout = self.layout
    layout.separator()
    layout.prop(context.scene, "autohide_on_transform", text="", **_get_icon())


# ----------------------------------------------------------------
#  Keymaps
# ----------------------------------------------------------------

_addon_keymaps = []


def _register_keymaps():
    kc = bpy.context.window_manager.keyconfigs.addon
    if not kc:
        return

    # Preferences から保存済みキー設定を取得
    prefs = None
    for key in (__name__, __package__ or ""):
        prefs = bpy.context.preferences.addons.get(key)
        if prefs:
            break
    if prefs:
        p = prefs.preferences
        play_key = p.play_key or "SPACE"
        play_ctrl, play_shift, play_alt = p.play_ctrl, p.play_shift, p.play_alt
    else:
        play_key, play_ctrl, play_shift, play_alt = "SPACE", False, False, False

    # Pose Mode
    km = kc.keymaps.new(name="Pose", space_type="EMPTY")
    kmi = km.keymap_items.new("autohide.on_play", play_key, "PRESS",
                               ctrl=play_ctrl, shift=play_shift, alt=play_alt)
    _addon_keymaps.append((km, kmi))
    for key, mode in (("G", "TRANSLATE"), ("R", "ROTATE"), ("S", "RESIZE")):
        kmi = km.keymap_items.new("autohide.on_transform", key, "PRESS")
        kmi.properties.mode = mode
        _addon_keymaps.append((km, kmi))

    # Animation (Timeline / Dopesheet / Graph Editor etc.)
    km_anim = kc.keymaps.new(name="Animation", space_type="EMPTY")
    kmi = km_anim.keymap_items.new("autohide.on_play", play_key, "PRESS",
                                    ctrl=play_ctrl, shift=play_shift, alt=play_alt)
    _addon_keymaps.append((km_anim, kmi))


# ----------------------------------------------------------------
#  Registration
# ----------------------------------------------------------------

_CLASSES = (
    AUTOHIDE_OT_on_play,
    AUTOHIDE_OT_on_transform,
    AUTOHIDE_OT_toggle_on_play,
    AUTOHIDE_OT_toggle_on_transform,
    AutoHideBonesPreferences,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)

    pcoll = bpy.utils.previews.new()
    icon_dir = os.path.join(os.path.dirname(__file__), "icon")
    pcoll.load("AUTOHIDE", os.path.join(icon_dir, "AUTOHIDE.png"), "IMAGE")
    _preview_collections["main"] = pcoll

    bpy.types.Scene.autohide_on_play = BoolProperty(
        name="Auto Hide on Play",
        description="Auto hide armature during animation playback",
        default=False,
    )
    bpy.types.Scene.autohide_on_transform = BoolProperty(
        name="Auto Hide on Transform",
        description="Auto hide bones during transform (G/R/S)",
        default=False,
    )

    if hasattr(bpy.types, "DOPESHEET_HT_playback_controls"):
        bpy.types.DOPESHEET_HT_playback_controls.append(_draw_playback_controls)
    bpy.types.VIEW3D_MT_editor_menus.append(_draw_viewport_header)

    _register_keymaps()


def unregister():
    for km, kmi in _addon_keymaps:
        km.keymap_items.remove(kmi)
    _addon_keymaps.clear()

    # user keyconfig に追加したトグル kmi を削除
    kc_user = bpy.context.window_manager.keyconfigs.user
    for km_name in ("Pose", "Animation"):
        km = next((k for k in kc_user.keymaps if k.name == km_name), None)
        if not km:
            continue
        remove = [kmi for kmi in km.keymap_items
                  if kmi.idname in ("autohide.toggle_on_play", "autohide.toggle_on_transform")]
        for kmi in remove:
            km.keymap_items.remove(kmi)

    if hasattr(bpy.types, "DOPESHEET_HT_playback_controls"):
        bpy.types.DOPESHEET_HT_playback_controls.remove(_draw_playback_controls)
    bpy.types.VIEW3D_MT_editor_menus.remove(_draw_viewport_header)

    if hasattr(bpy.types.Scene, "autohide_on_play"):
        del bpy.types.Scene.autohide_on_play
    if hasattr(bpy.types.Scene, "autohide_on_transform"):
        del bpy.types.Scene.autohide_on_transform

    for pcoll in _preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    _preview_collections.clear()

    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
