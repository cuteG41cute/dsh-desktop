"""加「管理器设置」页（照设计稿 settingsPage），并在侧栏里切换两页。"""

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml')

SETTINGS_PAGE = '''
                    <!-- ================= 管理器设置页 ================= -->
                    <ScrollViewer x:Name="SettingsScroll" Grid.Row="1" Visibility="Collapsed"
                                  VerticalScrollBarVisibility="Auto" Padding="30,25,30,15">
                        <StackPanel>
                            <Grid Margin="0,0,0,22">
                                <StackPanel>
                                    <TextBlock Text="MANAGER PREFERENCES" FontSize="8" FontWeight="Bold"
                                               Foreground="{DynamicResource Accent}" />
                                    <TextBlock Text="管理器设置" FontSize="25" FontWeight="SemiBold" Margin="0,6,0,0"
                                               Foreground="{DynamicResource Text}" />
                                    <TextBlock Text="查看运行环境，管理外观与维护选项。" FontSize="11" Margin="0,7,0,0"
                                               Foreground="{DynamicResource Muted}" />
                                </StackPanel>
                                <Button x:Name="SaveSettingsBtn" Style="{StaticResource BtnPrimary}"
                                        HorizontalAlignment="Right" VerticalAlignment="Bottom" Click="OnSaveSettings">
                                    <StackPanel Orientation="Horizontal">
                                        <Path Width="16" Height="16" Data="{StaticResource Icon.check}"
                                              Style="{StaticResource IconPath}" Stroke="{DynamicResource OnAccent}" />
                                        <TextBlock Text="保存设置" Margin="7,0,0,0" />
                                    </StackPanel>
                                </Button>
                            </Grid>

                            <Grid>
                                <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width="1.5*" />
                                    <ColumnDefinition Width="17" />
                                    <ColumnDefinition Width="1*" MinWidth="320" />
                                </Grid.ColumnDefinitions>

                                <StackPanel Grid.Column="0">
                                    <!-- 管理器信息 -->
                                    <Border Style="{StaticResource CardStyle}" Padding="21">
                                        <StackPanel>
                                            <StackPanel Orientation="Horizontal">
                                                <Border Width="34" Height="34" CornerRadius="10"
                                                        Background="{DynamicResource AccentSoft}">
                                                    <Path Width="17" Height="17" Data="{StaticResource Icon.info}"
                                                          Style="{StaticResource IconPath}" Stroke="{DynamicResource Accent}" />
                                                </Border>
                                                <StackPanel Margin="11,0,0,0" VerticalAlignment="Center">
                                                    <TextBlock Text="管理器信息" FontSize="13" FontWeight="SemiBold"
                                                               Foreground="{DynamicResource Text}" />
                                                    <TextBlock Text="当前安装与运行环境" FontSize="9" Margin="0,4,0,0"
                                                               Foreground="{DynamicResource Muted}" />
                                                </StackPanel>
                                            </StackPanel>
                                            <Border Height="1" Margin="0,17,0,0" Background="{DynamicResource InnerBorder}" />
                                            <StackPanel x:Name="InfoList" Margin="0,7,0,0" />
                                        </StackPanel>
                                    </Border>

                                    <!-- 维护与诊断 -->
                                    <Border Style="{StaticResource CardStyle}" Padding="21" Margin="0,17,0,0">
                                        <StackPanel>
                                            <StackPanel Orientation="Horizontal">
                                                <Border Width="34" Height="34" CornerRadius="10"
                                                        Background="{DynamicResource AccentSoft}">
                                                    <Path Width="17" Height="17" Data="{StaticResource Icon.wrench}"
                                                          Style="{StaticResource IconPath}" Stroke="{DynamicResource Accent}" />
                                                </Border>
                                                <StackPanel Margin="11,0,0,0" VerticalAlignment="Center">
                                                    <TextBlock Text="维护与诊断" FontSize="13" FontWeight="SemiBold"
                                                               Foreground="{DynamicResource Text}" />
                                                    <TextBlock Text="排查问题或检查更新" FontSize="9" Margin="0,4,0,0"
                                                               Foreground="{DynamicResource Muted}" />
                                                </StackPanel>
                                            </StackPanel>
                                            <WrapPanel Margin="0,17,0,0">
                                                <Button Style="{StaticResource BtnSecondary}" Height="34" FontSize="9"
                                                        Margin="0,0,8,8" Click="OnOpenManagerLog">
                                                    <StackPanel Orientation="Horizontal">
                                                        <Path Width="14" Height="14" Data="{StaticResource Icon.terminal}"
                                                              Style="{StaticResource IconPath}" />
                                                        <TextBlock Text="查看管理器日志" Margin="7,0,0,0" />
                                                    </StackPanel>
                                                </Button>
                                                <Button Style="{StaticResource BtnSecondary}" Height="34" FontSize="9"
                                                        Margin="0,0,8,8" Click="OnCopyDiagnostics">
                                                    <StackPanel Orientation="Horizontal">
                                                        <Path Width="14" Height="14" Data="{StaticResource Icon.copy}"
                                                              Style="{StaticResource IconPath}" />
                                                        <TextBlock Text="复制诊断信息" Margin="7,0,0,0" />
                                                    </StackPanel>
                                                </Button>
                                                <Button Style="{StaticResource BtnSecondary}" Height="34" FontSize="9"
                                                        Margin="0,0,8,8" Click="OnCheckUpdate">
                                                    <StackPanel Orientation="Horizontal">
                                                        <Path Width="14" Height="14" Data="{StaticResource Icon.update}"
                                                              Style="{StaticResource IconPath}" />
                                                        <TextBlock Text="检查更新" Margin="7,0,0,0" />
                                                    </StackPanel>
                                                </Button>
                                            </WrapPanel>
                                        </StackPanel>
                                    </Border>
                                </StackPanel>

                                <!-- 外观与日志 -->
                                <Border Grid.Column="2" Style="{StaticResource CardStyle}" Padding="21"
                                        VerticalAlignment="Top">
                                    <StackPanel>
                                        <StackPanel Orientation="Horizontal">
                                            <Border Width="34" Height="34" CornerRadius="10"
                                                    Background="{DynamicResource AccentSoft}">
                                                <Path Width="17" Height="17" Data="{StaticResource Icon.palette}"
                                                      Style="{StaticResource IconPath}" Stroke="{DynamicResource Accent}" />
                                            </Border>
                                            <StackPanel Margin="11,0,0,0" VerticalAlignment="Center">
                                                <TextBlock Text="外观与日志" FontSize="13" FontWeight="SemiBold"
                                                           Foreground="{DynamicResource Text}" />
                                                <TextBlock Text="个性化你的工作空间" FontSize="9" Margin="0,4,0,0"
                                                           Foreground="{DynamicResource Muted}" />
                                            </StackPanel>
                                        </StackPanel>

                                        <TextBlock Text="界面主题" FontSize="9" FontWeight="SemiBold" Margin="0,18,0,8"
                                                   Foreground="{DynamicResource Muted}" />
                                        <Border Padding="12" CornerRadius="11" Background="{DynamicResource AccentSoft}">
                                            <Grid>
                                                <Grid.ColumnDefinitions>
                                                    <ColumnDefinition Width="Auto" />
                                                    <ColumnDefinition Width="*" />
                                                    <ColumnDefinition Width="Auto" />
                                                </Grid.ColumnDefinitions>
                                                <Border Width="30" Height="30" CornerRadius="9">
                                                    <Border.Background>
                                                        <LinearGradientBrush StartPoint="0,0" EndPoint="1,1">
                                                            <GradientStop Color="{DynamicResource Accent2.Color}" Offset="0" />
                                                            <GradientStop Color="{DynamicResource Accent.Color}" Offset="1" />
                                                        </LinearGradientBrush>
                                                    </Border.Background>
                                                </Border>
                                                <StackPanel Grid.Column="1" Margin="10,0,0,0" VerticalAlignment="Center">
                                                    <TextBlock x:Name="SettingsThemeName" Text="毛玻璃" FontSize="10"
                                                               FontWeight="SemiBold" Foreground="{DynamicResource Text}" />
                                                    <TextBlock x:Name="SettingsModeName" Text="日间模式" FontSize="8"
                                                               Margin="0,3,0,0" Foreground="{DynamicResource Muted}" />
                                                </StackPanel>
                                                <Button Grid.Column="2" Cursor="Hand" Background="Transparent"
                                                        BorderThickness="0" VerticalAlignment="Center"
                                                        Click="OnSettingsChangeTheme">
                                                    <TextBlock Text="更换主题" FontSize="9"
                                                               Foreground="{DynamicResource Accent}" />
                                                </Button>
                                            </Grid>
                                        </Border>

                                        <TextBlock Text="日志面板保留行数" FontSize="9" FontWeight="SemiBold"
                                                   Margin="0,18,0,8" Foreground="{DynamicResource Muted}" />
                                        <Border BorderBrush="{DynamicResource InnerBorder}" BorderThickness="1"
                                                CornerRadius="10" Background="{DynamicResource Card}" Height="38">
                                            <Grid>
                                                <TextBox x:Name="LogLinesBox" Text="800" FontSize="11"
                                                         VerticalContentAlignment="Center" Margin="12,0,40,0"
                                                         Background="Transparent" BorderThickness="0"
                                                         Foreground="{DynamicResource Text}" />
                                                <TextBlock Text="行" FontSize="9" HorizontalAlignment="Right"
                                                           VerticalAlignment="Center" Margin="0,0,12,0"
                                                           Foreground="{DynamicResource Muted}" />
                                            </Grid>
                                        </Border>
                                        <TextBlock Text="建议保留 500–1500 行，过多可能影响性能。" FontSize="8"
                                                   Margin="0,7,0,0" Foreground="{DynamicResource Subtle}" />

                                        <Border Margin="0,19,0,0" Padding="11" CornerRadius="10"
                                                Background="{DynamicResource AccentSoft}">
                                            <StackPanel Orientation="Horizontal">
                                                <Path Width="14" Height="14" Data="{StaticResource Icon.info}"
                                                      Style="{StaticResource IconPath}" Stroke="{DynamicResource Accent}"
                                                      VerticalAlignment="Top" />
                                                <TextBlock Text="主题切换会立即预览，无需重启管理器。" FontSize="8.5"
                                                           Margin="8,0,0,0" TextWrapping="Wrap"
                                                           Foreground="{DynamicResource Muted}" />
                                            </StackPanel>
                                        </Border>
                                    </StackPanel>
                                </Border>
                            </Grid>
                        </StackPanel>
                    </ScrollViewer>
'''


def main():
    src = io.open(P, encoding='utf-8').read()

    # 1) 在仪表盘 ScrollViewer 之后插入设置页
    marker = '                    <!-- 内容区 -->'
    if marker not in src:
        print('MISS content marker')
        return 1
    # 找到仪表盘 ScrollViewer 的结束（它后面紧跟 </Grid> 结束主面板）
    dash_start = src.index('                    <ScrollViewer x:Name="ContentScroll"')
    dash_end = src.index('                    </ScrollViewer>', dash_start) + len('                    </ScrollViewer>\n')
    src = src[:dash_end] + SETTINGS_PAGE + src[dash_end:]

    # 2) 侧栏「实例概览」按钮命名 + 加点击
    old_nav = '''                            <Button Style="{StaticResource SideLink}" Foreground="{DynamicResource Accent}"
                                    Background="{DynamicResource Hover}">'''
    new_nav = '''                            <Button x:Name="OverviewNav" Style="{StaticResource SideLink}"
                                    Foreground="{DynamicResource Accent}" Background="{DynamicResource Hover}"
                                    Click="OnShowOverview">'''
    if old_nav not in src:
        print('MISS overview nav')
        return 1
    src = src.replace(old_nav, new_nav, 1)

    old_settings_nav = '<Button Style="{StaticResource SideLink}" x:Name="SettingsNav">'
    new_settings_nav = '<Button Style="{StaticResource SideLink}" x:Name="SettingsNav" Click="OnShowSettings">'
    if old_settings_nav not in src:
        print('MISS settings nav')
        return 1
    src = src.replace(old_settings_nav, new_settings_nav, 1)

    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('settings page added')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
