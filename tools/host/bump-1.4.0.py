"""把版本号提到 1.4.0，并把新加的 dsh_manager/icons/ 打进 deb。

（之前 icons/ 目录是后加的，build-deb.sh 里没有对应的拷贝行 —— 直接打包会漏掉图标，
  运行时 GdkPixbuf 找不到 svg，界面会退回成文字符号。）
"""
import io

BUILD = 'dsh-desktop/linux/manager/build-deb.sh'
CORE = 'dsh-desktop/linux/manager/dsh_manager/core.py'

s = io.open(BUILD, encoding='utf-8').read()
if 'dsh_manager/icons' not in s:
    anchor = ('install -m 0644 "$MANAGER_DIR/dsh_manager/plugins.py"  '
              '"$STAGE/usr/lib/dsh-manager/dsh_manager/"')
    assert anchor in s, 'anchors changed'
    add = ('mkdir -p "$STAGE/usr/lib/dsh-manager/dsh_manager/icons"\n'
           'cp -f "$MANAGER_DIR"/dsh_manager/icons/*.svg '
           '"$STAGE/usr/lib/dsh-manager/dsh_manager/icons/"\n')
    s = s.replace(anchor, add + anchor, 1)
s = s.replace('VERSION="1.3.3"', 'VERSION="1.4.0"', 1)
io.open(BUILD, 'w', encoding='utf-8', newline='\n').write(s)

c = io.open(CORE, encoding='utf-8').read()
c = c.replace("MANAGER_VERSION = '1.3.3'", "MANAGER_VERSION = '1.4.0'", 1)
io.open(CORE, 'w', encoding='utf-8', newline='\n').write(c)

print('build-deb.sh: icons + VERSION=1.4.0')
print('core.py: MANAGER_VERSION=1.4.0')
