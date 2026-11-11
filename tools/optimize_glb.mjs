/**
 * tools/optimize_glb.mjs
 * Script di ottimizzazione e compressione per modelli GLB.
 * Preserva i nomi dei nodi e i userData (Custom Properties di Blender).
 */

import fs from 'node:fs';
import path from 'node:path';

const inputGlb = path.resolve('public/models/house_raw.glb');
const outputGlb = path.resolve('public/models/house_optimized.glb');

async function optimize() {
  if (!fs.existsSync(inputGlb)) {
    console.error(`[ERROR] File di input non trovato: ${inputGlb}`);
    process.exit(1);
  }

  const inSize = fs.statSync(inputGlb).size / (1024 * 1024);
  console.log(`[GLTF Optimizer] Input: ${inputGlb} (${inSize.toFixed(2)} MB)`);

  try {
    const { NodeIO } = await import('@gltf-transform/core');
    const { KHRONOS_EXTENSIONS } = await import('@gltf-transform/extensions');
    const { dedup, prune, weld } = await import('@gltf-transform/functions');

    const io = new NodeIO().registerExtensions(KHRONOS_EXTENSIONS);
    const document = await io.read(inputGlb);

    // Applica ottimizzazioni sicure che non rimuovono userData o nomi di nodi
    await document.transform(
      dedup(),
      prune({ keepAttributes: true, keepLeaves: true }),
      weld()
    );

    await io.write(outputGlb, document);
    const outSize = fs.statSync(outputGlb).size / (1024 * 1024);
    console.log(`[GLTF Optimizer] Success! Output: ${outputGlb} (${outSize.toFixed(2)} MB)`);
  } catch (err) {
    console.warn(`[GLTF Optimizer] Warning: @gltf-transform non utilizzabile (${err.message}). Copio house_raw.glb -> house_optimized.glb`);
    fs.copyFileSync(inputGlb, outputGlb);
    console.log(`[GLTF Optimizer] house_optimized.glb pronto via fallback copy.`);
  }
}

optimize();

