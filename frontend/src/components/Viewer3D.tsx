import { useCallback, useEffect, useRef } from "react";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Dimension, Region } from "../api";

interface Props {
  /** パラメータ変更のたびに増えるトークン。変わったらSTLを再取得 */
  modelVersion: number;
  /** ハイライトする影響領域（パラメータhover中のみ非null） */
  highlight?: Region | null;
  /** hover 中のパラメータキー。一致する寸法だけ色を変える */
  hoverKey?: string | null;
  /** 別モデルを表示する場合のURL（外部編集済みモデル等）。null=パラメトリック形状 */
  srcOverride?: string | null;
  /** 半透明で重ねる参照モデルのURL（リガチャー → マウスピース）。null=重ねない */
  overlaySrc?: string | null;
  /** 図示する寸法。null / 空なら描かない */
  dimensions?: Dimension[] | null;
  onBusy?: (busy: boolean) => void;
  /** 参照モデルの取得中。本体の `onBusy` とは分ける（断面編集を待たせないため） */
  onOverlayBusy?: (busy: boolean) => void;
}

interface Ctx {
  scene: THREE.Scene; camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer; controls: OrbitControls;
  mesh: THREE.Mesh | null;
  overlay: THREE.Mesh | null;
  /** いま要求されている重ねのURL。取得が返ってきた時の取り違えを防ぐ */
  overlaySrc: string | null;
  /** 本体を読み込み中か。参照の取得はこれが終わってから */
  mainLoading: boolean;
  /** 本体の読み込み中に要求された重ね。終わったら取りに行く */
  pendingOverlay: string | null;
  /** 寸法線とラベルをまとめた入れ物 */
  dims: THREE.Group | null;
  dimLines: THREE.LineSegments | null;
  /** 寸法ごとのラベル（色替えでキャンバスを描き直さないために持っておく） */
  dimItems: { key: string; sprite: THREE.Sprite }[];
}

const BASE = new THREE.Color(0x7fa8d8);      // 通常部
const HILITE = new THREE.Color(0xffa03c);    // 影響部（オレンジ）
const DIMMED = new THREE.Color(0x4a5c72);    // ハイライト中の非対象部（暗め）

const DIM_COLOR = new THREE.Color(0x9fb4cc);   // 寸法線
const DIM_HILITE = HILITE;                     // hover 中のパラメータの寸法

/** モデル座標(z=0がティップ)で領域判定し頂点カラーを塗る */
function paintHighlight(mesh: THREE.Mesh, region: Region | null) {
  const geo = mesh.geometry as THREE.BufferGeometry;
  const pos = geo.getAttribute("position");
  let col = geo.getAttribute("color") as THREE.BufferAttribute | undefined;
  if (!col) {
    col = new THREE.BufferAttribute(new Float32Array(pos.count * 3), 3);
    geo.setAttribute("color", col);
  }
  // geometry.center() で原点移動済み → 元のモデル座標 = ローカル + centerOffset
  const off = mesh.userData.centerOffset as THREE.Vector3;
  for (let i = 0; i < pos.count; i++) {
    let c = BASE;
    if (region) {
      const y = pos.getY(i) + off.y;
      const z = pos.getZ(i) + off.z;
      const inZ = z >= region.z0 - 0.05 && z <= region.z1 + 0.05;
      const sideOk =
        region.side === "all" ||
        (region.side === "top" ? y > 0 : y < 0);
      c = inZ && sideOk ? HILITE : DIMMED;
    }
    col.setXYZ(i, c.r, c.g, c.b);
  }
  col.needsUpdate = true;
}

/** モデル座標で作ったものを本体と同じ world 変換に載せる。
 *
 *  本体は `geo.center()` 済みなので 頂点_world = R·(v − C_main)。重ねや寸法は
 *  center しないので、position を R·(−C_main) にすれば同じ式になる。**自分で
 *  center すると 2 つの重心が原点へ来て重ならない**（重心は z で 14.9〜16.5mm 違う）。
 */
function placeInModelFrame(ctx: Ctx, obj: THREE.Object3D) {
  const c = (ctx.mesh?.userData.centerOffset as THREE.Vector3 | undefined)
    ?? new THREE.Vector3();
  obj.position.copy(c).multiplyScalar(-1).applyEuler(obj.rotation);
}

function removeOverlay(ctx: Ctx) {
  if (!ctx.overlay) return;
  ctx.scene.remove(ctx.overlay);
  ctx.overlay.geometry.dispose();
  (ctx.overlay.material as THREE.Material).dispose();
  ctx.overlay = null;
}

// ------------------------------------------------------------------ 寸法

const DIM_FONT = "\"Yu Gothic UI\", Meiryo, system-ui, sans-serif";
//: ラベルの大きさ。`sizeAttenuation: false` のとき three が -mvPosition.z を
//  掛けて遠近割りを打ち消すので、**この scale がそのまま画面上の大きさ**になる
//  （カメラ距離に依らず一定。毎フレームのスケール計算が要らない）。
//  画面高さに対する比 ≈ scale × (1/tan(fov/2)) / 2 = scale × 1.207。
const LABEL_SCALE = 0.030;
//: 寸法 1 本が使う頂点数（補助線2 + 寸法線1 + 端の目盛2 = 5 セグメント）。
const VERTS_PER_DIM = 10;

function dimText(d: Dimension): string {
  const v = `${d.label} ${d.value.toFixed(2)}${d.unit ? " " + d.unit : ""}`;
  return d.requested === undefined ? v : `${v}（指定 ${d.requested.toFixed(2)}）`;
}

/** ラベル 1 枚。**白文字＋暗い縁取り**で描く。色は `material.color` で着けるので、
 *  hover の色替えでキャンバスを描き直さなくて済む。外部フォントは読まない。 */
function labelSprite(text: string): THREE.Sprite {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const fs = 22;
  const cv = document.createElement("canvas");
  const c = cv.getContext("2d")!;
  c.font = `${fs}px ${DIM_FONT}`;
  const w = Math.ceil(c.measureText(text).width) + 14;
  const h = fs + 12;
  cv.width = Math.ceil(w * dpr);
  cv.height = Math.ceil(h * dpr);
  // キャンバスのリサイズでコンテキストの状態が消えるので、ここで入れ直す
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.font = `${fs}px ${DIM_FONT}`;
  c.textAlign = "center";
  c.textBaseline = "middle";
  c.lineWidth = 4;
  c.strokeStyle = "#14171c";
  c.strokeText(text, w / 2, h / 2);
  c.fillStyle = "#ffffff";
  c.fillText(text, w / 2, h / 2);

  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex, transparent: true, depthTest: false, sizeAttenuation: false,
  }));
  sprite.scale.set(LABEL_SCALE * (w / h), LABEL_SCALE, 1);
  sprite.renderOrder = 4;
  return sprite;
}

function removeDims(ctx: Ctx) {
  for (const it of ctx.dimItems) {
    it.sprite.material.map?.dispose();
    it.sprite.material.dispose();
  }
  ctx.dimItems = [];
  ctx.dimLines?.geometry.dispose();
  (ctx.dimLines?.material as THREE.Material | undefined)?.dispose();
  ctx.dimLines = null;
  if (ctx.dims) ctx.scene.remove(ctx.dims);
  ctx.dims = null;
}

/** hover 中のパラメータの寸法だけ色を変える。**作り直さない**。 */
function tintDims(ctx: Ctx, hoverKey: string | null) {
  const col = ctx.dimLines?.geometry.getAttribute("color") as
    THREE.BufferAttribute | undefined;
  ctx.dimItems.forEach((it, i) => {
    const c = it.key && it.key === hoverKey ? DIM_HILITE : DIM_COLOR;
    it.sprite.material.color.copy(c);
    if (!col) return;
    for (let v = i * VERTS_PER_DIM; v < (i + 1) * VERTS_PER_DIM; v++) {
      col.setXYZ(v, c.r, c.g, c.b);
    }
  });
  if (col) col.needsUpdate = true;
}

/** 寸法線を組み立てる。逃がし量は**モデルの大きさから出す**（サーバは向きと段
 *  だけを持ち、見た目の距離を持たない）。本体がまだ無い間は何も作らない。 */
function buildDims(ctx: Ctx, dims: Dimension[] | null, hoverKey: string | null) {
  removeDims(ctx);
  const size = ctx.mesh?.userData.modelSize as THREE.Vector3 | undefined;
  if (!ctx.mesh || !size || !dims || dims.length === 0) return;

  const base = 0.06 * size.length();
  const group = new THREE.Group();
  const pos: number[] = [];
  const col: number[] = [];
  const seg = (p: THREE.Vector3, q: THREE.Vector3) => {
    pos.push(p.x, p.y, p.z, q.x, q.y, q.z);
    col.push(DIM_COLOR.r, DIM_COLOR.g, DIM_COLOR.b,
             DIM_COLOR.r, DIM_COLOR.g, DIM_COLOR.b);
  };

  for (const d of dims) {
    const a = new THREE.Vector3(...d.a);
    const b = new THREE.Vector3(...d.b);
    const dir = new THREE.Vector3(...d.dir);
    const off = dir.clone().multiplyScalar(base * (d.level + 1));
    const tick = dir.clone().multiplyScalar(base * 0.10);
    const A = a.clone().add(off);
    const B = b.clone().add(off);
    seg(a, A.clone().add(tick));                  // 補助線（寸法線を少し超す）
    seg(b, B.clone().add(tick));
    seg(A, B);                                    // 寸法線
    seg(A.clone().sub(tick), A.clone().add(tick));  // 端の目盛
    seg(B.clone().sub(tick), B.clone().add(tick));

    const sprite = labelSprite(dimText(d));
    sprite.position.copy(A).add(B).multiplyScalar(0.5)
      .add(tick.clone().multiplyScalar(2.2));
    group.add(sprite);
    ctx.dimItems.push({ key: d.key, sprite });
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  const lines = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({
    vertexColors: true, transparent: true, depthTest: false,
  }));
  lines.renderOrder = 3;
  group.add(lines);
  group.rotation.x = -Math.PI / 2;              // 本体と同じ寝かせ方
  placeInModelFrame(ctx, group);
  ctx.dims = group;
  ctx.dimLines = lines;
  ctx.scene.add(group);
  tintDims(ctx, hoverKey);
}

export default function Viewer3D({
  modelVersion, highlight, hoverKey, srcOverride, overlaySrc, dimensions,
  onBusy, onOverlayBusy,
}: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<Ctx | null>(null);
  const highlightRef = useRef<Region | null>(null);
  highlightRef.current = highlight ?? null;
  // 本体を読み直すと重心と大きさが変わりうるので、寸法もそこで置き直す。
  // そのときに最新の値を読めるよう ref に持っておく。
  const dimsRef = useRef<Dimension[] | null>(null);
  dimsRef.current = dimensions ?? null;
  const hoverRef = useRef<string | null>(null);
  hoverRef.current = hoverKey ?? null;

  useEffect(() => {
    const el = mountRef.current!;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x14171c);
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 2000);
    camera.position.set(90, 60, 130);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    el.appendChild(renderer.domElement);

    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(1, 1.4, 1.2);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0x88aaff, 0.8);
    fill.position.set(-1.2, -0.4, -1);
    scene.add(fill);
    scene.add(new THREE.AmbientLight(0xffffff, 0.35));
    scene.add(new THREE.GridHelper(160, 16, 0x2a3340, 0x222a35));

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      if (w === 0 || h === 0) return;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    let raf = 0;
    const animate = () => {
      raf = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    sceneRef.current = {
      scene, camera, renderer, controls, mesh: null, overlay: null,
      overlaySrc: null, mainLoading: false, pendingOverlay: null,
      dims: null, dimLines: null, dimItems: [],
    };
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.dispose();
      el.removeChild(renderer.domElement);
      sceneRef.current = null;
    };
  }, []);

  /** 参照モデルを取りに行く。**本体の読み込み中なら後回しにする** ——
   *  CAD のワーカは 1 本しか無いので、先に投げると本体の再生成（1.3秒）が
   *  参照のビルド（5.7秒）待ちになる。 */
  const loadOverlay = useCallback((src: string) => {
    const ctx = sceneRef.current;
    if (!ctx) return;
    if (ctx.mainLoading) { ctx.pendingOverlay = src; return; }
    ctx.pendingOverlay = null;
    onOverlayBusy?.(true);
    fetch(src)
      .then((r) => {
        if (!r.ok) throw new Error("ref model fetch failed");
        return r.arrayBuffer();
      })
      .then((buf) => {
        const c = sceneRef.current;
        if (!c || c.overlaySrc !== src) return;   // 途中でトグルを切った
        const geo = new STLLoader().parse(buf);
        geo.computeVertexNormals();
        const overlay = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
          color: 0xa8c0d8, metalness: 0.0, roughness: 0.8,
          // depthWrite を切るのは、参照が手前に来ても本体を隠さないため。
          transparent: true, opacity: 0.25, depthWrite: false,
        }));
        overlay.rotation.x = -Math.PI / 2;        // 本体と同じ寝かせ方
        removeOverlay(c);
        c.overlay = overlay;
        placeInModelFrame(c, overlay);
        c.scene.add(overlay);
      })
      .catch(() => { /* 参照が作れなければ重ねないだけ */ })
      .finally(() => onOverlayBusy?.(false));
  }, [onOverlayBusy]);
  const loadOverlayRef = useRef(loadOverlay);
  loadOverlayRef.current = loadOverlay;

  useEffect(() => {
    const ctx = sceneRef.current;
    if (!ctx) return;
    let cancelled = false;
    ctx.mainLoading = true;
    onBusy?.(true);
    fetch(srcOverride ?? `/api/model.stl?quality=preview&v=${modelVersion}`)
      .then((r) => {
        if (!r.ok) throw new Error("model fetch failed");
        return r.arrayBuffer();
      })
      .then((buf) => {
        if (cancelled || !sceneRef.current) return;
        const geo = new STLLoader().parse(buf);
        geo.computeVertexNormals();
        // center() 前の中心を保存 → モデル座標(z=0=ティップ)へ逆変換できるように
        geo.computeBoundingBox();
        const center = geo.boundingBox!.getCenter(new THREE.Vector3());
        const modelSize = geo.boundingBox!.getSize(new THREE.Vector3());
        geo.center();
        const mat = new THREE.MeshStandardMaterial({
          color: 0xffffff, metalness: 0.15, roughness: 0.45,
          vertexColors: true,
        });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.userData.centerOffset = center;
        mesh.userData.modelSize = modelSize;   // 寸法線の逃がし量の基準
        mesh.rotation.x = -Math.PI / 2; // Z軸(設計軸)を水平に寝かせる
        paintHighlight(mesh, highlightRef.current);
        const c = sceneRef.current;
        if (c.mesh) {
          c.scene.remove(c.mesh);
          c.mesh.geometry.dispose();
        }
        c.scene.add(mesh);
        c.mesh = mesh;
        // 本体が動けば重ねと寸法の基準（重心・大きさ）も動く
        if (c.overlay) placeInModelFrame(c, c.overlay);
        buildDims(c, dimsRef.current, hoverRef.current);
      })
      .catch(() => { /* 生成失敗時は前のモデルを維持 */ })
      .finally(() => {
        if (cancelled) return;      // 次の依頼が既に走っている
        onBusy?.(false);
        const c = sceneRef.current;
        if (!c) return;
        c.mainLoading = false;
        if (c.pendingOverlay) loadOverlayRef.current(c.pendingOverlay);
      });
    return () => { cancelled = true; };
  }, [modelVersion, srcOverride, onBusy]);

  useEffect(() => {
    const ctx = sceneRef.current;
    if (!ctx) return;
    ctx.overlaySrc = overlaySrc ?? null;
    if (!overlaySrc) {
      removeOverlay(ctx);
      ctx.pendingOverlay = null;
      return;
    }
    loadOverlay(overlaySrc);
  }, [overlaySrc, loadOverlay]);

  useEffect(() => {
    const ctx = sceneRef.current;
    if (ctx) buildDims(ctx, dimensions ?? null, hoverRef.current);
  }, [dimensions]);

  useEffect(() => {
    const ctx = sceneRef.current;
    if (ctx) tintDims(ctx, hoverKey ?? null);
  }, [hoverKey]);

  useEffect(() => {
    const mesh = sceneRef.current?.mesh;
    if (mesh) paintHighlight(mesh, highlight ?? null);
  }, [highlight]);

  return (
    <div ref={mountRef} style={{ position: "absolute", inset: 0 }} />
  );
}
