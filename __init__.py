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

_MOUSE_EVENTS = {
    'LEFTMOUSE', 'MIDDLEMOUSE', 'RIGHTMOUSE',
    'BUTTON4MOUSE', 'BUTTON5MOUSE', 'BUTTON6MOUSE', 'BUTTON7MOUSE',
    'PEN', 'ERASER', 'MOUSEMOVE', 'TRACKPADPAN', 'TRACKPADZOOM',
    'MOUSEROTATE', 'MOUSESMARTZOOM',
    'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'WHEELINMOUSE', 'WHEELOUTMOUSE',
    'WHEELLEFTMOUSE', 'WHEELRIGHTMOUSE',
}

_UNSUPPORTED_KEY_EVENTS = {
    'ACTIONMOUSE', 'SELECTMOUSE', 'INBETWEEN_MOUSEMOVE',
    'TEXTINPUT', 'WINDOW_DEACTIVATE',
}

_UNSUPPORTED_KEY_PREFIXES = (
    'EVT_TWEAK_',
    'NDOF_',
    'TIMER',
)

_KEYMAP_NAMES = ("Pose", "Animation")


def _is_supported_key_event(identifier):
    if identifier == "NONE" or identifier in _MOUSE_EVENTS:
        return True
    if identifier in _UNSUPPORTED_KEY_EVENTS:
        return False
    return not identifier.startswith(_UNSUPPORTED_KEY_PREFIXES)


# EnumProperty 用キーアイテムリスト（キーボード / マウスのみ）
_KEY_ITEMS = [
    (item.identifier, item.name, "", item.value)
    for item in bpy.types.KeyMapItem.bl_rna.properties["type"].enum_items
    if _is_supported_key_event(item.identifier)
]


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
            getattr(context.scene, "autohide_on_play", False)
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

    mode: StringProperty(default="TRANSLATE")

    def modal(self, context, event):
        if event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER", "RIGHTMOUSE", "ESC"} and event.value == "RELEASE":
            _restore_overlays(self._original_visibility, self._hide_mode)
            return {"FINISHED", "PASS_THROUGH"}
        return {"PASS_THROUGH"}

    def cancel(self, _context):
        _restore_overlays(self._original_visibility, self._hide_mode)

    def invoke(self, context, _event):
        if not getattr(context.scene, "autohide_on_transform", False):
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
        "TRANSLATE": bpy.ops.transform.translate,
        "ROTATE": bpy.ops.transform.rotate,
        "RESIZE": bpy.ops.transform.resize,
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
    for km_name in _KEYMAP_NAMES:
        _sync_play_kmi(km_name, self.play_key, self.play_ctrl, self.play_shift, self.play_alt)


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
    wm = bpy.context.window_manager
    _sync_keyconfig_item(
        wm.keyconfigs.addon, km_name, "autohide.on_play", key, ctrl, shift, alt, track_addon=True
    )
    _sync_keyconfig_item(
        wm.keyconfigs.user, km_name, "autohide.on_play", key, ctrl, shift, alt
    )


def _update_toggle_keymap(self, _context):
    _sync_toggle_kmi("autohide.toggle", self.toggle_key,
                     self.toggle_ctrl, self.toggle_shift, self.toggle_alt)


def _remove_tracked_kmi(target_kmi):
    _addon_keymaps[:] = [
        (km, kmi) for km, kmi in _addon_keymaps
        if kmi != target_kmi
    ]


def _sync_keyconfig_item(kc, km_name, idname, key, ctrl, shift, alt, *, track_addon=False):
    if not kc:
        return

    km = next((k for k in kc.keymaps if k.name == km_name), None)
    if not km:
        if key == "NONE":
            return
        km = kc.keymaps.new(name=km_name, space_type="EMPTY")

    matches = [kmi for kmi in km.keymap_items if kmi.idname == idname]
    primary = matches[0] if matches else None

    for extra in matches[1:]:
        km.keymap_items.remove(extra)
        if track_addon:
            _remove_tracked_kmi(extra)

    if key == "NONE":
        if primary:
            km.keymap_items.remove(primary)
            if track_addon:
                _remove_tracked_kmi(primary)
        return

    if primary:
        _set_kmi_key(primary, key, ctrl, shift, alt)
        return

    kmi = km.keymap_items.new(idname, key, "PRESS",
                              ctrl=ctrl, shift=shift, alt=alt)
    if track_addon:
        _addon_keymaps.append((km, kmi))


def _sync_toggle_kmi(idname, key, ctrl, shift, alt):
    """toggle 用 kmi を addon / user keyconfig で同期する"""
    wm = bpy.context.window_manager
    kc_addon = wm.keyconfigs.addon
    kc_user = wm.keyconfigs.user
    for km_name in _KEYMAP_NAMES:
        _sync_keyconfig_item(
            kc_addon, km_name, idname, key, ctrl, shift, alt, track_addon=True
        )
        _sync_keyconfig_item(
            kc_user, km_name, idname, key, ctrl, shift, alt
        )


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
        default="SPACE",
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
    p = _get_prefs()
    if p:
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
