import * as THREE from "three";

/**
 * Draw-call batching for the piano model.
 *
 * The GLB is ~1,750 separate meshes (88 keys, ~1,650 action parts, case parts),
 * and every one is a draw call in each of the main, floor-reflection and shadow
 * passes (~4,200 calls/frame). Meshes that share a material are folded into one
 * THREE.BatchedMesh, which draws them all in a single multi-draw call with
 * per-instance matrices and per-instance frustum culling.
 *
 * The original meshes stay in the graph but move to BATCH_SOURCE_LAYER, which
 * no camera renders: the rigs (piano.js, action.js, case.js) keep posing them
 * and `sync()` copies their world matrices into the batch. A layer — not
 * `visible = false` — because hiding a mesh also hides its children (the lid
 * mesh parents the hinges and prop), while layers are per-object. Raycasters
 * that pick model parts must enable this layer.
 */

export const BATCH_SOURCE_LAYER = 31;

function effectivelyVisible(obj) {
  for (let o = obj; o; o = o.parent) if (!o.visible) return false;
  return true;
}

function attributeSignature(geo) {
  const parts = [];
  for (const name of Object.keys(geo.attributes).sort()) {
    const a = geo.attributes[name];
    if (a.isInterleavedBufferAttribute) return null;
    parts.push(`${name}:${a.itemSize}:${a.normalized ? 1 : 0}:${a.array.constructor.name}`);
  }
  return parts.join(",");
}

function isBatchable(mesh) {
  if (!mesh.isMesh || mesh.isInstancedMesh || mesh.isSkinnedMesh || mesh.isBatchedMesh) {
    return false;
  }
  const mat = mesh.material;
  if (!mat || Array.isArray(mat) || mat.transparent) return false;
  // Custom draw ordering / hooks don't survive merging.
  if (mesh.renderOrder !== 0 || mesh.onBeforeRender !== THREE.Object3D.prototype.onBeforeRender) {
    return false;
  }
  const geo = mesh.geometry;
  if (Object.keys(geo.morphAttributes ?? {}).length) return false;
  return mesh.layers.isEnabled(0) && effectivelyVisible(mesh);
}

/**
 * Fold same-material meshes under `root` into BatchedMeshes added to `parent`
 * (which must have an identity world transform, e.g. the scene).
 * @param {THREE.Object3D} root
 * @param {THREE.Object3D} parent
 * @param {{ minGroupSize?: number }} [opts]
 * @returns {{ batches: THREE.BatchedMesh[], meshCount: number, sync: () => void }}
 */
export function batchMeshes(root, parent, { minGroupSize = 2 } = {}) {
  root.updateMatrixWorld(true);

  /** @type {Map<string, THREE.Mesh[]>} */
  const groups = new Map();
  root.traverse((obj) => {
    if (!isBatchable(obj)) return;
    const geo = obj.geometry;
    const sig = attributeSignature(geo);
    if (sig == null) return;
    const key = [
      obj.material.uuid,
      sig,
      geo.index ? "i" : "n",
      obj.castShadow ? "c" : "-",
      obj.receiveShadow ? "r" : "-",
    ].join("|");
    const list = groups.get(key);
    if (list) list.push(obj);
    else groups.set(key, [obj]);
  });

  /** @type {THREE.BatchedMesh[]} */
  const batches = [];
  /** Flat [batch, instanceId, mesh] records for sync(). */
  const records = [];
  let meshCount = 0;

  for (const meshes of groups.values()) {
    if (meshes.length < minGroupSize) continue;
    const unique = new Map();
    for (const m of meshes) unique.set(m.geometry.uuid, m.geometry);
    let vertexCount = 0;
    let indexCount = 0;
    for (const g of unique.values()) {
      vertexCount += g.attributes.position.count;
      indexCount += g.index ? g.index.count : 0;
    }

    const first = meshes[0];
    const batch = new THREE.BatchedMesh(
      meshes.length,
      vertexCount,
      indexCount,
      first.material,
    );
    batch.name = `Batch_${first.material.name || "material"}`;
    batch.castShadow = first.castShadow;
    batch.receiveShadow = first.receiveShadow;
    // Opaque-only batches: per-instance depth sorting buys nothing here.
    batch.sortObjects = false;

    const geoIds = new Map();
    for (const mesh of meshes) {
      let gid = geoIds.get(mesh.geometry.uuid);
      if (gid == null) {
        gid = batch.addGeometry(mesh.geometry);
        geoIds.set(mesh.geometry.uuid, gid);
      }
      const id = batch.addInstance(gid);
      batch.setMatrixAt(id, mesh.matrixWorld);
      records.push(batch, id, mesh);
      mesh.layers.set(BATCH_SOURCE_LAYER);
      meshCount++;
    }
    parent.add(batch);
    batches.push(batch);
  }

  return {
    batches,
    meshCount,
    /** Copy the hidden source meshes' current world matrices into the batches. */
    sync() {
      root.updateMatrixWorld();
      for (let i = 0; i < records.length; i += 3) {
        records[i].setMatrixAt(records[i + 1], records[i + 2].matrixWorld);
      }
    },
  };
}
