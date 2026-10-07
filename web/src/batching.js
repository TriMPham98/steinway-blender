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
 * Parts that repeat one shared geometry + material many times (the action's
 * wippens, jacks, hammers in size groups, damper heads...) go to a
 * THREE.InstancedMesh first: one plain instanced draw instead of a multi-draw
 * entry per part, which ANGLE's Metal backend replays as individual draws
 * (~1,800 action sub-draws per pass cost ~3 ms/frame on an M1 Pro).
 *
 * Meshes tagged `userData.batchGroup` only merge within their group, so a group
 * (e.g. the piano action) can be shown or hidden as a whole — see `drawsIn`.
 *
 * The original meshes stay in the graph but move to BATCH_SOURCE_LAYER, which
 * no camera renders: the rigs (piano.js, action.js, case.js) keep posing them
 * and `sync()` copies their world matrices into the batch / instances. A layer — not
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
  // Parts that fade or toggle on their own (the removable music desk).
  if (mesh.userData.noBatch) return false;
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
 * @param {{ minGroupSize?: number, minInstances?: number }} [opts]
 * @returns {{ batches: THREE.BatchedMesh[], instanced: THREE.InstancedMesh[], meshCount: number, sync: () => void }}
 */
export function batchMeshes(root, parent, { minGroupSize = 2, minInstances = 8 } = {}) {
  root.updateMatrixWorld(true);

  // Pass 1: shared geometry + material repeated often enough -> instancing.
  /** @type {Map<string, THREE.Mesh[]>} */
  const repeats = new Map();
  root.traverse((obj) => {
    if (!isBatchable(obj)) return;
    const key = [
      obj.userData.batchGroup ?? "",
      obj.geometry.uuid,
      obj.material.uuid,
      obj.castShadow ? "c" : "-",
      obj.receiveShadow ? "r" : "-",
    ].join("|");
    const list = repeats.get(key);
    if (list) list.push(obj);
    else repeats.set(key, [obj]);
  });
  /** @type {THREE.InstancedMesh[]} */
  const instanced = [];
  /** Flat [instancedMesh, index, mesh] records for sync(). */
  const instRecords = [];
  const sphere = new THREE.Sphere();
  let meshCount = 0;
  for (const meshes of repeats.values()) {
    if (meshes.length < minInstances) continue;
    const first = meshes[0];
    const inst = new THREE.InstancedMesh(first.geometry, first.material, meshes.length);
    inst.name = `Instanced_${first.material.name || "material"}`;
    inst.userData.batchGroup = first.userData.batchGroup;
    inst.castShadow = first.castShadow;
    inst.receiveShadow = first.receiveShadow;
    meshes.forEach((mesh, i) => {
      inst.setMatrixAt(i, mesh.matrixWorld);
      instRecords.push(inst, i, mesh);
      mesh.layers.set(BATCH_SOURCE_LAYER);
      meshCount++;
    });
    inst.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    // Moving parts travel a few cm from where they were measured; pad the
    // culling sphere rather than recomputing it every pose frame.
    inst.computeBoundingSphere();
    sphere.copy(inst.boundingSphere);
    inst.boundingSphere.radius = sphere.radius + 0.1;
    parent.add(inst);
    instanced.push(inst);
  }

  // Pass 2: everything else folds into per-material BatchedMeshes.
  /** @type {Map<string, THREE.Mesh[]>} */
  const groups = new Map();
  root.traverse((obj) => {
    if (!isBatchable(obj)) return;
    const geo = obj.geometry;
    const sig = attributeSignature(geo);
    if (sig == null) return;
    const key = [
      obj.userData.batchGroup ?? "",
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
    batch.userData.batchGroup = first.userData.batchGroup;
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
    instanced,
    meshCount,
    /** @param {string} group @returns {THREE.Mesh[]} draws built from that group */
    drawsIn(group) {
      return [...instanced, ...batches].filter((d) => d.userData.batchGroup === group);
    },
    /** Copy the hidden source meshes' current world matrices into the draws. */
    sync() {
      root.updateMatrixWorld();
      for (let i = 0; i < records.length; i += 3) {
        records[i].setMatrixAt(records[i + 1], records[i + 2].matrixWorld);
      }
      for (let i = 0; i < instRecords.length; i += 3) {
        instRecords[i].setMatrixAt(instRecords[i + 1], instRecords[i + 2].matrixWorld);
      }
      for (const inst of instanced) inst.instanceMatrix.needsUpdate = true;
    },
  };
}
