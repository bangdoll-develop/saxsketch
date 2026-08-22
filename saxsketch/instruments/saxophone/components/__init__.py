"""サクソフォンのコンポーネント登録。"""
from .body import BodyComponent
from .ligature import LigatureComponent
from .mouthpiece import MouthpieceComponent
from .neck import NeckComponent
from .reed import ReedComponent
from .set_check import set_card as SET_CARD

COMPONENTS = {
    "mouthpiece": MouthpieceComponent,
    "reed": ReedComponent,
    "ligature": LigatureComponent,
    "neck": NeckComponent,
    "body": BodyComponent,
}

#: セット全体の適合カード（`Instrument.set_card` が拾う）。部品どうしでしか
#: 出せない量だけを扱う —— 各部品の規格照合はそれぞれのカードにある。
__all__ = ["COMPONENTS", "SET_CARD"]
