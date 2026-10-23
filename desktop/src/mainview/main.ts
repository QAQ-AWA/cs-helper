import { createApp } from 'vue';
import App from './App.vue';
import { showMainWindowAfterFirstPaint } from './native';
import { installAppGuards } from './utils/app-guards';
import { installNoTabFocus } from './utils/no-tab-focus';
import { logRuntimeDiagnostics } from './utils/runtime-diagnostics';
import { installLongTaskObserver, startupMark } from './utils/startup-metrics';
import { i18n, currentLocale, setDocumentLocale } from './i18n';
import { setAppLocale } from './native';
import './index.css';
import { clientLog } from '@core/log/client-log';

startupMark('main.ts loaded');
installLongTaskObserver();

installAppGuards();
installNoTabFocus();
setDocumentLocale(currentLocale());
void setAppLocale(currentLocale());
// 前端异常也进日志：出问题的机器上没有 devtools，只能靠这份落盘记录。
window.addEventListener('error', (event) => {
  clientLog('ERROR', '前端异常', `${event.message} @ ${event.filename}:${event.lineno}`);
});
window.addEventListener('unhandledrejection', (event) => {
  clientLog('ERROR', '未处理异常', String(event.reason));
});
clientLog('INFO', '启动', `客户端启动 ${__APP_VERSION__}`);

createApp(App).use(i18n).mount('#app');

startupMark('vue mount called');
void showMainWindowAfterFirstPaint();

window.setTimeout(() => {
  logRuntimeDiagnostics();
}, 3000);
