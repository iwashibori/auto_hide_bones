# AGENTS.md — Auto Hide Bones

## リポジトリ構成

このアドオンは**親リポジトリから独立した別リポジトリ**として管理されている。

```
BLD_myAddon/addons/              ← 親リポジトリ (github: blender-addons)
├── .git/
├── .gitignore                   ← auto_hide_bones/ を除外
├── gui_slider/
└── auto_hide_bones/             ← 独立リポジトリ (github: auto_hide_bones)
    ├── .git/                    ← 自分の .git を持つ
    └── ...
```

- **親リポジトリ**: `https://github.com/iwashibori/blender-addons` — gui_slider 等を管理
- **本リポジトリ**: `https://github.com/iwashibori/auto_hide_bones` — auto_hide_bones 単体
- 親の `.gitignore` で `auto_hide_bones/` は除外済み。git 操作は必ず本リポジトリ側で行うこと

## 作業ディレクトリの切り替え

Codex のワーキングディレクトリは `addons/`（親リポジトリ）がデフォルト。

- **「auto_hide_bones で作業して」** → `git -C auto_hide_bones` で本リポジトリに対して操作
- **「親リポジトリで作業して」** → そのまま `addons/` で操作
