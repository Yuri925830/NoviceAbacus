import fs from "node:fs";
import sharp from "sharp";

const names = [
  "huai-te-portrait-v1",
  "huai-te-advisor-v1",
  "huai-te-dawn-v1",
  "huai-te-vault-v1",
  "huai-te-trend-v1",
];

await Promise.all(
  names.map(async (name) => {
    const input = `public/brand/${name}.png`;
    const output = `public/brand/${name}.webp`;
    await sharp(input)
      .resize({ width: 1600, withoutEnlargement: true })
      .webp({ quality: 84, effort: 5 })
      .toFile(output);
    process.stdout.write(`${name}: ${fs.statSync(output).size} bytes\n`);
  }),
);
