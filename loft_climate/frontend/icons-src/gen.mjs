import sharp from 'sharp';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const src = fs.readFileSync(path.join(ROOT, 'icons-src/icon.svg'));

async function gen(file, size, opts={}) {
  const out = path.join(ROOT, file);
  let img;
  if (opts.maskable) {
    const inner = Math.round(size * 0.6);
    img = sharp({create: {width: size, height: size, channels: 4, background: '#0f172a'}})
      .composite([{ input: await sharp(src).resize(inner, inner).png().toBuffer(),
                    gravity: 'center' }]);
  } else {
    img = sharp(src).resize(size, size);
  }
  await img.png().toFile(out);
  console.log('wrote', out);
}

await gen('public/icons/icon-192.png', 192);
await gen('public/icons/icon-512.png', 512);
await gen('public/icons/icon-maskable-512.png', 512, {maskable: true});
await gen('public/icons/apple-touch-icon.png', 180);
