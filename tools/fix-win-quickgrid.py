"""修复被上一次脚本弄坏的「常用功能」区块：改成 WrapPanel + 四张命名卡片。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml')

START = '                            <Grid x:Name="QuickGrid">'
END_MARK = '                            </Grid>\n\n                            <!-- 最近日志 -->'

NEW = '''                            <WrapPanel x:Name="QuickGrid">
                                <Border x:Name="Quick1" Style="{StaticResource CardStyle}" Height="82" Cursor="Hand"
                                        Padding="13" Margin="0,0,11,11">
                                    <StackPanel Orientation="Horizontal" VerticalAlignment="Center">
                                        <Border Width="34" Height="34" CornerRadius="10"
                                                Background="{DynamicResource AccentSoft}">
                                            <Path Width="17" Height="17" Data="{StaticResource Icon.key}"
                                                  Style="{StaticResource IconPath}" Stroke="{DynamicResource Accent}" />
                                        </Border>
                                        <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                            <TextBlock Text="查看 Token" FontSize="10.5" FontWeight="SemiBold"
                                                       Foreground="{DynamicResource Text}" />
                                            <TextBlock x:Name="Quick1Sub" Text="访问凭证与连接信息" FontSize="8" Margin="0,5,0,0"
                                                       Foreground="{DynamicResource Muted}" />
                                        </StackPanel>
                                    </StackPanel>
                                </Border>
                                <Border x:Name="Quick2" Style="{StaticResource CardStyle}" Height="82" Cursor="Hand"
                                        Padding="13" Margin="0,0,11,11">
                                    <StackPanel Orientation="Horizontal" VerticalAlignment="Center">
                                        <Border Width="34" Height="34" CornerRadius="10"
                                                Background="{DynamicResource AccentSoft}">
                                            <Path Width="17" Height="17" Data="{StaticResource Icon.puzzle}"
                                                  Style="{StaticResource IconPath}" Stroke="{DynamicResource Accent}" />
                                        </Border>
                                        <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                            <TextBlock Text="管理插件" FontSize="10.5" FontWeight="SemiBold"
                                                       Foreground="{DynamicResource Text}" />
                                            <TextBlock x:Name="Quick2Sub" Text="安装、启用与配置扩展" FontSize="8" Margin="0,5,0,0"
                                                       Foreground="{DynamicResource Muted}" />
                                        </StackPanel>
                                    </StackPanel>
                                </Border>
                                <Border x:Name="Quick3" Style="{StaticResource CardStyle}" Height="82" Cursor="Hand"
                                        Padding="13" Margin="0,0,11,11">
                                    <StackPanel Orientation="Horizontal" VerticalAlignment="Center">
                                        <Border Width="34" Height="34" CornerRadius="10"
                                                Background="{DynamicResource AccentSoft}">
                                            <Path Width="17" Height="17" Data="{StaticResource Icon.update}"
                                                  Style="{StaticResource IconPath}" Stroke="{DynamicResource Accent}" />
                                        </Border>
                                        <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                            <TextBlock Text="检查更新" FontSize="10.5" FontWeight="SemiBold"
                                                       Foreground="{DynamicResource Text}" />
                                            <TextBlock x:Name="Quick3Sub" Text="当前已是最新版本" FontSize="8" Margin="0,5,0,0"
                                                       Foreground="{DynamicResource Muted}" />
                                        </StackPanel>
                                    </StackPanel>
                                </Border>
                                <Border x:Name="Quick4" Style="{StaticResource CardStyle}" Height="82" Cursor="Hand"
                                        Padding="13" Margin="0,0,0,11">
                                    <StackPanel Orientation="Horizontal" VerticalAlignment="Center">
                                        <Border Width="34" Height="34" CornerRadius="10"
                                                Background="{DynamicResource AccentSoft}">
                                            <Path Width="17" Height="17" Data="{StaticResource Icon.folder}"
                                                  Style="{StaticResource IconPath}" Stroke="{DynamicResource Accent}" />
                                        </Border>
                                        <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                            <TextBlock Text="数据目录" FontSize="10.5" FontWeight="SemiBold"
                                                       Foreground="{DynamicResource Text}" />
                                            <TextBlock x:Name="Quick4Sub" Text="浏览配置与本地数据" FontSize="8" Margin="0,5,0,0"
                                                       Foreground="{DynamicResource Muted}" />
                                        </StackPanel>
                                    </StackPanel>
                                </Border>
                            </WrapPanel>

                            <!-- 最近日志 -->'''


def main():
    src = io.open(P, encoding='utf-8').read()
    start = src.index(START)
    end = src.index(END_MARK, start) + len(END_MARK)
    src = src[:start] + NEW + src[end:]
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('repaired quick section:', start, '->', end)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
