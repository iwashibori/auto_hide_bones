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


def _get_hide_mode():
    prefs = None
    for key in (__name__, __package__ or ""):
        prefs = bpy.context.preferences.addons.get(key)
        if prefs:
            break
    if prefs:
        return prefs.preferences.hide_mode
    return "BONES"


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
        # If already playing, just stop (the running modal will restore)
        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()
            return {"FINISHED"}

        should_hide = (
            getattr(context.scene, "autohide_on_play", False)
            and context.mode == "POSE"
        )

        if should_hide:
            self._hide(context)

        bpy.ops.screen.animation_play()

        if not should_hide:
            return {"FINISHED"}

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _hide(self, context):
        self._hide_mode = _get_hide_mode()
        self._space = None
        space = context.space_data
        if not space or space.type != "VIEW_3D":
            return
        attr = "show_overlays" if self._hide_mode == "OVERLAYS" else "show_bones"
        if getattr(space.overlay, attr):
            setattr(space.overlay, attr, False)
            self._space = space

    def _restore(self, context):
        space = getattr(self, "_space", None)
        if space:
            attr = "show_overlays" if self._hide_mode == "OVERLAYS" else "show_bones"
            try:
                setattr(space.overlay, attr, True)
            except ReferenceError:
                pass
            self._space = None
        timer = getattr(self, "_timer", None)
        if timer:
            context.window_manager.event_timer_remove(timer)
            self._timer = None

    def cancel(self, context):
        self._restore(context)


class AUTOHIDE_OT_on_transform(Operator):
    bl_idname = "autohide.on_transform"
    bl_label = "Auto Hide on Transform"
    bl_description = "Hide armature during transform operation"
    bl_options = {"REGISTER"}

    mode: StringProperty(default="TRANSLATE")

    def modal(self, context, event):
        if event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER", "RIGHTMOUSE", "ESC"} and event.value == "RELEASE":
            self._restore()
            return {"FINISHED", "PASS_THROUGH"}
        return {"PASS_THROUGH"}

    def invoke(self, context, _event):
        if not getattr(context.scene, "autohide_on_transform", False):
            return self._run_transform()

        self._hide_mode = _get_hide_mode()
        self._space = None
        space = context.space_data
        if space and space.type == "VIEW_3D":
            attr = "show_overlays" if self._hide_mode == "OVERLAYS" else "show_bones"
            if getattr(space.overlay, attr):
                setattr(space.overlay, attr, False)
                self._space = space

        result = self._run_transform()
        if result == {"CANCELLED"}:
            self._restore()
            return {"CANCELLED"}

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _run_transform(self):
        _OPS = {
            "TRANSLATE": bpy.ops.transform.translate,
            "ROTATE": bpy.ops.transform.rotate,
            "RESIZE": bpy.ops.transform.resize,
        }
        op = _OPS.get(self.mode)
        if not op:
            return {"CANCELLED"}
        try:
            op("INVOKE_DEFAULT")
        except RuntimeError:
            return {"CANCELLED"}
        return {"FINISHED"}

    def _restore(self):
        space = getattr(self, "_space", None)
        if space:
            attr = "show_overlays" if self._hide_mode == "OVERLAYS" else "show_bones"
            try:
                setattr(space.overlay, attr, True)
            except ReferenceError:
                pass
            self._space = None


class AUTOHIDE_OT_toggle(Operator):
    bl_idname = "autohide.toggle"
    bl_label = "Toggle Auto Hide"
    bl_description = "Toggle Auto Hide on/off"

    def execute(self, context):
        scene = context.scene
        new_state = not (scene.autohide_on_play or scene.autohide_on_transform)
        scene.autohide_on_play = new_state
        scene.autohide_on_transform = new_state
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


def _update_toggle_keymap(self, _context):
    _sync_toggle_kmi("autohide.toggle", self.toggle_key,
                     self.toggle_ctrl, self.toggle_shift, self.toggle_alt)


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

    hide_mode: EnumProperty(
        name="Hide Mode",
        items=[
            ("BONES", "Bones Only", "Hide bones only"),
            ("OVERLAYS", "All Overlays", "Hide all overlays"),
        ],
        default="OVERLAYS",
    )

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

    # Toggle hotkey
    toggle_key: EnumProperty(
        name="Key",
        items=_KEY_ITEMS,
        default="C",
        update=_update_toggle_keymap,
    )
    toggle_ctrl: BoolProperty(name="Ctrl", update=_update_toggle_keymap)
    toggle_shift: BoolProperty(name="Shift", update=_update_toggle_keymap)
    toggle_alt: BoolProperty(name="Alt", default=True, update=_update_toggle_keymap)

    def draw(self, _context):
        layout = self.layout

        box = layout.box()
        box.label(text="Hide Mode", icon="OVERLAY")
        box.row().prop(self, "hide_mode", expand=True)

        box = layout.box()
        box.label(text="Keymaps", icon="KEYINGSET")

        # Auto Hide on Play
        self._draw_hotkey_row(box, "Auto Hide on Play", "play_key", "play_ctrl", "play_shift", "play_alt")
        box.separator()
        # Toggle Auto Hide
        self._draw_hotkey_row(box, "Toggle Auto Hide", "toggle_key", "toggle_ctrl", "toggle_shift", "toggle_alt")

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

def _draw_viewport_header(self, context):
    if context.mode != "POSE":
        return
    layout = self.layout
    layout.separator()
    layout.operator("autohide.toggle", text="",
                    depress=context.scene.autohide_on_play or context.scene.autohide_on_transform,
                    **_get_icon())


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
        toggle_key = p.toggle_key or "C"
        toggle_ctrl, toggle_shift, toggle_alt = p.toggle_ctrl, p.toggle_shift, p.toggle_alt
    else:
        play_key, play_ctrl, play_shift, play_alt = "SPACE", False, False, False
        toggle_key, toggle_ctrl, toggle_shift, toggle_alt = "C", False, False, True

    # Pose Mode
    km = kc.keymaps.new(name="Pose", space_type="EMPTY")
    kmi = km.keymap_items.new("autohide.on_play", play_key, "PRESS",
                               ctrl=play_ctrl, shift=play_shift, alt=play_alt)
    _addon_keymaps.append((km, kmi))
    for key, mode in (("G", "TRANSLATE"), ("R", "ROTATE"), ("S", "RESIZE")):
        kmi = km.keymap_items.new("autohide.on_transform", key, "PRESS")
        kmi.properties.mode = mode
        _addon_keymaps.append((km, kmi))
    if toggle_key != "NONE":
        kmi = km.keymap_items.new("autohide.toggle", toggle_key, "PRESS",
                                   ctrl=toggle_ctrl, shift=toggle_shift, alt=toggle_alt)
        _addon_keymaps.append((km, kmi))

    # Animation (Timeline / Dopesheet / Graph Editor etc.)
    km_anim = kc.keymaps.new(name="Animation", space_type="EMPTY")
    kmi = km_anim.keymap_items.new("autohide.on_play", play_key, "PRESS",
                                    ctrl=play_ctrl, shift=play_shift, alt=play_alt)
    _addon_keymaps.append((km_anim, kmi))
    if toggle_key != "NONE":
        kmi = km_anim.keymap_items.new("autohide.toggle", toggle_key, "PRESS",
                                        ctrl=toggle_ctrl, shift=toggle_shift, alt=toggle_alt)
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

    bpy.types.Scene.autohide_on_play = BoolProperty(
        name="Auto Hide on Play",
        description="Auto hide bones during animation playback",
        default=False,
    )
    bpy.types.Scene.autohide_on_transform = BoolProperty(
        name="Auto Hide on Transform",
        description="Auto hide bones during transform (G/R/S)",
        default=False,
    )
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
                  if kmi.idname == "autohide.toggle"]
        for kmi in remove:
            km.keymap_items.remove(kmi)

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
