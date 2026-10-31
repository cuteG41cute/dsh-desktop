const themes = {
  frost: '毛玻璃', liquid: '液态玻璃', crystal: '水晶', flat: '扁平化',
  alpine: '雪山', dawn: '晨光', sea: '静海'
};
const instances = {
  'dsh': { avatar: 'DS', running: false, pid: '—', path: '/home/twinblade/Program/dsh' },
  'deepseek-harness-1': { avatar: 'D1', running: true, pid: '90837', path: '/home/twinblade/Program/deepseek-harness-1' },
  'deepseek-harness-2': { avatar: 'D2', running: false, pid: '—', path: '/home/twinblade/Program/deepseek-harness-2' }
};
const params = new URLSearchParams(location.search);
let currentTheme = params.get('theme') || localStorage.getItem('dsh-theme') || 'frost';
let currentMode = params.get('mode') || localStorage.getItem('dsh-mode') || 'day';
if (!themes[currentTheme]) currentTheme = 'frost';
if (!['day', 'night'].includes(currentMode)) currentMode = 'day';
let selectedInstance = 'deepseek-harness-1';
let toastTimer;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function setAppearance(theme, mode, persist = true) {
  currentTheme = themes[theme] ? theme : currentTheme;
  currentMode = ['day', 'night'].includes(mode) ? mode : currentMode;
  document.body.dataset.theme = currentTheme;
  document.body.dataset.mode = currentMode;
  $('#themeName').textContent = themes[currentTheme];
  $('#settingsThemeName').textContent = themes[currentTheme];
  $('#settingsModeName').textContent = currentMode === 'day' ? '日间模式' : '夜间模式';
  $('#modeToggle').setAttribute('aria-label', currentMode === 'day' ? '切换夜间模式' : '切换日间模式');
  $$('[data-set-theme]').forEach(button => button.classList.toggle('selected', button.dataset.setTheme === currentTheme));
  if (persist) {
    localStorage.setItem('dsh-theme', currentTheme);
    localStorage.setItem('dsh-mode', currentMode);
  }
}

function toast(message) {
  clearTimeout(toastTimer);
  $('#toastText').textContent = message;
  $('#toast').classList.add('show');
  toastTimer = setTimeout(() => $('#toast').classList.remove('show'), 2600);
}

function closeMenus() {
  $('#themeMenu').hidden = true;
  $('#moreMenu').hidden = true;
  $('#themeTrigger').setAttribute('aria-expanded', 'false');
}

function showPage(page) {
  const settings = page === 'settings';
  $('#dashboardPage').hidden = settings;
  $('#settingsPage').hidden = !settings;
  $('#settingsNav').classList.toggle('selected', settings);
  $('#overviewNav').classList.toggle('selected', !settings);
  $('#breadcrumbCurrent').textContent = settings ? '管理器设置' : '实例概览';
  closeMenus();
}

function selectInstance(name) {
  if (!instances[name]) return;
  selectedInstance = name;
  const item = instances[name];
  $$('.instance-item').forEach(button => button.classList.toggle('active', button.dataset.instance === name));
  $('#instanceTitle').textContent = name;
  $('#installPath').textContent = item.path;
  $('#pidValue').textContent = item.pid;
  $('.large-avatar').firstChild.textContent = item.avatar;
  $('#statusBadge').classList.toggle('stopped', !item.running);
  $('#statusBadge').innerHTML = `<i></i>${item.running ? '运行中' : '已停止'}`;
  $('#metricStatus').textContent = item.running ? '运行中' : '已停止';
  $('.live-indicator').innerHTML = `<i></i>${item.running ? '服务正常' : '服务已停止'}`;
  $(`.instance-item[data-instance="${name}"] .status-dot`).classList.toggle('stopped', !item.running);
  $('#stopService').classList.toggle('btn-danger-soft', item.running);
  $('#stopService').classList.toggle('btn-secondary', !item.running);
  $('#stopService').innerHTML = item.running
    ? '<svg><use href="#i-stop"/></svg>停止'
    : '<svg><use href="#i-external"/></svg>启动';
  showPage('dashboard');
}

function openModal() {
  closeMenus();
  $('#modalBackdrop').hidden = false;
  setTimeout(() => $('#newInstanceName').focus(), 50);
}
function closeModal() { $('#modalBackdrop').hidden = true; }

setAppearance(currentTheme, currentMode, false);

$('#themeTrigger').addEventListener('click', event => {
  event.stopPropagation();
  const open = $('#themeMenu').hidden;
  closeMenus();
  $('#themeMenu').hidden = !open;
  $('#themeTrigger').setAttribute('aria-expanded', String(open));
});
$('#moreTrigger').addEventListener('click', event => {
  event.stopPropagation();
  const open = $('#moreMenu').hidden;
  closeMenus();
  $('#moreMenu').hidden = !open;
});
$$('[data-set-theme]').forEach(button => button.addEventListener('click', () => {
  setAppearance(button.dataset.setTheme, currentMode);
  closeMenus();
}));
$('#modeToggle').addEventListener('click', () => setAppearance(currentTheme, currentMode === 'day' ? 'night' : 'day'));
$('#settingsThemeButton').addEventListener('click', event => {
  event.stopPropagation();
  $('#themeMenu').hidden = false;
  $('#themeTrigger').setAttribute('aria-expanded', 'true');
});
document.addEventListener('click', event => { if (!event.target.closest('.theme-select-wrap') && !event.target.closest('.more-wrap')) closeMenus(); });
$('.instance-list').addEventListener('click', event => {
  const button = event.target.closest('[data-instance]');
  if (button) selectInstance(button.dataset.instance);
});
$('#overviewNav').addEventListener('click', () => showPage('dashboard'));
$('#settingsNav').addEventListener('click', () => showPage('settings'));
$('#saveSettings').addEventListener('click', () => toast(`设置已保存 · 日志保留 ${$('#logLines').value} 行`));
$$('[data-action]').forEach(button => button.addEventListener('click', () => {
  const action = button.dataset.action;
  closeMenus();
  if (action === '卸载实例') toast('为避免误操作，卸载需要在正式程序中二次确认');
  else if (action === '复制诊断信息') toast('诊断信息已复制到剪贴板');
  else toast(`${action} · 原型交互演示`);
}));
$('#openWindow').addEventListener('click', () => toast(`已打开 ${selectedInstance} 的窗口`));
$('#stopService').addEventListener('click', () => {
  const item = instances[selectedInstance];
  item.running = !item.running;
  item.pid = item.running ? '90837' : '—';
  selectInstance(selectedInstance);
  toast(item.running ? '实例服务已启动' : '实例服务已停止');
});
$('#notificationBtn').addEventListener('click', () => toast('实例窗口有新版本，重建窗口后生效'));
$('#helpBtn').addEventListener('click', () => toast('帮助中心 · 原型交互演示'));
$('#viewLogs').addEventListener('click', () => toast('完整日志面板 · 原型交互演示'));
$('#addInstance').addEventListener('click', openModal);
$('#newInstance').addEventListener('click', openModal);
$('#modalClose').addEventListener('click', closeModal);
$('#modalCancel').addEventListener('click', closeModal);
$('#modalBackdrop').addEventListener('click', event => { if (event.target === $('#modalBackdrop')) closeModal(); });
$('#newInstanceForm').addEventListener('submit', event => {
  event.preventDefault();
  const name = $('#newInstanceName').value.trim();
  if (!name) return;
  if (instances[name]) { toast('该实例名称已存在'); return; }
  instances[name] = { avatar: 'D' + (Object.keys(instances).length), running: false, pid: '—', path: `/home/twinblade/Program/${name}` };
  const button = document.createElement('button');
  button.className = 'instance-item';
  button.dataset.instance = name;
  button.innerHTML = `<span class="instance-avatar">${instances[name].avatar}</span><span class="instance-copy"><strong></strong><small>v0.2.1-rc.5</small></span><i class="status-dot stopped"></i>`;
  button.querySelector('strong').textContent = name;
  $('.instance-list').appendChild(button);
  $('.side-section-title .count').textContent = Object.keys(instances).length;
  closeModal();
  selectInstance(name);
  toast(`实例 ${name} 已创建`);
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') { closeMenus(); closeModal(); }
});
window.previewAppearance = (theme, mode) => setAppearance(theme, mode, false);
