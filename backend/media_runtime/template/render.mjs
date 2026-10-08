import path from 'node:path';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {bundle} from '@remotion/bundler';
import {renderMedia, renderStill, selectComposition} from '@remotion/renderer';

const root = process.cwd();
const timeline = JSON.parse(await readFile(path.join(root, 'timeline.json'), 'utf8'));
const report = (stage, extra = {}) => console.log(JSON.stringify({stage, ...extra}));
const browserExecutable = process.env.WORKBENCH_BROWSER;
await mkdir(path.join(root, 'dist'), {recursive: true});
report('准备动画工程');
const serveUrl = await bundle({entryPoint: path.join(root, 'src', 'index.tsx'), publicDir: path.join(root, 'public')});
const composition = await selectComposition({serveUrl, id: 'Film', browserExecutable});
await renderStill({
  serveUrl, composition, browserExecutable,
  output: path.join(root, 'dist', 'poster.png'),
  frame: Math.min(Math.round(timeline.fps * 2), composition.durationInFrames - 1),
});
if (!process.argv.includes('--still')) {
  let previous = -1;
  await renderMedia({
    composition, serveUrl, browserExecutable,
    codec: 'h264', crf: 18, pixelFormat: 'yuv420p',
    outputLocation: path.join(root, 'dist', 'preview.mp4'),
    concurrency: 3, jpegQuality: 95, audioBitrate: '192k',
    onProgress: ({progress}) => {
      const percent = Math.floor(progress * 100);
      if (percent >= previous + 2) {
        previous = percent;
        report('渲染动画', {percent});
      }
    },
  });
}
await writeFile(path.join(root, 'dist', 'timeline.json'), JSON.stringify(timeline, null, 2));
report('渲染完成', {percent: 100});
