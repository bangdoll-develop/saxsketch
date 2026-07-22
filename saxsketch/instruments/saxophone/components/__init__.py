"""サクソフォンのコンポーネント登録。"""
from saxsketch.core.registry import Component

from .ligature import LigatureComponent
from .mouthpiece import MouthpieceComponent
from .neck import NeckComponent
from .reed import ReedComponent


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


class BodyComponent(_Planned):
    id = "body"
    label = "本体・管体（Phase 4-B.2）"


COMPONENTS = {
    "mouthpiece": MouthpieceComponent,
    "reed": ReedComponent,
    "ligature": LigatureComponent,
    "neck": NeckComponent,
    "body": BodyComponent,
}
