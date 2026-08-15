"""サクソフォンのコンポーネント登録。"""
from .body import BodyComponent
from .ligature import LigatureComponent
from .mouthpiece import MouthpieceComponent
from .neck import NeckComponent
from .reed import ReedComponent

COMPONENTS = {
    "mouthpiece": MouthpieceComponent,
    "reed": ReedComponent,
    "ligature": LigatureComponent,
    "neck": NeckComponent,
    "body": BodyComponent,
}
