"""アプリケーション状態（シングルユーザー・ローカルアプリ）。"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import threading
from pathlib import Path

from saxsketch.core.project import Member, Project
from saxsketch.core.registry import get_registry
from saxsketch.core.schema import ParamSet

from .hostenv import IS_WSL, windows_documents

#: 設定ファイルの版。**上げるのは移行が要るときだけ。**
#: 2 = 出力先を「環境から導く」に変えた版（下の `_migrate_export_root`）。
SETTINGS_VERSION = 2

#: 旧バージョンが既定として書き込んでいた出力先。移行判定にだけ使う。
_LEGACY_EXPORT_ROOT = Path.home() / "Documents" / "SaxSketch"

DEFAULT_SETTINGS = {
    "settings_version": SETTINGS_VERSION,
    "external_tools": {
        "freecad": "",
        "slicer": "",
        "openwind_note": "Phase 2 で統合予定",
    },
    "recent_projects": [],
    # 空 = 未設定。既定は `default_export_root()` がその都度導く。ここに値を
    # 焼き付けると、環境（WSL / ネイティブ）が変わっても古い場所を指し続ける。
    "export_root": "",
}


def settings_dir() -> Path:
    """設定の置き場所。`SAXSKETCH_HOME` で差し替えられる。

    差し替え口が要るのは**テストのため**。以前は実ユーザーの
    `~/.saxsketch/settings.json` を直接書き換えていて、「最近使ったプロジェクト」が
    pytest の一時ディレクトリ 10 件で埋まっていた（実際に起きた）。
    """
    override = os.environ.get("SAXSKETCH_HOME")
    return Path(override) if override else Path.home() / ".saxsketch"


def settings_file() -> Path:
    return settings_dir() / "settings.json"


def default_export_root() -> Path:
    """エクスポートの既定の出力先。

    WSL では **Windows 側の**ドキュメントを使う。サーバは Linux で動いているが、
    出来上がった STL や入稿 ZIP を掴むのは Windows のエクスプローラだから、
    `~/Documents` に置くと利用者からはほぼ辿れない場所に消える。
    """
    docs = windows_documents() if IS_WSL else None
    return (docs or Path.home() / "Documents") / "SaxSketch"


def _migrate_export_root(value: str) -> str:
    """旧版が既定として書き込んだ出力先を「未設定」に戻す（版 1 → 2 で一度だけ）。

    旧既定は Linux 側の `~/Documents/SaxSketch`。WSL で動かすと Windows の
    エクスプローラからほぼ辿れない場所で、しかも**利用者が選んだのではなく
    `DEFAULT_SETTINGS` が勝手に書いた値**なので捨てて構わない。

    判定を「実在しないこと」にしてはいけない —— そのフォルダは書き出した結果
    実在するのが普通で、条件がほぼ成立しない。かといって値の一致だけで毎回
    消すと、**同じ場所を自分で選び直した人の設定が二度と保存できない**。
    だから一致で判定し、**版で一度きり**にする。保存時に版が刻まれる。
    """
    if IS_WSL and value and Path(value) == _LEGACY_EXPORT_ROOT:
        return ""
    return value


def _existing(paths) -> list[str]:
    """実在するパスだけ残す。"""
    return [p for p in paths if p and Path(p).exists()]


class MemberState:
    """部品 1 つぶんの実行時状態（コンポーネント実体・現在値・キャッシュ）。

    **キャッシュは部品ごとに持つ。** セットでは 3 部品が同時に生きていて、
    どれか 1 つを触っただけで全部を作り直すと、マウスピース 5.6〜6.2 秒 ＋
    リガチャー 1.3 秒 を毎回払うことになる。鍵（`AppState._member_key`）に
    **束ねた参照**が入っているので、マウスピースを動かしたときだけ従属部品の
    鍵も変わる ＝ 無効化の条件を別に書かなくてよい。
    """

    def __init__(self, component, paramset: ParamSet):
        self.component = component
        self.paramset = paramset
        # 採寸ワークフロー（Phase 4-A）。音響基準定数(size_info)への局所上書き。
        self.size_overrides: dict = {}
        self.base_size: dict = {}   # コンポーネント既定の size_info（descriptor 由来のコピー）
        self.pending_derived: dict | None = None
        self.stl_cache: dict[str, bytes] = {}
        # 参照コンポーネントの STL（重ね表示）。鍵は `ref_hash()` なので
        # パラメータを動かしても消えない（参照が変わったときだけ作り直す）。
        self.ref_stl_cache: dict[str, bytes] = {}
        self.sim_cache: dict[str, dict] = {}
        self.imp_cache: dict[str, dict] = {}
        self.wav_cache: dict[str, tuple] = {}

    def clear_caches(self) -> None:
        self.stl_cache.clear()
        self.ref_stl_cache.clear()
        self.sim_cache.clear()
        self.imp_cache.clear()
        self.wav_cache.clear()

    def bind_size(self) -> None:
        """コンポーネント既定の size_info を控え、局所上書きを重ねて再束縛する。

        `component.size_info` は descriptor の dict 参照そのものなので、控えは必ず
        コピーする。上書きは新しい dict を割り当てて行い、descriptor は汚さない。
        """
        base = getattr(self.component, "size_info", None)
        self.base_size = dict(base) if base else {}
        self.apply_size_overrides()

    def apply_size_overrides(self) -> None:
        if not hasattr(self.component, "size_info"):
            return
        self.component.size_info = {**self.base_size, **self.size_overrides}


class AppState:
    def __init__(self):
        self.registry = get_registry()
        self.project: Project | None = None
        #: 部品ID → 実行時状態。`component` / `paramset` は active への委譲。
        self.members: dict[str, MemberState] = {}
        self.build_lock = threading.Lock()
        # 旧プロジェクトを開いたときの変換報告（`Component.migrate_params`）や、
        # セットの部品を足し引きしたときの形状変化の報告。
        # 黙って値を変えないための経路なので、利用者が何か触るまで残す。
        self.notices: list[str] = []
        # 直近の `apply_params` が帯／壁で丸めた項目（`ParamSet.adjustments`）。
        # `notices` と違い**次の適用で必ず入れ替わる** —— スライダを 1 本動かす
        # たびに出るものなので、残すと古い報告が積み上がる。
        self.adjustments: list[dict] = []
        self.settings = self._load_settings()

    # ---------------------------------------------------------- active への委譲
    # 単体しか無かった頃の呼び出し（`STATE.component` / `STATE.paramset` …）が
    # そのまま動く。セットで増えたのは「どのメンバーを見ているか」だけなので、
    # 全経路を書き換えるより委譲で吸収するほうが壊す面が小さい。

    @property
    def member_state(self) -> MemberState:
        return self.members[self.project.active]

    @property
    def component(self):
        return self.members[self.project.active].component if self.project else None

    @property
    def paramset(self) -> ParamSet | None:
        return self.members[self.project.active].paramset if self.project else None

    @property
    def size_overrides(self) -> dict:
        return self.member_state.size_overrides

    @size_overrides.setter
    def size_overrides(self, value: dict) -> None:
        self.member_state.size_overrides = value

    @property
    def _pending_derived(self) -> dict | None:
        return self.member_state.pending_derived

    @_pending_derived.setter
    def _pending_derived(self, value: dict | None) -> None:
        self.member_state.pending_derived = value

    # ---------------------------------------------------------- 設定

    def _load_settings(self) -> dict:
        loaded: dict = {}
        path = settings_file()
        if path.exists():
            with contextlib.suppress(Exception):
                loaded = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_SETTINGS)
        merged.update(loaded)
        # 消えたプロジェクトは読み込みの時点で落とす。`/api/recent` も同じ条件で
        # 濾しているが、保存側が素通しだと一度混ざったゴミが永久に残る。
        merged["recent_projects"] = _existing(merged.get("recent_projects", []))
        # 版は **loaded** で見る。merged は既定で埋まっているので判定できない。
        if int(loaded.get("settings_version", 1)) < SETTINGS_VERSION:
            merged["export_root"] = _migrate_export_root(merged.get("export_root", ""))
        merged["settings_version"] = SETTINGS_VERSION
        return merged

    def save_settings(self) -> None:
        settings_dir().mkdir(parents=True, exist_ok=True)
        settings_file().write_text(
            json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def export_root(self) -> Path:
        """エクスポートの出力先。設定が空なら環境から導く。"""
        value = str(self.settings.get("export_root") or "").strip()
        return Path(value) if value else default_export_root()

    def push_recent(self, path: str) -> None:
        recent = [p for p in _existing(self.settings.get("recent_projects", []))
                  if p != path]
        recent.insert(0, path)
        self.settings["recent_projects"] = recent[:10]
        self.save_settings()

    # ---------------------------------------------------------- プロジェクト

    def _new_member(self, component_id: str, name: str | None = None) -> Member:
        """テンプレート既定値で部品 1 つを起こす（実行時状態はまだ作らない）。"""
        inst = self.registry.get(self.project.instrument_id)
        component = inst.make_component(component_id, self.project.template_id)
        ps = ParamSet(component.param_specs(),
                      component.template.get(component_id, {}))
        tmpl_label = inst.templates[self.project.template_id].get(
            "label", self.project.template_id)
        return Member(component_id=component_id,
                      name=name or f"{tmpl_label} {component.label}",
                      params=dict(ps.values))

    def _mount(self, member: Member) -> list[str]:
        """メンバーの実行時状態を作って束ねる。変換報告（あれば）を返す。

        **`ParamSet.apply` の前に `migrate_params` を通す。** apply は未知キーを
        黙って捨てるので、後では旧値が残っていない。
        """
        inst = self.registry.get(self.project.instrument_id)
        component = inst.make_component(member.component_id, self.project.template_id)
        paramset = ParamSet(component.param_specs(),
                            component.template.get(member.component_id, {}))
        values, notices = component.migrate_params(dict(member.params))
        paramset.apply(values)
        member.params = dict(paramset.values)
        ms = MemberState(component, paramset)
        # 採寸チェックポイントに保存された音響基準の上書きを復元する。
        ms.size_overrides = dict(
            (member.survey or {}).get("checkpoint", {}).get("size_overrides", {}))
        self.members[member.component_id] = ms
        ms.bind_size()
        return notices

    def _mount_all(self) -> list[str]:
        self.members = {}
        notices: list[str] = []
        for member in self.project.members.values():
            notices += self._mount(member)
        self._bind_all_refs()
        return notices

    def new_project(self, instrument_id: str, template_id: str,
                    component_id: str | None = None, name: str | None = None,
                    set_id: str | None = None) -> None:
        """単体（`component_id`）またはセット（`set_id`）を新規に起こす。

        セットは descriptor の `sets` 定義を読むだけで、どの部品が組になるかを
        ここには書かない（コアは楽器を知らない）。**必須メンバーだけ**作る ——
        任意の部品は「まだ設計していない」が正しい初期状態で、先に作ると設計して
        いない物の寸法が設計値のように従属部品へ流れる。
        """
        inst = self.registry.get(instrument_id)
        tmpl_label = inst.templates[template_id].get("label", template_id)
        if set_id:
            sdef = inst.set_def(set_id)
            member_ids = [m["component"] for m in sdef["members"]
                          if m.get("required", True)]
            active = inst.set_master(set_id)
            set_name = name or f"{tmpl_label} {sdef.get('label', set_id)}"
        else:
            if component_id is None:
                raise ValueError("component_id か set_id のどちらかが必要です")
            member_ids = [component_id]
            active = component_id
            set_name = name or (
                f"{tmpl_label} {inst.component_classes[component_id].label}")

        self.project = Project(instrument_id=instrument_id, template_id=template_id,
                               name=set_name, members={}, active=active,
                               set_id=set_id)
        for cid in member_ids:
            self.project.add_member(self._new_member(cid))
        self._mount_all()
        self.notices = []

    def open_project(self, path: str) -> None:
        self.project = Project.load(path)
        self.notices = self._mount_all()
        self.push_recent(path)

    def save_project(self, path: str) -> None:
        assert self.project is not None
        self._sync_params()
        self.project.save(path)
        self.push_recent(path)

    def _sync_params(self) -> None:
        """各メンバーの現在値をプロジェクトへ書き戻す（保存・参照束ねの前）。"""
        for cid, ms in self.members.items():
            self.project.member(cid).params = dict(ms.paramset.values)

    # ---------------------------------------------------------- セット（メンバー操作）

    def set_definition(self) -> dict | None:
        """このプロジェクトが属するセット定義。

        `set_id` が入っていればそれ。入っていない（＝単体で作った）場合は、
        **編集中の部品を含むセット定義**を探す —— これが無いと、あとから
        「リガチャーを足す」ができない（管体・ネックのようにセットを持たない
        部品では見つからず、UI は部品タブを出さない）。
        """
        if self.project is None:
            return None
        inst = self.registry.get(self.project.instrument_id)
        if self.project.set_id:
            try:
                return inst.set_def(self.project.set_id)
            except KeyError:
                return None  # 定義が消えた楽器でも開けなくならないように
        for s in inst.sets:
            if any(m["component"] in self.project.members for m in s["members"]):
                return s
        return None

    def set_summary(self) -> dict | None:
        """フロント表示用のセット情報。

        **セットに育てられる単体プロジェクトでも返す**（部品タブに「＋リガチャー」が
        出て、そこから一式にできる）。どのセットにも属さない部品（管体・ネック）では
        None で、UI は部品タブを出さない。
        """
        if self.project is None:
            return None
        sdef = self.set_definition()
        if sdef is None and not self.project.is_set:
            return None
        inst = self.registry.get(self.project.instrument_id)
        sdef = sdef or {}
        defined = {m["component"]: m for m in sdef.get("members", [])}
        # 定義に無い部品（単体プロジェクトから部品を足した場合）も並べる
        order = list(defined) + [c for c in self.project.members if c not in defined]
        members = []
        for cid in order:
            cls = inst.component_classes.get(cid)
            if cls is None:
                continue
            present = self.project.has(cid)
            members.append({
                "component_id": cid,
                "label": cls.label,
                "name": self.project.member(cid).name if present else None,
                "present": present,
                "required": bool(defined.get(cid, {}).get("required", False)),
                "master": defined.get(cid, {}).get("role") == "master",
            })
        return {
            "set_id": self.project.set_id,
            "label": sdef.get("label", "セット"),
            # 実際に組になっているか（単体だが育てられる状態は False）
            "is_set": self.project.is_set,
            "active": self.project.active,
            "members": members,
            # 追加できる部品（この楽器のセット定義に載っていて、まだ居ないもの）
            "addable": [m["component_id"] for m in members if not m["present"]],
        }

    def set_card(self) -> dict | None:
        """セット全体の適合カード（部品どうしでしか出せない量）。

        **コンポーネント実体も渡す。** 「リガチャーがどのリードを想定しているか」は
        部品側の規則（セットのリード → 無ければテンプレート）なので、判定側で
        同じ分岐を書き直すと出所が 2 か所になる。
        """
        if self.project is None or not self.project.is_set:
            return None
        inst = self.registry.get(self.project.instrument_id)
        members = {cid: {"params": dict(ms.paramset.values), "component": ms.component}
                   for cid, ms in self.members.items()}
        size_info: dict = {}
        for ms in self.members.values():
            size_info = getattr(ms.component, "size_info", None) or {}
            if size_info:
                break
        return inst.set_card(size_info, members)

    def assembly_placements(self) -> dict:
        """合わせ表示用の配置。**編集中の部品を基準**にした相対変換で返す。

        3D の本体（編集中の部品）は従来どおり自分のモデル座標で描く —— 寸法線も
        影響領域のハイライトもその座標で作られているので、本体を動かすと全部
        ずれる。動かすのは重ねる側だけにする。

        土台座標での配置を `R_x(θ_i)·F^{f_i}·v + t_i`（`F = R_z(π)` ＝ 裏返し）と
        すると、基準 a から見た配置は `T_a^{-1}∘T_i` で

            回転  = F^{f_a}·R_x(θ_i − θ_a)·F^{f_i}
            平行  = F^{f_a}·R_x(−θ_a)·(t_i − t_a)

        `F·R_x(θ)·F = R_x(−θ)` かつ `F² = I` なので、これは
        `R_x(±(θ_i−θ_a))·F^{f_a xor f_i}` に畳める ——**同じ形のまま閉じている**
        ので、両端に一般の行列を持ち込まずに済む（`Component.assembly_placement`）。

        置き場所を返さない部品（`None`）は**出さない**。間違った位置に置くより
        出さないほうが安全で、出せなかったことは `unplaced` で伝える。
        """
        if self.project is None or not self.project.is_set:
            return {"active": None, "parts": [], "unplaced": []}
        import math

        active = self.project.active
        place: dict[str, dict] = {}
        unplaced: list[str] = []
        for cid, ms in self.members.items():
            pl = ms.component.assembly_placement(dict(ms.paramset.values))
            if pl is None:
                unplaced.append(ms.component.label)
            else:
                place[cid] = pl
        base = place.get(active)
        if base is None:
            # 基準そのものが置けない ＝ 相対変換を作れない
            return {"active": active, "parts": [], "unplaced": unplaced}

        th_a = math.radians(base["rotate_x_deg"])
        flip_a = bool(base.get("flip_z", False))
        ca, sa = math.cos(-th_a), math.sin(-th_a)
        parts = []
        for cid, pl in place.items():
            if cid == active:
                continue
            dx = pl["origin"][0] - base["origin"][0]
            dy = pl["origin"][1] - base["origin"][1]
            dz = pl["origin"][2] - base["origin"][2]
            x = dx
            y = dy * ca - dz * sa
            z = dy * sa + dz * ca
            dth = pl["rotate_x_deg"] - base["rotate_x_deg"]
            if flip_a:
                # F を左から掛ける ＝ 角を反転し、平行移動の x,y を反転する
                dth = -dth
                x, y = -x, -y
            parts.append({
                "component_id": cid,
                "label": self.members[cid].component.label,
                "origin": [x, y, z],
                "rotate_x_deg": dth,
                "flip_z": flip_a != bool(pl.get("flip_z", False)),
                # 形の同一性。ブラウザのキャッシュ鍵（`?v=`）に使う。
                "hash": self._member_key(cid)[:12],
            })
        return {"active": active, "parts": parts, "unplaced": unplaced}

    def set_active(self, component_id: str) -> None:
        """編集対象の部品を切り替える。"""
        assert self.project is not None
        if not self.project.has(component_id):
            raise ValueError(f"この プロジェクト に「{component_id}」はありません")
        self.project.active = component_id
        self._bind_all_refs()
        self.notices = []

    def add_member(self, component_id: str) -> None:
        """セットに部品を足す（テンプレート既定値から）。

        足した部品を参照する側（リガチャー → リード）は**形が変わる**。黙って
        変えないために報告を積む（`notices`）。
        """
        assert self.project is not None
        inst = self.registry.get(self.project.instrument_id)
        cls = inst.component_classes.get(component_id)
        if cls is None or not cls.available():
            raise ValueError("このコンポーネントは未実装です")
        if self.project.has(component_id):
            raise ValueError(f"「{cls.label}」は既にこのセットにあります")
        self.project.add_member(self._new_member(component_id))
        self._mount(self.project.member(component_id))
        self._adopt_set_id(component_id)
        notices = self._affected_by(component_id)
        self._bind_all_refs()
        self.project.active = component_id
        self.notices = notices

    def remove_member(self, component_id: str) -> None:
        """セットから部品を外す。

        **外せるかどうかは従属関係で決まる**（descriptor の `required` ではない）。
        `required` は「新規セットで最初から作る」だけの意味で、これを「外せない」に
        流用すると、リガチャーを外す経路がどこにも無くなる（1 つの値が 2 つの意味を
        決める規則をこのリポジトリでは作らない）。
        """
        assert self.project is not None
        inst = self.registry.get(self.project.instrument_id)
        # **具体的な理由を先に出す。** 土台が外せないのは「他が従属しているから」で、
        # 実際に居る部品の名前を出せるならそちらのほうが次の一手が分かる。
        for cid, ms in self.members.items():
            if cid == component_id:
                continue
            if getattr(ms.component, "REQUIRES_REF", None) == component_id:
                raise ValueError(
                    f"「{ms.component.label}」が「"
                    f"{inst.component_classes[component_id].label}」に従属しています。"
                    f"先にそちらを外してください。")
        sdef = self.set_definition() or {}
        for m in sdef.get("members", []):
            if m["component"] == component_id and m.get("role") == "master":
                raise ValueError(
                    f"「{inst.component_classes[component_id].label}」はこのセットの"
                    f"土台なので外せません。他の部品が寸法をここから取ります。")
        notices = self._affected_by(component_id, removing=True)
        self.project.remove_member(component_id)
        self.members.pop(component_id, None)
        self._bind_all_refs()
        self.notices = notices

    def _adopt_set_id(self, component_id: str) -> None:
        """単体プロジェクトに部品を足したら、そのセット定義の一員として名乗る。

        名乗らないと、出力の既定範囲もセットの適合カードも「単体」のままになる
        （**部品は 2 つ入っているのに**）。既に `set_id` があれば触らない。
        """
        if self.project.set_id:
            return
        inst = self.registry.get(self.project.instrument_id)
        for s in inst.sets:
            ids = {m["component"] for m in s["members"]}
            if component_id in ids and set(self.project.members) <= ids:
                self.project.set_id = s["id"]
                return

    def _affected_by(self, component_id: str, removing: bool = False) -> list[str]:
        """`component_id` を参照している部品への影響報告。

        **必須参照も報告する。** 取り込んだ参照スナップショットを持つ部品
        （例: 単体で作ったリガチャー）にマウスピースを足すと、以後はセットの
        マウスピースが正になり**形が変わる**。黙って変えない。
        """
        inst = self.registry.get(self.project.instrument_id)
        label = inst.component_classes[component_id].label
        out = []
        for cid, ms in self.members.items():
            if cid == component_id:
                continue
            if getattr(ms.component, "REQUIRES_REF", None) == component_id:
                had = bool(self.project.member(cid).refs.get(component_id, {})
                           .get("source"))
                out.append(
                    f"「{ms.component.label}」は{label}に従属します。"
                    f"これ以降はセットの{label}に追従します"
                    + ("（取り込んでいた参照は使われなくなります）" if had else ""))
            elif component_id in getattr(ms.component, "OPTIONAL_REFS", ()):
                out.append(
                    f"「{ms.component.label}」は{label}の寸法を参照します。"
                    + (f"{label}を外したので、同サイズのテンプレート値へ戻ります"
                       if removing else
                       f"これ以降は設計中の{label}の実寸に合わせた形になります"))
        return out

    def import_member(self, path: str) -> str:
        """既存の単体 .wproj をセットのメンバーとして取り込む。

        検証は `set_reference` と同じ（楽器・サイズ違いを弾く）。セットは
        テンプレートを 1 か所しか持たないので、取り込む側だけ確認すればよい。
        取込後は**セットの値が正**（元ファイルとは切り離される）。
        """
        assert self.project is not None
        src = Project.load(path)
        if len(src.members) != 1:
            raise ValueError("セットのプロジェクトはメンバーとして取り込めません。"
                             "取り込みたい部品を単体 .wproj へ書き出してください。")
        if (src.instrument_id != self.project.instrument_id
                or src.template_id != self.project.template_id):
            raise ValueError(
                f"このプロジェクトは「{self._template_label(src)}」用です。"
                f"「{self._template_label(self.project)}」のものを選んでください。")
        cid = src.component_id
        inst = self.registry.get(self.project.instrument_id)
        if cid not in inst.component_classes:
            raise ValueError(f"未知のコンポーネントです: {cid}")
        if self.project.has(cid):
            # **黙って置き換えない。** 上書きすると、いまセットで設計している
            # ぶんが戻せないまま消える（取り消しの仕組みは無い）。
            raise ValueError(
                f"このセットには既に「{inst.component_classes[cid].label}」があります。"
                f"取り込んだもので置き換えるなら、先に今の"
                f"「{inst.component_classes[cid].label}」を外してください"
                f"（残しておきたい場合は単体 .wproj へ書き出してから）。")
        member = src.active_member
        member.refs = {}          # セット内では兄弟メンバーが正（生きた参照）
        self.project.add_member(member)
        self._adopt_set_id(cid)
        notices = self._mount(member)
        notices += self._affected_by(cid)
        self._bind_all_refs()
        self.project.active = cid
        self.notices = notices
        return cid

    def export_member(self, component_id: str, path: str) -> str:
        """セットの部品 1 つを単体 .wproj として書き出す。

        **束ねた参照を凍結スナップショットとして持たせる。** 単体で開いたときに
        参照が空だと、テンプレート既定値へ落ちて別の形になる（書き出した本人が
        見ていた形と違う物が出てくる）。
        """
        assert self.project is not None
        if not self.project.has(component_id):
            raise ValueError(f"この プロジェクト に「{component_id}」はありません")
        self._sync_params()
        src = self.project.member(component_id)
        refs = copy.deepcopy(self.members[component_id].component.refs)
        for entry in refs.values():
            if entry.get("source") == "set":
                entry["source"] = None
                entry["label"] = f"{entry.get('label', '')}（セットから書出）".strip()
        member = Member(
            component_id=component_id, name=src.name, params=dict(src.params),
            refs=refs, notes=src.notes, frozen=copy.deepcopy(src.frozen),
            derived=copy.deepcopy(src.derived), derived_stl=src.derived_stl,
            survey=copy.deepcopy(src.survey))
        out = Project(instrument_id=self.project.instrument_id,
                      template_id=self.project.template_id,
                      name=src.name, members={component_id: member},
                      active=component_id)
        out.save(path)
        self.push_recent(path)
        return path

    # ---------------------------------------------------------- 参照コンポーネント

    def _default_ref(self, ref_id: str) -> dict:
        """参照未設定時の既定値。自テンプレートの当該ブロックを ParamSet で正規化する。

        テンプレートに欠けたキーはコンポーネントの既定値で埋まるため、参照は常に
        「完全なパラメータ一式」になる（ジオメトリ生成も音響合成もそのまま使える）。
        """
        inst = self.registry.get(self.project.instrument_id)
        ref_comp = inst.make_component(ref_id, self.project.template_id)
        ps = ParamSet(ref_comp.param_specs(),
                      ref_comp.template.get(ref_id, {}))
        tmpl_label = inst.templates[self.project.template_id].get(
            "label", self.project.template_id)
        return {
            "source": None,
            "label": f"{tmpl_label} テンプレート既定値",
            "params": dict(ps.values),
        }

    def _template_label(self, proj: Project) -> str:
        """プロジェクトのテンプレート表示名（エラーメッセージ用）。"""
        try:
            inst = self.registry.get(proj.instrument_id)
            return inst.templates[proj.template_id].get("label", proj.template_id)
        except KeyError:
            return proj.template_id

    def _bind_all_refs(self) -> None:
        """全メンバーの参照を束ね直す。

        **セット内は「生きた参照」**。兄弟メンバーの現在値をそのつど束ねるので、
        マウスピースを触ればリガチャー側の形も判定も追従する（取込操作が要らない）。
        セットに居ない参照だけが、従来どおりの凍結スナップショット。

        パラメータを触るたびに呼ぶが、やっているのは dict のコピーだけで CAD は
        走らない。無効化はキャッシュ鍵（`_member_key`）が束ねた参照を含むことで
        自動的に効く。
        """
        if self.project is None:
            return
        self._sync_params()
        for cid in self.members:
            self._bind_refs(cid)

    def _bind_refs(self, component_id: str | None = None) -> None:
        """コンポーネントに参照を結び付ける。

        1. 同じセットに兄弟メンバーが居ればその**現在値**
        2. 居なければメンバーが持つ取込スナップショット
        3. それも無ければ **必須参照のときだけ**テンプレート既定値を作って持たせる
           （任意参照は「まだ設計していない」が正しいので束ねない）
        """
        cid = component_id or self.project.active
        ms = self.members[cid]
        comp = ms.component
        member = self.project.member(cid)
        required = getattr(comp, "REQUIRES_REF", None)
        refs: dict = {}
        for ref_id in ([required] if required else []) + list(
                getattr(comp, "OPTIONAL_REFS", ())):
            if ref_id is None or ref_id == cid:
                continue
            if self.project.has(ref_id):
                sib = self.project.member(ref_id)
                refs[ref_id] = {"source": "set", "label": sib.name,
                                "params": dict(sib.params)}
            elif member.refs.get(ref_id):
                refs[ref_id] = member.refs[ref_id]
            elif ref_id == required:
                member.refs[ref_id] = self._default_ref(ref_id)
                refs[ref_id] = member.refs[ref_id]
        comp.set_refs(refs)

    def set_reference(self, ref_id: str, path: str | None) -> None:
        """参照コンポーネントを .wproj から取込む。path=None で既定値へ戻す。"""
        required = getattr(self.component, "REQUIRES_REF", None)
        if required != ref_id:
            raise ValueError(
                f"{self.component.label} は「{ref_id}」を参照しません")
        if self.project.has(ref_id):
            # セット内に本体が居る。取り込むと「どちらが正か」が 2 つになる。
            raise ValueError(
                f"このセットの{self.members[ref_id].component.label}が参照元です"
                f"（設計中の値に追従します）。別のものを使いたい場合は、"
                f"セットの{self.members[ref_id].component.label}側で取り込んでください。")
        if path is None:
            self.project.refs[ref_id] = self._default_ref(ref_id)
        else:
            src = Project.load(path)
            if src.component_id != ref_id:
                raise ValueError(
                    f"このプロジェクトは「{src.component_id}」です。"
                    f"「{ref_id}」の .wproj を選んでください。")
            # 楽器・サイズが違う参照は通さない。自コンポーネントの size_info（規格寸法）や
            # BOM のサイズ表記は自テンプレート由来のままなので、形だけ別サイズになる。
            if (src.instrument_id != self.project.instrument_id
                    or src.template_id != self.project.template_id):
                raise ValueError(
                    f"このマウスピースは「{self._template_label(src)}」用です。"
                    f"「{self._template_label(self.project)}」のものを選んでください。")
            inst = self.registry.get(src.instrument_id)
            ref_comp = inst.make_component(ref_id, src.template_id)
            ps = ParamSet(ref_comp.param_specs(),
                          ref_comp.template.get(ref_id, {}))
            ps.apply(src.params)
            self.project.refs[ref_id] = {
                "source": path, "label": src.name, "params": dict(ps.values)}
        self._bind_refs()
        self.member_state.clear_caches()

    def reference_summary(self) -> dict | None:
        """フロント表示用の参照情報。参照不要なコンポーネントでは None。"""
        ref_id = getattr(self.component, "REQUIRES_REF", None)
        if not ref_id:
            return None
        entry = self.component.refs.get(ref_id, {})
        return {
            "component_id": ref_id,
            "label": entry.get("label", "-"),
            # セットの兄弟から束ねたぶんは取込元ファイルを持たない。UI は
            # `live` を見て「追従中」と出し、取込ボタンを引っ込める。
            "live": entry.get("source") == "set",
            "source": None if entry.get("source") == "set" else entry.get("source"),
            "dims": [list(d) for d in self.component.ref_dimensions()],
            # 参照の形をそのまま重ねられるか（`Component.REF_SHARES_FRAME`）と、
            # その参照の同一性。フロントはこの 2 つだけでトグルと URL を決める
            # ——「リガチャーだけ」という楽器固有の知識を UI に置かないため。
            "overlay": bool(getattr(self.component, "REF_SHARES_FRAME", False)),
            "hash": self.ref_hash(),
        }

    def apply_params(self, values: dict) -> dict:
        """スライダーの値を適用する。成立しない組は**保存せずに弾く**。

        `ParamSpec.validate` はパラメータを 1 本ずつしか見ないので、各自のレンジ内
        なのに組み合わせると形状が潰れる値の組が作れる（`Component.params_error`）。
        保存してしまうと以後の `simulate` も `build` も同じ理由で落ち、スライダーを
        戻すための画面ごと出せなくなる。試した値を捨てて `ValueError` を上げる。
        """
        assert self.paramset is not None and self.project is not None
        keep = dict(self.paramset.values)
        applied = self.paramset.apply(values)
        # 帯／壁で丸めた項目。**弾いたときは報告しない** —— 値は保存されて
        # いないので、丸めた話をしても画面の値と合わない。
        self.adjustments = list(self.paramset.adjustments)
        bad = self.component.params_error(applied) if self.component else None
        if bad:
            self.paramset.apply(keep)
            self.adjustments = []
            raise ValueError(bad)
        self.project.params = dict(applied)
        # 従属する部品（リガチャー・リード）の参照を追従させる。dict のコピーだけで
        # CAD は走らない。ここを飛ばすと、マウスピースを動かしても従属側の形と
        # 判定が古い値のまま残る。
        self._bind_all_refs()
        self.notices = []      # 利用者が値を触った時点で変換報告は役目を終える
        return applied

    # ---------------------------------------------------------- 形状

    def _member_key(self, component_id: str | None = None) -> str:
        """部品 1 つのキャッシュ鍵。

        **束ねた参照（`component.refs`）を含める。** セットではマウスピースを
        動かすと従属部品の参照が変わるので、鍵もそこで変わる ＝ 無効化の条件を
        別に書かなくてよい。
        """
        cid = component_id or self.project.active
        ms = self.members[cid]
        payload = json.dumps(
            {"i": self.project.instrument_id, "t": self.project.template_id,
             "c": cid, "p": ms.paramset.values,
             "r": ms.component.refs, "so": ms.size_overrides},
            sort_keys=True, default=str)
        return hashlib.md5(payload.encode()).hexdigest()

    def _params_key(self) -> str:
        return self._member_key()

    def _clear_caches(self) -> None:
        for ms in self.members.values():
            ms.clear_caches()

    def build_part(self, component_id: str | None = None):
        ms = self.members[component_id or self.project.active]
        with self.build_lock:
            return ms.component.build(dict(ms.paramset.values))

    def build_part_cad(self, component_id: str | None = None):
        """STEP 出力用のソリッド。面を1枚ずつに畳んだ版（`Component.build_cad`）。

        プレビュー・STL・シミュレーションは `build_part()` のまま。STEP だけ
        分けるのは、プリミティブ表現はブーリアンが数倍遅い代わりに FreeCAD で
        面選択とフィレットができるという、出力先でしか意味の無い差だから。
        """
        ms = self.members[component_id or self.project.active]
        with self.build_lock:
            return ms.component.build_cad(dict(ms.paramset.values))

    def build_spec(self, tolerance: float, cad: bool = False,
                   component_id: str | None = None) -> dict:
        """ビルドに必要な入力だけを取り出した、プロセス間で運べる辞書。

        `component_id` を渡すとそのメンバーぶん（セットの合わせ表示・一括出力）。
        既定は編集中の部品。
        """
        cid = component_id or self.project.active
        ms = self.members[cid]
        return {
            "instrument_id": self.project.instrument_id,
            "template_id": self.project.template_id,
            "component_id": cid,
            "refs": copy.deepcopy(ms.component.refs),
            "params": dict(ms.paramset.values),
            "tolerance": tolerance,
            "cad": cad,
        }

    def _build_stl(self, spec: dict) -> bytes:
        """スペック 1 つを STL バイト列にする。**ビルドの入口はここだけ。**

        ビルド自体は**別プロセス**へ出す。OCCT が GIL を離さないので、親で回すと
        再生成中に断面もパラメータ更新も止まる（`buildworker` の注記を参照）。
        ワーカが使えない環境では親で作る — 遅いだけで結果は同じ
        （子と同じ `build_from_spec` を通るので、手順が 2 つに割れない）。
        """
        from saxsketch.server.buildworker import WORKER, build_from_spec
        if WORKER.alive:
            with contextlib.suppress(RuntimeError):
                return WORKER.build_stl(spec)
        with self.build_lock:
            return build_from_spec(spec)

    def get_stl_bytes(self, tolerance: float = 0.03,
                      component_id: str | None = None) -> bytes:
        """プレビュー/エクスポート用の STL。`component_id` でメンバー指定。"""
        cid = component_id or self.project.active
        ms = self.members[cid]
        key = self._member_key(cid) + f":{tolerance}"
        cached = ms.stl_cache.get(key)
        if cached is not None:
            return cached

        data = self._build_stl(self.build_spec(tolerance, component_id=cid))

        # キャッシュは直近3件のみ保持
        if len(ms.stl_cache) > 3:
            ms.stl_cache.clear()
        ms.stl_cache[key] = data
        return data

    # ---------------------------------------------------------- 参照の重ね表示

    def ref_hash(self) -> str | None:
        """参照スナップショットの同一性。参照を持たないコンポーネントでは None。

        **重ね表示の鍵はこれ 1 つ。** サーバのキャッシュ鍵とフロントの `?v=` に
        同じ値を使う（別々の条件で無効化される状態を作らないため）。
        """
        ref_id = getattr(self.component, "REQUIRES_REF", None)
        entry = self.component.refs.get(ref_id or "") if self.project else None
        if not ref_id or not entry:
            return None
        payload = json.dumps(
            {"i": self.project.instrument_id, "t": self.project.template_id,
             "c": ref_id, "p": entry.get("params", {})},
            sort_keys=True, default=str)
        return hashlib.md5(payload.encode()).hexdigest()[:12]

    def ref_stl_bytes(self, tolerance: float = 0.05) -> bytes:
        """参照コンポーネントだけを作った STL（重ね表示用）。

        **常にプレビュー品質**。重ねは目で位置関係を見るためのもので、
        寸法を測る用途には出さない（測るのは判定カードの数字）。

        マウスピースのビルドはリガチャーの 4.4 倍（5.6〜6.2 秒 対 1.3 秒）かかる。
        参照が変わったときだけ作れば済むので、鍵は `ref_hash()`
        —— スライダーを動かしても変わらない。
        """
        assert self.project is not None and self.component is not None
        ref_id = getattr(self.component, "REQUIRES_REF", None)
        entry = self.component.refs.get(ref_id or "", {})
        if not ref_id or not entry.get("params"):
            raise ValueError("参照コンポーネントがありません")

        ms = self.member_state
        key = f"{self.ref_hash()}:{tolerance}"
        cached = ms.ref_stl_cache.get(key)
        if cached is not None:
            return cached

        # 参照そのものを作るスペック。参照（マウスピース）は自分の参照を持たない。
        # `template_id` は据え置き —— `set_reference` が楽器・サイズ違いを弾いて
        # いるので、参照は必ず同じテンプレート。
        spec = self.build_spec(tolerance)
        spec.update(component_id=ref_id, params=dict(entry["params"]), refs={})
        data = self._build_stl(spec)
        ms.ref_stl_cache.clear()      # 参照は 1 つしか要らない
        ms.ref_stl_cache[key] = data
        return data

    def simulate(self, component_id: str | None = None) -> dict:
        """シミュレーション結果。同じパラメータなら作り直さない。

        `GET /api/project` と `PUT /api/project/params` の両方から呼ばれるので、
        スライダーを1目盛り動かすたびに走る。中身は決定的（乱数なし）なので
        `_params_key()` でそのままキャッシュしてよい。パラメータ・参照・
        size_overrides のどれかが変われば鍵が変わり、明示的な `_clear_caches()`
        でも消える。
        """
        ms = self.members[component_id or self.project.active]
        key = self._member_key(component_id)
        cached = ms.sim_cache.get(key)
        if cached is not None:
            return cached
        res = ms.component.simulate(dict(ms.paramset.values))
        # 警告は**ここで足す**。各コンポーネントの `simulate()` に書かせると、
        # 部品が増えるたびに書き足し忘れる経路ができる（`/api/section` が
        # `dimensions()` をルート側で足しているのと同じ理由）。
        #
        # この便に載せるのが要点 —— 右パネルは `GET /api/project` と
        # `PUT /api/project/params` の 2 経路しか見ていないので、載せれば
        # **スライダ 1 目盛ごとに更新される**。以前は `section()` の戻り値に
        # だけ入っていて、断面タブを開いた人にしか届かなかった。
        res["warnings"] = ms.component.warnings(dict(ms.paramset.values))
        if len(ms.sim_cache) > 4:
            ms.sim_cache.clear()
        ms.sim_cache[key] = res
        return res

    # ---------------------------------------------------------- Tier3（インピーダンス・音合成）

    def impedance(self) -> dict:
        """入力インピーダンス（重い→パラメータハッシュでキャッシュ）。"""
        ms = self.member_state
        key = self._params_key() + ":imp"
        cached = ms.imp_cache.get(key)
        if cached is not None:
            return cached
        res = ms.component.impedance(dict(ms.paramset.values))
        if len(ms.imp_cache) > 4:
            ms.imp_cache.clear()
        ms.imp_cache[key] = res
        return res

    def synthesize_wav(self, embouchure: str) -> tuple[bytes, dict]:
        """単音の物理モデル音（数秒〜かかる→キャッシュ＋ビルドと直列化）。"""
        key = self._params_key() + f":wav:{embouchure}"
        cached = self.member_state.wav_cache.get(key)
        if cached is not None:
            return cached
        with self.build_lock:
            res = self.component.synthesize(dict(self.paramset.values), embouchure)
        self._cache_wav(key, res)
        return res

    def scale_wav(self) -> tuple[bytes, dict]:
        key = self._params_key() + ":scale"
        cached = self.member_state.wav_cache.get(key)
        if cached is not None:
            return cached
        with self.build_lock:
            res = self.component.scale(dict(self.paramset.values))
        self._cache_wav(key, res)
        return res

    def _cache_wav(self, key: str, res: tuple) -> None:
        cache = self.member_state.wav_cache
        if len(cache) > 4:
            cache.clear()
        cache[key] = res

    # ---------------------------------------------------------- 外部編集（凍結・再取込）

    def is_stale(self, component_id: str | None = None) -> bool:
        """凍結後にパラメータ**または参照コンポーネント**が変更されたか。

        リード/リガチャーは参照マウスピースの寸法で形が決まるため、自パラメータが
        同じでも参照を差し替えれば凍結時とは別の形状になる。参照を見ないと、
        古い外部編集モデルがそのまま入稿パッケージに入ってしまう。
        """
        if self.project is None:
            return False
        cid = component_id or self.project.active
        member = self.project.member(cid)
        # 外部取込モデルは凍結パラメータから派生していないので陳腐化しない
        # （自分の設計を後からいじっても、取込んだ市販モデルは無関係のまま）。
        if (member.derived or {}).get("kind") == "external":
            return False
        if member.frozen is None:
            return False
        cur = self.members[cid].paramset.values
        for k, v in member.frozen["params"].items():
            if cur.get(k) != v:
                return True
        return self._refs_changed(cid)

    def _refs_changed(self, component_id: str | None = None) -> bool:
        """凍結時の参照パラメータと現在の差分。

        比較するのは `params` だけ（`source`/`label` は形状に影響しない）。
        `refs` を持たない Phase 3 以前の凍結スナップショットは比較をスキップする。
        """
        cid = component_id or self.project.active
        frozen_refs = self.project.member(cid).frozen.get("refs")
        if frozen_refs is None:
            return False
        for ref_id, entry in frozen_refs.items():
            cur = self.members[cid].component.refs.get(ref_id, {})
            if entry.get("params") != cur.get("params"):
                return True
        return False

    def manual_edit_summary(self) -> dict:
        """フロント表示用の外部編集状態。"""
        p = self.project
        if p is None:
            return {"frozen": None, "derived": None, "stale": False}
        frozen = None
        if p.frozen is not None:
            frozen = {"frozen_at": p.frozen["frozen_at"],
                      "export_dir": p.frozen.get("export_dir"),
                      "solid_volume_cc": p.frozen.get("solid_volume_cc")}
        derived = None
        if p.derived is not None:
            derived = {"imported_at": p.derived["imported_at"],
                       "source_file": p.derived["source_file"],
                       "quality": p.derived["quality"],
                       "kind": p.derived.get("kind", "edited")}
        return {"frozen": frozen, "derived": derived, "stale": self.is_stale()}

    def freeze(self, export_dir: str, solid_volume_cc: float | None) -> dict:
        """現パラメータで凍結スナップショットを記録。既存の派生モデルは破棄。"""
        from datetime import datetime, timezone
        assert self.project is not None
        self.project.frozen = {
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "params": dict(self.paramset.values),
            # 参照も凍結する。リード/リガチャーは参照マウスピースで形が決まるため。
            # **束ねた参照**（`component.refs`）で見る —— セットでは兄弟メンバーの
            # 現在値が正で、メンバー自身の `refs` は空のことがある。
            "refs": copy.deepcopy(self.component.refs),
            "solid_volume_cc": solid_volume_cc,
            "export_dir": export_dir,
        }
        self.project.derived = None
        self.project.derived_stl = None
        self._pending_derived = None
        return self.manual_edit_summary()

    def unfreeze(self) -> dict:
        assert self.project is not None
        self.project.frozen = None
        self.project.derived = None
        self.project.derived_stl = None
        self._pending_derived = None
        return self.manual_edit_summary()

    _pending_derived: dict | None = None  # {stl_bytes, source_file, quality, analysis}

    @contextlib.contextmanager
    def _frozen_refs(self):
        """凍結時の参照でコンポーネントを一時的に動かす。

        比較の基準形状は凍結時のものでなければならない。現在の参照で作ると、
        参照を差し替えた後の解析が「編集による差分」と「参照差替えによる差分」を
        混ぜてしまう。
        """
        frozen_refs = (self.project.frozen or {}).get("refs")
        if frozen_refs is None:
            yield
            return
        current = self.component.refs
        self.component.set_refs(copy.deepcopy(frozen_refs))
        try:
            yield
        finally:
            self.component.set_refs(current)

    def analyze_derived(self, path: str) -> dict:
        """編集済みモデルを読み込み解析（まだ登録しない）。"""
        from saxsketch.analysis import meshdiff
        assert self.project is not None and self.project.frozen is not None
        frozen_params = dict(self.project.frozen["params"])

        edited = meshdiff.load_mesh(path)
        quality = meshdiff.mesh_quality(edited)

        with self._frozen_refs():
            with self.build_lock:
                ref_part = self.component.build(frozen_params)
            ref_mesh = meshdiff.part_to_mesh(ref_part, tolerance=0.03)
            ref_vol_cc = float(ref_mesh.volume / 1000.0)
            analysis = self.component.analyze_import(frozen_params, ref_mesh, edited)

        vol_row = None
        if quality["volume_cc"] is not None:
            delta_pct = (quality["volume_cc"] - ref_vol_cc) / ref_vol_cc * 100.0
            vol_row = {"frozen_cc": round(ref_vol_cc, 2),
                       "edited_cc": round(quality["volume_cc"], 2),
                       "delta_pct": round(delta_pct, 2)}
            if abs(delta_pct) > 5.0:
                analysis["warnings"].append(
                    f"⚠ 体積が {delta_pct:+.1f}% 変化しています。削りすぎ／穴あきの疑い。")
        else:
            analysis["warnings"].append(
                "⚠ メッシュが水密ではありません。修復しないと印刷できません。")

        # STL バイト列を保持（STEP等は解析メッシュから STL 化）
        import trimesh  # noqa: F401
        stl_bytes = edited.export(file_type="stl")
        if isinstance(stl_bytes, str):
            stl_bytes = stl_bytes.encode()
        self._pending_derived = {
            "stl_bytes": stl_bytes,
            "source_file": path,
            "quality": quality,
            "analysis": {**analysis, "volume": vol_row},
        }
        return {"quality": quality, "volume": vol_row, **analysis}

    def load_external(self, path: str) -> dict:
        """外部（本アプリ非由来）の完成モデルを読み込み、整列・採寸して
        表示・入稿用の派生モデル候補にする。

        差分や逆算はしない——市販完成品は座標系も内部形状も本アプリの設計と別物で、
        領域別偏差もパラメータ逆算も意味を持たない（かつ非重なりメッシュ同士の差分は
        極端に重い）。ここでは座標非依存の整列で表示・エクスポートできる姿勢に載せ、
        確実に測れる外形寸法だけを採寸する。凍結は不要。
        """
        from saxsketch.analysis import align, meshdiff
        assert self.project is not None and self.component is not None

        mesh = meshdiff.load_mesh(path)
        quality = meshdiff.mesh_quality(mesh)
        measured = self.component.survey_measure_mesh(mesh)
        # 表示・外部編集用に正準姿勢（主軸=+Z, シャンク=+Z側）へ整列した STL を保持
        aligned, _, info = align.axis_align(mesh)
        stl_bytes = aligned.export(file_type="stl")
        if isinstance(stl_bytes, str):
            stl_bytes = stl_bytes.encode()

        self._pending_derived = {
            "stl_bytes": stl_bytes,
            "source_file": path,
            "quality": quality,
            "kind": "external",
            "measured": measured.get("measured", {}),
            "analysis": {
                "regions": [], "params": [],
                "warnings": measured.get("notes", []),
                "volume": None,
                "align": info,
            },
        }
        return {
            "kind": "external",
            "quality": quality,
            "measured": measured.get("measured", {}),
            "measured_size": measured.get("measured_size", {}),
            "confidence": measured.get("confidence", {}),
            "notes": measured.get("notes", []),
            "align": info,
        }

    def commit_derived(self) -> dict:
        """解析済み／取込済みモデルをプロジェクトに登録。"""
        from datetime import datetime, timezone
        assert self.project is not None
        pd = self._pending_derived
        if pd is None:
            raise ValueError("先に編集済みモデルを取込・解析してください")
        self.project.derived = {
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "source_file": pd["source_file"],
            "quality": pd["quality"],
            "analysis": pd["analysis"],
            "kind": pd.get("kind", "edited"),
            "measured": pd.get("measured", {}),
        }
        self.project.derived_stl = pd["stl_bytes"]
        self._pending_derived = None
        return self.manual_edit_summary()

    def discard_derived(self) -> dict:
        assert self.project is not None
        self.project.derived = None
        self.project.derived_stl = None
        self._pending_derived = None
        return self.manual_edit_summary()

    # ---------------------------------------------------------- 採寸ワークフロー（Phase 4-A）

    def _apply_size_overrides(self) -> None:
        self.member_state.apply_size_overrides()

    def survey_state(self) -> dict:
        """フロント採寸パネル用の状態。現在の設計値/基準値でフィールドを埋める。"""
        empty = {"targets": {"params": [], "size": []}, "measured": {},
                 "measured_size": {}, "has_checkpoint": False, "card": None,
                 "surveyed_at": None, "note": ""}
        if self.project is None or self.component is None:
            return empty
        targets = self.component.survey_targets()
        for f in targets["params"]:
            f["current"] = self.paramset.values.get(f["key"])
        for f in targets["size"]:
            f["current"] = self.component.size_info.get(f["key"])
        s = self.project.survey or {}
        return {
            "targets": targets,
            "measured": s.get("measured", {}),
            "measured_size": s.get("measured_size", {}),
            "has_checkpoint": bool(s.get("checkpoint")),
            "card": s.get("card"),
            "surveyed_at": s.get("surveyed_at"),
            "note": s.get("note", ""),
        }

    @staticmethod
    def _clean_measures(raw: dict | None, allowed: set) -> dict:
        """許可キーのみ・数値化できる値だけを拾う（空欄/未知キーは捨てる）。"""
        out: dict = {}
        for k, v in (raw or {}).items():
            if k not in allowed or v is None or v == "":
                continue
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                continue
        return out

    def survey_commit(self, measured: dict | None, measured_size: dict | None,
                      note: str = "") -> dict:
        """採寸値を反映し、復元点（チェックポイント）を記録する。"""
        from datetime import datetime, timezone
        assert self.project is not None and self.component is not None
        targets = self.component.survey_targets()
        param_keys = {f["key"] for f in targets["params"]}
        size_keys = {f["key"] for f in targets["size"]}

        # 採寸前の値（照合カードの比較基準）
        before_params = dict(self.paramset.values)
        before_size = dict(self.component.size_info)

        # 系統A: 設計パラ（ParamSet でクランプ・型変換される）
        m_params = self._clean_measures(measured, param_keys)
        if m_params:
            self.apply_params(m_params)
        applied_params = {k: self.paramset.values[k] for k in m_params}

        # 系統B: 音響基準定数（size_info への局所上書き）
        m_size = self._clean_measures(measured_size, size_keys)
        self.size_overrides = {**self.size_overrides, **m_size}
        self._apply_size_overrides()

        card = self.component.survey_card(
            before_params, before_size, applied_params, m_size)

        prev = self.project.survey or {}
        self.project.survey = {
            "surveyed_at": datetime.now(timezone.utc).isoformat(),
            "note": note or "",
            "measured": {**prev.get("measured", {}), **applied_params},
            "measured_size": {**prev.get("measured_size", {}), **m_size},
            "checkpoint": {
                "params": dict(self.paramset.values),
                "refs": copy.deepcopy(self.component.refs),
                "size_overrides": dict(self.size_overrides),
            },
            "card": card,
        }
        self.project.params = dict(self.paramset.values)
        self._clear_caches()
        return self.survey_state()

    def survey_revert(self) -> dict:
        """採寸チェックポイントへ復元する（設計をいじって破綻した時の回復）。"""
        assert self.project is not None
        cp = (self.project.survey or {}).get("checkpoint")
        if not cp:
            raise ValueError("復元点がありません。先に採寸を確定してください。")
        self.apply_params(dict(cp["params"]))
        if cp.get("refs") is not None:
            # セット内の参照は兄弟メンバーが正なので、復元しても束ね直しで上書き
            # される（復元点が意味を持つのは取込スナップショットの場合だけ）。
            self.project.refs = copy.deepcopy(cp["refs"])
            self._bind_all_refs()
        self.size_overrides = dict(cp.get("size_overrides", {}))
        self._apply_size_overrides()
        self._clear_caches()
        return self.survey_state()

    def survey_clear(self) -> dict:
        """採寸ブロックと音響基準の上書きを破棄する（params は現状維持）。"""
        assert self.project is not None
        self.project.survey = None
        self.size_overrides = {}
        self._apply_size_overrides()
        self._clear_caches()
        return self.survey_state()


STATE = AppState()
