"""加 --selftest-actions：对本机发现的实例跑一遍「是否受管 / 修复自检」，结果写 crash.log。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'App.xaml.cs')

OLD = '                if (args.Contains("--newinstance"))'
NEW = '''                if (args.Contains("--selftest-actions"))
                {
                    SelfTestActionsAndExit();
                }
                else if (args.Contains("--newinstance"))'''

ANCHOR = '    /// <summary>--newinstance：只打开「新建实例」对话框并截图。</summary>'

METHOD = '''    /// <summary>
    /// --selftest-actions：对发现的每个实例跑一遍「是否受管 / 修复自检」，
    /// 结果写进 crash.log（开发期用命令行验证动作层，不用点界面）。
    /// </summary>
    private void SelfTestActionsAndExit()
    {
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        Task.Run(async () =>
        {
            var list = DshDiscovery.Scan().ToList();
            DshDiscovery.AttachRunning(list);
            DshDiscovery.ApplyRegistryPorts(list);
            foreach (var inst in list)
            {
                Log("[selftest] " + inst.Label + " | " + inst.Source + " | dir=" + inst.Dir
                    + " | managed=" + InstanceActions.IsManaged(inst)
                    + " | running=" + inst.Running + " port=" + inst.Port);
                var (ok, msg) = await InstanceActions.RepairAsync(inst, m => Log("    | " + m));
                Log("[selftest]   repair -> " + (ok ? "OK" : "FAIL") + ": " + msg);
            }
            Dispatcher.Invoke(Shutdown);
        });
    }

''' + ANCHOR


def main():
    src = io.open(P, encoding='utf-8').read()
    if OLD not in src:
        print('MISS args')
        return 1
    src = src.replace(OLD, NEW, 1)
    if ANCHOR not in src:
        print('MISS anchor')
        return 1
    src = src.replace(ANCHOR, METHOD, 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('selftest-actions added')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
