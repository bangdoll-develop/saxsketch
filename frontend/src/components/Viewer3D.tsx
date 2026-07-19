import { useEffect, useRef } from "react";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Region } from "../api";

interface Props {
  /** パラメータ変更のたびに増えるトークン。変わったらSTLを再取得 */
  modelVersion: number;
  /** ハイライトする影響領域（パラメータhover中のみ非null） */
  highlight?: Region | null;
  /** 別モデルを表示する場合のURL（外部編集済みモデル等）。null=パラメトリック形状 */
  srcOverride?: string | null;
  onBusy?: (busy: boolean) => void;
}

const BASE = new THREE.Color(0x7fa8d8);      // 通常部
const HILITE = new THREE.Color(0xffa03c);    // 影響部（オレンジ）
const DIMMED = new THREE.Color(0x4a5c72);    // ハイライト中の非対象部（暗め）

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

export default function Viewer3D({ modelVersion, highlight, srcOverride, onBusy }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<{
    scene: THREE.Scene; camera: THREE.PerspectiveCamera;
    renderer: THREE.WebGLRenderer; controls: OrbitControls;
    mesh: THREE.Mesh | null;
  } | null>(null);
  const highlightRef = useRef<Region | null>(null);
  highlightRef.current = highlight ?? null;

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

    sceneRef.current = { scene, camera, renderer, controls, mesh: null };
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.dispose();
      el.removeChild(renderer.domElement);
      sceneRef.current = null;
    };
  }, []);

  useEffect(() => {
    const ctx = sceneRef.current;
    if (!ctx) return;
    let cancelled = false;
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
        geo.center();
        const mat = new THREE.MeshStandardMaterial({
          color: 0xffffff, metalness: 0.15, roughness: 0.45,
          vertexColors: true,
        });
        const mesh = new THREE.Mesh(geo, mat);
        mesh.userData.centerOffset = center;
        mesh.rotation.x = -Math.PI / 2; // Z軸(設計軸)を水平に寝かせる
        paintHighlight(mesh, highlightRef.current);
        const c = sceneRef.current;
        if (c.mesh) {
          c.scene.remove(c.mesh);
          c.mesh.geometry.dispose();
        }
        c.scene.add(mesh);
        c.mesh = mesh;
      })
      .catch(() => { /* 生成失敗時は前のモデルを維持 */ })
      .finally(() => { if (!cancelled) onBusy?.(false); });
    return () => { cancelled = true; };
  }, [modelVersion, srcOverride, onBusy]);

  useEffect(() => {
    const mesh = sceneRef.current?.mesh;
    if (mesh) paintHighlight(mesh, highlight ?? null);
  }, [highlight]);

  return (
    <div ref={mountRef} style={{ position: "absolute", inset: 0 }} />
  );
}
