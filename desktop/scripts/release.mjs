import { copyFileSync, existsSync, mkdirSync, rmSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { root } from './load-env.mjs';

const releaseDir = join(root, 'release');
const exeSource = join(root, 'src-tauri/target/release/cs-match-helper.exe');
const appExeName = 'cs-match-helper.exe';
const exeDest = join(releaseDir, appExeName);
const legacyWidgetReleaseDir = join(releaseDir, 'gamebar-widget');

if (!existsSync(exeSource)) {
  console.error(`未找到构建产物: ${exeSource}`);
  console.error('请先运行 tauri build');
  process.exit(1);
}

mkdirSync(releaseDir, { recursive: true });
rmSync(legacyWidgetReleaseDir, { recursive: true, force: true });
copyFileSync(exeSource, exeDest);

const exeSize = statSync(exeDest).size;
console.log(`已输出主程序: ${exeDest}  (${exeSize} bytes)`);
