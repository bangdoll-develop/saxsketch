"""楽器・コンポーネントのプラグインレジストリ。

楽器の追加 = saxsketch/instruments/<id>/ ディレクトリを追加するだけ。
必要物:
  - descriptor.json  … 楽器の物理定数・メタ情報
  - templates/*.json … サイズテンプレート（パラメータ初期値）
  - components/      … Component 派生クラス（COMPONENTS で公開）
コアは楽器の中身を知らない。
"""
from __future__ import annotations

import importlib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .schema import ParamSpec

INSTRUMENTS_DIR = Path(__file__).resolve().parent.parent / "instruments"


class Component(ABC):
    """設計対象コンポーネント（マウスピース、リード等）の基底クラス。"""

    id: str = ""
    label: str = ""  # 日本語名
    #: 従属先コンポーネントのID。設定するとプロジェクトが参照スナップショットを持つ
    #: （例: リード/リガチャー → "mouthpiece"）。None なら参照不要。
    REQUIRES_REF: str | None = None
    #: **あれば使う**参照のID（例: リガチャー → "reed"）。`REQUIRES_REF` と違い、
    #: 無くても設計は成立する（部品側がテンプレート等の既定へ落ちる）。セットに
    #: その部品が居るときだけ束ねられる。
    #:
    #: 必須と任意を分けてあるのは、**無いときの意味が違う**から。必須の参照が
    #: 無ければ形が決まらないので既定値を作って埋めるしかないが、任意の参照は
    #: 「まだ設計していない」が正しい状態で、埋めると設計していない物の寸法を
    #: 設計値のように見せることになる。
    OPTIONAL_REFS: tuple[str, ...] = ()
    #: 参照コンポーネントと**同じ座標系**で作られているか。True のとき UI は
    #: 参照の形をそのまま重ねられる（変換が要らない）。
    #:
    #: 既定を False にしてあるのは、**間違って重なるより重ならない方が安全**だから。
    #: 座標系が一致するかはコンポーネント自身にしか分からない（コアは楽器を知らない）。
    REF_SHARES_FRAME: bool = False

    def __init__(self, descriptor: dict, template: dict):
        self.descriptor = descriptor
        self.template = template
        self.refs: dict = {}

    # ------------------------------------------------------------ 参照

    def set_refs(self, refs: dict) -> None:
        self.refs = refs or {}

    def ref_params(self) -> dict:
        """参照コンポーネントのパラメータ。未設定なら空 dict。"""
        entry = self.refs.get(self.REQUIRES_REF or "", {})
        return dict(entry.get("params", {}))

    def ref_dimensions(self) -> list[tuple[str, str]]:
        """参照の要約表示用の主要寸法（UI カード）。"""
        return []

    @abstractmethod
    def param_specs(self) -> list[ParamSpec]:
        ...

    @abstractmethod
    def build(self, params: dict) -> Any:
        """build123d の Part（水密ソリッド）を返す。"""

    def build_cad(self, params: dict) -> Any:
        """STEP 出力用のソリッド。既定は `build()` と同じもの。

        `build()` は面が微小パッチの集まりで、FreeCAD で面を選択したり外周エッジへ
        フィレットを掛けたりできない。それが要るコンポーネントだけ、**同じ形を
        1面ずつのプリミティブで張り直した版**をここで返す（形は変えない）。
        プリミティブ表現はブーリアンが数倍遅いので、対話中に走る `build()` とは
        分けてある。
        """
        return self.build(params)

    def params_error(self, params: dict) -> str | None:
        """パラメータの組が形状として成立しないときに理由を返す。既定は常に `None`。

        `ParamSpec` は**パラメータを 1 本ずつしか見ない**（`validate` は範囲外を
        黙ってクランプする）ので、各自のレンジ内なのに組み合わせると成立しない
        値の組が作れる。それを見つけられるのは部品側だけなので、ここで問う。

        コアは楽器を知らないままでよい: 返るのは表示用の 1 文だけで、コアはそれを
        そのままユーザーへ渡す。**成立しない値は保存しない**（保存すると次の
        `simulate` も `build` も同じ理由で落ち、セッションが戻せなくなる）。
        """
        return None

    def migrate_params(self, values: dict) -> tuple[dict, list[str]]:
        """保存済みプロジェクトのパラメータを現行のキーへ移す。既定は恒等。

        `ParamSet.apply` は**未知のキーを黙って捨てる**ので、パラメータを作り
        替えると古い .wproj が黙って既定値へ落ちる（利用者の設計が理由も無く
        変わる）。ここで変換し、**何をどう移したかを 1 行返す**。

        コアは楽器を知らないままでよい: 返るのは表示用の文字列だけで、コアは
        それをそのまま利用者へ渡す（`params_error` と同じ形のフック）。
        """
        return values, []

    @abstractmethod
    def simulate(self, params: dict) -> dict:
        """設計時シミュレーション結果（Tier1/2、感度、倍音列）を返す。"""

    @abstractmethod
    def bom(self, params: dict) -> list[dict]:
        """部品表の行リスト。"""

    def spec_extras(self, params: dict) -> dict:
        """仕様書用の追加情報。

        Returns:
            {"dimensions": [(名前, 値), …],
             "sections":   [{"title": str, "svg": str}, …]}

        断面図は各コンポーネントが `saxsketch.export.svg.polyline_svg()` を使って
        自分で組み立てる。共通側は図の中身を知らない（コアは楽器を知らない）。
        """
        return {}

    def regions(self, params: dict) -> dict:
        """各パラメータの影響領域 {key: {z0, z1, side, label}}（3Dハイライト用）。"""
        return {}

    def dimensions(self, params: dict) -> list[dict]:
        """パラメータの寸法を図示するための線分。既定は無し。

        要素は `saxsketch.core.dimension.dim()` が組み立てる（**値は線の両端から
        測る**ので、ラベルと線が食い違わない）。座標はコンポーネント自身の
        モデル座標で、3D も断面もそのまま描ける。

        **CAD ビルドを伴わないこと**が要件。`section()` と同じくドラッグ中に
        叩かれるので、形状法則の数値計算だけで組み立てる。

        空リストなら UI は寸法トグルを出さない —— 「どの部品が寸法を持つか」を
        UI に書かない（`GET /api/section` の 404 で断面タブを出し分けるのと同じ）。
        """
        return []

    def warnings(self, params: dict) -> list[str]:
        """いまのパラメータについての注意。**CAD ビルドを伴わないこと**。

        `params_error` と違い、値は**適用されている**（弾いてはいない）。
        「形が法則どおり出ていない」「形は指定どおりだが吹けない」を伝える経路。

        空リストなら UI は警告カードを出さない。**「どの部品が警告を持つか」を
        UI に書かない**（`GET /api/section` の 404 で断面タブを出し分けるのと
        同じ約束）。

        **便に載せるのはコア側**（`AppState.simulate` が `simulate()` の結果へ
        足す）。各コンポーネントの `simulate()` に書き足させると、部品が増えた
        ときに書き忘れる経路ができる —— `/api/section` が `dimensions()` を
        ルート側で足しているのと同じ理由。
        """
        return []

    def assembly_placement(self, params: dict) -> dict | None:
        """組み合わせたときの置き場所。**土台部品のモデル座標**で返す。

        Returns:
            `{"origin": [x, y, z], "rotate_x_deg": float, "flip_z": bool}` …
            部品のモデル座標を **`flip_z` なら先に Z 軸まわり 180° 裏返し**、
            続いて X 軸まわりに `rotate_x_deg` 回してから `origin` へ運ぶと、
            組んだ姿になる。`flip_z` は省略可（既定 `False`）。
            `None` … 置き場所が分からない（合わせ表示に出さない）。

        **回転は「X 軸まわり ＋ 裏返すか否か」だけ**。一般の 4×4 を通さないのは、
        この形 `R_x(θ)·F^f`（`F = R_z(π)`）が**合成で閉じている**から ——
        `F·R_x(θ)·F = R_x(−θ)` なので、基準を別の部品へ移した相対変換も
        同じ形のまま書ける（`AppState.assembly_placements`）。両端（サーバと
        ブラウザ）に行列の合成を持ち込まずに済む。足りなくなったら足す。

        裏返しが要るのは、部品のモデルが**どちら向きに肉を持つか**が部品ごとに
        違うため。リードは底面 y=0 から +y へ肉が付くが、載せる相手（テーブル面）の
        外向き法線は −y なので、そのまま置くとマウスピースの中へ潜る。

        既定が `None` なのは `REF_SHARES_FRAME` と同じ理由 ——
        **間違った位置に置くより出さないほうが安全**。座標系を知っているのは
        部品自身だけで、コアは楽器を知らない。
        """
        return None

    def section(self, params: dict) -> dict | None:
        """中央面の断面と、そこで直接ドラッグできるハンドル。

        Returns:
            {"z_range": [z0, z1],
             "curves":  {name: [[z, y], …]},
             "handles": [{key, label, axis, z, y, value, min, max, span,
                          unit, step, active}, …],
             "title": str}
            対応しないコンポーネントは None（UI は断面タブを出さない）。

        `warnings` と `dimensions` は**ルート側が足す**（`GET /api/section`）ので
        ここでは返さない。どちらも `warnings()` / `dimensions()` の 1 か所が
        出所で、断面を持つ部品が増えたときに書き写し忘れる経路を作らない。

        **CAD ビルドを伴わないこと**が要件。ドラッグ中に毎回叩かれるので、
        形状法則の数値計算だけで組み立てる。
        """
        return None

    # --- 採寸ワークフロー（Phase 4-A）。対応コンポーネントだけがオーバーライドする ---

    def survey_targets(self) -> dict:
        """採寸で入力できるフィールド。

        Returns:
            {"params": [{"key","label","unit","min","max","step"}, …],  # 設計パラ（paramset）
             "size":   [{"key","label","unit"}, …]}                     # 音響基準定数（size_info）
        既定は対象なし。
        """
        return {"params": [], "size": []}

    def survey_card(self, before_params: dict, before_size: dict,
                    measured_params: dict, measured_size: dict) -> dict | None:
        """採寸 vs 設計 の照合カード（SimCard 形）。対象なしなら None。"""
        return None

    def survey_measure_mesh(self, mesh) -> dict:
        """外部メッシュ（3mf/STL 等）から採寸ターゲットを実測してプレフィル値を返す。

        Returns {"measured": {param_key: value}, "measured_size": {size_key: value},
                 "confidence": {key: "high|med|low"}, "notes": [str]}。
        既定は測定なし（確実に測れる外形寸法だけを対応コンポーネントが実装する）。
        """
        return {"measured": {}, "measured_size": {}, "confidence": {}, "notes": []}

    def analyze_import(self, frozen_params: dict, ref_mesh, edited_mesh) -> dict:
        """外部編集モデルの解析。領域別偏差＋（可能なら）パラメータ逆算。

        Returns {"regions": [...], "params": [...], "warnings": [...]}
        既定実装は領域別偏差のみ。逆算は各コンポーネントでオーバーライド。
        """
        from saxsketch.analysis import meshdiff
        return {
            "regions": meshdiff.region_deviations(
                ref_mesh, edited_mesh, self.regions(frozen_params)),
            "params": [],
            "warnings": [],
        }

    # --- Tier3（音響）。対応するコンポーネントだけがオーバーライドする ---

    def impedance(self, params: dict) -> dict:
        """入力インピーダンス曲線。"""
        raise NotImplementedError(f"{self.label}にはインピーダンス計算がありません")

    def synthesize(self, params: dict, embouchure: str) -> tuple[bytes, dict]:
        """物理モデルによる単音の WAV。"""
        raise NotImplementedError(f"{self.label}には音合成がありません")

    def scale(self, params: dict) -> tuple[bytes, dict]:
        """物理モデルによる簡易スケールの WAV。"""
        raise NotImplementedError(f"{self.label}には音合成がありません")

    def cavity_volume(self, params: dict) -> dict:
        """内部空洞体積の高速近似 {"total_cc","effective_cc"}（ゴールシーク用）。"""
        raise NotImplementedError

    def goal_seek_size_info(self) -> dict:
        """Tier1 目標値などのサイズ情報（ゴールシーク用）。"""
        raise NotImplementedError

    @classmethod
    def available(cls) -> bool:
        """実装済みで選択可能か（未実装の将来コンポーネントは False）。"""
        return getattr(cls, "AVAILABLE", True)


class Instrument:
    def __init__(self, path: Path):
        self.path = path
        self.id = path.name
        self.descriptor = json.loads((path / "descriptor.json").read_text(encoding="utf-8"))
        self.templates: dict[str, dict] = {}
        for tf in sorted((path / "templates").glob("*.json")):
            self.templates[tf.stem] = json.loads(tf.read_text(encoding="utf-8"))
        mod = importlib.import_module(f"saxsketch.instruments.{self.id}.components")
        self.component_classes: dict[str, type[Component]] = mod.COMPONENTS
        #: セットで組める部品の並び（descriptor の `sets`）。**コアは中身を知らない**
        #: —— どの部品が組になるかは楽器の事情なので、データとして読むだけ。
        self.sets: list[dict] = list(self.descriptor.get("sets", []))
        #: セット全体の適合カードを出す関数（あれば）。`components/__init__.py` が
        #: `SET_CARD` で公開する。部品どうしでしか出せない量はここでしか出せない。
        self.set_card_fn = getattr(mod, "SET_CARD", None)

    def make_component(self, component_id: str, template_id: str) -> Component:
        cls = self.component_classes[component_id]
        template = self.templates[template_id]
        return cls(self.descriptor, template)

    # ------------------------------------------------------------ セット

    def set_def(self, set_id: str) -> dict:
        for s in self.sets:
            if s["id"] == set_id:
                return s
        raise KeyError(f"セット定義がありません: {set_id}")

    def set_master(self, set_id: str) -> str:
        """セットの土台になる部品ID（`role == "master"`。既定は先頭）。"""
        members = self.set_def(set_id)["members"]
        for m in members:
            if m.get("role") == "master":
                return m["component"]
        return members[0]["component"]

    def set_card(self, size_info: dict, members: dict[str, dict]) -> dict | None:
        """セット全体の適合カード。楽器が実装していなければ None。"""
        if self.set_card_fn is None:
            return None
        return self.set_card_fn(size_info, members)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "label": self.descriptor.get("label", self.id),
            "templates": [
                {"id": tid, "label": t.get("label", tid)}
                for tid, t in self.templates.items()
            ],
            "components": [
                {"id": cid, "label": cls.label, "available": cls.available()}
                for cid, cls in self.component_classes.items()
            ],
            "sets": [
                {"id": s["id"], "label": s.get("label", s["id"]),
                 "members": [
                     {"component": m["component"],
                      "label": self.component_classes[m["component"]].label,
                      "required": bool(m.get("required", True)),
                      "master": m.get("role") == "master"}
                     for m in s["members"]
                     if m["component"] in self.component_classes],
                 }
                for s in self.sets
            ],
        }


class Registry:
    def __init__(self):
        self.instruments: dict[str, Instrument] = {}
        for d in sorted(INSTRUMENTS_DIR.iterdir()):
            if d.is_dir() and (d / "descriptor.json").exists():
                self.instruments[d.name] = Instrument(d)

    def get(self, instrument_id: str) -> Instrument:
        return self.instruments[instrument_id]

    def summaries(self) -> list[dict]:
        return [i.summary() for i in self.instruments.values()]


_registry: Registry | None = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry
