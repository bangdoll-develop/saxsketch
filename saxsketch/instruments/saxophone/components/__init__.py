"""サクソフォンのコンポーネント登録。"""
from saxsketch.core.registry import Component

from .mouthpiece import MouthpieceComponent


class _Planned(Component):
    """後フェーズ実装予定のプレースホルダ（UI にグレー表示するため登録だけする）。"""
    AVAILABLE = False

    def param_specs(self):
        raise NotImplementedError(f"{self.label} は今後のフェーズで実装予定です")

    def build(self, params):
        raise NotImplementedError

    def simulate(self, params):
        raise NotImplementedError

    def bom(self, params):
        raise NotImplementedError


class ReedComponent(_Planned):
    id = "reed"
    label = "リード（Phase 3）"


class LigatureComponent(_Planned):
    id = "ligature"
    label = "リガチャー（Phase 3）"


class NeckComponent(_Planned):
    id = "neck"
    label = "ネック（Phase 4）"


class BodyComponent(_Planned):
    id = "body"
    label = "本体・管体（Phase 4）"


COMPONENTS = {
    "mouthpiece": MouthpieceComponent,
    "reed": ReedComponent,
    "ligature": LigatureComponent,
    "neck": NeckComponent,
    "body": BodyComponent,
}
